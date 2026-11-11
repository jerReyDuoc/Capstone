#!/usr/bin/env bash
# HU-23 · Comprueba que una imagen Docker NO lleva secretos adentro.
#
#   .github/scripts/verificar_imagen.sh <imagen>
#
# Falla (código 1) si encuentra:
#   1. un archivo .env (o .env.*, salvo .env.example) en cualquier parte de la imagen;
#   2. una variable de entorno de la imagen con nombre de secreto y con valor
#      (PASSWORD, SECRET, KEY, TOKEN...). Los secretos se inyectan al ejecutar el
#      contenedor (secretos de Container Apps o el .env de docker compose), nunca al construir;
#   3. un ARG/ENV con nombre de secreto en el historial de capas (docker history).
# Lo usa el workflow ci.yml en cada pull request y se puede correr en local.
set -euo pipefail

IMAGEN="${1:?uso: verificar_imagen.sh <imagen>}"
PATRON='(PASSWORD|PASSWD|SECRET|_KEY|TOKEN|CREDENTIAL|CONNECTION_STRING|DATABASE_URL)'
# Variables públicas de las imágenes base que calzan con el patrón pero no son secretos
# (python:*-slim publica la huella de la clave GPG con que se firma CPython)
PERMITIDAS='^(GPG_KEY)='
fallas=0

echo "== Revisando la imagen ${IMAGEN}"

# 1. Archivos .env dentro de la imagen (sin mirar las librerías de terceros, que no son
#    nuestras y a veces traen .env de ejemplo en sus pruebas)
encontrados="$(docker run --rm --entrypoint sh "${IMAGEN}" -c \
  'find / -xdev \( -path /proc -o -path /sys -o -path "*/site-packages" -o -path "*/node_modules" \) -prune \
     -o \( -name ".env" -o -name ".env.*" \) ! -name ".env.example" -type f -print 2>/dev/null || true')"
if [ -n "${encontrados}" ]; then
  echo "::error::La imagen ${IMAGEN} contiene archivos .env:"
  echo "${encontrados}"
  fallas=1
else
  echo "OK  sin archivos .env"
fi

# 2. Variables de entorno horneadas en la imagen
variables="$(docker image inspect "${IMAGEN}" --format '{{range .Config.Env}}{{println .}}{{end}}')"
sospechosas="$(printf '%s\n' "${variables}" | grep -E "^[A-Z0-9_]*${PATRON}[A-Z0-9_]*=.+" | grep -vE "${PERMITIDAS}" || true)"
if [ -n "${sospechosas}" ]; then
  echo "::error::La imagen ${IMAGEN} trae variables con nombre de secreto y valor (solo se muestran los nombres):"
  printf '%s\n' "${sospechosas}" | cut -d= -f1
  fallas=1
else
  echo "OK  sin variables de entorno con secretos"
fi

# 3. Historial de capas (ARG/ENV usados al construir)
historial="$(docker history --no-trunc --format '{{.CreatedBy}}' "${IMAGEN}")"
en_historial="$(printf '%s\n' "${historial}" | grep -oE "\b[A-Z0-9_]*${PATRON}[A-Z0-9_]*=[^ ]+" | grep -vE "${PERMITIDAS}" || true)"
if [ -n "${en_historial}" ]; then
  echo "::error::El historial de ${IMAGEN} muestra valores de secretos (solo se muestran los nombres):"
  printf '%s\n' "${en_historial}" | cut -d= -f1 | sort -u
  fallas=1
else
  echo "OK  sin secretos en el historial de capas"
fi

exit "${fallas}"

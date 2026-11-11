#!/usr/bin/env bash
# HU-23 · Despliega una versión (etiqueta de imagen) en el ambiente de staging de Azure.
#
# Lo ejecuta el workflow deploy-staging.yml, y también se puede correr a mano desde un
# PC con Azure CLI (`az login`), con el mismo resultado. Es repetible: correrlo dos veces
# con la misma etiqueta deja todo igual.
#
#   .github/scripts/desplegar_staging.sh <etiqueta>
#
# Requisitos: las imágenes <ACR>.azurecr.io/api:<etiqueta> y web:<etiqueta> ya publicadas
# (el workflow las construye antes; a mano: ver Proyecto/docs/DESPLIEGUE_STAGING.md).
#
# Pasos (si uno falla, los siguientes no corren):
#   1. Guarda las imágenes que están corriendo ahora (para volver atrás).
#   2. Migraciones: actualiza el job "migrate" a la etiqueta nueva, lo ejecuta y espera
#      "Succeeded". Si falla, NO se toca ninguna app.
#   3. Datos semilla (opcional): igual con el job "seed".
#   4. Actualiza api y worker (misma imagen) y espera a que la revisión nueva esté sana.
#   5. Actualiza web y espera.
#   6. Prueba de humo por HTTPS contra la URL pública: /health (web -> api) y la portada.
#   Si 4, 5 o 6 fallan, vuelve solo las tres apps a las imágenes del paso 1.
#
# Variables (con sus valores por defecto):
#   RG=rg-complainceia  ACR=acrcomplainceia
#   APP_API=api  APP_WORKER=worker  APP_WEB=web  JOB_MIGRATE=migrate  JOB_SEED=seed
#   MIGRAR=true          false = no ejecuta migraciones (solo si sabes que no hay cambios de esquema)
#   SEMBRAR=false        true  = ejecuta el job de datos semilla después de migrar
#   ESPERA_MAX_S=900     tiempo máximo para cada job y cada revisión
#   VERIFICAR_IMAGENES=true  false = no comprueba que las imágenes existan (el workflow
#                        las acaba de publicar)
set -euo pipefail

TAG="${1:?uso: desplegar_staging.sh <etiqueta-de-imagen>}"
RG="${RG:-rg-complainceia}"
ACR="${ACR:-acrcomplainceia}"
APP_API="${APP_API:-api}"
APP_WORKER="${APP_WORKER:-worker}"
APP_WEB="${APP_WEB:-web}"
JOB_MIGRATE="${JOB_MIGRATE:-migrate}"
JOB_SEED="${JOB_SEED:-seed}"
MIGRAR="${MIGRAR:-true}"
SEMBRAR="${SEMBRAR:-false}"
ESPERA_MAX_S="${ESPERA_MAX_S:-900}"
PAUSA_S="${PAUSA_S:-15}"   # espera entre reintentos de la prueba de humo

SERVIDOR="${ACR}.azurecr.io"
IMG_API="${SERVIDOR}/api:${TAG}"
IMG_WEB="${SERVIDOR}/web:${TAG}"

RESUMEN="${GITHUB_STEP_SUMMARY:-/dev/null}"
URL_ARCHIVO="$(mktemp)"
APPS_TOCADAS=0
declare -A ANTERIOR=()

log()   { echo "[$(date -u +%H:%M:%S)] $*"; }
error() { echo "::error::$*" >&2; }

imagen_actual() {
  az containerapp show -n "$1" -g "$RG" --query "properties.template.containers[0].image" -o tsv
}

# ¿Está publicada la imagen? Primero con Docker (usa el mismo login con que se publicó:
# usuario del ACR o `az acr login`); si no hay Docker, con `az acr` (requiere que la
# identidad tenga permiso de lectura sobre el registro).
existe_imagen() {
  local imagen="$1" repo_tag="${1#*/}"
  if command -v docker >/dev/null 2>&1 && docker manifest inspect "$imagen" >/dev/null 2>&1; then
    return 0
  fi
  az acr repository show -n "$ACR" --image "$repo_tag" -o none >/dev/null 2>&1
}

existe_job() {
  az containerapp job show -n "$1" -g "$RG" --query name -o tsv >/dev/null 2>&1
}

# ------------------------------------------------------------------ vuelta atrás
volver_atras() {
  local codigo=$?
  trap - ERR EXIT
  if [ "$codigo" -ne 0 ] && [ "$APPS_TOCADAS" -eq 1 ]; then
    error "El despliegue falló: se vuelven api, worker y web a la versión anterior."
    for app in "$APP_API" "$APP_WORKER" "$APP_WEB"; do
      if [ -n "${ANTERIOR[$app]:-}" ]; then
        log "Volviendo $app a ${ANTERIOR[$app]}"
        az containerapp update -n "$app" -g "$RG" --image "${ANTERIOR[$app]}" -o none \
          || error "No se pudo volver $app: hazlo a mano (ver la guía, sección 6)."
      fi
    done
    echo "### ❌ Despliegue fallido: se restauró la versión anterior" >> "$RESUMEN"
    echo "Las migraciones de base de datos NO se revierten (ver la guía, sección 6)." >> "$RESUMEN"
  fi
  exit "$codigo"
}
trap volver_atras EXIT

# ------------------------------------------------------------------ jobs
ejecutar_job() {
  local job="$1" inicio estado ejecucion
  log "Job $job -> $IMG_API"
  az containerapp job update -n "$job" -g "$RG" --image "$IMG_API" -o none
  ejecucion="$(az containerapp job start -n "$job" -g "$RG" --query name -o tsv)"
  log "Ejecución $ejecucion iniciada; esperando el resultado..."
  inicio=$SECONDS
  while :; do
    estado="$(az containerapp job execution show -n "$job" -g "$RG" \
      --job-execution-name "$ejecucion" --query properties.status -o tsv 2>/dev/null || echo Desconocido)"
    case "$estado" in
      Succeeded) log "Job $job terminó bien."; return 0 ;;
      Failed|Stopped|Degraded)
        error "El job $job terminó en estado $estado. Revisa sus registros en Log Analytics: ContainerJobName_s == '$job'"
        return 1 ;;
    esac
    if [ $((SECONDS - inicio)) -ge "$ESPERA_MAX_S" ]; then
      error "El job $job no terminó en ${ESPERA_MAX_S}s (último estado: $estado)."
      return 1
    fi
    sleep 10
  done
}

# ------------------------------------------------------------------ apps
esperar_revision() {
  local app="$1" revision salud estado inicio
  revision="$(az containerapp show -n "$app" -g "$RG" --query properties.latestRevisionName -o tsv)"
  log "Esperando la revisión $revision de $app..."
  inicio=$SECONDS
  while :; do
    read -r estado salud <<<"$(az containerapp revision show -n "$app" -g "$RG" --revision "$revision" \
      --query "[properties.runningState, properties.healthState]" -o tsv 2>/dev/null | tr '\n\t' '  ')"
    case "$estado" in
      Running|RunningAtMaxScale)
        if [ "$salud" != "Unhealthy" ]; then log "$app sana ($revision, $estado, salud: ${salud:-None})."; return 0; fi ;;
      Failed|Degraded)
        error "La revisión $revision de $app quedó en $estado. Revisa sus registros: ContainerAppName_s == '$app'"
        return 1 ;;
    esac
    if [ $((SECONDS - inicio)) -ge "$ESPERA_MAX_S" ]; then
      error "$app no quedó sana en ${ESPERA_MAX_S}s (estado: $estado, salud: $salud)."
      return 1
    fi
    sleep 10
  done
}

actualizar_app() {
  local app="$1" imagen="$2"
  log "Actualizando $app -> $imagen"
  APPS_TOCADAS=1
  az containerapp update -n "$app" -g "$RG" --image "$imagen" -o none
  esperar_revision "$app"
}

# ------------------------------------------------------------------ prueba de humo
prueba_humo() {
  local fqdn url intento cuerpo codigo cabeceras
  fqdn="$(az containerapp show -n "$APP_WEB" -g "$RG" --query properties.configuration.ingress.fqdn -o tsv)"
  url="https://${fqdn}"
  log "Prueba de humo contra $url"
  for intento in $(seq 1 12); do
    # curl verifica el certificado: si el HTTPS no es válido, la prueba falla
    if cuerpo="$(curl -fsS --max-time 20 "${url}/health")" && echo "$cuerpo" | grep -q '"ok"'; then
      codigo="$(curl -sS -o /dev/null --max-time 30 -w '%{http_code}' "${url}/")"
      if [ "$codigo" = "200" ]; then
        log "OK  /health responde '$cuerpo' (web -> api) y la portada responde 200."
        cabeceras="$(curl -sSI --max-time 20 "${url}/" | tr -d '\r')"
        echo "$cabeceras" | grep -qi '^strict-transport-security:' \
          && log "OK  cabecera HSTS presente." || log "Aviso: la portada no envía la cabecera HSTS."
        codigo="$(curl -sS -o /dev/null --max-time 20 -w '%{http_code}' "http://${fqdn}/" || true)"
        case "$codigo" in 301|302|307|308) log "OK  http:// redirige a https:// ($codigo)." ;;
          *) log "Aviso: http:// respondió $codigo (se esperaba una redirección a https)." ;; esac
        echo "$url" > "$URL_ARCHIVO"
        return 0
      fi
    fi
    log "Intento $intento/12 sin éxito; reintento en ${PAUSA_S} s..."
    sleep "$PAUSA_S"
  done
  error "La prueba de humo falló: $url/health o la portada no responden bien."
  return 1
}

# ================================================================== principal
log "Desplegando la etiqueta $TAG en el grupo $RG"
if [ "${VERIFICAR_IMAGENES:-true}" = "true" ]; then
  for img in "$IMG_API" "$IMG_WEB"; do
    existe_imagen "$img" || {
      error "No encuentro la imagen $img. Si la etiqueta es correcta, revisa el inicio de sesión en el registro (secretos API_REGISTRY_* o permiso AcrPull de la identidad)."
      exit 1
    }
    log "Imagen encontrada: $img"
  done
fi

for app in "$APP_API" "$APP_WORKER" "$APP_WEB"; do
  ANTERIOR[$app]="$(imagen_actual "$app")"
  log "Versión actual de $app: ${ANTERIOR[$app]}"
done

if [ "$MIGRAR" = "true" ]; then
  ejecutar_job "$JOB_MIGRATE"
else
  log "Migraciones omitidas (MIGRAR=$MIGRAR)."
fi

if [ "$SEMBRAR" = "true" ]; then
  if existe_job "$JOB_SEED"; then
    ejecutar_job "$JOB_SEED"
  else
    error "No existe el job $JOB_SEED. Créalo con Proyecto/infra/azure/preparar_staging.sh (ver la guía, sección 2)."
    exit 1
  fi
fi

actualizar_app "$APP_API" "$IMG_API"
actualizar_app "$APP_WORKER" "$IMG_API"
actualizar_app "$APP_WEB" "$IMG_WEB"
prueba_humo

{
  echo "### ✅ Staging actualizado a \`${TAG}\`"
  echo ""
  echo "| | |"
  echo "|---|---|"
  echo "| URL | $(cat "$URL_ARCHIVO") |"
  echo "| api y worker | \`${IMG_API}\` |"
  echo "| web | \`${IMG_WEB}\` |"
  echo "| Migraciones | ${MIGRAR} |"
  echo "| Datos semilla | ${SEMBRAR} |"
  echo "| Versión anterior de api | \`${ANTERIOR[$APP_API]}\` |"
} >> "$RESUMEN"
log "Listo: staging corre la etiqueta $TAG en $(cat "$URL_ARCHIVO")"

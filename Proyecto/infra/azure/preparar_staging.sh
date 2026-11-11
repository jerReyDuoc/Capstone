#!/usr/bin/env bash
# HU-23 · Preparación (una sola vez) del ambiente de staging en Azure Container Apps.
#
# Se ejecuta en Azure Cloud Shell (Bash) o en cualquier terminal con Azure CLI y jq,
# después de `az login`. Es idempotente: se puede correr de nuevo sin romper nada.
#
#   export SEMILLA_ADMIN_EMAIL=admin@therionlabs.cl
#   export SEMILLA_ADMIN_PASSWORD='una-clave-larga-y-unica'     # 12+ caracteres
#   bash Proyecto/infra/azure/preparar_staging.sh
#
# Qué hace:
#   1. Comprueba que existan el grupo de recursos, el registro, las apps y el job migrate.
#   2. Revisa los permisos de la identidad que usa GitHub Actions (OIDC) y, con
#      --asignar-roles, le da "Contributor" en el grupo y "AcrPush" en el registro.
#   3. Crea (o actualiza) el job "seed" de datos semilla. Copia del job "migrate" el
#      entorno, la identidad y el acceso al registro, y de la app "api" las variables y
#      secretos (usa el rol limitado de la base, no el dueño). El correo y la clave del
#      administrador se guardan como SECRETOS del job, nunca en el código ni en la imagen.
#   4. Deja el worker con exactamente 1 réplica (las tareas programadas no se duplican)
#      y la web sin tráfico HTTP sin cifrar (http:// redirige a https://).
#   5. Muestra los secretos y variables que hay que tener en GitHub.
#
# Opciones:
#   --asignar-roles   crea las asignaciones de rol que falten (requiere ser Owner)
#   --sin-seed        no crea ni modifica el job seed
#
# Variables (por defecto): RG=rg-complainceia ACR=acrcomplainceia APP_API=api
#   APP_WORKER=worker APP_WEB=web JOB_MIGRATE=migrate JOB_SEED=seed
#   AZURE_CLIENT_ID=<client id de la identidad OIDC; el mismo valor del secreto API_AZURE_CLIENT_ID>
set -euo pipefail

RG="${RG:-rg-complainceia}"
ACR="${ACR:-acrcomplainceia}"
APP_API="${APP_API:-api}"
APP_WORKER="${APP_WORKER:-worker}"
APP_WEB="${APP_WEB:-web}"
JOB_MIGRATE="${JOB_MIGRATE:-migrate}"
JOB_SEED="${JOB_SEED:-seed}"
ASIGNAR_ROLES=false
CON_SEED=true
for a in "$@"; do
  case "$a" in
    --asignar-roles) ASIGNAR_ROLES=true ;;
    --sin-seed) CON_SEED=false ;;
    *) echo "Opción desconocida: $a" >&2; exit 2 ;;
  esac
done

ok()    { echo "  OK   $*"; }
aviso() { echo "  !!   $*"; }
paso()  { echo; echo "== $*"; }

command -v az >/dev/null || { echo "Falta Azure CLI (az). Usa Azure Cloud Shell." >&2; exit 1; }
command -v jq >/dev/null || { echo "Falta jq. Usa Azure Cloud Shell, que ya lo trae." >&2; exit 1; }
az extension add --name containerapp --upgrade --only-show-errors >/dev/null

# ------------------------------------------------------------------ 1. recursos
paso "1. Recursos existentes"
SUB="$(az account show --query id -o tsv)"
ok "Suscripción $(az account show --query name -o tsv)"
az group show -n "$RG" -o none && ok "Grupo de recursos $RG"
ACR_ID="$(az acr show -n "$ACR" --query id -o tsv)" && ok "Registro $ACR"
for app in "$APP_API" "$APP_WORKER" "$APP_WEB"; do
  az containerapp show -n "$app" -g "$RG" -o none && ok "Container App $app"
done
az containerapp job show -n "$JOB_MIGRATE" -g "$RG" -o none && ok "Job $JOB_MIGRATE"
ENV_ID="$(az containerapp show -n "$APP_API" -g "$RG" --query properties.environmentId -o tsv)"
ok "Entorno ${ENV_ID##*/}"

# ------------------------------------------------------------------ 2. permisos OIDC
paso "2. Permisos de la identidad de GitHub Actions"
if [ -z "${AZURE_CLIENT_ID:-}" ]; then
  aviso "Define AZURE_CLIENT_ID (el valor del secreto API_AZURE_CLIENT_ID) para revisar los permisos."
else
  PRINCIPAL="$(az ad sp show --id "$AZURE_CLIENT_ID" --query id -o tsv 2>/dev/null \
    || az identity list --query "[?clientId=='$AZURE_CLIENT_ID'].principalId | [0]" -o tsv)"
  if [ -z "$PRINCIPAL" ]; then
    aviso "No encontré la identidad con client id $AZURE_CLIENT_ID."
  else
    RG_ID="/subscriptions/$SUB/resourceGroups/$RG"
    revisar_rol() {  # rol alcance descripción
      local n
      n="$(az role assignment list --assignee "$PRINCIPAL" --scope "$2" --include-inherited \
        --query "[?roleDefinitionName=='$1' || roleDefinitionName=='Owner'] | length(@)" -o tsv)"
      if [ "${n:-0}" -gt 0 ]; then ok "$1 en $3"
      elif [ "$ASIGNAR_ROLES" = true ]; then
        az role assignment create --assignee-object-id "$PRINCIPAL" --assignee-principal-type ServicePrincipal \
          --role "$1" --scope "$2" -o none && ok "$1 en $3 (asignado ahora)"
      else aviso "Falta $1 en $3. Vuelve a correr con --asignar-roles."
      fi
    }
    revisar_rol "Contributor" "$RG_ID" "el grupo $RG (actualizar apps y ejecutar jobs)"
    # Contributor en el grupo ya permite publicar imágenes en un ACR del mismo grupo; AcrPush
    # se revisa por si el registro restringe el acceso por permisos de datos.
    revisar_rol "AcrPush" "$ACR_ID" "el registro $ACR (publicar imágenes)"
  fi
fi

# ------------------------------------------------------------------ 3. job seed
if [ "$CON_SEED" = true ]; then
  paso "3. Job de datos semilla ($JOB_SEED)"
  : "${SEMILLA_ADMIN_EMAIL:?Define SEMILLA_ADMIN_EMAIL (correo del administrador del piloto)}"
  : "${SEMILLA_ADMIN_PASSWORD:?Define SEMILLA_ADMIN_PASSWORD (12+ caracteres)}"
  if [ "${#SEMILLA_ADMIN_PASSWORD}" -lt 12 ]; then
    echo "SEMILLA_ADMIN_PASSWORD debe tener al menos 12 caracteres." >&2; exit 1
  fi

  API_JSON="$(az containerapp show -n "$APP_API" -g "$RG" -o json)"
  MIG_JSON="$(az containerapp job show -n "$JOB_MIGRATE" -g "$RG" -o json)"
  IMAGEN="$(jq -r '.properties.template.containers[0].image' <<<"$API_JSON")"
  PERFIL="$(jq -r '.properties.workloadProfileName // "Consumption"' <<<"$MIG_JSON")"
  REGISTRO="$(jq -c '.properties.configuration.registries[0] // {}' <<<"$MIG_JSON")"
  REG_PASS_REF="$(jq -r '.passwordSecretRef // ""' <<<"$REGISTRO")"

  # Variables de la app api (mismas conexiones, rol limitado de la BD)
  mapfile -t VARS < <(jq -r '.properties.template.containers[0].env[]
    | if .secretRef then "\(.name)=secretref:\(.secretRef)" else "\(.name)=\(.value // "")" end' <<<"$API_JSON")
  VARS+=("SEMILLA_ADMIN_EMAIL=secretref:semilla-admin-email" "SEMILLA_ADMIN_PASSWORD=secretref:semilla-admin-password")

  # Secretos de la app api (con sus valores; no se imprimen) + los del administrador
  SECRETOS_JSON="$(az containerapp secret list -n "$APP_API" -g "$RG" --show-values -o json)"
  mapfile -t SECRETOS < <(jq -r --arg omitir "$REG_PASS_REF" \
    '.[] | select(.name != $omitir) | select(.value != null) | "\(.name)=\(.value)"' <<<"$SECRETOS_JSON")
  SECRETOS+=("semilla-admin-email=${SEMILLA_ADMIN_EMAIL}" "semilla-admin-password=${SEMILLA_ADMIN_PASSWORD}")

  if az containerapp job show -n "$JOB_SEED" -g "$RG" -o none 2>/dev/null; then
    az containerapp job secret set -n "$JOB_SEED" -g "$RG" --secrets "${SECRETOS[@]}" -o none
    az containerapp job update -n "$JOB_SEED" -g "$RG" --image "$IMAGEN" \
      --replace-env-vars "${VARS[@]}" -o none
    ok "Job $JOB_SEED actualizado (imagen $IMAGEN)"
  else
    # Acceso al registro: el mismo que usa el job migrate
    REG_ARGS=(--registry-server "$(jq -r '.server' <<<"$REGISTRO")")
    IDENTIDAD="$(jq -r '.identity // ""' <<<"$REGISTRO")"
    if [ -n "$IDENTIDAD" ] && [ "$IDENTIDAD" != "system" ]; then
      REG_ARGS+=(--registry-identity "$IDENTIDAD" --mi-user-assigned "$IDENTIDAD")
    elif [ "$IDENTIDAD" = "system" ]; then
      REG_ARGS+=(--registry-identity system --mi-system-assigned)
    else
      REG_ARGS+=(--registry-username "$(jq -r '.username' <<<"$REGISTRO")"
                 --registry-password "$(jq -r --arg r "$REG_PASS_REF" '.[] | select(.name == $r) | .value' \
                   <<<"$(az containerapp job secret list -n "$JOB_MIGRATE" -g "$RG" --show-values -o json)")")
    fi
    az containerapp job create -n "$JOB_SEED" -g "$RG" --environment "$ENV_ID" \
      --workload-profile-name "$PERFIL" \
      --trigger-type Manual --replica-timeout 1800 --replica-retry-limit 0 --parallelism 1 \
      --replica-completion-count 1 \
      --image "$IMAGEN" --cpu 1 --memory 2Gi \
      --command "python" --args "scripts/sembrar_staging.py" \
      "${REG_ARGS[@]}" \
      --secrets "${SECRETOS[@]}" \
      --env-vars "${VARS[@]}" -o none
    ok "Job $JOB_SEED creado (imagen $IMAGEN, perfil $PERFIL)"
  fi
  unset SECRETOS SECRETOS_JSON
fi

# ------------------------------------------------------------------ 4. escala y HTTPS
paso "4. Escala del worker y HTTPS de la web"
az containerapp update -n "$APP_WORKER" -g "$RG" --min-replicas 1 --max-replicas 1 -o none
ok "worker con 1 réplica (mínimo y máximo)"
az containerapp ingress update -n "$APP_WEB" -g "$RG" --allow-insecure false -o none
FQDN="$(az containerapp show -n "$APP_WEB" -g "$RG" --query properties.configuration.ingress.fqdn -o tsv)"
ok "web solo por HTTPS: https://$FQDN"
PROXY="$(az containerapp show -n "$APP_WEB" -g "$RG" \
  --query "properties.template.containers[0].env[?name=='TRUSTED_PROXY_HOPS'].value | [0]" -o tsv)"
[ "$PROXY" = "1" ] && ok "TRUSTED_PROXY_HOPS=1 en web" \
  || aviso "TRUSTED_PROXY_HOPS de web es '${PROXY:-vacío}': debe ser 1 (hay un proxy de Azure delante)."

# ------------------------------------------------------------------ 5. GitHub
paso "5. Configuración que debe tener GitHub (Settings > Secrets and variables > Actions)"
cat <<EOF
  Secretos (ya existen desde la configuración del portal):
    API_AZURE_CLIENT_ID, API_AZURE_TENANT_ID, API_AZURE_SUBSCRIPTION_ID
    API_REGISTRY_USERNAME, API_REGISTRY_PASSWORD   (opcionales)
  Variables (opcionales; estos son los valores por defecto):
    AZ_RESOURCE_GROUP=$RG
    AZ_ACR_NAME=$ACR
    MIGRACIONES_AUTOMATICAS=true
    SEMBRAR_AL_DESPLEGAR=false
  Los secretos WEB_AZURE_* y WEB_REGISTRY_* ya no se usan y se pueden borrar.

Listo. Siguiente paso: Actions > Deploy staging > Run workflow (marca "Cargar los datos semilla").
EOF

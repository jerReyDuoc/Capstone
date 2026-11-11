# Entrega HU-23 · Pipeline de CI/CD y ambiente de staging

Las rutas de este zip son relativas a la raíz del repositorio `Capstone/`. Copia el contenido sobre el repositorio respetando las carpetas.

## Archivos nuevos o modificados

| Archivo | |
|---|---|
| `.github/workflows/ci.yml` | nuevo |
| `.github/workflows/deploy-staging.yml` | nuevo |
| `.github/scripts/desplegar_staging.sh` | nuevo |
| `.github/scripts/verificar_imagen.sh` | nuevo |
| `Proyecto/infra/azure/preparar_staging.sh` | nuevo |
| `Proyecto/backend/scripts/sembrar_staging.py` | nuevo |
| `Proyecto/backend/tests/test_hu23_semilla_staging.py` | nuevo |
| `Proyecto/docs/DESPLIEGUE_STAGING.md` | nuevo |
| `Extras/Cambios/backend/CAMBIOS_HU23.md` | nuevo |
| `Proyecto/README.md` | modificado |

## Archivos que hay que BORRAR del repositorio

Los reemplazan `ci.yml` y `deploy-staging.yml`. Si se dejan, se despliega dos veces y sin esperar a las pruebas.

```
.github/workflows/ci-backend.yml
.github/workflows/api-AutoDeployTrigger-c5796439-6bbf-418e-a801-b887fd433cb3.yml
.github/workflows/web-AutoDeployTrigger-97cdcf98-b9ca-44c9-9158-18cbd3100429.yml
```

## Orden recomendado

1. Copiar los archivos y borrar los tres workflows anteriores en una rama nueva (`git switch -c hu-23-pipeline`), hacer commit y subir la rama.
2. **Antes del merge**, en Azure Cloud Shell: `git clone -b hu-23-pipeline https://github.com/jerReyDuoc/Capstone.git` y ejecutar `Proyecto/infra/azure/preparar_staging.sh` (guía, sección 2). Así los permisos y el job `seed` están listos para el primer despliegue automático.
3. Abrir el pull request a `main`. El workflow **CI** corre solo; revisar que **CI aprobado** quede en verde.
4. Hacer el merge. CI corre en `main` y, en verde, **Deploy staging** despliega automáticamente.
5. Proteger `main` con el check **CI aprobado** (guía, sección 3).
6. *Actions > Deploy staging > Run workflow* con **Cargar los datos semilla** marcado.

El detalle completo está en `Proyecto/docs/DESPLIEGUE_STAGING.md`.

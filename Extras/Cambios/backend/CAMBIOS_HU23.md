# HU-23 · Pipeline de CI/CD y ambiente de staging

> Como Equipo de desarrollo / Product Owner, quiero que cada cambio ejecute las pruebas automáticamente y se despliegue en un ambiente de staging accesible, para detectar errores antes de integrar y poder pilotear con usuarios reales (HU-14).

**Decisión del PO (11-nov-2026):** el ambiente actual de Azure Container Apps (North Central US, `APP_ENV=production`) **es** el staging del piloto (opción A, sin costo adicional). No se crea un ambiente aparte.

## Estado anterior

| Pieza | Problema |
|---|---|
| `ci-backend.yml` (T-08) | Solo backend. No construía imágenes. Su filtro de rutas no permitía marcarlo como check obligatorio |
| `api-AutoDeployTrigger-*.yml` y `web-AutoDeployTrigger-*.yml` (creados por el portal de Azure) | Desplegaban en **cada push a `main` aunque las pruebas fallaran**, con `paths: '**'` (la API se redesplegaba por un cambio del frontend) y con `actions/checkout@v2` |
| `worker` y job `migrate` | Se actualizaban a mano desde el portal después de cada despliegue |
| Datos semilla | Solo catálogos (migraciones). El administrador se creaba por consola con `crear_admin` (pide la clave por teclado) y no había evaluaciones para la comparativa |
| Frontend | Sin CI (ni TypeScript ni vitest) |
| Documentación | El despliegue no estaba en el repositorio. El README marcaba "Pipeline CI/CD y staging: 🔴 Pendiente" |

## Qué se agregó o cambió

| Archivo | Tipo | Para qué |
|---|---|---|
| `.github/workflows/ci.yml` | nuevo (reemplaza `ci-backend.yml`) | En cada PR, push a `main` y a mano: pytest + cobertura ≥ 70 % + SonarQube opcional (igual que T-08); TypeScript + vitest; construcción de las imágenes `api` y `web` sin publicarlas, con revisión de secretos y prueba de arranque; check único **CI aprobado** |
| `.github/workflows/deploy-staging.yml` | nuevo (reemplaza los dos `*-AutoDeployTrigger-*.yml`) | Corre solo si CI pasó en un push a `main`. Construye y publica `api:<sha>` y `web:<sha>`, y llama al script de despliegue. Manual: elegir una etiqueta (volver atrás), migrar sí/no y cargar los datos semilla |
| `.github/scripts/desplegar_staging.sh` | nuevo | Despliegue repetible: job `migrate` → (opcional) job `seed` → `api`, `worker` y `web` con espera de revisión sana → prueba de humo HTTPS (`/health` web→api, portada, HSTS, redirección http→https) → **vuelta atrás automática** si algo falla. Se puede correr igual desde Cloud Shell |
| `.github/scripts/verificar_imagen.sh` | nuevo | Falla si la imagen tiene archivos `.env`, variables con nombre de secreto y valor, o secretos en el historial de capas |
| `Proyecto/infra/azure/preparar_staging.sh` | nuevo | Preparación de una sola vez (Cloud Shell): revisa recursos y permisos de la identidad OIDC (Contributor y AcrPush, `--asignar-roles`), crea el job `seed`, deja el `worker` con 1 réplica, fuerza HTTPS en `web` y revisa `TRUSTED_PROXY_HOPS=1` |
| `Proyecto/backend/scripts/sembrar_staging.py` | nuevo | Datos semilla idempotentes: administrador desde secretos (sin teclado) y 20 evaluaciones completadas sintéticas (2 rubros × 10, IDs desde 990001) para que la comparativa sectorial supere k = 5; recalcula el benchmark; `--eliminar` las borra antes de medir el piloto |
| `Proyecto/backend/tests/test_hu23_semilla_staging.py` | nuevo | 5 pruebas: crea admin, evaluaciones, resúmenes y benchmark con k = 5; idempotencia sin pisar la clave; `--actualizar-clave`; `--eliminar` solo borra lo sembrado; clave corta y BD sin catálogos con mensaje claro |
| `Proyecto/docs/DESPLIEGUE_STAGING.md` | nuevo | Guía completa: flujo, preparación, protección de `main`, flujo de trabajo, despliegue manual, vuelta atrás, mapa de secretos, verificación QA, costos y solución de problemas |
| `Proyecto/README.md` | modificado | Estado, sección de CI/CD, estructura y backlog |

No se modificó código de la aplicación (backend ni frontend). La interfaz no cambia.

## Decisiones

1. **Migraciones automáticas al desplegar.** Antes eran manuales "para no aplicar cambios de esquema sin supervisión". Ahora la supervisión es el pull request revisado, con pruebas en verde, y la migración corre **antes** de actualizar la API. Si falla, ninguna app se toca. Se apagan con la variable `MIGRACIONES_AUTOMATICAS=false`.
2. **Un solo despliegue para las tres apps, con la misma etiqueta.** `api`, `worker` y `web` corren siempre el mismo commit, y el `worker` ya no queda atrasado.
3. **OIDC sin *environments* de GitHub.** La credencial federada del portal confía en `ref:refs/heads/main`. Usar `environment:` cambiaría el sujeto y rompería el inicio de sesión.
4. **Se reutiliza la identidad `API_AZURE_*`** para todo. Los secretos `WEB_AZURE_*` / `WEB_REGISTRY_*` quedan sin uso.
5. **Semilla con el rol limitado** (`complianceia_app`, mismas variables que `api`) y no con el dueño de la base.
6. **Las evaluaciones de ejemplo cuentan en el benchmark** (`es_prueba=false`), porque ese es su propósito. Por eso existe `--eliminar` antes de medir la HU-14.

## Cómo verificarlo

Ver `Proyecto/docs/DESPLIEGUE_STAGING.md`, sección 8 (tabla criterio → prueba → evidencia).

```bash
# Local: pruebas de la semilla
docker compose run --rm --no-deps api pytest tests/test_hu23_semilla_staging.py -v
# Local: imagen sin secretos
docker compose build api && bash .github/scripts/verificar_imagen.sh complianceai-backend:latest
```

## Pendiente / riesgos

- **Proteger `main`** (sección 3 de la guía): lo tiene que activar un administrador del repositorio. Sin esto el pipeline avisa, pero no bloquea.
- **Primer run del CI del frontend:** `npm run typecheck` nunca había corrido en CI. Si el código tiene errores de tipos, el primer PR quedará en rojo y habrá que corregirlos.
- **Reversa de migraciones:** no es automática. Las migraciones deben ser compatibles con la versión anterior del código; si no, restauración a un punto en el tiempo de PostgreSQL.
- **Costo:** 35–55 USD/mes estimados frente a 100 USD de crédito. Configurar un presupuesto con alertas.
- La documentación PDF de Azure (sección 8, "Integración y despliegue continuo") queda desactualizada: el `worker` y `migrate` ya no se actualizan a mano.

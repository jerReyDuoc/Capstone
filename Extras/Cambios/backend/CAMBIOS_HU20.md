# HU-20 · Confidencialidad del diagnóstico (backend)

*Como encuestado (organización evaluada) quiero que solo yo y los administradores de Therion Labs podamos ver mis respuestas, evidencias y reportes, para proteger la confidencialidad de mi diagnóstico frente a otros encuestados.*

HU-19 ya había dejado el alcance por evaluación (`app/core/alcance.py`) para la encuesta pública, pero con las evaluaciones por invitación abiertas sin token detrás del interruptor `EXIGIR_TOKEN_EVALUACIONES=false`, y con las métricas de IA, la bandeja de seguridad y la revisión humana sin ninguna protección. HU-20 cierra esas tres brechas. No hay migración ni endpoints nuevos.

## Quién puede qué

| Rutas | Sin token | Encuestado / referente dueño | Otro encuestado / referente | Admin |
|---|---|---|---|---|
| Evaluación, filtro, progreso, cerrar, completar, resumen, comparativa, plan formativo, informe PDF y envío, respuestas, evidencias | 401 | ✅ | **404** | ✅ |
| `GET /api/evaluaciones` (listado) | 401 | solo las suyas | — | todas |
| `GET /api/evaluaciones/benchmark` (agregado) | 401 | ✅ | ✅ | ✅ |
| `GET /api/ia/metricas`, `GET /api/seguridad/eventos`, `PATCH /api/seguridad/eventos/{id}/revisado`, `PATCH /api/respuestas/{id}/revision`, `PATCH /api/evaluaciones/{id}/prueba`, `POST /api/auth/encuestado/clave` | 401 | **403** | 403 | ✅ |
| Catálogos (`/dominios`, `/rubros`, `/rutas-formativas`, `/brechas`), `/controles`, landing (`/encuesta-publica/aviso-legal`, `/iniciar`), `/health`, ARCOP catálogo y seguimiento | ✅ | ✅ | ✅ | ✅ |

El "dueño" es el encuestado de la encuesta pública (`sub` = id de la evaluación, token de HU-19) o el referente de una evaluación por invitación (`sub` = usuario temporal). Lo ajeno responde 404 con el mismo cuerpo que un id inexistente, y sin token se responde 401 aunque el id no exista, para que los ids correlativos no se puedan enumerar. Un token mal firmado o vencido es 401 `TOKEN_INVALIDO`.

## Cambios

| Archivo | Qué cambia |
|---|---|
| `app/core/config.py` | `EXIGIR_TOKEN_EVALUACIONES` pasa a `true` por defecto. `false` queda solo para desarrollo y el validador lo prohíbe con `APP_ENV=production`. |
| `app/core/alcance.py` | Nuevas dependencias `actor_de_evaluaciones` (listado y benchmark: 401 sin token) y `solo_admin`. Una respuesta o evidencia inexistente sin token ahora es 401 (antes llegaba al 404 de la ruta). Docstring con la matriz actualizada. |
| `app/api/routes/evaluaciones.py` | El listado usa `actor_de_evaluaciones`; `/prueba` usa `solo_admin`. |
| `app/api/routes/reportes.py` | `GET /benchmark` exige token (cualquier rol). |
| `app/api/routes/respuestas.py` | `PATCH /{id}/revision` es solo admin (antes: cualquiera menos el encuestado, incluso sin token). |
| `app/api/routes/metricas_ia.py`, `app/api/routes/seguridad.py` | Todo el router exige admin. |
| `.env.example`, `Proyecto/README.md` | Documentación del interruptor y columna Auth de la tabla de endpoints. |

## Pruebas (criterio 3)

`tests/test_hu20_autorizacion.py` (en proceso, SQLite; 75 casos). Cada caso arma una BD nueva con dos evaluaciones públicas (A y B, cada una con su encuestado) y la evaluación por invitación 1 (referente 1), con respuesta y evidencia en A y en 1, y prueba con seis actores: sin token, encuestado de A, encuestado de B, referente 1, referente 2 y admin.

- **Rutas con alcance**: las 18 rutas de evaluaciones/respuestas/evidencias/reportes, contra la evaluación pública y contra la de invitación: 401 sin token, 404 `EVALUACION_NO_ENCONTRADA` para cada ajeno, y el dueño y el admin pasan el control.
- **Solo admin**: las 6 rutas, 401 sin token y 403 `NO_AUTORIZADO` para encuestados y referentes, incluido el dueño de los datos.
- **Públicas**: las 11 rutas responden sin token, y los catálogos devuelven lo mismo con y sin token.
- **Listado y benchmark** por actor, ids inexistentes sin token (401), tokens vencidos o con otra firma (401), y el 404 de lo ajeno idéntico al de lo inexistente.
- **Cobertura de la matriz**: `test_todas_las_rutas_estan_clasificadas` recorre `app.routes` y falla si aparece un endpoint que no está en ninguna matriz (o si la matriz nombra uno que ya no existe). Así ninguna HU futura puede agregar una ruta sin decidir quién la usa.
- **Interruptor**: con `false` solo se abren las evaluaciones por invitación (lo público y lo de admin siguen cerrados), y en production no se puede apagar.

### Ajustes a las pruebas existentes

Las pruebas que llamaban sin token a evaluaciones por invitación ahora se autentican:

- `tests/_api_harness.py`: `cliente_api()` envía por defecto un token de admin (`rol="admin"`); `rol="referente"` usa el del usuario temporal 1 y `rol=None` no envía ninguno. Si el entorno no define `AUTH_SECRET`, usa uno de pruebas durante la prueba y deja el valor previo al salir.
- `test_hu19_encuesta_publica.py`, `test_solicitudes_arcop.py`, `test_t06_minimizacion.py`: usan `cliente_api(rol=None)` porque manejan sus propios tokens. En HU-19, `test_las_evaluaciones_por_invitacion_siguen_igual_sin_token` pasa a `..._exigen_token_de_su_referente` y el listado sin token ahora espera 401. En ARCOP, las dos pruebas de supresión preparan y verifican los datos como admin.
- `test_e2e_capa_ia.py` (admin) y `test_hu06_regresion_pii.py` (referente) agregan el token a su cliente.
- Modo live (`test_latencia_api.py`, `test_live_capa_ia.py`): definir `QA_TOKEN_ADMIN` con el token de un admin activo.

```bash
docker compose exec api pytest tests/test_hu20_autorizacion.py -v
docker compose exec worker pytest tests -v -rxX
```

Para el modo live:

```bash
docker compose exec api python -m app.core.autenticacion --usuario <id del admin> --rol admin_therion
# PowerShell: $env:QA_TOKEN_ADMIN="<token>"
```

## Impacto en el frontend (prototipo)

El flujo del encuestado (`/bff/api/*`) no cambia: el BFF ya enviaba su Bearer y la lista blanca de `lib/servidor/proxy.ts` no incluye ninguna ruta de admin.

El **modo interno del panel** (`lib/api.ts`, que llama a `/api/evaluaciones` sin token para ver las evaluaciones por invitación) ahora recibe 401. Hasta que el frontend nuevo tenga el login del admin, para revisar el panel con datos de prueba en local se puede poner `EXIGIR_TOKEN_EVALUACIONES=false` en el `.env` (solo `APP_ENV=development`; el backend no arranca con eso en production). Las evaluaciones de la encuesta pública siguen exigiendo su token igual.

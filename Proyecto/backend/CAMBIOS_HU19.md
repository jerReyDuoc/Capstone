# HU-19 · Encuesta pública desde la landing (backend)

*Como visitante de la landing quiero iniciar el autodiagnóstico sin invitación ni registro y poder retomarlo más tarde.*

El frontend correspondiente y el checklist de verificación están en `frontend-next/CAMBIOS_HU19.md`.

## Migración `e2b7c9d4f8a1` (revisa `d4a7c2e9b8f3`)

| Tabla | Columna | Para qué |
|---|---|---|
| `evaluacion` | `origen` (`invitacion` \| `publica`, CHECK, índice) | Lo fija solo el backend. Las existentes quedan `invitacion`. |
| `evaluacion` | `es_prueba` (bool, false) | Las marcadas por un admin no entran al benchmark. |
| `usuario_temporal` | `aviso_legal_version`, `fecha_aceptacion_aviso` | Qué versión del aviso legal (HU-04) aceptó y cuándo (UTC). |

> Si en tu repo local hay migraciones posteriores a `d4a7c2e9b8f3` que no están en `main`, cambia `down_revision` por tu head (`alembic heads`).

## Endpoints nuevos

| Método y ruta | Quién | Qué hace |
|---|---|---|
| `POST /api/encuesta-publica/iniciar` | BFF de Next | `{rubro_id, aviso_legal:{version, aceptado}, captcha_token}` → 201 `{evaluacion_id, clave_acceso, access_token, token_type, expira_en}`. Crea usuario temporal anónimo + evaluación `publica` + clave (solo hash) en una transacción. |
| `PATCH /api/encuesta-publica/email` | encuestado | `{email \| null}` → 204. Email opcional. |
| `GET /api/encuesta-publica/limites` | encuestado | Evidencias y validaciones con IA restantes hoy, y hora de reinicio. |
| `GET /api/encuesta-publica/aviso-legal` | público | Versión vigente del aviso. |
| `PATCH /api/evaluaciones/{id}/prueba` | admin | `{es_prueba}`: excluir/incluir del benchmark. |

Retomar usa el endpoint que ya existía, `POST /api/auth/encuestado {evaluacion_id, clave}`, que ahora además limita intentos (20 por IP cada 10 min y 10 por evaluación cada 15 min → 429 `DEMASIADOS_INTENTOS`).

Errores nuevos (formato `{detail: {codigo, mensaje, ...}}`): `AVISO_NO_ACEPTADO` 422, `AVISO_DESACTUALIZADO` 409 (con `version_vigente`), `RUBRO_INVALIDO` 422, `CAPTCHA_INVALIDO` 403, `ORIGEN_NO_PERMITIDO` 403, `DEMASIADOS_INTENTOS` / `LIMITE_EVALUACIONES` 429 (con `Retry-After` y `reintentar_en_s`), `LIMITE_EVIDENCIAS` / `LIMITE_EVIDENCIAS_IP` / `CUOTA_LLM_AGOTADA` / `CUOTA_LLM_GLOBAL_AGOTADA` 429 (con `reinicia_en` en UTC), `LIMITADOR_NO_DISPONIBLE` 503.

## Alcance: cada encuestado solo ve su evaluación (`app/core/alcance.py`)

Se aplica a todas las rutas de evaluaciones, filtro, reportes, respuestas y evidencias.

| Quién | Evaluación pública | Evaluación por invitación |
|---|---|---|
| admin | todas | todas |
| encuestado (sub = id de evaluación) | solo la suya; otra → 404 | ninguna (404) |
| referente | ninguna (404) | solo las de su usuario temporal |
| sin token | 401 | igual que antes, salvo `EXIGIR_TOKEN_EVALUACIONES=true` (interruptor de HU-20) |

Lo ajeno responde 404 y no 403, para no confirmar ids correlativos. Un token mal formado responde 401 (no se trata como anónimo). El encuestado no puede usar `PATCH /respuestas/{id}/revision` (403), y `GET /api/evaluaciones` nunca lista evaluaciones públicas a quien no sea admin. Además, el usuario temporal de la encuesta pública no puede entrar como `referente` con su email opcional.

## Protección contra abuso (`app/infrastructure/cache/limitador.py`, `app/infrastructure/security/captcha.py`)

- **Contadores en Redis** (el mismo de ARQ), con ventana fija atómica (`SET NX EX` + `INCR`). Si Redis falla responde 503 (falla cerrado). Las claves usan una huella HMAC de la IP, nunca la IP en claro.
- **IP real:** solo se confía en `X-Cliente-IP` si viene con `X-BFF-Secret` correcto (`BFF_SHARED_SECRET`, obligatorio en producción). Sin el secreto se usa la IP de la conexión.
- **CAPTCHA Turnstile** validado en el servidor (`siteverify`, acción `iniciar_encuesta`, idempotency key, falla cerrado). Sin `TURNSTILE_SECRET_KEY` se omite solo en development/test.
- **Cuota diaria de IA:** 1 evidencia subida = 1 validación. Se cuenta por evaluación (40 por defecto) y en total (2000), y se reinicia a medianoche de `ZONA_HORARIA_CUOTAS`. Se reserva antes de guardar el archivo y se devuelve si la subida falla.
- **Alcance de los límites:** solo aplican a evaluaciones `publica`; las de invitación no cambian.

Valores por defecto en `config.py`; ver `.env.example`.

## Benchmark (criterio 4)

`update_benchmark.py` ya contaba solo `estado_progreso = 'completada'`, el estado al que únicamente se llega con `POST /completar` (cuestionario completo y sin evidencias en validación). Ahora además excluye `es_prueba = true`. Las evaluaciones abandonadas nunca llegan a `completada`, así que no entran. El frontend no envía ningún flag de benchmark.

## Pruebas

`tests/test_hu19_encuesta_publica.py` (en proceso, SQLite) cubre los 4 criterios: creación, aislamiento entre encuestados, retomar con clave, email opcional, intentos y cupos por IP, CAPTCHA, BFF, cuota de IA, límite de evidencias, devolución de cupo y benchmark.

En `APP_ENV=test` el limitador es nuevo en cada petición (las pruebas existentes no acumulan contadores); las de HU-19 lo reemplazan por uno persistente.

```bash
docker compose exec api pytest tests/test_hu19_encuesta_publica.py -v
docker compose exec worker pytest tests -v -rxX
```

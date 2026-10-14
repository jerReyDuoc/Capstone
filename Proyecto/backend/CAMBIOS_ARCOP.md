# Solicitudes de derechos ARCOP

Historia de usuario: *como Titular de Datos Personales quiero registrar solicitudes
formales de Acceso, Rectificación, Supresión, Oposición, Portabilidad o Bloqueo para
garantizar el cumplimiento de los derechos de la Ley N.º 21.719.*

Base: rama `main` en el commit `03d5bdb` ("Docker agregado"). Head de Alembic previo: `a168283ff2b8`.

## Cómo aplicar

1. Descomprimir el zip sobre la raíz del repo (las rutas empiezan en `Proyecto/`), o aplicar
   `arcop.patch` con `git apply arcop.patch` desde la raíz.
2. En `backend/.env` agregar `AUTH_SECRET` (generar con
   `python -c "import secrets; print(secrets.token_urlsafe(48))"`).
3. `alembic upgrade head` (o `docker compose up -d --build`, el servicio `migrate` la aplica).
4. `pytest tests -v -rxX`.

## Archivos

| Tipo | Archivo | Qué hace |
|---|---|---|
| nuevo | `app/domain/models/solicitud_arcop.py` | Modelos `SolicitudARCOP` y `EventoSolicitud`, enums de tipo/estado/evento y la máquina de estados `TRANSICIONES_ARCOP` |
| nuevo | `app/core/autenticacion.py` | Token bearer firmado (HMAC-SHA256, solo stdlib), `Actor`, `obtener_actor`, `requerir_rol`. Roles `referente` y `admin_therion` (los mismos del frontend) |
| nuevo | `app/infrastructure/repositories/solicitud_arcop_repository.py` | Persistencia; cambio + evento en la misma transacción; `SELECT … FOR UPDATE` al transicionar |
| nuevo | `app/application/use_cases/gestionar_solicitud_arcop.py` | Reglas de negocio: permisos por rol, propiedad, transiciones, validaciones |
| nuevo | `app/application/schemas/arcop_schemas.py` | Peticiones y respuestas |
| nuevo | `app/api/routes/arcop.py` | Endpoints `/api/arcop/...` |
| nuevo | `migrations/versions/e5a1c9d4b2f7_solicitudes_arcop.py` | Tablas `solicitudes_arcop` y `eventos_solicitud_arcop` |
| nuevo | `tests/test_solicitudes_arcop.py` | Pruebas en proceso (arnés `_api_harness.py`, SQLite en memoria) |
| modificado | `app/main.py` | Registra el router `arcop` |
| modificado | `app/domain/models/__init__.py` | Exporta los nuevos modelos (Alembic los detecta) |
| modificado | `app/core/config.py` | `AUTH_SECRET`, `AUTH_TOKEN_TTL_MIN`; en `production` exige `AUTH_SECRET` ≥ 32 caracteres |
| modificado | `.env.example`, `env.example` | Variables nuevas |

## Modelo de datos (migración `e5a1c9d4b2f7`, revisa `a168283ff2b8`)

`solicitudes_arcop`: `id_solicitud` PK · `tipo` · `estado` · `descripcion` (texto del titular) ·
`Usuario_temporal_id` FK → `usuario_temporal.id` (titular) · `fecha_creacion` · `fecha_actualizacion` ·
`fecha_cierre` · `respuesta` (resolución). CHECK de `tipo` y `estado`; índices por titular y estado.

`eventos_solicitud_arcop` (historial): `id_evento` PK · `Solicitudes_arcop_id_solicitud` FK · `fecha` ·
`tipo_evento` (creada, cambio_estado, informacion_aportada, resolucion, cancelacion) ·
`estado_anterior` · `estado_nuevo` · `actor_rol` · `actor_id` · `comentario`.

Fechas en UTC sin zona, igual que `eventos_seguridad` y `llamadas_llm`.

## Ciclo de vida

```
recibida ──► en_revision ──► en_proceso ──► resuelta
   │             │  ▲              │
   │             ▼  │              └──────► rechazada
   │     pendiente_informacion
   │             │
   ├─────────────┴──► rechazada   (admin, con respuesta)
   └─────────────┴──► cancelada   (titular, desde recibida / en_revision / pendiente_informacion)
```

`resuelta`, `rechazada` y `cancelada` son finales (fijan `fecha_cierre`, no admiten más cambios).

| Acción | Quién | Desde |
|---|---|---|
| crear (→ recibida) | titular | — |
| en_revision | admin | recibida, pendiente_informacion |
| pendiente_informacion (comentario obligatorio) | admin | en_revision |
| aportar información (→ en_revision) | titular | pendiente_informacion |
| en_proceso | admin | en_revision |
| resolución `resuelta` | admin | en_proceso |
| resolución `rechazada` | admin | recibida, en_revision, pendiente_informacion, en_proceso |
| cancelada | titular | recibida, en_revision, pendiente_informacion |

## Endpoints

Todos menos `/catalogo` exigen `Authorization: Bearer <token>`.

| Método | Ruta | Rol | Respuesta |
|---|---|---|---|
| GET | `/api/arcop/catalogo` | público | tipos, estados y transiciones |
| POST | `/api/arcop/solicitudes` | referente | 201 + detalle |
| GET | `/api/arcop/solicitudes?page&size&estado&tipo&usuario_temporal_id` | ambos | `{items,total,page,size,pages}`; el titular solo ve las suyas |
| GET | `/api/arcop/solicitudes/{id}` | ambos | detalle + historial; 404 si es de otro titular |
| PATCH | `/api/arcop/solicitudes/{id}/estado` | admin_therion | `{estado, comentario?}` |
| POST | `/api/arcop/solicitudes/{id}/resolucion` | admin_therion | `{resultado: resuelta\|rechazada, respuesta}` |
| POST | `/api/arcop/solicitudes/{id}/cancelacion` | referente | `{motivo?}` |
| POST | `/api/arcop/solicitudes/{id}/informacion` | referente | `{informacion}` |

Errores: 400 validación (texto), 401 `NO_AUTENTICADO`/`TOKEN_INVALIDO`, 403 `NO_AUTORIZADO`,
404 no encontrada, 409 `TRANSICION_INVALIDA` (incluye `estado_actual` y `permitidas`),
503 `AUTH_NO_CONFIGURADA` si falta `AUTH_SECRET`.

## Probar a mano (PowerShell, desde `Proyecto/backend` con el venv activo)

```powershell
$t = python -m app.core.autenticacion --usuario 1 --rol referente     # usuario_temporal 1 debe existir
$a = python -m app.core.autenticacion --usuario 1 --rol admin_therion
$T = @{ Authorization = "Bearer $t" }; $A = @{ Authorization = "Bearer $a" }
$api = "http://localhost:8000/api/arcop/solicitudes"

$s = Invoke-RestMethod -Method Post $api -Headers $T -ContentType "application/json" `
     -Body '{"tipo":"acceso","descripcion":"Solicito copia de mis datos personales."}'
Invoke-RestMethod $api -Headers $T
Invoke-RestMethod "$api/$($s.id_solicitud)" -Headers $T
Invoke-RestMethod -Method Patch "$api/$($s.id_solicitud)/estado" -Headers $A -ContentType "application/json" -Body '{"estado":"en_revision"}'
Invoke-RestMethod -Method Patch "$api/$($s.id_solicitud)/estado" -Headers $A -ContentType "application/json" -Body '{"estado":"en_proceso"}'
Invoke-RestMethod -Method Post "$api/$($s.id_solicitud)/resolucion" -Headers $A -ContentType "application/json" `
     -Body '{"resultado":"resuelta","respuesta":"Se adjunta el detalle de sus datos."}'
```

En Swagger (`/docs`) cada endpoint muestra el campo de header `authorization`: pegar
`Bearer <token>` ahí.

## Decisiones que requieren confirmación

1. **Autenticación.** El backend no tenía autenticación: todos los endpoints actuales son
   abiertos y solo el frontend simula login y roles. Sin identificar al titular no se puede
   cumplir "un titular no ve solicitudes ajenas", así que se agregó un único punto de
   identidad (`app/core/autenticacion.py`) que reutiliza los roles del frontend. **No hay
   endpoint de login**: los tokens se emiten con el CLI de prueba. Falta decidir cómo se
   emiten en producción (login real, link de invitación de `usuario_temporal`, etc.).
   Los endpoints existentes no se tocaron.
2. **Titular = `usuario_temporal`.** Es la única entidad de usuario. Si el titular puede ser
   alguien sin cuenta (p. ej. un trabajador de la empresa evaluada), hará falta otra entidad
   o datos de contacto en la solicitud.
3. **Plazos legales.** No se calcula fecha límite de respuesta ni vencimientos: el plazo y su
   forma de cómputo (días hábiles/corridos, prórrogas) dependen de la Ley 21.719 y deben
   confirmarse antes de agregarlos (columna `fecha_limite` + alerta).
4. **Verificación de identidad del titular, excepciones y causales de rechazo.** No se
   modelaron requisitos legales específicos; el rechazo solo exige una respuesta en texto.
5. **Estados `pendiente_informacion` y `cancelada`.** Son decisiones de diseño (pedir
   antecedentes al titular y permitir desistimiento), no requisitos legales. El titular no
   puede cancelar una vez `en_proceso`.
6. **Duplicados.** No se bloquea abrir dos solicitudes del mismo tipo a la vez (podrían ser
   distintas rectificaciones). Si se quiere impedir, es un cambio de una línea en el caso de uso.
7. **Expiración del `usuario_temporal`.** No se revisa `fecha_expiracion` al crear o consultar:
   un usuario con invitación vencida probablemente sigue teniendo derechos sobre sus datos.
8. **Ejecución de la solicitud.** El flujo registra y resuelve la solicitud; no ejecuta
   automáticamente la supresión, portabilidad, etc. sobre los datos.
9. **Integración con auditoría existente.** `eventos_seguridad` es específico de prompt
   injection, por eso el historial va en su propia tabla (`eventos_solicitud_arcop`).

# HU-27 · Empresa cliente, usuario definitivo y migración de la evaluación (backend)

*Como administrador de Therion Labs quiero registrar a una empresa que contrató el servicio, crear su usuario definitivo y migrar a ella la evaluación que hizo como usuario temporal, para que el cliente siga en el servicio pagado con su historial, sin repetir el autodiagnóstico.*

Cuando se empezó la HU no existían en `main` la solicitud de contratación (HU-31), la bitácora de auditoría (HU-09) ni el panel interno (HU-28). Por acuerdo del equipo, HU-27 deja una **base mínima** de HU-31 y HU-09, pensada para que quien tome esas HU la amplíe sin reescribirla, y la pantalla del administrador en `frontend-next` (ver `Extras/Cambios/frontend/CAMBIOS_HU27.md`).

## Cómo funciona

El usuario temporal termina su autodiagnóstico y pide contratar (`POST /api/contratacion/solicitudes`), dejando un contacto y autorizando expresamente que su evaluación pase a su empresa si contrata. Cuando el acuerdo comercial se cierra, el administrador marca la solicitud como `contratada` y, desde el panel, da de alta a la empresa con su usuario definitivo. Esa alta es **una sola transacción**: se crea la empresa, se crea el usuario (sin contraseña, rol único `cliente`), se migran las evaluaciones de las solicitudes elegidas, se emite el enlace de activación y se registra todo en la bitácora. Si cualquier paso falla (por ejemplo, una de las solicitudes no está contratada), no queda nada creado ni modificado. Después del commit se envía el correo con el enlace; si el correo falla, la empresa ya existe y el administrador reenvía el enlace.

La migración no copia datos. Las respuestas, evidencias y el resumen cuelgan de la evaluación, y el plan formativo y el informe PDF se calculan a partir de ellos, así que migrar consiste en reasignar la evaluación a la empresa (`evaluacion.empresa_id`). Copiar habría duplicado datos personales y dejado dos versiones del mismo diagnóstico. En la misma transacción se borra la clave de acceso de la evaluación (deja de funcionar), se anonimiza y cierra el usuario temporal (sin email, con `fecha_anonimizacion`, lo que invalida también sus tokens vigentes) y se borran los datos de contacto de la solicitud, porque desde ese momento el contacto vive solo en el usuario definitivo.

El usuario definitivo recibe un enlace de un solo uso que vence a las 72 horas (configurable). El administrador nunca ve ni define la contraseña y el sistema nunca la envía. El token del enlace va en el fragmento de la URL (`/activar#token=…`), que el navegador no envía al servidor, y en la base de datos solo queda su SHA-256. Con la contraseña definida, el cliente inicia sesión en `POST /api/auth/cliente` y ve, con las mismas rutas del panel, solo las evaluaciones migradas a su empresa.

## Criterios de aceptación

| Criterio | Dónde se cumple | Prueba |
|---|---|---|
| 1. El admin crea la empresa (razón social, RUT, rubro, fechas del contrato) y su usuario definitivo (nombre, email) con el único rol cliente | `POST /api/admin/empresas`; RUT validado con módulo 11 y único; email único; `CHECK rol = 'cliente'` y `UNIQUE (empresa_id)` en la BD | `test_flujo_completo…`, `test_validaciones_del_alta_de_empresa`, `test_un_solo_usuario_por_empresa_y_rol_unico_en_la_bd` |
| 2. Asocia una o más evaluaciones autorizadas en una solicitud (HU-31); en una transacción pasan respuestas, evidencias, resumen, plan formativo e informes; la clave temporal deja de funcionar y el usuario temporal queda cerrado sin duplicar contacto | `app/application/use_cases/migrar_evaluacion.py`; también `POST /api/admin/empresas/{id}/evaluaciones` para asociar más después del alta | `test_flujo_completo…`, `test_si_una_solicitud_no_es_valida_no_se_migra_nada`, `test_no_se_migra_sin_autorizacion_con_arcop_abierta_ni_dos_veces`, `test_asociar_otra_evaluacion…` |
| 3. Enlace de activación de un solo uso y con vencimiento; nunca se envía una contraseña; todo el proceso en la bitácora (HU-09) | `app/application/use_cases/activacion_cuenta.py`, `POST /api/auth/activacion`, tabla `bitacora_auditoria` | `test_flujo_completo…`, `test_enlace_vencido_reenvio…`, `test_sin_servidor_de_correo…` |

## Reglas de la migración

Una solicitud solo se migra si está `contratada`, tiene `autoriza_migracion = true`, su evaluación está completada y no pertenece ya a otra empresa, el usuario temporal no fue suprimido antes (ARCOP o conservación vencida) y no hay una solicitud ARCOP abierta sobre esa evaluación o ese titular. Esta última regla evita que una supresión pendiente borre después datos que ya son de la empresa. Además, `AnonimizacionRepository` ahora excluye las evaluaciones con `empresa_id`, de modo que ni una supresión del titular temporal ni la retención de T-06 pueden tocar lo migrado. Las solicitudes y evaluaciones se bloquean con `SELECT … FOR UPDATE` para que dos administradores no migren lo mismo a la vez.

El rubro del benchmark sigue siendo el del usuario temporal con que se respondió la evaluación (se conserva `usuario_temporal_id`, ya anonimizado). La empresa guarda además su propio rubro.

## Archivos

| Archivo | Cambio |
|---|---|
| `migrations/versions/b7e4d2a9c6f1_hu27_empresa_usuario_definitivo.py` | **Nuevo.** Tablas `empresa`, `usuario_definitivo`, `token_activacion`, `solicitud_contratacion`, `bitacora_auditoria`; columnas `evaluacion.empresa_id` y `evaluacion.fecha_migracion`. En PostgreSQL agrega un índice único sobre `lower(email)` y un trigger que impide `UPDATE`/`DELETE` en la bitácora. `down_revision = a9d3e5f7c1b2` (HU-12). |
| `app/domain/models/empresa.py`, `usuario_definitivo.py`, `solicitud_contratacion.py`, `bitacora_auditoria.py` | **Nuevos.** Modelos (incluye `TokenActivacion`). |
| `app/domain/models/evaluacion.py`, `__init__.py` | `empresa_id`, `fecha_migracion`; registro de los modelos nuevos. |
| `app/application/use_cases/migrar_evaluacion.py` | **Nuevo.** Caso de uso transaccional de la migración (nunca hace commit; lo hace quien llama). |
| `app/application/use_cases/contratacion_empresa.py` | **Nuevo.** Solicitudes de contratación (base HU-31) y alta/asociación/reenvío de la empresa cliente. |
| `app/application/use_cases/activacion_cuenta.py` | **Nuevo.** Token de activación, correo, verificación y activación con reglas de contraseña. |
| `app/application/use_cases/iniciar_sesion.py` | Login del rol `cliente`. |
| `app/infrastructure/repositories/bitacora_repository.py` | **Nuevo.** `registrar()` (rechaza emails, nombres, contraseñas y tokens en `detalle`) y `listar()`. |
| `app/infrastructure/repositories/anonimizacion_repository.py` | No anonimiza evaluaciones migradas. |
| `app/api/routes/admin_clientes.py`, `contratacion.py` | **Nuevos.** Rutas de `/api/admin` y `/api/contratacion`. |
| `app/api/routes/auth.py` | `POST /api/auth/cliente`, `/activacion/verificar` y `/activacion`, con límites de intentos por IP y por email. |
| `app/api/routes/evaluaciones.py`, `app/core/alcance.py` | El rol `cliente` ve solo las evaluaciones de su empresa. El listado ya no devuelve todo a un rol desconocido. |
| `app/api/routes/arcop.py` | Listado y detalle ARCOP solo para titulares y admin. Sin esto, el id del cliente se habría confundido con el de un usuario temporal. |
| `app/core/autenticacion.py` | Rol `cliente`; en cada petición se exige usuario activo y contrato vigente. |
| `app/core/rut.py` | **Nuevo.** Normalización y dígito verificador del RUT. |
| `app/core/config.py` | `ACTIVACION_TTL_HORAS`, `ACTIVACION_URL_BASE`, `CLIENTE_PASSWORD_MIN`, `CONSENTIMIENTO_CONTRATACION_VERSION`. |
| `app/core/catalogo_datos_personales.py` | Clasificación T-06 de todas las columnas nuevas. |
| `app/main.py` | Registra los routers nuevos. |
| `tests/test_hu27_empresa_cliente.py` | **Nuevo.** 16 pruebas. |
| `tests/test_hu20_autorizacion.py` | Clasifica las rutas nuevas en la matriz de HU-20. |
| `Proyecto/.env.example`, `Proyecto/README.md` | Variables y endpoints nuevos. |

## Variables de entorno

| Variable | Por defecto | Uso |
|---|---|---|
| `ACTIVACION_URL_BASE` | `http://localhost:3000/activar` | Página que recibe el enlace. En production debe ser `https://` (se comprueba antes de guardar el alta). |
| `ACTIVACION_TTL_HORAS` | `72` | Vigencia del enlace. |
| `CLIENTE_PASSWORD_MIN` | `12` | Largo mínimo (no puede ser menor que 10). Además: letras y números, sin espacios en los extremos, sin el correo ni el nombre. |
| `CONSENTIMIENTO_CONTRATACION_VERSION` | `2026-10-v1` | Versión del texto de autorización. Si el PO cambia el texto, se sube la versión y el frontend debe mostrar el nuevo. |

El correo usa la configuración existente (`CORREO_MODO`). En desarrollo, con `CORREO_MODO=archivo`, el enlace queda en `STORAGE_DIR/correos/*.eml`.

## Cómo probarlo en Docker

```bash
docker compose exec api alembic upgrade head
docker compose exec worker pytest tests/test_hu27_empresa_cliente.py tests/test_hu20_autorizacion.py tests/test_t06_minimizacion.py -v
docker compose exec worker pytest tests -v -rxX
```

Por Swagger (`/docs`): haz una evaluación pública hasta completarla, pide contratar con el token del encuestado (`POST /api/contratacion/solicitudes`), y con el token de admin marca la solicitud como contratada (`PATCH /api/admin/contrataciones/{id}`) y crea la empresa (`POST /api/admin/empresas`). Abre el `.eml` de `storage/correos`, copia el token del enlace y actívalo en `POST /api/auth/activacion`. Luego entra con `POST /api/auth/cliente` y consulta `GET /api/evaluaciones/{id}/plan-formativo` con ese token.

## Verificación hecha

La suite completa pasó en proceso (SQLite): 507 aprobadas y 9 omitidas, contra 485 antes del cambio. Además se probó la migración en un PostgreSQL 16 real: cadena completa de Alembic hasta `b7e4d2a9c6f1`, downgrade y nuevo upgrade, el trigger de solo inserción rechazando `UPDATE` y `DELETE`, el `CHECK` del rol rechazando `rol = 'admin'`, el flujo completo de punta a punta por la API (alta, migración, activación, login y plan formativo/PDF del cliente) y `scripts/auditoria_minimizacion.py`, que clasifica las 24 tablas y no encuentra PII en la bitácora.

## Pendientes y decisiones abiertas

- **Textos de consentimiento** (pendiente del PO): el texto de autorización de traspaso en `app/api/routes/contratacion.py` es provisorio.
- **Reglas del contrato** (pendiente del PO): hoy el cliente entra solo con contrato vigente (`fecha_inicio ≤ hoy ≤ fecha_termino`) y la activación se permite aunque el contrato aún no empiece. No hay renovación ni baja; el estado `bloqueado` existe pero no tiene endpoint todavía.
- **HU-31** puede ampliar `solicitud_contratacion` (notificaciones, seguimiento comercial, pantalla para el usuario temporal). HU-27 depende solo de `evaluacion_id`, `autoriza_migracion`, `estado` y del borrado del contacto al migrar.
- **HU-09** puede agregar acciones a `Accion` en `bitacora_repository.py`, filtros, exportación y retención. La bitácora es de solo inserción por diseño.
- **HU-28** puede integrar `/admin/clientes` en el panel interno completo.
- Falta el login del cliente en el frontend y la recuperación de contraseña (fuera del alcance de esta HU).

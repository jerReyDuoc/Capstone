# HU-09 · Log inmutable para el Auditor Externo (backend)

*Como Auditor Externo, quiero exportar un log inmutable con el historial de modificaciones y supresiones de datos, para demostrar la trazabilidad requerida por el Art. 14 ter de la Ley N.º 21.719.*

La base ya existía: HU-27 creó la bitácora (`bitacora_auditoria`) con un trigger que impedía `UPDATE` y `DELETE`, y HU-18 le agregó una cadena HMAC fila a fila. Para cumplir esta HU faltaban cosas de fondo. La tabla no guardaba la IP, no existía un rol de auditor ni una forma de exportar, la verificación recorría fila por fila cargando toda la tabla en memoria, y el trigger no frenaba un `TRUNCATE` (un trigger por fila no se dispara con `TRUNCATE`). Además, la API se conectaba a PostgreSQL como `postgres`, que es superusuario: con esa conexión un `REVOKE` no sirve de nada, así que "sin permisos UPDATE/DELETE" no era cierto. Y las supresiones más importantes para la ley (las de ARCOP y las de los plazos de conservación de T-06) ni siquiera quedaban en la bitácora.

## Cómo funciona

**La tabla se llama `audit_log`** (se renombró con `ALTER TABLE ... RENAME`, así que se conservan las filas, sus hashes y los índices). La clase del modelo sigue siendo `BitacoraAuditoria`, con el alias `AuditLog`, para no tocar los cerca de 40 lugares que registran acciones.

**La inmutabilidad tiene tres capas.** La primera son los permisos: la API y el worker ya no se conectan como `postgres`, sino con el rol `complianceia_app` (`DB_APP_USER`), que no es superusuario ni dueño de las tablas. En el resto de las tablas tiene lo de siempre (leer, insertar, modificar y borrar), pero en `audit_log` y `audit_log_sello` solo `SELECT` e `INSERT`. Las migraciones siguen corriendo con el dueño (`POSTGRES_USER`), que es quien crea el rol con la clave `DB_APP_PASSWORD`. La segunda capa son los triggers, que impiden `UPDATE`, `DELETE` y `TRUNCATE` aunque los intente el dueño. La tercera es la evidencia: si alguien con superusuario desactiva los triggers y cambia algo, la cadena HMAC y los sellos por lote lo delatan e indican en qué lote ocurrió.

**Cada registro trae los cinco campos obligatorios**: la fecha (UTC), el actor (rol e id, o `sistema` para los procesos internos), la IP, la acción y el resultado (`ok`, `rechazado`, `error` u `omitido`). La IP la pone sola un middleware ASGI (`app/core/contexto_auditoria.py`): toma la del visitante que reenvía el BFF de Next.js si trae el secreto correcto, o la de la conexión, y siempre la valida y normaliza con `ipaddress`, de modo que un encabezado con otra cosa nunca llega al log. Fuera de una petición HTTP queda `sistema:worker` o `sistema:cli`. En PostgreSQL lo exigen restricciones `CHECK` y en el código, `BitacoraRepository.registrar()`. Las restricciones se crearon `NOT VALID`: rigen para toda fila nueva, porque las filas anteriores a HU-09 no tienen IP y no se pueden modificar.

**La IP entra al hash.** El canónico de la cadena HMAC pasó a una versión `v2` que incluye la IP; las filas anteriores siguen verificándose con `v1`. Borrar o cambiar la IP de una fila ya encadenada cambia su hash y se detecta.

**La verificación es por lote.** Cada `AUDIT_SELLO_CADA_MIN` minutos (15) el worker toma las filas sin sellar, las corta en lotes de `AUDIT_LOTE_TAMANO` (500) y por cada lote guarda en `audit_log_sello` su `hash_lote`, su `sello` encadenado al sello anterior y una firma HMAC del sello. El último lote puede quedar incompleto: no se espera a juntar 500 filas para dejar evidencia. El sellado toma el mismo *advisory lock* que el encadenamiento de filas, y como cada transacción que inserta en el log lo conserva hasta su commit, al sellar no puede quedar una fila "en vuelo" con un id menor que otra ya confirmada.

```
huella(fila) = SHA-256("<id>|" + canónico(fila))
hash_lote    = SHA-256("\n".join(huellas del lote, en orden de id))
sello        = SHA-256(canónico(lote, desde_id, hasta_id, cantidad, hash_lote, fecha, sello_anterior))
firma        = HMAC-SHA256(clave de la bitácora, sello)
```

`hash_lote` y `sello` son SHA-256 sin clave: **el auditor los recalcula con el archivo exportado sin pedirnos nada**. La firma con clave prueba ante nosotros que un sello lo emitió el sistema y no alguien con acceso directo a la BD. La verificación del servidor recorre el log una sola vez, de a bloques y sin cargarlo entero, y comprueba a la vez la cadena HMAC, cada lote contra su sello y que no haya filas fuera de un lote. Si algo falla, informa el motivo por lote: `hash_lote_distinto`, `cantidad_distinta`, `rango_distinto`, `cadena_de_sellos_rota`, `sello_alterado`, `firma_invalida` o `filas_fuera_de_lote`.

## El Auditor Externo

Es un rol nuevo, `auditor_externo`, con cuentas en la tabla `usuario_auditor`. Las crea un admin (`POST /api/admin/auditores` o `python -m app.core.crear_auditor`) con correo, organización auditora, contraseña y vigencia en días (máximo `AUDITOR_VIGENCIA_MAX_DIAS`, 90). La cuenta vence sola: al vencer o al desactivarla, el token deja de servir en la petición siguiente. El login (`POST /api/auth/auditor`) tiene las mismas protecciones que el del admin en HU-28 (intentos limitados, sesión revocable, cada intento en el log), y su sesión nunca dura más que la cuenta.

El auditor **solo ve el log**: consulta con filtros, verificación, lotes y exportación. Cualquier otra ruta le responde 403 o, en las de evaluaciones, 404. De paso se cerró un detalle de `verificar_alcance`: un rol que no fuera admin, cliente, encuestado ni referente caía en la rama "sin token"; ahora recibe 404 siempre.

El historial se filtra por **categoría**, que se calcula a partir de la acción: `modificacion`, `supresion`, `creacion`, `acceso`, `seguridad` y `auditoria`. Con `?categoria=supresion` y `?categoria=modificacion` el auditor obtiene justamente lo que pide el art. 14 ter.

**La exportación** (`GET /api/auditoria/exportacion?desde=&hasta=`) primero sella lo pendiente y luego entrega un ZIP con los **lotes completos** que tocan el rango. Por eso pueden aparecer algunos registros justo antes o después de las fechas pedidas: si se recortara un lote, su hash ya no se podría recalcular. El ZIP contiene:

| Archivo | Para qué |
|---|---|
| `audit_log.jsonl` | un registro por línea; es el que se verifica |
| `audit_log.csv` | lo mismo para abrir en Excel (con BOM para las tildes) y filtrar por `categoria` |
| `lotes.json` | el sello de cada lote |
| `verificacion.json` | la verificación del log completo hecha por el sistema al exportar, que incluye las firmas HMAC |
| `manifiesto.json` | SHA-256 de cada archivo, rango, lotes, `sello_anterior_al_primer_lote` y `ultimo_sello` |
| `verificar_exportacion.py` | verificación independiente, con Python 3.10+ y solo la librería estándar |
| `LEEME.txt` | instrucciones para el auditor |

El script recalcula los SHA-256 de los archivos, el hash de cada lote, la cadena de sellos y el enlace `hash_anterior` entre registros. Con `--ancla <sello>` comprueba que un sello anotado en una exportación anterior siga idéntico, es decir, que nadie reescribió el pasado. La cabecera `X-Audit-Export-SHA256` trae el hash del ZIP, que también queda en el log. Cada consulta, verificación y exportación queda registrada en el propio log, porque quién accedió a un registro que contiene IPs también tiene que ser trazable.

## Modificaciones y supresiones que ahora quedan en el log

| Acción | Categoría | Dónde |
|---|---|---|
| `arcop.solicitud_creada`, `arcop.estado_cambiado`, `arcop.informacion_aportada`, `arcop.plazo_prorrogado`, `arcop.solicitud_resuelta`, `arcop.solicitud_cancelada` | creación / modificación | `SolicitudARCOPRepository`: un registro por cada evento del historial, en la misma transacción |
| `arcop.datos_suprimidos` | supresión | supresión aprobada; el detalle trae `suprimido` con el conteo por tabla |
| `retencion.titular_anonimizado` (R1), `retencion.arcop_anonimizada` (R2), `retencion.extractos_eliminados` (R3), `retencion.conversaciones_eliminadas` (R4) | supresión | `AplicarRetencionUseCase`, actor `sistema`, con la regla y el plazo aplicado |
| `evidencia.original_suprimido` | supresión | worker: HU-06 reemplaza el archivo por su texto anonimizado |
| `respuesta.modificada` | modificación | cambio de una declaración ya guardada (no la creación ni el guardado automático idéntico) |
| `respuesta.revision_humana` | modificación | revisión del admin |
| `evaluacion.marcada_prueba`, `encuestado.clave_generada` | modificación | acciones del admin |
| `auditor.*`, `auditoria.*` | creación / modificación / auditoría | cuentas y accesos del auditor |

Ninguno guarda textos libres (justificaciones, descripciones, respuestas): solo ids, estados, conteos y si el texto cambió. Las acciones que ya existían (contrato, documentos, tutor, migración, sesiones) quedaron clasificadas en su categoría.

Un cambio menor: el aviso comercial de HU-31 registraba `resultado = "fallido"`. El dominio del log quedó en `ok`, `rechazado`, `error` y `omitido`, así que ahora ese caso queda como `error` (significa lo mismo). Se ajustó su prueba.

## Criterios de aceptación

| Criterio | Dónde se cumple | Prueba (`tests/test_hu09_audit_log.py`) |
|---|---|---|
| 1. Tabla `audit_log` append-only sin permisos UPDATE/DELETE | Migración `d2f8a6c4e1b9`: renombre, rol `complianceia_app` con solo `SELECT, INSERT` en el log, `REVOKE` a `PUBLIC`, triggers de `UPDATE`/`DELETE`/`TRUNCATE`; compose conecta api y worker con ese rol. El código no tiene cómo modificar ni borrar filas | `test_c1_el_codigo_no_tiene_como_modificar_ni_borrar_el_log`, `test_c1_la_migracion_quita_update_delete_truncate_y_agrega_triggers`, `test_c1_compose_conecta_api_y_worker_con_el_rol_limitado` y, en PostgreSQL real, `test_c1_en_postgresql_el_rol_de_la_app_no_puede_update_delete_truncate` (`HU09_PG_LIVE=1`) |
| 2. Registro obligatorio de timestamp, usuario/sistema, IP, acción y resultado | Middleware de IP, `registrar()` valida, `CHECK` en la BD; la IP en el hash `v2` | `test_c2_cada_registro_trae_fecha_actor_ip_accion_y_resultado`, `test_c2_ip_del_bff_solo_con_su_secreto_y_siempre_normalizada`, `test_c2_registrar_rechaza_campos_obligatorios_invalidos`, `test_c2_fuera_de_una_peticion_el_origen_es_el_proceso`, `test_c2_la_bd_rechaza_un_registro_sin_ip` |
| 3. Verificación de integridad por hash en lote | `audit_log_sello`, `audit_log_lotes.py` (sellado y verificación), `GET /api/auditoria/verificacion`, script del ZIP | `test_c3_*` (alteración, borrado, reorden, renumeración, sellos, firma, API), `test_exportacion_zip_verificable_sin_el_sistema`, `test_exportacion_adulterada_la_detecta_el_script` |

Además: `test_auditor_solo_lee_el_log_y_cada_acceso_queda_registrado`, `test_auditor_filtra_modificaciones_y_supresiones`, `test_cuentas_de_auditor_validan_vencen_y_se_desactivan`, `test_rutas_hu09_por_rol` (401/403/200 por rol en las 8 rutas nuevas), `test_modificacion_de_respuesta_y_revision_quedan_en_el_log_sin_texto`, `test_supresion_arcop_queda_en_el_log_con_lo_suprimido`, `test_retencion_registra_cada_supresion_como_sistema` y los de exportación por rango y tope de filas.

## Endpoints nuevos

| Método | Ruta | Quién |
|---|---|---|
| POST | `/api/auth/auditor` | público (devuelve el token del auditor) |
| GET | `/api/auditoria/registros?desde=&hasta=&categoria=&accion=&entidad=&entidad_id=&resultado=&actor_rol=&page=&size=` | auditor, admin |
| GET | `/api/auditoria/verificacion` | auditor, admin |
| GET | `/api/auditoria/lotes` | auditor, admin |
| GET | `/api/auditoria/exportacion?desde=&hasta=` | auditor, admin |
| GET | `/api/auditoria/catalogo` | auditor, admin |
| GET / POST | `/api/admin/auditores` | admin |
| PATCH | `/api/admin/auditores/{id}` | admin |

`GET /api/admin/bitacora` ahora trae `ip` y `categoria` en cada fila, y `GET /api/admin/bitacora/verificacion` conserva todas las claves de HU-18 y agrega `lotes`, `filas` y `ancla_lote`. El frontend actual no se ve afectado.

## Archivos

| Archivo | Cambio |
|---|---|
| `migrations/versions/d2f8a6c4e1b9_hu09_audit_log_inmutable.py` | **Nuevo.** Renombre, `ip`, `CHECK NOT VALID`, triggers, `audit_log_sello`, `usuario_auditor`, rol `auditor_externo` en `sesion_usuario` y rol de PostgreSQL de la app. `down_revision = a7c4e2f9d1b3` (HU-10). Tiene `downgrade` (probado ida y vuelta). |
| `app/domain/models/bitacora_auditoria.py` | Tabla `audit_log`, `ip`, `CHECK` (también en el SQLite de las pruebas), resultados válidos, alias `AuditLog`. |
| `app/domain/models/auditoria_externa.py` | **Nuevo.** `AuditLogSello` y `UsuarioAuditor`. |
| `app/domain/auditoria_hash.py` | Canónico `v2` con IP, huella pública, `hash_lote`, sellos, `VerificadorCadena` por partes y `verificar_sello`. |
| `app/domain/verificar_exportacion.py` | **Nuevo.** Script independiente del auditor (va dentro del ZIP). |
| `app/core/contexto_auditoria.py` | **Nuevo.** Middleware y normalización de la IP; origen `sistema:worker` / `sistema:cli`. |
| `app/core/crear_auditor.py` | **Nuevo.** CLI para crear, extender o desactivar auditores. |
| `app/infrastructure/repositories/audit_log_lotes.py` | **Nuevo.** Sellado por lote y verificación en una pasada. |
| `app/infrastructure/repositories/bitacora_repository.py` | IP automática, validación de campos obligatorios, acciones nuevas, categorías y filtros por fecha, categoría, resultado y rol. |
| `app/infrastructure/repositories/bitacora_cadena.py` | La IP entra al hash; recorrido por bloques que no llena la sesión. |
| `app/application/use_cases/auditoria_externa.py` | **Nuevo.** Consulta, verificación, exportación ZIP y cuentas de auditor. |
| `app/api/routes/auditoria.py` | **Nuevo.** Rutas del auditor y de las cuentas. |
| `app/core/autenticacion.py`, `app/core/alcance.py`, `app/domain/models/sesion.py` | Rol `auditor_externo`; un rol desconocido no ve evaluaciones; sesión del auditor. |
| `app/application/use_cases/iniciar_sesion.py`, `app/api/routes/auth.py` | Login del auditor; la regeneración de la clave del encuestado queda en el log. |
| `app/infrastructure/repositories/solicitud_arcop_repository.py`, `app/application/use_cases/gestionar_solicitud_arcop.py` | Cada evento ARCOP en el log; la supresión con los conteos. |
| `app/application/use_cases/aplicar_retencion.py` | Cada supresión de T-06 en el log. |
| `app/application/use_cases/create_respuesta.py`, `app/api/routes/respuestas.py`, `app/api/routes/evaluaciones.py` | Modificación y revisión de respuestas; marca de prueba. |
| `app/application/use_cases/process_evidence.py`, `app/worker/tasks.py` | Supresión del original (HU-06); cron de sellado; origen `sistema:worker`. |
| `app/application/use_cases/aviso_contratacion.py` | `fallido` pasa a `error`. |
| `app/api/routes/admin_clientes.py`, `app/main.py`, `app/core/config.py`, `app/core/cliente.py` | IP y categoría en la bitácora del admin; verificación por lote; middleware y rutas; variables nuevas. |
| `app/core/catalogo_datos_personales.py` | `audit_log` (con la IP como excepción documentada), `audit_log_sello` y `usuario_auditor`. |
| `tests/test_hu09_audit_log.py` | **Nuevo.** 32 pruebas (una en vivo, opcional). |
| `tests/test_hu18_*.py`, `test_hu20_*.py`, `test_hu31_*.py`, `test_t06_*.py` | Nombre de la tabla, rutas nuevas en la matriz, `error` en vez de `fallido` y `DB_APP_PASSWORD` en la configuración de producción. |
| `Proyecto/docker-compose.yml` | `migrate` con el dueño; `api` y `worker` con `complianceia_app` y sin la clave del dueño. |
| `Proyecto/.env.example`, `Proyecto/README.md` | Variables y documentación de HU-09. |

## Cómo aplicarlo y probarlo en Docker

Desde `Proyecto/`, después de copiar los archivos:

```bash
docker compose up -d --build
docker compose logs migrate             # debe terminar en "Running upgrade a7c4e2f9d1b3 -> d2f8a6c4e1b9"
docker compose exec api alembic current # d2f8a6c4e1b9 (head)
docker compose exec worker pytest tests -v -rxX
docker compose exec -e HU09_PG_LIVE=1 worker pytest tests/test_hu09_audit_log.py -v
```

La última línea corre la prueba contra el PostgreSQL real del compose: confirma que la app ya no es superusuario y que `UPDATE`, `DELETE` y `TRUNCATE` sobre el log responden *permission denied* (no deja nada escrito: el `INSERT` de prueba se revierte). Para verlo a mano:

```bash
docker compose exec db psql -U postgres -d complaince_db -c "UPDATE audit_log SET resultado='error' WHERE id=1"
# ERROR: audit_log es de solo inserción (HU-09): UPDATE no permitido   <- trigger, aunque seas el dueño
```

Para probar como auditor, por Swagger (`/docs`): con el token del admin llama a `POST /api/admin/auditores` con `{"email": "auditora@firma.cl", "organizacion": "Firma Auditora SpA", "password": "una-clave-de-12+", "dias_vigencia": 30}`, luego a `POST /api/auth/auditor` y autoriza con ese token. `GET /api/auditoria/verificacion` debe dar `integra: true`, y `GET /api/auditoria/exportacion` descarga el ZIP. Descomprímelo y corre `python verificar_exportacion.py .` en la carpeta.

**Si tu `.env` ya existía**, no hace falta tocarlo en desarrollo: el compose y el backend usan por defecto `complianceia_app` / `complianceia_app_dev`. Si alguien definió `DB_APP_PASSWORD`, tiene que estar en el `.env` antes de `docker compose up`, porque `migrate` crea el rol con esa clave y `api`/`worker` se conectan con ella.

## Verificación hecha

En este entorno no hubo PyPI, así que las dependencias se armaron desde el código fuente en GitHub (y algunos módulos nativos de LangGraph con sustitutos solo para importar). Con eso se corrió **la suite completa: 737 aprobadas y 9 omitidas** (antes 706 y 8; la omitida nueva es la prueba en vivo). La cobertura no se midió aquí (no hubo `pytest-cov`); la mide el CI.

La migración se probó contra un **PostgreSQL 16 real**: `upgrade` con filas de bitácora anteriores a HU-09, `downgrade -1` y `upgrade` de nuevo. Conectado como `complianceia_app`, `UPDATE`, `DELETE` y `TRUNCATE` sobre `audit_log` y `audit_log_sello` dan *permission denied*, los `CHECK` rechazan filas sin IP, sin id de actor o con un resultado inválido, y el rol no puede crear tablas, desactivar triggers ni escribir en `alembic_version`. Como `postgres`, los triggers frenan `UPDATE`, `DELETE` y `TRUNCATE`. También se corrió el código async real (registro, sellado, verificación y exportación) contra ese PostgreSQL con el rol limitado. Las filas `v1` anteriores a HU-09 y las nuevas `v2` verificaron juntas, y el script del ZIP dio OK. Después, como superusuario, se desactivó el trigger, se alteró una fila y se borró otra: el servidor y el script independiente detectaron ambas cosas e indicaron los lotes 2 y 3.

## Pendientes y decisiones abiertas

- **Conservación del log** (pendiente del PO). El log es inmutable, así que una supresión ARCOP no borra las IPs del log: se conservan por la obligación de responsabilidad (art. 14 ter). Si el PO fija un plazo, la purga tendría que hacerse por lote sellado y exportado, con un procedimiento del dueño de la BD; no se implementó. Queda documentado en el catálogo de T-06.
- **Ancla externa.** La cadena sola no detecta que alguien borre los últimos lotes; para eso el auditor anota el `ultimo_sello` de cada exportación y lo usa como `--ancla` en la siguiente. Si se quiere ir más allá, el sello podría publicarse en un tercero (correo al auditor o un servicio de sellado de tiempo).
- **Recuperación de contraseña del auditor**: no tiene flujo propio; la cambia el admin (`PATCH /api/admin/auditores/{id}` o el CLI con `--password`).
- **Frontend**: el criterio del equipo se cumple con el backend. Si se quiere, la pantalla del auditor en `frontend-next` (consulta, verificación y botón de exportar) y la gestión de auditores en el panel interno serían una tarea aparte.
- **BD administrada sin permiso de crear roles** (por ejemplo, en el piloto): la migración avisa y omite el rol. Habría que crearlo a mano con las mismas sentencias de `_crear_rol_app()`.
- **Scripts que corren dentro de `api` o `worker`** (por ejemplo, `poblar_panel_prueba.py`) ahora usan el rol limitado: pueden modificar y borrar sus datos de prueba en las tablas normales, pero no tocar `audit_log`, y `TRUNCATE` no está permitido en ninguna tabla. Si un script necesita más, se corre con `docker compose exec db psql -U postgres ...`.
- **Guía de puesta en marcha (PDF)**: conviene agregar `DB_APP_USER`/`DB_APP_PASSWORD` y el comando de la prueba en vivo.

# HU-30 · Vigencia del contrato de la empresa cliente (backend)

*Como Administrador de Therion Labs quiero controlar la vigencia del contrato de cada empresa cliente, para que el servicio pagado esté disponible solo para clientes con contrato vigente.*

Hasta ahora el contrato era solo un par de fechas y la regla vivía en dos lugares: el login del cliente respondía 403 `CONTRATO_NO_VIGENTE` y cada petición del rol `cliente` se rechazaba con 401 si el contrato había terminado. Eso tenía dos problemas frente a esta HU. Primero, el administrador no podía hacer nada con el contrato después del alta (no había renovación, suspensión ni término). Segundo, al vencer el contrato el cliente perdía de golpe todo, incluso lo que es gratuito para cualquier encuestado y sus derechos ARCOP. HU-30 separa las dos cosas: el contrato decide el **servicio pagado**, no el acceso a la cuenta.

## Cómo funciona

El contrato tiene ahora un **estado** que fija el administrador (`activo`, `suspendido` o `terminado`) además de sus fechas. La **situación** se calcula en cada petición combinando ambos, así que un contrato vence solo al pasar su fecha de término, sin cron. Las reglas están en un único módulo sin base de datos, `app/domain/contrato.py`, que usan el modelo `Empresa` y las guardas:

| Situación | Cuándo | Servicio pagado | Documentos |
|---|---|---|---|
| `pendiente` | activo y aún no llega la fecha de inicio | no | sí |
| `vigente` | activo y hoy entre inicio y término | **sí** | sí |
| `suspendido` | suspendido por el admin (mientras no pase la fecha de término) | no | sí |
| `vencido` | activo (o suspendido) con la fecha de término ya pasada, dentro del plazo de gracia | no | sí |
| `terminado` | terminado por el admin, dentro del plazo de gracia | no | sí |
| `finalizado` | vencido o terminado y fuera del plazo de gracia | no | no (retención, HU-25) |

El plazo de gracia es `CONTRATO_GRACIA_DIAS` (30 por defecto) contado desde el día en que el contrato dejó de regir: la fecha de término pactada o la de terminación anticipada, la que ocurra primero. Así, terminar un contrato que ya había vencido no le regala otros 30 días.

El cliente **sigue pudiendo iniciar sesión** sin contrato vigente. `POST /api/auth/cliente` responde 200 y trae `contrato` con la situación y el mensaje para mostrar, y el token sirve para lo gratuito (evaluación, resultados, informe PDF y plan formativo), para sus documentos mientras dure la gracia y para ARCOP. Lo pagado lo corta `app/core/servicio_pagado.py`, que ya era el punto único que dejó preparado HU-26: `empresa_con_servicio` exige contrato vigente y responde 403 `CONTRATO_NO_VIGENTE` con la `situacion` y, si corresponde, `documentos_disponibles_hasta`; la nueva `empresa_con_documentos` deja descargar hasta el fin de la gracia y después responde 403 `PLAZO_GRACIA_VENCIDO`.

## Criterios de aceptación

| Criterio | Dónde se cumple | Prueba (`tests/test_hu30_contrato.py`) |
|---|---|---|
| 1. Desde el panel interno el admin renueva, suspende o termina el contrato, y cada cambio queda en el audit log | `POST /api/admin/empresas/{id}/contrato/renovacion`, `/suspension`, `/reactivacion` y `/terminacion` (`gestionar_contrato.py`). Cada operación bloquea la fila de la empresa y registra en la misma transacción `contrato.renovado`, `contrato.suspendido`, `contrato.reactivado` o `contrato.terminado` con el estado, la situación y las fechas antes y después, y el motivo | `test_api_admin_renueva_suspende_reactiva_y_termina_y_cada_cambio_queda_en_la_bitacora`, `test_operaciones_permitidas_por_situacion` |
| 2. Sin contrato vigente, 403 `CONTRATO_NO_VIGENTE` en cursos, tutor IA, borradores y espacio de la empresa; lo gratuito no cambia | `empresa_con_servicio` en `/api/formacion/*`, `/api/remediacion/*` y `GET /api/cliente/empresa`; las rutas de `/api/evaluaciones` no dependen del contrato. El tutor IA y los borradores todavía no tienen rutas: cuando se creen deben usar la misma guarda, y una prueba lo vigila | `test_api_sin_contrato_vigente_el_servicio_pagado_responde_403_y_lo_gratuito_no_cambia` (suspendido, pendiente y vencido), `test_rutas_del_servicio_pagado_usan_la_guarda`, `test_situacion_del_contrato` |
| 3. Al terminar, descarga de documentos durante un plazo de gracia; después, retención (HU-25); ARCOP disponible siempre | `empresa_con_documentos` en la constancia; `GET /api/cliente/contrato` lista lo que puede descargar; `empresas_con_gracia_vencida()` entrega a HU-25 las empresas a procesar; el rol `cliente` pasa a ser titular ARCOP (columna `solicitudes_arcop.Usuario_definitivo_id`) y su supresión se resuelve con `anonimizar_usuario_definitivo()` | `test_api_plazo_de_gracia_para_documentos_y_despues_retencion`, `test_api_supresion_arcop_del_cliente_borra_sus_datos_y_no_toca_la_empresa`, `test_terminar_un_contrato_ya_vencido_no_reinicia_el_plazo_de_gracia` |

## Reglas de las operaciones

Renovar fija una nueva fecha de término, que debe ser posterior a la actual y a hoy (y no más de 10 años adelante, para atajar un año mal escrito), y deja el contrato `activo`: sirve tanto para extender un contrato vigente como para recuperar uno vencido, suspendido o terminado mientras dure la gracia. Suspender se permite solo con el contrato vigente o pendiente y corta el servicio sin terminar el contrato; reactivar la levanta sin tocar fechas. Terminar se permite en cualquier situación salvo ya terminado o finalizado y abre el plazo de gracia. Fuera de la gracia no se acepta ninguna operación (409 `CONTRATO_FINALIZADO`): los datos ya quedaron para la retención y volver a contratar requiere un acuerdo nuevo. Cualquier otra operación no permitida responde 409 `TRANSICION_CONTRATO_INVALIDA` con la lista de las que sí se pueden hacer, para que el panel muestre solo esos botones.

El motivo de una suspensión o terminación es obligatorio y viene de una lista cerrada (`no_pago`, `solicitud_cliente`, `incumplimiento`, `fin_acuerdo`, `otro`). No se aceptó texto libre a propósito, porque terminaría en la bitácora, que es de solo inserción y no admite datos personales.

Suspender o terminar no cierra las sesiones del cliente. No hace falta: su token sigue sirviendo para lo que no depende del contrato y el servicio pagado se corta en la petición siguiente.

## ARCOP del usuario definitivo

Hasta HU-27 el rol `cliente` no era titular ARCOP (la ruta le respondía 403). Como el criterio 3 pide que los derechos sigan disponibles siempre, ahora el usuario definitivo crea, consulta, cancela y aporta información a sus solicitudes con las mismas rutas de `/api/arcop`, con contrato vigente o no. La tabla admite un tercer tipo de titular y el `CHECK` sigue exigiendo exactamente uno (escrito con `CASE` para que valga igual en PostgreSQL y en el SQLite de las pruebas).

Una supresión resuelta borra los datos de la **persona**: nombre, correo (queda un marcador irrepetible en el dominio reservado `.invalid`), contraseña y sus textos en las solicitudes; cierra la cuenta y sus sesiones y revoca sus enlaces de activación y recuperación. No toca la empresa ni sus evaluaciones migradas, porque son de la persona jurídica y su conservación la deciden el contrato y HU-25. El titular puede seguir su solicitud con el código público de seguimiento.

## Archivos

| Archivo | Cambio |
|---|---|
| `migrations/versions/a4c7e2f9d1b3_hu30_vigencia_contrato.py` | **Nuevo.** Columnas del contrato en `empresa` (con sus `CHECK`) y `solicitudes_arcop.Usuario_definitivo_id` con el nuevo `CHECK` de un titular. `down_revision = e9b4c2d7a1f6` (HU-17). Tiene `downgrade`. Las empresas existentes quedan `activo`. |
| `app/domain/contrato.py` | **Nuevo.** Estados, situaciones, motivos, operaciones permitidas y cálculo de la vigencia y del plazo de gracia (sin BD). |
| `app/domain/models/empresa.py` | Columnas nuevas, `vigencia()`; `contrato_vigente()` ahora considera también la suspensión y la terminación. |
| `app/application/use_cases/gestionar_contrato.py` | **Nuevo.** Renovar, suspender, reactivar y terminar con bitácora; `contrato_dict()` y `empresas_con_gracia_vencida()` (para HU-25). |
| `app/core/servicio_pagado.py` | Las guardas usan la vigencia; nueva `empresa_con_documentos`; 403 con la situación y el plazo. |
| `app/core/autenticacion.py` | El token del cliente ya no depende del contrato (solo de que la cuenta esté activa). |
| `app/application/use_cases/iniciar_sesion.py` | El login del cliente no se rechaza por contrato; devuelve `contrato` y lo deja en la bitácora. |
| `app/api/routes/admin_clientes.py` | Las cuatro rutas del contrato; las empresas traen `contrato` (estado, situación, motivos, fin de la gracia). |
| `app/api/routes/cliente.py` | `GET /api/cliente/empresa` pasa a ser servicio pagado; nuevo `GET /api/cliente/contrato`. |
| `app/api/routes/formacion.py` | La constancia usa `empresa_con_documentos`. |
| `app/api/routes/arcop.py`, `app/application/schemas/arcop_schemas.py` | El rol `cliente` es titular; las respuestas traen `usuario_definitivo_id`. |
| `app/application/use_cases/gestionar_solicitud_arcop.py`, `app/infrastructure/repositories/solicitud_arcop_repository.py` | Creación, propiedad, listado y supresión del titular cliente. |
| `app/infrastructure/repositories/anonimizacion_repository.py` | `anonimizar_usuario_definitivo()`. |
| `app/domain/models/solicitud_arcop.py`, `app/domain/models/sesion.py` | Columna del titular cliente y `CHECK`; motivo de cierre `supresion_arcop`. |
| `app/infrastructure/repositories/bitacora_repository.py` | Acciones `contrato.*`. |
| `app/core/config.py` | `CONTRATO_GRACIA_DIAS` (0 a 365). |
| `app/core/catalogo_datos_personales.py` | Clasificación T-06 de las columnas nuevas y plazo de conservación del cliente actualizado. |
| `tests/test_hu30_contrato.py` | **Nuevo.** 17 pruebas de reglas puras y 5 de API. |
| `tests/test_hu27_empresa_cliente.py` | La prueba de contrato terminado pasa a la regla nueva y el cliente ya ve `/api/arcop/solicitudes`. |
| `tests/test_hu20_autorizacion.py` | Clasifica las 5 rutas nuevas. |
| `Proyecto/.env.example`, `Proyecto/README.md` | Variable y endpoints nuevos. |

## Cómo probarlo en Docker

```bash
docker compose exec api alembic upgrade head
docker compose exec worker pytest tests/test_hu30_contrato.py tests/test_hu27_empresa_cliente.py tests/test_hu28_sesion.py tests/test_hu26_formacion.py tests/test_hu20_autorizacion.py tests/test_solicitudes_arcop.py tests/test_t06_minimizacion.py -v
docker compose exec worker pytest tests -v -rxX
```

Por Swagger (`/docs`), con un cliente ya activado (flujo de HU-27): con el token del admin llama a `POST /api/admin/empresas/{id}/contrato/suspension` con `{"motivo": "no_pago"}`. Con el token del cliente, `GET /api/cliente/empresa` y `GET /api/formacion/avance` responden 403 `CONTRATO_NO_VIGENTE`, mientras `GET /api/evaluaciones/{id}/informe/pdf` sigue respondiendo y `GET /api/cliente/contrato` muestra la situación. Reactiva, termina con `{"motivo": "fin_acuerdo"}` y descarga la constancia de un módulo completado: funciona hasta la fecha que indica `documentos_disponibles_hasta`. En `GET /api/admin/bitacora?entidad=empresa` quedan todos los cambios.

## Verificación hecha

En este entorno no hubo acceso a PyPI ni a npm, así que **la suite de pytest y la de vitest no se pudieron ejecutar aquí**: córranlas en Docker con los comandos de arriba antes de subir. Sí se ejecutaron las 17 pruebas de reglas puras de `test_hu30_contrato.py` (todas pasan), se compiló todo el Python modificado (`py_compile`) y se revisaron a mano las pruebas de API contra los caminos del código. La migración no se probó contra un PostgreSQL real; conviene hacer `alembic upgrade head`, `downgrade -1` y de nuevo `upgrade head` en el Docker local.

## Pendientes y decisiones abiertas

- **Plazo de gracia** (pendiente del PO): 30 días por defecto en `CONTRATO_GRACIA_DIAS`.
- **Qué pasa después de la gracia** es de HU-25. Esta HU deja la empresa `finalizado`, corta las descargas y entrega la lista con `empresas_con_gracia_vencida()`; no borra nada por su cuenta.
- **Tutor IA y borradores** no existen todavía como rutas. Deben depender de `empresa_con_servicio` (y la descarga de borradores, de `empresa_con_documentos`); `test_rutas_del_servicio_pagado_usan_la_guarda` ya revisa los prefijos `/api/tutor` y `/api/borradores`.
- **Suspensión del contrato durante la gracia de documentos**: con el contrato suspendido el cliente puede descargar sus documentos (son de la empresa y la suspensión no es el fin del contrato). Si el PO prefiere cortarlas, basta con cambiar `documentos_disponibles` en `app/domain/contrato.py`.
- **Panel interno**: el backend del criterio 1 está completo; falta agregar los botones en `frontend-next` (`PanelClientes.tsx`), usando la lista `permitidas` del 409 o la situación del contrato para mostrar solo las operaciones válidas.
- **Bloqueo de cuentas por un admin** sigue sin endpoint (pendiente de HU-27/HU-28).

# HU-25 · Anonimización automática de usuarios temporales vencidos

> Como Oficial de Privacidad de Datos, quiero que los datos de usuarios temporales vencidos se
> anonimicen automáticamente tras un plazo de retención, para cumplir el principio de limitación
> de la conservación de la Ley N.º 21.719.

## Punto de partida

T-06 ya había dejado el mecanismo base: `aplicar_retencion.py` con la regla **R1** (titulares
vencidos → misma anonimización que una supresión ARCOP aprobada), un cron diario en el worker y el
script `scripts/retencion_datos.py`. Le faltaban tres cosas para cumplir esta HU:

1. El plazo solo se podía cambiar editando el `.env` y reiniciando (el Oficial de Privacidad no
   tiene acceso al servidor). Además venía vacío, así que la regla estaba apagada.
2. No quedaba registro de la **ejecución**: solo de cada titular anonimizado. Una corrida sin
   nada que hacer, una que fallaba o una simulación no dejaban rastro, y no se podía demostrar
   que la tarea corre todos los días.
3. Si un titular fallaba, se perdía en el log del worker. Tampoco había nada que impidiera que el
   cron y una corrida manual se ejecutaran al mismo tiempo.

## Criterios de aceptación

| Criterio | Cómo se cumple | Prueba |
|---|---|---|
| 1. Plazo de retención configurable | Tabla nueva `configuracion_retencion` (fila única). El Oficial de Privacidad lo fija en **/admin/retencion** con tres modos: *valor del servidor* (`RETENCION_DATOS_TITULAR_DIAS`, el estado inicial), *plazo propio* (entre `RETENCION_TITULAR_MIN_DIAS`=30 y `RETENCION_TITULAR_MAX_DIAS`=3650 días) o *desactivada*. Cada ejecución lee el plazo vigente: no hay que reiniciar nada. Cada cambio queda en el audit log (`retencion.configuracion_cambiada`) con el valor anterior y el nuevo. Antes de guardar se ve cuántos usuarios se anonimizarían, y si el cambio adelanta la anonimización de alguien se pide confirmación. | `test_plazo_del_panel_manda_sobre_el_entorno_y_cada_cambio_queda_en_el_log`, `test_validacion_del_plazo`, `test_config_valida_limites_hora_y_timeout`, `test_api_panel_configura_previsualiza_simula_y_encola` |
| 2. Tarea programada que reutiliza la anonimización de ARCOP y conserva puntajes | `aplicar_retencion_task` corre todos los días a `RETENCION_HORA_UTC` (03:00 UTC), con su propio timeout (`RETENCION_TIMEOUT_S`=3600 s; el resto de las tareas tiene 300). R1 llama a `AnonimizacionRepository.anonimizar_titular/anonimizar_encuestado`, **la misma rutina de la supresión ARCOP aprobada**. No toca `respuestas.estado_clasificacion*`, `resumen` ni `benchmark`, y las evaluaciones migradas a una empresa (HU-27) quedan fuera. El titular con una solicitud ARCOP abierta espera hasta que se resuelva. | `test_worker_programa_la_tarea_y_la_permite_encolar`, `test_reutiliza_la_anonimizacion_de_arcop`, `test_conserva_puntajes_y_el_benchmark_no_cambia` (el benchmark recalculado después es idéntico al de antes) |
| 3. Cada ejecución queda en el audit log | Un registro `retencion.ejecucion` (categoría *supresión*, así lo ve el Auditor Externo) por corrida, en su propia transacción: origen (`cron`, `manual` o `cli`), si fue simulación, plazos de cada regla, de dónde salió el plazo de titulares, fecha de corte, conteos (anonimizados, en espera por ARCOP, **fallidos**, archivos borrados…), duración y error. Se registra **siempre**, también cuando no hubo nada que anonimizar, cuando se omitió porque había otra en curso (`resultado=omitido`) y cuando falló (`resultado=error`, y el error se relanza). Se mantienen los registros por titular de T-06. Nunca lleva datos personales. | `test_cada_ejecucion_queda_en_el_log_aunque_no_haya_nada`, `test_ejecucion_manual_registra_al_admin_y_la_fecha_de_corte`, `test_dos_ejecuciones_a_la_vez_la_segunda_se_omite_y_queda_registrada`, `test_un_titular_que_falla_no_detiene_al_resto_y_la_ejecucion_queda_con_error`, `test_una_ejecucion_que_se_cae_igual_queda_registrada_y_libera_la_marca` |

## Gestión de riesgos

| Riesgo | Control |
|---|---|
| Un error de tipeo ("1" en vez de "100") anonimiza de un día para otro a todos los vencidos (irreversible) | Mínimo de 30 días en el panel (configurable). Vista previa en vivo y confirmación cuando el cambio adelanta la anonimización. Ejecutar a mano exige marcar "Entiendo que no se puede deshacer" y `confirmar=true` en la API. |
| El cron y una ejecución manual corren a la vez | Marca `ejecucion_desde` tomada con un UPDATE condicional (atómico en PostgreSQL). La segunda se omite y queda registrada. Si el worker muere, la marca vence a los `RETENCION_BLOQUEO_MAX_MIN` (120) minutos. La ejecución manual se encola con un id fijo (`retencion-manual`), así que no se acumulan duplicados en la cola. |
| Una corrida larga se corta a los 300 s del worker | Timeout propio de `RETENCION_TIMEOUT_S` (3600 s) para esta tarea. Cada titular se procesa en su transacción: si se corta, lo hecho queda y el resto se retoma al día siguiente. |
| Un titular que falla pasa inadvertido | `titulares_fallidos` en el resultado y en el registro de la ejecución (`resultado=error`). El panel lo muestra como "Con N fallos". Ese titular queda sin marcar y se reintenta en la próxima ejecución. |
| Anonimizar a quien tiene un derecho ARCOP en trámite | Se omite (T-06) y se cuenta como "en espera por ARCOP abierta" en el panel y en el log. |
| Usuarios temporales sin fecha de expiración que nunca se retienen | El panel muestra cuántos hay ("Sin fecha de vencimiento") para que el Oficial lo vea. |
| El audit log filtra datos personales | El detalle lleva solo plazos, fechas, conteos y códigos; `BitacoraRepository` rechaza correos y claves prohibidas. La tabla nueva no tiene datos personales y está clasificada en el inventario de T-06. |

## Archivos

**Backend** (`Proyecto/backend/`)

| Archivo | Cambio |
|---|---|
| `app/domain/models/configuracion_retencion.py` | **Nuevo.** Modelo de la fila única (fuente del plazo, plazo, fecha de cambio y marca de ejecución en curso). |
| `migrations/versions/e7c3a9f2b6d4_hu25_configuracion_retencion.py` | **Nueva** migración (down: `d4b8e2f6a9c3`, HU-33). Crea la tabla con CHECKs y siembra la fila en modo `entorno`: al migrar no cambia nada hasta que se fije un plazo. |
| `app/application/use_cases/configurar_retencion.py` | **Nuevo.** Plazo vigente, validación, cambio auditado, marca de ejecución y próxima corrida. |
| `app/application/use_cases/aplicar_retencion.py` | Lee el plazo de la BD, toma y libera la marca, registra cada ejecución, cuenta los fallidos y recibe `origen` y `actor`. Con `plazos=` explícitos (pruebas) se comporta como antes. |
| `app/api/routes/admin_retencion.py` | **Nuevo.** `GET/PATCH /api/admin/retencion`, `GET /vista-previa?dias=N`, `POST /simulacion`, `POST /ejecuciones` (encola en el worker), `GET /ejecuciones`. Solo `admin_therion`. |
| `app/worker/tasks.py` | Cron a `RETENCION_HORA_UTC` con timeout propio; la tarea también se puede encolar (ejecución manual con el id del admin). |
| `app/core/config.py` | `RETENCION_TITULAR_MIN_DIAS`, `RETENCION_TITULAR_MAX_DIAS`, `RETENCION_HORA_UTC`, `RETENCION_TIMEOUT_S`, `RETENCION_BLOQUEO_MAX_MIN`, con validación. |
| `app/infrastructure/repositories/bitacora_repository.py` | Acciones `retencion.ejecucion` (supresión) y `retencion.configuracion_cambiada` (modificación). |
| `app/core/catalogo_datos_personales.py` | Tabla nueva clasificada (sin datos personales); el plazo de titulares menciona el panel. |
| `app/main.py`, `app/domain/models/__init__.py` | Registro del router y del modelo. |
| `scripts/retencion_datos.py` | Origen `cli` en el log y aviso si había otra ejecución en curso. |
| `tests/test_hu25_retencion.py` | **Nuevo.** 14 pruebas, 18 casos (criterios 1-3, riesgos y API). |
| `tests/test_hu20_autorizacion.py` | Rutas nuevas clasificadas (`RUTAS_RETENCION`). |

**Frontend** (`Proyecto/frontend-next/`)

| Archivo | Cambio |
|---|---|
| `app/admin/retencion/page.tsx`, `components/admin/PanelRetencion.tsx` | **Nueva** pantalla "Retención de datos": plazo vigente, próxima ejecución, cuántos se anonimizarían hoy y cuántos no tienen vencimiento; cambiar el plazo con vista previa y confirmación; simular y ejecutar; qué se anonimiza y qué se conserva; historial de ejecuciones y de cambios. |
| `lib/admin/retencion.ts` | **Nuevo.** Tipos, llamadas y lógica pura (validación, textos, cuándo confirmar). |
| `lib/servidor/proxyAdmin.ts` | Lista blanca del BFF: rutas de retención y el parámetro `dias`. |
| `components/admin/BarraAdmin.tsx` | Sección "Retención de datos" en la barra del panel. |
| `tests/hu25_retencion.test.ts` | **Nuevo.** Lógica pura y proxy. |

`Proyecto/.env.example`: variables nuevas comentadas.

## Cómo probar

```powershell
docker compose up -d --build                     # aplica la migración (servicio migrate) y reinicia api, worker y web
docker compose exec api alembic current          # debe mostrar e7c3a9f2b6d4 (head)
docker compose run --rm --no-deps api pytest tests/test_hu25_retencion.py tests/test_t06_minimizacion.py tests/test_hu09_audit_log.py tests/test_hu20_autorizacion.py tests/test_hu15_tutor.py -q
cd frontend-next; npx vitest run tests/hu25_retencion.test.ts; cd ..
```

En el navegador: `/admin/login` → **Retención de datos**. Fijar 365 días, **Simular** y revisar el
historial. Desde la consola también se puede simular: `docker compose exec worker python scripts/retencion_datos.py`.

Para ver la anonimización de punta a punta en desarrollo: deja una evaluación con
`usuario_temporal.fecha_expiracion` hace más de 365 días (con `psql`), pulsa **Ejecutar ahora**
y revisa en el historial y en `/api/admin/bitacora?accion=retencion.titular_anonimizado` que se
anonimizó y que su puntaje sigue en la comparativa del rubro.

## Pendientes y decisiones del PO

- **Valor del plazo.** La propuesta de T-06 sigue en pie: 365 días después de vencer el acceso,
  para poder comparar un diagnóstico con el del año siguiente. Lo fija el Oficial de Privacidad
  en el panel; no hace falta tocar el `.env`.
- **Plazos de ARCOP cerradas, eventos de seguridad y tutor** (R2-R4): siguen en variables de
  entorno. Esta HU trata los usuarios temporales; si el PO lo pide, la misma tabla admite más
  columnas sin cambiar el mecanismo.
- **Empresas con el plazo de gracia vencido (HU-29/HU-30):** `empresas_con_gracia_vencida()`
  sigue disponible, pero sus datos son de la persona jurídica y de un contrato. Queda fuera de
  esta HU, que trata los usuarios temporales; conviene abrir una historia propia que defina qué
  se borra (p. ej. los archivos de `documento_empresa`).

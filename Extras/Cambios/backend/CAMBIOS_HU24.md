# HU-24 · Matriz normativa editable con versionado (backend)

> Como Administrador de Therion Labs, quiero editar controles, brechas, rutas y reglas de aplicabilidad con versionado, para actualizar la matriz cuando cambie la normativa sin modificar código.

## Qué cambia

Hasta ahora la matriz vivía en las semillas de las migraciones y el árbol de aplicabilidad (qué controles se preguntan según las respuestas del filtro F1–F7) estaba fijo en `app/application/filters/control_tree.py`. Cualquier cambio normativo obligaba a escribir una migración o tocar código. Con HU-24 el administrador lo hace desde el panel interno, y cada cambio queda versionado y auditado.

El flujo es de borrador y publicación. El admin crea un **borrador**, que es una copia completa de la versión vigente. Sobre él agrega, modifica, retira o restaura controles, brechas, rutas formativas y preguntas de filtro, y fija las reglas de cada control (aplica siempre o se suma con ciertas preguntas del filtro). Mientras edita, el cuestionario sigue funcionando con la versión vigente y nadie más ve los cambios. Cuando está listo, revisa los errores, las advertencias y las diferencias, y **publica** con una etiqueta (por ejemplo `2026.2`) y una nota que describe el cambio normativo. La publicación ocurre en una sola transacción: las tablas del catálogo quedan iguales al borrador, el borrador pasa a `publicada` y la anterior a `reemplazada`.

## Decisiones

**Una versión es un documento completo.** La tabla nueva `matriz_version` guarda, por cada versión, todo el contenido de la matriz en JSON (dimensiones, rutas, brechas, controles con sus reglas y preguntas de filtro) y su huella SHA-256. Así una versión antigua se puede leer tal cual era, sin reconstruirla desde un historial de cambios. La lógica pura (estructura, huella, árbol, edición, validación y diferencias) está en `app/domain/matriz/` y no depende de la BD.

**Las tablas de siempre siguen siendo la fuente del cuestionario.** `matriz_controles`, `catalogo_brechas`, `ruta_formativa` y `preguntas_filtro` reflejan la versión vigente, así que el resto del sistema (respuestas, puntajes, plan formativo, tutor, borradores) no cambió su forma de leer el catálogo. El árbol pasó a la tabla `regla_aplicabilidad` y a la columna `preguntas_filtro.es_compuerta`, y se lee con una caché en memoria (`app/infrastructure/cache/arbol_aplicabilidad.py`).

**Retirar no es borrar.** "Eliminar" un elemento publicado lo deja con `activo=false`: deja de aparecer en el cuestionario, en `/api/controles` y en los catálogos públicos, pero las respuestas, brechas y avances de evaluaciones anteriores lo siguen encontrando por su id. Solo un elemento nuevo que aún no se publica se quita del borrador. Por la misma razón, el código de un control, una brecha o una pregunta de filtro ya publicados no se puede cambiar; para corregirlo se retira y se crea otro. Tampoco se puede retirar algo que otro elemento activo usa (una brecha asignada a un control, una ruta asignada a una brecha, una pregunta de filtro usada por una regla).

**Criterio 2: cada evaluación guarda su versión.** `POST /completar` registra en `evaluacion.matriz_version_id` la versión publicada en ese momento, junto con su texto en `version_matriz` (el que imprime el informe de HU-21). El informe PDF, la ficha, el plan formativo, los borradores de HU-16 y el recálculo por remediación de HU-17 leen los controles, brechas y rutas de **esa** versión (`app/application/informes/carga.py` y `generate_resumen.py`), aunque el admin haya publicado otra después. Las evaluaciones en curso pasan a la versión nueva al publicar, porque todavía no tienen resultado.

**Las versiones publicadas son inmutables.** En PostgreSQL un trigger (`matriz_version_inmutable`) impide cambiar el contenido, la huella o la etiqueta de una versión publicada o reemplazada, y borrarla, también con el rol limitado de la API (HU-09). Solo el borrador se puede editar o descartar.

**Volver atrás sin perder historia.** Se puede crear un borrador desde una versión anterior. Lo que se agregó después entra al borrador como retirado, y al publicarlo se obtiene una versión nueva igual a la antigua, con su propia etiqueta en el historial.

**Edición concurrente.** El borrador lleva un número de `revision` que sube con cada cambio. Si dos administradores editan a la vez, el que envía una revisión vieja recibe `409 BORRADOR_CAMBIADO` y la pantalla recarga la última versión.

**Validación antes de publicar.** Son errores (impiden publicar) un control sin pregunta, dimensión o criticidad, códigos repetidos o con formato inválido, referencias a brechas, rutas o preguntas de filtro retiradas, niveles inválidos u órdenes de filtro repetidos. Son advertencias (se puede publicar igual) un control que nunca se pregunta porque no tiene reglas, un control sin brecha, una brecha sin ruta, una pregunta de filtro que no suma nada, la ausencia de compuerta y una dimensión que queda sin controles. Publicar un borrador igual a la vigente se rechaza con `SIN_CAMBIOS`.

**Caché entre procesos.** Al publicar, el proceso que publicó invalida el árbol y el catálogo de controles en el acto. Los demás procesos (otros workers de uvicorn y el worker arq) comparan cada 15 segundos qué versión está publicada y recargan si cambió.

**Versión inicial.** La migración siembra la versión `MATRIZ_VERSION` (por defecto `2026.1`) con lo que hay hoy en la BD y el árbol de `control_tree.py`, y deja en ella a todas las evaluaciones cerradas: antes de HU-24 la matriz no era editable, así que es la misma con que se respondieron. Su texto de versión se calcula igual que en HU-21, de modo que coincide con lo ya impreso en los informes. Las constantes de `control_tree.py` quedan como semilla y como respaldo cuando la tabla de reglas está vacía (la BD SQLite de las pruebas).

## Criterios de aceptación

| Criterio | Dónde se cumple | Prueba (`tests/test_hu24_matriz_versionada.py`) |
|---|---|---|
| C1. CRUD de matriz, brechas, rutas y árbol (solo admin) | `app/api/routes/admin_matriz.py`, `app/application/use_cases/mantenedor_matriz.py`, `app/domain/matriz/edicion.py` | `test_rutas_hu24_solo_admin`, `test_c1_crud_del_borrador_con_ids_temporales_y_retiro_sin_borrar`, `test_c1_la_edicion_protege_a_las_evaluaciones_anteriores`, `test_c1_arbol_editable_por_control`, `test_c1_el_arbol_como_dato_es_igual_al_que_estaba_en_el_codigo`, `test_c1_c3_flujo_completo_editar_validar_publicar_y_auditar` |
| C2. Las evaluaciones cerradas conservan su versión | `evaluacion.matriz_version_id` (POST `/completar`), `carga.py`, `generate_resumen.py`, trigger de inmutabilidad | `test_c2_la_evaluacion_cerrada_conserva_su_version`, `test_borrador_desde_una_version_anterior_permite_volver_atras` |
| C3. Cada cambio queda en el audit log | Acciones `matriz.borrador_creado`, `matriz.borrador_editado`, `matriz.borrador_descartado`, `matriz.version_publicada` y `matriz.publicacion_rechazada` en `bitacora_repository.py` | `test_c1_c3_flujo_completo_editar_validar_publicar_y_auditar`, `test_el_detalle_del_cambio_es_apto_para_el_audit_log` |

El detalle de cada edición en el audit log dice qué elemento cambió y los campos con su valor anterior y nuevo (recortados a 120 caracteres y sin correos, como exige HU-09). La publicación registra la etiqueta, la huella, la versión que reemplaza, el conteo de cambios y la nota. Los intentos de publicar rechazados también quedan, con su motivo.

## Endpoints nuevos (solo `admin_therion`)

| Método | Ruta | Uso |
|---|---|---|
| GET | `/api/admin/matriz` | Versión vigente, borrador en edición y etiqueta sugerida |
| GET | `/api/admin/matriz/versiones` | Historial con autor, fecha, nota y evaluaciones que usan cada versión |
| GET | `/api/admin/matriz/versiones/{id}` | Contenido, árbol y diferencias con la anterior |
| POST | `/api/admin/matriz/borrador` | Crea el borrador (`desde_version_id` opcional para volver a una anterior) |
| GET | `/api/admin/matriz/borrador` | Contenido, árbol, cambios, errores y advertencias |
| GET | `/api/admin/matriz/borrador/validacion` | Problemas y diferencias antes de publicar |
| POST | `/api/admin/matriz/borrador/descartar` | Descarta el borrador |
| POST | `/api/admin/matriz/borrador/publicar` | `{etiqueta, nota_cambio, revision}` |
| POST | `/api/admin/matriz/borrador/{entidad}` | Crea (`controles`, `brechas`, `rutas`, `preguntas-filtro`) |
| PATCH | `/api/admin/matriz/borrador/{entidad}/{id}` | Modifica |
| POST | `/api/admin/matriz/borrador/{entidad}/{id}/retirar` | Retira (o quita, si es nuevo) |
| POST | `/api/admin/matriz/borrador/{entidad}/{id}/restaurar` | Restaura un retirado |
| PATCH | `/api/admin/matriz/borrador/controles/{id}/aplicabilidad` | `{aplica_siempre, filtros}`: reglas del árbol |

Todas están en la matriz de acceso de HU-20 (`RUTAS_HU24` en `tests/test_hu20_autorizacion.py`).

## Base de datos

Migración `f8c2a6d4e1b7` (sobre `b6d2f9a4c8e1`, HU-16): tablas `matriz_version` y `regla_aplicabilidad`; columnas `activo` en `matriz_controles`, `catalogo_brechas` y `ruta_formativa`; `es_compuerta` en `preguntas_filtro`; `matriz_version_id` en `evaluacion`; índices únicos parciales (una sola publicada, a lo más un borrador) y el trigger de inmutabilidad. Las columnas y tablas nuevas quedaron clasificadas en `app/core/catalogo_datos_personales.py` (T-06, sin datos personales; el contenido JSON y la nota se escanean igual por si alguien pega un correo).

## Archivos

Nuevos: `app/domain/matriz/` (`contenido.py`, `edicion.py`, `validacion.py`, `diferencias.py`), `app/domain/models/matriz_version.py`, `app/infrastructure/repositories/matriz_repository.py`, `app/infrastructure/cache/arbol_aplicabilidad.py`, `app/infrastructure/cache/versiones_matriz.py`, `app/application/use_cases/mantenedor_matriz.py`, `app/api/routes/admin_matriz.py`, `migrations/versions/f8c2a6d4e1b7_hu24_matriz_versionada.py`, `tests/test_hu24_matriz_versionada.py`.

Modificados: `app/application/filters/control_tree.py` (árbol como dato, semilla), `app/infrastructure/repositories/evaluacion_repository.py`, `app/api/routes/filtro.py`, `app/application/use_cases/responder_filtro.py`, `app/application/use_cases/generate_resumen.py`, `app/application/use_cases/completar_evaluacion.py`, `app/application/informes/carga.py`, `app/infrastructure/cache/catalogo_controles.py`, `app/infrastructure/repositories/catalogo_repository.py`, `app/api/routes/controles.py`, `app/infrastructure/repositories/bitacora_repository.py`, `app/core/catalogo_datos_personales.py`, modelos `matriz_control.py`, `catalogo_brechas.py`, `ruta_formativa.py`, `pregunta_filtro.py`, `evaluacion.py` y `__init__.py`, `app/main.py`, `tests/conftest.py`, `tests/test_bordes_na_y_evidencia.py` (sesión falsa usa el árbol semilla), `tests/test_hu20_autorizacion.py`.

## Verificación

Toda la suite en proceso pasa: 827 aprobadas y 8 omitidas (incluidas las 26 de HU-24). La siembra de la migración se probó por separado: crea la versión `2026.1` con el mismo texto de versión que calculaba HU-21, 40 reglas (22 base) y F1 como compuerta, y el árbol resultante es idéntico al de `control_tree.py` en las 128 combinaciones del filtro. El trigger de PostgreSQL se verifica al correr la migración en Docker.

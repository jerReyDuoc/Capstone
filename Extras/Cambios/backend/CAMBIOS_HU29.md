# HU-29 · Historial de evaluaciones, reevaluación y "Mis documentos" (backend)

*Como usuario definitivo de una empresa cliente, quiero consultar el historial de evaluaciones de mi empresa, iniciar una reevaluación y acceder a los documentos generados, para medir la evolución de la madurez de mi organización y mantener ordenada la documentación de cumplimiento.* Prioridad alta, 5 SP.

Hasta ahora el espacio de la empresa (HU-28) solo listaba las evaluaciones migradas desde el autodiagnóstico, con un puntaje calculado como promedio simple y ordenadas por fecha de migración. La empresa no podía volver a evaluarse: la única forma de crear una evaluación era la landing pública, que siempre crea un usuario temporal anónimo. Y los documentos estaban repartidos: el informe PDF se generaba al vuelo en cada descarga, las evidencias no se podían bajar y las constancias solo aparecían en el panel de formación.

HU-29 agrega tres cosas sobre lo que ya existía, sin cambiar las rutas del cuestionario: un historial con su evolución, una reevaluación que nace perteneciendo a la empresa y un lugar único para los documentos, con descarga y eliminación auditadas.

## Criterios de aceptación

| Criterio | Dónde se cumple | Prueba (`tests/test_hu29_historial_documentos.py`) |
|---|---|---|
| 1. "Mis evaluaciones" con todas las evaluaciones de la empresa, incluidas las migradas: fecha, estado, puntaje global y nivel, con gráfico de evolución global y por dimensión | `GET /api/cliente/evaluaciones`. La lógica es pura (`app/application/informes/historial.py`) y la lectura de la BD está en `historial_empresa.py`. Devuelve la tabla (de la más reciente a la más antigua) y las series del gráfico (global y una por dimensión, solo completadas) | `test_historial_con_migrada_y_reevaluaciones`, `test_dimension_que_no_aplica_queda_como_punto_vacio`, `test_api_historial_reevaluacion_y_benchmark` |
| 2. Una evaluación nueva iniciada desde la cuenta pertenece a la empresa, sin usuario temporal. Para el benchmark solo cuenta la evaluación más reciente de cada empresa | `POST /api/cliente/evaluaciones` crea la evaluación con `empresa_id` y origen `empresa`, sin usuario temporal ni clave. Se responde con las rutas de siempre del cuestionario y la sesión del cliente. `UpdateBenchmarkUseCase` cuenta, de cada empresa, solo su evaluación completada de mayor id | `test_api_historial_reevaluacion_y_benchmark`, `test_benchmark_cuenta_solo_la_mas_reciente_de_cada_empresa`, `test_api_sin_contrato_vigente_ve_el_historial_pero_no_reevalua` |
| 3. "Mis documentos" con informes PDF, borradores (HU-16), evidencias y constancias (HU-26), con descarga y eliminación; cada eliminación queda en el audit log | `GET /api/cliente/documentos` y las rutas de descarga y eliminación de `cliente.py` (`documentos_empresa.py`). Cada eliminación registra `documento.eliminado` con el tipo y los ids; cada descarga, `documento.descargado` | `test_api_mis_documentos_descarga_y_eliminacion_auditada`, `test_api_limite_de_informes_y_evaluacion_no_completada` |

## Cómo funciona

**Historial.** El puntaje global de cada evaluación es el promedio de sus dimensiones ponderado por controles evaluados, la misma fórmula de `GET /api/evaluaciones/{id}/resumen` y del informe PDF (antes `/api/cliente/empresa` usaba un promedio simple y podía no coincidir con el panel). El nivel usa los cortes de siempre (inicial, en desarrollo, gestionado, optimizado). Cada fila trae su variación frente a la evaluación completada anterior y marca cuál es la **vigente** (la completada más reciente). Una reevaluación en curso aparece en la tabla pero no en el gráfico: su vista previa no es un resultado definitivo. La fecha de referencia es la de término; como las evaluaciones anteriores a esta HU no la tienen, para ellas se usa la de inicio. La ruta es lectura de resultados, así que responde también sin contrato vigente (igual que el resumen); solo `puede_reevaluar` depende del contrato.

**"La más reciente".** Se define en un solo lugar (`evaluacion_mas_reciente()`) como la evaluación completada de mayor id. Los ids son correlativos y una reevaluación siempre se crea después de las migradas, así que no hace falta comparar fechas (la de migración no existe en las reevaluaciones y la de inicio es solo un día). La usan el benchmark, el historial, el panel de formación y el tutor IA, que antes ordenaban por `fecha_migracion` y no habrían visto la reevaluación.

**Reevaluación.** Solo puede haber una abierta por empresa: si ya existe, la API responde 409 `EVALUACION_EN_CURSO` con su id para retomarla. El caso de uso bloquea la fila de la empresa y, en PostgreSQL, un índice único parcial (`uq_evaluacion_empresa_en_curso`) lo impide también a nivel de BD. Iniciarla es parte del servicio pagado (403 `CONTRATO_NO_VIGENTE` sin contrato vigente) y queda en la bitácora (`evaluacion.reevaluacion_iniciada`). La evaluación se responde con el filtro F1–F7, las respuestas, las evidencias y `/completar` de siempre: `alcance.py` ya dejaba al cliente operar sobre las evaluaciones de su empresa. Sin token una reevaluación responde 401 siempre, incluso con `EXIGIR_TOKEN_EVALUACIONES=false`. Al completarla se registra `evaluacion.completada_empresa`, se guarda `fecha_completado` y su informe PDF se archiva solo en "Mis documentos" (`DOCUMENTOS_ARCHIVAR_AL_COMPLETAR`); si eso falla, `/completar` responde igual y el usuario puede guardarlo a mano.

**Rubro.** La comparativa, el informe y el benchmark toman ahora el rubro de la empresa y, si la evaluación no tiene empresa, el del usuario temporal (`rubro_id_de_evaluacion()`), porque la reevaluación no tiene usuario temporal.

**Mis documentos.** Los informes y los borradores se guardan en una tabla nueva, `documento_empresa`, con el archivo cifrado en reposo (Fernet, subclave `documentos` de `ENTITY_MAP_KEY`), un nombre de descarga que arma el sistema y el SHA-256 del contenido, que se verifica al descargar. Las evidencias y las constancias no se copian: se leen de su tabla. Se descargan y eliminan con contrato vigente, suspendido o en plazo de gracia (`empresa_con_documentos`, HU-30). Lo ajeno responde 404.

| Tipo | Descargar | Eliminar |
|---|---|---|
| Informe PDF | El PDF tal como era al guardarlo. Se guarda al completar una reevaluación o con `POST /api/cliente/documentos/informes`; máximo `DOCUMENTOS_INFORMES_POR_EVALUACION` (5) por evaluación | Borra la fila y el archivo |
| Borrador (HU-16) | Igual que el informe | Igual que el informe |
| Evidencia | Tras la validación, en el disco solo queda su texto anonimizado (HU-06): eso es lo que se descarga. Si el motor de anonimización no estaba activo, el original descifrado. 409 `EVIDENCIA_EN_PROCESO` mientras el worker la valida | Borra el archivo y `datos_extraidos`; marca `fecha_eliminacion`. Conserva la clasificación, los estados y los puntajes, así que el historial sigue explicable y **ningún puntaje cambia** (HU-26: solo cambia con evidencia nueva) |
| Constancia | La ruta de siempre, `/api/formacion/modulos/{ruta_id}/constancia` | Anula el código (`codigo_constancia = NULL`, `fecha_eliminacion_constancia`). El módulo sigue completado; la descarga responde 404 `CONSTANCIA_ELIMINADA` |

El registro de la bitácora nunca lleva el contenido ni el nombre que subió el usuario: solo el tipo, los ids, el origen y el estado. El archivo se borra del disco **después** del commit, para que una transacción fallida no deje un documento listado sin archivo.

**Para HU-16.** La tabla ya admite el tipo `borrador`. HU-16 solo tiene que llamar a `guardar_documento(db, empresa_id=…, tipo="borrador", nombre=…, contenido=…, mime_type=…, actor=…)` y hacer commit; el borrador aparece en "Mis documentos" con descarga y eliminación sin tocar nada más. El nombre solo admite `[A-Za-z0-9_.-]`.

## Endpoints nuevos (rol `cliente`)

| Método | Ruta | Guarda | Respuesta |
|---|---|---|---|
| GET | `/api/cliente/evaluaciones` | `cliente` | Historial, evolución, `puede_reevaluar`, `servicio_habilitado` |
| POST | `/api/cliente/evaluaciones` | servicio pagado | 201 `{evaluacion_id, estado_progreso, origen, fecha_inicio, empresa_id}`; 409 `EVALUACION_EN_CURSO` |
| GET | `/api/cliente/documentos` | documentos | `{informes, borradores, evidencias, constancias, documentos_disponibles_hasta}` |
| POST | `/api/cliente/documentos/informes` | documentos | `{evaluacion_id}` → 201; 404, 409 `EVALUACION_NO_COMPLETADA`, `LIMITE_INFORMES`, 503 `PDF_NO_DISPONIBLE` |
| GET | `/api/cliente/documentos/{id}/descarga` | documentos | Archivo (`Content-Disposition: attachment`) |
| DELETE | `/api/cliente/documentos/{id}` | documentos | 204 |
| GET | `/api/cliente/documentos/evidencias/{id}/descarga` | documentos | `text/plain` (anonimizada) u original |
| DELETE | `/api/cliente/documentos/evidencias/{id}` | documentos | 204; 409 `EVIDENCIA_EN_PROCESO` |
| DELETE | `/api/cliente/documentos/constancias/{ruta_id}` | documentos | 204 |

`POST /api/evaluaciones/{id}/completar` agrega `documento_id` a su respuesta cuando la evaluación es de una empresa. `GET /api/cliente/empresa` agrega `origen` y `fecha_completado` a cada evaluación y las ordena de la más reciente a la más antigua.

## Archivos

| Archivo | Cambio |
|---|---|
| `migrations/versions/f1d6b3a8c2e4_hu29_historial_documentos.py` | **Nuevo.** `evaluacion.origen` admite `empresa`, `evaluacion.fecha_completado`, índice único parcial (solo PostgreSQL), tabla `documento_empresa`, `evidencias.fecha_eliminacion` y `avance_formativo.fecha_eliminacion_constancia`. `down_revision = c3d9a1f7e5b8` (HU-18). Tiene `downgrade`. Nada cambia para los datos existentes |
| `app/domain/models/documento_empresa.py` | **Nuevo.** Modelo `DocumentoEmpresa` (registrado en `models/__init__.py`) |
| `app/domain/models/evaluacion.py` | `ORIGEN_EMPRESA`, `fecha_completado`, `es_de_empresa` |
| `app/domain/models/evidencia.py`, `formacion.py` | Columnas de eliminación |
| `app/application/informes/historial.py` | **Nuevo.** Lógica pura: puntaje global, historial, series del gráfico, selección del benchmark y mediana |
| `app/application/use_cases/historial_empresa.py` | **Nuevo.** Historial desde la BD, `IniciarReevaluacionUseCase`, `evaluacion_mas_reciente()`, `rubro_id_de_evaluacion()` |
| `app/application/use_cases/documentos_empresa.py` | **Nuevo.** `guardar_documento()` (también para HU-16), `archivar_informe()`, `tras_completar()` y `DocumentosEmpresa` (listar, descargar, eliminar) |
| `app/application/use_cases/update_benchmark.py` | Solo la más reciente de cada empresa; rubro de la empresa; una sola consulta de puntajes y la mediana en Python |
| `app/application/use_cases/completar_evaluacion.py` | Fija `fecha_completado` |
| `app/application/use_cases/formacion_empresa.py` | Usa `evaluacion_mas_reciente()`; 404 `CONSTANCIA_ELIMINADA` |
| `app/application/informes/carga.py`, `app/api/routes/reportes.py` | Rubro de la empresa en el informe y la comparativa; `/completar` llama a `tras_completar()` |
| `app/api/routes/cliente.py` | Las nueve rutas de HU-29 |
| `app/api/routes/evaluaciones.py`, `app/core/alcance.py` | Una reevaluación sin token siempre responde 401 y no aparece en el listado sin token |
| `app/infrastructure/llm/factory.py` | `crear_storage_documentos()` |
| `app/infrastructure/repositories/bitacora_repository.py` | Acciones `evaluacion.reevaluacion_iniciada`, `evaluacion.completada_empresa`, `documento.generado`, `documento.descargado`, `documento.eliminado` |
| `app/core/config.py` | `DOCUMENTOS_INFORMES_POR_EVALUACION` (5) y `DOCUMENTOS_ARCHIVAR_AL_COMPLETAR` (true) |
| `app/core/catalogo_datos_personales.py` | Columnas nuevas clasificadas (T-06) |
| `tests/test_hu29_historial_documentos.py` | **Nuevo.** 7 pruebas de lógica pura y 4 de API en proceso |
| `Proyecto/README.md` | Endpoints y pantallas de HU-29 |

## Cómo probar

```powershell
docker compose exec api alembic upgrade head
docker compose exec worker pytest tests/test_hu29_historial_documentos.py -v
docker compose exec worker pytest tests -v -rxX
```

En este entorno solo se pudieron correr las pruebas de lógica pura (6 pasan; la que compara constantes con el modelo y las 4 de API necesitan SQLAlchemy y se omitieron). **Corran la suite completa en Docker antes de subir**, sobre todo `test_hu19_encuesta_publica.py` (benchmark), `test_hu26_formacion.py`, `test_hu27_empresa_cliente.py`, `test_hu30_contrato.py` y `test_t06_minimizacion.py`.

## Decisiones para revisar con el PO

1. **Eliminar una evidencia no borra su resultado.** Se borra el archivo, pero la clasificación y los puntajes quedan, para que el historial de madurez no cambie al ordenar documentos. Si el PO prefiere que eliminar una evidencia la quite también del cálculo, habría que recalcular el resumen, lo que contradice la regla de HU-26.
2. **Eliminar una constancia anula su código y no se vuelve a emitir.** El módulo sigue completado. Si se quiere permitir reemitirla con un código nuevo, es una ruta pequeña sobre la misma tabla.
3. **Informes guardados como foto.** Cada informe archivado es el PDF de ese momento (por ejemplo, antes de una remediación). El panel sigue generando el informe al día cuando se descarga desde los resultados.
4. **Retención (HU-25).** Al vencer el plazo de gracia, la retención deberá borrar también los archivos de `documento_empresa`; `empresas_con_gracia_vencida()` ya entrega las empresas.

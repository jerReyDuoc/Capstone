# HU-26 · Avance de los módulos formativos y HU-17 · Re-evaluación con evidencia (backend)

*HU-26. Como Usuario definitivo de una empresa cliente, quiero realizar los módulos recomendados en el plan formativo y registrar el avance, para cerrar las brechas detectadas mediante formación y demostrar el progreso alcanzado.* Prioridad media · 5 SP.

*HU-17. Como Evaluador de Madurez de IA, quiero cargar archivos de evidencia para que el Agente IA los analice y re-evalúe el control, para actualizar automáticamente el puntaje de madurez y cerrar la brecha sin repetir el autodiagnóstico.* Prioridad alta · 5 SP.

Las dos historias van juntas porque el tercer criterio de HU-26 depende de HU-17: completar un módulo marca sus brechas con "formación hecha", pero el puntaje solo cambia con evidencia nueva. La parte del frontend y la especificación de diseño están en `Extras/Cambios/frontend/CAMBIOS_HU26_HU17.md`.

## Cómo funciona

**Recorrido de un módulo (HU-26).** Un módulo del plan formativo de HU-12 es una ruta del catálogo (`ruta_formativa`). La migración nueva le da a cada ruta sus lecciones (`leccion_formativa`, una por cada línea de `contenidos`, con texto y material de apoyo como placeholders, según la decisión del PO del 26-oct) y una actividad de verificación (`pregunta_verificacion`, tres preguntas de selección única por ruta, escritas a partir de sus objetivos). Si el equipo agrega una ruta sin lecciones, el sistema las arma igual desde `contenidos`, así nunca queda un módulo vacío. La respuesta correcta nunca sale por la API: el servidor entrega las opciones con un id y en un orden estable por empresa, y corrige él.

El cliente abre el módulo, ve cada lección y la marca como vista. La primera lección vista crea la fila de avance de la empresa (`avance_formativo`, en curso). Con todas las lecciones vistas se habilita la actividad: con 70 de 100 o más (configurable) el módulo queda **completado**, con su fecha y un código de constancia único (`CF-XXXX-XXXX`, sin caracteres ambiguos). Reprobar suma un intento y dice qué preguntas fallaron, pero no la respuesta correcta; las explicaciones solo se muestran al aprobar. Hay un máximo de 5 intentos por empresa, módulo y día (en Redis), para que adivinar no sea una estrategia. La constancia es un PDF de una página (reportlab) con la empresa, el módulo, su dimensión, nivel, horas y modalidad, la fecha, la nota y el código.

**Avance de la empresa (HU-26 C2).** `GET /api/formacion/avance` cruza el plan de la evaluación con los avances de la empresa: módulos sin empezar, en curso y completados, el porcentaje por dimensión y por nivel (módulos completados sobre el total), las horas hechas y qué brechas ya tienen la formación completa. Si una brecha se cierra con evidencia, su módulo deja de estar en el plan, pero si la empresa ya lo había hecho sigue contando (aparece con `en_plan: false`, motivo `historial`): cerrar una brecha nunca baja el avance.

**Remediación con evidencia (HU-17).** Desde las brechas, el cliente sube un PDF, DOCX o TXT para un control con brecha de una evaluación completada de su empresa, dice a qué estado llegó (cumplido o parcialmente cumplido, siempre mejor que el actual) y, si quiere, explica qué cambió. La API valida el tipo por su **contenido** (no solo la extensión), el tamaño, que no haya otra evidencia del mismo control en análisis y el límite diario de la empresa; la justificación pasa por la capa anti prompt-injection y se guarda anonimizada (HU-06), igual que el nombre del archivo. El archivo queda cifrado y el worker lo procesa como siempre, con estas diferencias para la remediación:

- extrae el texto real del PDF (pypdf) o del DOCX (librería estándar) antes del NER y del LLM, y rechaza sin gastar cuota un archivo sin texto legible (un PDF escaneado);
- verifica localmente los términos del control (`terminos_control`: los encontrados, los que faltan y la cobertura) y los guarda para mostrarlos;
- **RAG local**: si el documento no cabe en el prompt (más de `MAX_CHARS_EVIDENCIA_LLM`), lo divide en pasajes y recupera con BM25 los que más hablan de lo que pide el control (calculado en el servidor, sin servicios externos); esos pasajes, en su orden original, son el contexto del LLM. Antes el LLM veía solo las primeras páginas, y una política de 30 páginas que trataba el tema en la página 20 no se podía validar. Aplica también al cuestionario; el texto que cabe completo llega igual que antes;
- el LLM recibe lo que la empresa declaró en la remediación, no la declaración original del cuestionario, que se conserva;
- **una evidencia nueva nunca baja un control**: si el LLM no tiene certeza, o clasifica igual o peor que el estado vigente, la evidencia queda rechazada y el control no cambia; si se bloquea por seguridad, también se rechaza sin tocar la respuesta;
- si el control mejora, se sincroniza la brecha y se **recalcula el resumen** (puntaje general y radar) en el mismo proceso; antes de y después queda en la evidencia (`estado_previo`, `estado_resultante`) y en la bitácora.

La extracción de texto también arregla el hallazgo de la revisión del backlog sobre el cuestionario normal: antes un PDF o DOCX llegaba ilegible al LLM (T-SM-54). La lista blanca de tipos y el tamaño máximo (T-SM-55) se aplican ahora a toda evidencia, también en el cuestionario. El texto plano se sigue leyendo exactamente igual que antes.

**Punto único para HU-30.** Todas las rutas del servicio pagado dependen de `empresa_con_servicio` en `app/core/servicio_pagado.py`, y la decisión de si la empresa puede usarlo vive solo en `servicio_habilitado()`. Hoy es "contrato vigente", lo mismo que exige el login. Cuando HU-30 agregue suspensión, renovación o plazo de gracia, basta con cambiar esa función: las rutas responden 403 `CONTRATO_NO_VIGENTE` sin cambios. Hay una prueba que lo demuestra (`test_api_solo_el_cliente_con_servicio_activo`).

## Criterios de aceptación

| Criterio | Dónde se cumple | Prueba |
|---|---|---|
| HU-26 C1. Con contrato vigente cada módulo del plan se recorre: contenidos, material de apoyo (placeholders) y actividad de verificación al final | `app/core/servicio_pagado.py`, `GET /api/formacion/modulos/{id}`, `POST …/lecciones/{orden}/vista`, `POST …/verificacion`; contenido sembrado en la migración | `test_api_recorrido_completo_avance_constancia_y_puntaje_intacto`, `test_api_solo_el_cliente_con_servicio_activo`, `test_la_actividad_publica_no_revela_la_respuesta…`, `test_corregir_aprueba_con_el_umbral…` |
| HU-26 C2. El avance queda en la empresa (iniciados, completados y % por dimensión y nivel) y se ve en el panel de formación | Tabla `avance_formativo` (única por empresa y módulo); `resumir_avance()`; `GET /api/formacion/avance` y `/api/admin/empresas/{id}/formacion` | `test_avance_por_modulo_dimension_y_nivel`, `test_cerrar_una_brecha_no_baja_el_avance`, prueba de API |
| HU-26 C3. Al completar se registra la fecha y se descarga una constancia; las brechas muestran la formación hecha y el puntaje solo cambia con evidencia nueva | `fecha_completado`, `codigo_constancia`, `GET …/constancia`; `brechas[].formacion_completada`; el resumen no se toca | `test_constancia_pdf_de_una_pagina_con_el_codigo`, `test_brechas_del_modulo_completado_muestran_formacion_hecha`, la prueba de API compara el resumen antes y después |
| HU-17 C1. Carga de archivos (PDF, DOCX, TXT) en la vista de remediación | `POST /api/remediacion/respuestas/{id}/evidencias`, `validar_archivo()` | `test_detecta_pdf_docx_y_txt…`, `test_rechaza_lo_que_no_es_pdf_docx_o_txt`, `test_api_cuestionario_tambien_rechaza_tipos_no_admitidos` |
| HU-17 C2. Análisis RAG/NER local para verificar términos del control | `extraer_texto()` antes del NER (HU-06), `terminos_control()` y `recuperar_fragmentos()` (RAG local con BM25 sobre los términos del control) | `test_extrae_el_texto_real_de_pdf_y_docx`, `test_terminos_del_control_se_verifican_localmente`, `test_rag_local_recupera_los_pasajes_del_control_en_documentos_largos` |
| HU-17 C3. Actualización del estado del control y recálculo del puntaje global y del radar | `ProcessEvidenceUseCase._decidir_remediacion` y `_cerrar_remediacion` → `GenerateResumenUseCase` | `test_worker_la_remediacion_solo_mejora_y_recalcula`, `test_api_remediacion_actualiza_el_control_y_el_puntaje` |

## Archivos

| Archivo | Cambio |
|---|---|
| `migrations/versions/d6e1a4c8f2b5_hu26_hu17_formacion_remediacion.py` | **Nuevo.** Tablas `leccion_formativa`, `pregunta_verificacion`, `avance_formativo`; columnas de remediación en `evidencias`; contenido semilla (48 lecciones y 36 preguntas para las 12 rutas). `down_revision = f3a8d1c6e4b2` (HU-28). Tiene `downgrade`. |
| `app/domain/models/formacion.py` | **Nuevo.** `LeccionFormativa`, `PreguntaVerificacion`, `AvanceFormativo`, `EstadoAvance`. |
| `app/domain/models/evidencia.py`, `__init__.py` | `origen`, `estado_declarado`, `justificacion_remediacion`, `estado_previo`, `estado_resultante`, `terminos_control`; registro de los modelos nuevos. |
| `app/application/formacion/logica.py` | **Nuevo.** Lógica pura: lecciones, actividad pública, corrección, código de constancia y resumen del avance. |
| `app/application/formacion/constancia_pdf.py` | **Nuevo.** Constancia PDF. |
| `app/application/use_cases/formacion_empresa.py` | **Nuevo.** Recorrido, avance, verificación y constancia, con bitácora. |
| `app/application/evidencias/archivos.py` | **Nuevo.** Lista blanca por contenido, extracción de texto PDF/DOCX/TXT y términos del control. |
| `app/application/use_cases/remediacion.py` | **Nuevo.** Listado de controles con brecha, subida y detalle de la remediación. |
| `app/application/use_cases/process_evidence.py` | Extracción de texto, términos del control, reglas de la remediación y recálculo del resumen. |
| `app/application/use_cases/upload_evidence.py` | `validar_archivo()`: tamaño máximo y solo PDF/DOCX/TXT (415/413). |
| `app/application/informes/analisis.py` | Cada brecha del plan lleva su `respuesta_id` (para enlazar con la remediación). |
| `app/api/routes/formacion.py`, `remediacion.py` | **Nuevos.** Rutas `/api/formacion` y `/api/remediacion`. |
| `app/api/routes/admin_clientes.py` | `GET /api/admin/empresas/{id}/formacion`. |
| `app/core/servicio_pagado.py` | **Nuevo.** Punto único del acceso al servicio pagado (HU-30). |
| `app/worker/tasks.py` | Inyecta el recálculo y la auditoría de la remediación. |
| `app/infrastructure/repositories/bitacora_repository.py` | Acciones `formacion.*` y `remediacion.*`. |
| `app/core/config.py` | `FORMACION_UMBRAL_APROBACION`, `FORMACION_INTENTOS_DIA`, `EVIDENCIA_MAX_MB`, `REMEDIACION_EVIDENCIAS_DIA`, `EVIDENCIA_MIN_CARACTERES` con validaciones. |
| `app/core/catalogo_datos_personales.py` | Clasificación T-06 de las tablas y columnas nuevas (la justificación de remediación es texto libre anonimizado). |
| `app/main.py` | Registra los routers nuevos. |
| `requirements.txt` | `pypdf` (hay que reconstruir api y worker). |
| `tests/test_hu26_formacion.py`, `tests/test_hu17_remediacion.py` | **Nuevos.** 22 pruebas (lógica, PDF, RAG, worker y API). |
| `tests/test_hu20_autorizacion.py` | Clasifica las 9 rutas nuevas en la matriz de HU-20. |
| `tests/test_bordes_na_y_evidencia.py` | La prueba de evidencia muy larga acepta el recorte por pasajes del RAG (≤ máximo). |
| `Proyecto/.env.example`, `Proyecto/README.md` | Variables, endpoints y páginas nuevas. |

## Variables de entorno

| Variable | Por defecto | Uso |
|---|---|---|
| `FORMACION_UMBRAL_APROBACION` | `70` | Nota mínima para aprobar la actividad. |
| `FORMACION_INTENTOS_DIA` | `5` | Intentos por empresa, módulo y día. |
| `EVIDENCIA_MAX_MB` | `10` | Tamaño máximo de una evidencia (el BFF corta en 12 MB). |
| `REMEDIACION_EVIDENCIAS_DIA` | `20` | Evidencias de remediación por empresa y día. |
| `EVIDENCIA_MIN_CARACTERES` | `40` | Texto mínimo para enviar una remediación al LLM. |

## Cómo aplicarlo y probarlo en Docker

1. Descomprime el zip **sobre la raíz del repo** (respeta `Proyecto/` y `Extras/`).
2. `docker compose up -d --build` (api y worker necesitan `pypdf`) y `docker compose exec api alembic upgrade head`. Si tu head no es `f3a8d1c6e4b2`, cambia `down_revision` en la migración nueva.
3. `docker compose exec worker pytest tests -v -rxX`.

Por Swagger, con un cliente ya activado (flujo de HU-27/28): `GET /api/formacion/avance`, abre un módulo, marca sus lecciones, responde la actividad y descarga la constancia; luego compara `GET /api/evaluaciones/{id}/resumen`: no cambió. Para HU-17, `GET /api/remediacion/evaluaciones/{id}`, sube un PDF a un control no cumplido y, cuando el worker termine, consulta `GET /api/remediacion/evidencias/{id}`: si el LLM lo aceptó, el control y el puntaje cambiaron.

## Verificación hecha

En este entorno no hay PyPI, pero se armaron FastAPI 0.115, SQLAlchemy 2.0.36, aiosqlite, pydantic-settings, Alembic y el resto desde sus repositorios de GitHub, así que **la suite completa corrió aquí: 576 aprobadas y 9 omitidas, sin fallas** (las omitidas son las de modo live y spaCy real). Las 22 pruebas nuevas corren completas. `test_bordes_na_y_evidencia.py::test_evidencia_muy_larga_se_trunca_antes_del_llm` se ajustó: un texto largo ya no se corta exactamente en el máximo, sino que se reduce a sus pasajes más relevantes sin pasarlo, incluidas las de API en proceso. La migración se probó con Alembic sobre SQLite (los esquemas previos no corren en SQLite, así que se partió del esquema de HU-28 y se hizo stamp): upgrade, downgrade y un segundo upgrade; siembra 48 lecciones y 36 preguntas, y las evidencias existentes quedan con `origen = cuestionario`. **No se probó en PostgreSQL**: corran `alembic upgrade head` y `alembic downgrade -1 && alembic upgrade head` en su Docker antes de subir.

## Decisiones para validar con el PO

1. **Contenido de los cursos**: las lecciones y el material son placeholders (decisión del 26-oct); las 36 preguntas están escritas a partir de los objetivos de cada ruta y conviene que Therion Labs las revise. Se editan en las tablas o en la migración.
2. **Nota mínima 70 y 5 intentos por día**.
3. **Un avance por empresa**: si la empresa tiene una evaluación nueva, los módulos ya completados siguen contando.
4. **La remediación nunca baja un control** y solo acepta estados mejores que el actual. Si el PO quiere que una evidencia pueda bajarlo (por ejemplo, una política derogada), es un cambio en `_decidir_remediacion`.
5. **RAG en HU-17 C2**: se implementó como recuperación local de los pasajes de la evidencia más relevantes para el control (BM25, sin embeddings ni servicios externos, así ningún texto sale del servidor antes del NER). Si el PO quiere búsqueda semántica con embeddings o recuperar también sobre la normativa, es una ampliación de `recuperar_fragmentos()`.
6. **HU-30**: las reglas del contrato siguen pendientes; ver `servicio_pagado.py`.

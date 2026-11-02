# HU-21 · Informe del autodiagnóstico en PDF (backend)

> Como Director de Riesgos / Representante Legal, quiero descargar el informe del autodiagnóstico en PDF con puntajes por dimensión, brechas priorizadas y rutas recomendadas, para presentar los resultados al directorio o a un auditor.

## Qué cambia

El informe PDF ya existía desde HU-11/HU-12, pero estaba pensado para el propio encuestado: no se podía identificar una copia suelta, no decía con qué matriz se calcularon los puntajes y el aviso legal era una sola línea al final. HU-21 lo convierte en un documento que se puede dejar en un acta de directorio o entregar a un auditor.

La **portada** ahora tiene una ficha de identificación con el código de evaluación, la fecha de la evaluación, la fecha de emisión, la versión de la matriz, la versión del aviso legal y el rubro. Debajo va el **aviso legal completo** (HU-04), con la delimitación de responsabilidad conforme a la Ley N.º 21.719 y la versión que aceptó el encuestado antes de responder. Luego vienen los **5 puntajes de HU-03** (Global, Gobernanza de IA, Gestión de Riesgos, Protección de Datos y Uso Responsable), cada uno con su barra de 0 a 100 y la meta punteada, y un resumen de brechas y rutas. Las páginas siguientes mantienen la comparativa, las brechas priorizadas (HU-11) y el plan formativo (HU-12).

En el **pie de cada página** va el aviso legal resumido, el código de evaluación, la versión de la matriz y "Página X de Y", para que una hoja suelta no pierda su contexto. El informe cierra con un bloque de **identificación y verificación** que imprime una huella de los resultados.

## Decisiones

**Código de evaluación.** Tiene la forma `CIA-2026-000123-6`: año de inicio, número de la evaluación y un dígito verificador módulo 11 (el mismo algoritmo del RUT). No necesita columna nueva, es estable entre descargas y permite detectar un código mal transcrito.

**Versión de la matriz.** Es la etiqueta `MATRIZ_VERSION` (variable de entorno, por defecto `2026.1`) más los 8 primeros caracteres de un SHA-256 del contenido de la matriz de controles, por ejemplo `2026.1+3fa9c2d1`. Así, si alguien modifica una pregunta, su criticidad o su dominio y olvida subir la etiqueta, la huella cambia igual. `POST /completar` la guarda en la nueva columna `evaluacion.version_matriz`, de modo que el informe dice con qué matriz se calcularon los puntajes aunque la matriz cambie después. Las evaluaciones completadas antes de esta migración quedan en NULL: su informe imprime la versión vigente y lo aclara, sin inventar un dato que no se registró.

**Los 5 puntajes siempre.** El informe toma las dimensiones del catálogo de la BD (tabla `dominio`), todas, y las ordena como HU-03 (Global, Gobernanza de IA, Gestión de Riesgos, Protección de Datos, Uso Responsable); no inventa dimensiones que esa instalación no tiene. Una dimensión con todas sus preguntas N/A antes desaparecía del resultado (observación de HU-03, tarea T-SM-12); en el informe aparece como "Sin preguntas aplicables".

**Inventarios de control.** La columna `evaluacion.version_matriz` quedó clasificada en `app/core/catalogo_datos_personales.py` (sin datos personales, T-06) y la ruta `/informe/ficha` en la matriz de acceso de HU-20, con el mismo alcance que el PDF.

**Huella de los resultados.** Es un SHA-256 de los puntajes, la lista completa de brechas y las rutas del plan, sin la fecha de emisión. Dos descargas de la misma evaluación dan la misma huella; si alguien edita una copia, deja de coincidir con la que entrega la API. Un filtro de brechas en la descarga no la altera.

**Un solo armado.** El informe se construía en dos lugares (descarga y "Mis documentos"). Ahora `app/application/informes/informe.py` lo arma para la descarga, el correo, el PDF archivado y la ficha, así todos llevan el mismo código y la misma huella.

**Texto del aviso.** Es un borrador técnico (tarea T-SM-14) en `ficha.py`, con su propia versión (`2026-11-v1`) para no obligar a los encuestados a aceptar de nuevo el aviso de la encuesta. Lo debe validar el PO con Therion Labs y el docente; si cambia, se sube la versión y queda impresa en cada informe.

## Criterios de aceptación

| Criterio | Dónde se cumple | Prueba |
|---|---|---|
| C1. El PDF se genera con los datos de la API | `GET /informe/pdf` arma el PDF en el servidor desde la BD (`carga.py` → `informe.py` → `pdf_informe.py`); la página del panel solo lo descarga | `test_api_completar_registra_la_version_de_la_matriz_y_el_pdf_la_imprime` |
| C2. Aviso legal en la primera página y en el pie | Caja de aviso en la portada; `_Lienzo._pie()` en todas las páginas | `test_aviso_legal_completo_en_la_primera_pagina`, `test_aviso_legal_y_pagina_x_de_y_en_el_pie_de_todas_las_paginas` |
| C2. Los 5 puntajes (HU-03), brechas (HU-11) y rutas (HU-12) | `cinco_puntajes()`; secciones de brechas y plan | `test_siempre_cinco_puntajes_en_el_orden_de_hu03`, `test_dimension_sin_preguntas_aplicables_se_informa_y_no_desaparece`, `test_pdf_trae_los_5_puntajes_las_brechas_y_las_rutas` |
| C3. Fecha, código de evaluación y versión de la matriz | Ficha de la portada; `evaluacion.version_matriz` | `test_codigo_de_evaluacion_con_anio_numero_y_digito`, `test_codigo_mal_transcrito_se_detecta_por_el_digito`, `test_huella_de_la_matriz_no_depende_del_orden_y_cambia_con_el_contenido`, `test_portada_del_pdf_lleva_fecha_codigo_y_version`, `test_evaluacion_antigua_usa_la_version_vigente_y_lo_avisa` |

Además se verifica que el PDF y la ficha no muestren códigos internos (regla del 29-10) y que la huella sea estable entre descargas y sensible a los resultados.

## Endpoint nuevo

`GET /api/evaluaciones/{id}/informe/ficha` devuelve en JSON lo que imprime la portada: código, fechas, versión de la matriz (y si quedó registrada), aviso legal, los 5 puntajes, el resumen de brechas (total, por severidad y las 3 principales, sin códigos), el resumen de rutas, la huella y el nombre del archivo. Tiene el mismo alcance que el PDF (encuestado dueño, usuario definitivo de la empresa o admin) y responde 404 `SIN_RESULTADOS` si la evaluación no tiene resumen.

## Archivos

Nuevos: `app/application/informes/ficha.py` (lógica pura: código, versión, 5 puntajes, huella y aviso), `app/application/informes/informe.py` (armado único del informe y JSON de la ficha), `migrations/versions/e5a9c3f1b7d2_hu21_version_matriz_evaluacion.py`, `tests/test_hu21_informe_pdf.py`.

Modificados: `app/application/informes/pdf_informe.py` (portada, pie, verificación), `app/application/informes/carga.py` (`version_matriz_vigente()` y datos de la ficha), `app/api/routes/informes.py` (ruta `/informe/ficha`), `app/application/use_cases/completar_evaluacion.py` (guarda la versión), `app/application/use_cases/documentos_empresa.py` (usa el armado único), `app/domain/models/evaluacion.py` (columna `version_matriz`), `app/core/config.py` (`MATRIZ_VERSION`), `Proyecto/README.md`.

## Configuración

`MATRIZ_VERSION` (opcional, por defecto `2026.1`, máximo 30 caracteres). Súbela cuando se publique una matriz de controles nueva. No hay otras variables nuevas.

## Pendientes

La validación del texto del aviso legal por el PO (T-SM-14). Queda como mejora registrar en el audit log (HU-09) cada descarga del informe, si el PO lo considera necesario para la trazabilidad frente al auditor.

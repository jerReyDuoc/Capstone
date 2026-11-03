# HU-16 · Borradores adaptados de documentos de cumplimiento (backend)

*Como Gestor de Riesgos e IA, quiero que el Agente IA genere borradores adaptados de políticas, avisos y procedimientos normativos, para acelerar la creación de la documentación legal e institucional requerida para mitigar las no-conformidades.*

Hasta ahora la plataforma le decía a la empresa qué le faltaba (brechas, plan formativo, tutor) pero no le entregaba el documento que muchas de esas brechas piden: la política de IA aprobada, el aviso de privacidad o la evaluación de impacto. HU-29 ya había dejado preparada la tabla `documento_empresa` con el tipo `borrador`; esta historia agrega lo que faltaba para llegar ahí: las plantillas, la generación adaptada a la evaluación, la revisión con edición y la consolidación.

## Cómo se arma un borrador

La decisión central fue que **el documento lo arma el backend y el LLM solo adapta partes de él**. Un LLM que escribe una política entera desde cero inventa artículos, debilita obligaciones y cambia de estructura en cada intento; para un documento legal eso es inaceptable. Por eso cada plantilla (`app/application/borradores/plantillas.py`) es una lista de cláusulas con su texto base, y cada cláusula declara la dimensión del modelo de madurez a la que aporta, los controles de la matriz que ayuda a cerrar, una *medida prioritaria* para cuando la empresa tiene brecha en esos controles y si el Agente IA puede reescribirla. Las cláusulas de identificación del responsable, derechos de los titulares y aprobación quedan fijas: su texto es el que exige la ley y no se negocia con el modelo.

`generador.py` toma la plantilla y el contexto de la evaluación más reciente de la empresa (la misma regla del panel de formación y del tutor) y produce un Markdown con encabezado de borrador, tabla de control de versiones, las cláusulas numeradas, el fundamento normativo de cada una, el **Anexo A** (puntaje y nivel por dimensión, brechas abiertas y qué secciones del documento las abordan) y el **Anexo B** (plan de implementación con las brechas que el documento ayuda a cerrar, por prioridad). El fundamento no lo escribe nadie a mano: se toma de `framework_fuente` y `articulo_referencia` de `matriz_controles`, igual que hace el tutor desde su v1.1. La razón social, el RUT y el rubro los completa el backend; el LLM nunca los ve. Los códigos internos de controles y brechas no aparecen en ningún lugar del documento (regla de interfaz del 29-oct), y hay una prueba que lo vigila.

Los datos que la empresa debe aportar quedan como marcadores `[COMPLETAR: …]`. El usuario los reemplaza al revisar y, si intenta consolidar con marcadores pendientes, el backend responde 409 `CAMPOS_PENDIENTES` hasta que lo confirme.

## El Agente IA

Se agregó una tercera skill al grafo de LangGraph, `borrador`, con su `TareaIA.REDACTAR_BORRADOR`, su prompt versionado (`app/application/ai/prompts/borrador.py`, versión `borrador/1.0.0`) y su schema (`BorradorIA`: introducción, secciones adaptadas por id de cláusula y notas de revisión). Pasa por el mismo `AIGateway`, así que las reglas R1 a R6 siguen aplicando: lo único que escribe la empresa son sus indicaciones de redacción, que el gateway pasa por el NER antes del LLM.

La skill cumple los mismos estándares que HU-18 exigió al tutor. El nodo `guardia` revisa las indicaciones con `FiltroAgente` y, si hay un ataque, la ejecución termina sin llamar al NER ni al LLM; el usuario recibe 422 `INSTRUCCIONES_BLOQUEADAS` (con un mensaje ético distinto si la categoría es `uso_indebido`), queda un evento de seguridad con origen `borrador` y una fila en el audit log. El system prompt lleva un canario por llamada. Después del LLM, el nodo `validar_borrador` aplica `borradores/salida_ia.py`: descarta secciones de cláusulas que no se entregaron o que son fijas, duplicadas o que citan artículos que no están en las fuentes reales de la plantilla; quita código, títulos, tablas, enlaces y códigos internos; y si el modelo filtró el system prompt descarta **todo** lo que aportó. Las etiquetas del NER (`[NOMBRE_ANON]`…) que el modelo deje en su texto se convierten en `[COMPLETAR: nombre]` para que la empresa sepa qué completar.

Si la IA está deshabilitada (`BORRADORES_IA_HABILITADA=false`), si el usuario desmarca "Adaptar con el Agente IA", si se agotó la cuota o si el LLM falla, el borrador **se arma igual** con la plantilla y la evaluación, y la respuesta trae un `aviso` y la advertencia correspondiente. Cuando la falla es del servicio de IA la cuota se devuelve.

## Revisión, edición y consolidación

El borrador vive en la tabla nueva `borrador_documento` mientras está `en_revision`. El contenido se guarda **cifrado** con un tipo nuevo, `TextoCifradoBorrador`, con su propia subclave (`borradores`) derivada de `ENTITY_MAP_KEY`. Es la misma excepción documentada de ARCOP en HU-06: un aviso de privacidad necesita el canal real del Encargado de Protección de Datos, así que el contenido no se puede reemplazar por etiquetas. Las indicaciones que se dieron al Agente IA no se guardan; en la bitácora queda solo su huella HMAC.

Cada edición (`PATCH`) envía la versión que se editó; si otra pestaña u otra persona guardó antes, responde 409 `VERSION_DESACTUALIZADA`. La descarga previa entrega Markdown o PDF; el PDF (`pdf_borrador.py`, reportlab, mismo estilo que el informe de HU-21) lleva la marca de agua «BORRADOR» debajo del texto y "Página X de Y". El Markdown se trata como texto no confiable al pasarlo a PDF: todo se escapa y solo se reconoce un subconjunto cerrado (títulos, párrafos, viñetas, listas numeradas, citas, tablas, negrita, cursiva y código en línea).

Al consolidar, el PDF final (sin marca de agua) se guarda en "Mis documentos" con `guardar_documento(tipo="borrador")` de HU-29 y el borrador queda de solo lectura con el id del documento. Descartar un borrador consolidado no borra su PDF, y si el usuario borra el PDF en Mis documentos el borrador queda con `documento_id` en NULL (`ON DELETE SET NULL`).

## Criterios de aceptación

| Criterio | Dónde se cumple | Pruebas (`tests/test_hu16_borradores.py`) |
|---|---|---|
| 1. Plantillas editables en Markdown/PDF (Políticas LLM, Avisos de privacidad, PIA) | `plantillas.py` (tres plantillas), `generador.py` (Markdown), `pdf_borrador.py` (PDF), `GET /api/borradores/plantillas`, `POST /api/borradores`, `GET …/descarga?formato=md\|pdf` | `test_tres_plantillas_editables…`, `test_pdf_de_cada_plantilla`, `test_parser_markdown…`, `test_api_generar_revisar_editar_descargar_y_consolidar` |
| 2. Cláusulas ajustadas a la Ley N.º 21.719 y a las dimensiones del modelo | Cláusulas por dimensión con medidas prioritarias por brecha, fundamento de la matriz, Anexos A y B; skill `borrador` del agente con guardia y validación de salida | `test_borrador_con_identidad…`, `test_anexo_a_alinea…`, `test_aviso_de_privacidad_cubre…`, `test_agente_adapta_ancla…`, `test_agente_bloquea_la_inyeccion…`, `test_fuga_del_system_prompt…`, `test_salida_con_articulo_inventado…` |
| 3. Revisión, edición y descarga previa a consolidación | Estado `en_revision`, `PATCH` con control de versión, descarga previa con marca de agua, `POST …/consolidacion` con confirmación de pendientes y PDF en Mis documentos | `test_api_generar_revisar_editar_descargar_y_consolidar`, `test_pendientes_y_etiquetas…` |

Además: roles y contrato (`test_api_solo_usuario_definitivo_con_contrato_vigente`), inyección en las indicaciones (`test_api_instrucciones_con_inyeccion_se_bloquean_sin_llm`), plantilla sin IA y falla del LLM (`test_api_sin_ia_o_si_falla_el_llm…`), cuota, límite de borradores en revisión y aislamiento entre empresas (`test_api_cuota_agotada_limite_en_revision_y_aislamiento_por_empresa`) y la validación de la configuración.

## Reglas

Todas las rutas `/api/borradores` exigen usuario definitivo con **contrato vigente** (`empresa_con_servicio`, HU-30); la prueba de HU-30 que vigila el prefijo `/api/borradores` ahora tiene rutas reales que revisar. El PDF consolidado se sigue descargando desde Mis documentos durante el plazo de gracia, como cualquier documento. Un borrador de otra empresa responde 404 en todas las rutas.

En el audit log quedan `borrador.generado`, `borrador.editado`, `borrador.descargado`, `borrador.consolidado`, `borrador.descartado` y `borrador.instrucciones_bloqueadas`, con el tipo, la versión, conteos, la traza y la versión del prompt, pero nunca el texto del borrador ni de las indicaciones. Las categorías del Auditor Externo los clasifican como creación, modificación, supresión y seguridad.

## Configuración (`Proyecto/.env`, todas opcionales)

| Variable | Por defecto | Para qué |
|---|---|---|
| `BORRADORES_IA_DIA_EMPRESA` | 10 | Borradores adaptados con IA por empresa y día (0 = sin límite). Sin cuota, el borrador se arma con la plantilla |
| `BORRADORES_MAX_EN_REVISION` | 20 | Borradores en revisión por empresa |
| `BORRADORES_MAX_CHARS_CONTENIDO` | 30000 | Largo máximo del Markdown editado (el BFF acepta 64 KB de JSON) |
| `BORRADORES_MAX_CHARS_INSTRUCCIONES` | 1500 | Largo de las indicaciones al Agente IA |
| `BORRADORES_IA_HABILITADA` | true | `false` = solo plantilla, sin llamar al LLM |
| `BORRADOR_MODELO`, `BORRADOR_MAX_TOKENS_SALIDA`, `BORRADOR_TIMEOUT_S`, `BORRADOR_TEMPERATURA` | `LLM_MODEL`, 6000, 60, 0.2 | Límites de la tarea `redactar_borrador` |

## Base de datos

Migración `b6d2f9a4c8e1_hu16_borradores_cumplimiento.py` (revisa `e5a9c3f1b7d2`, la de HU-21): crea `borrador_documento`. `documento_empresa` no cambia. El rol `complianceia_app` recibe los permisos por los `ALTER DEFAULT PRIVILEGES` de HU-09. La tabla quedó clasificada en el inventario de T-06 (`catalogo_datos_personales.py`): el contenido como texto libre cifrado, las notas del Agente IA como derivado de IA anonimizado y el usuario que lo generó como metadato.

## Archivos

Nuevos: `app/application/borradores/` (`__init__.py`, `plantillas.py`, `generador.py`, `salida_ia.py`, `pdf_borrador.py`), `app/application/ai/prompts/borrador.py`, `app/application/schemas/borrador.py`, `app/application/use_cases/borradores.py`, `app/api/routes/borradores.py`, `app/domain/models/borrador.py`, la migración y `tests/test_hu16_borradores.py`.

Modificados: `app/application/ai/agente/grafo.py` y `__init__.py` (skill `borrador`, canario por skill), `app/application/ai/agente/salida.py` (las reglas de fuga, código y enlaces quedaron reutilizables con `problemas_en_textos`, sin cambiar el comportamiento del tutor), `app/application/ai/politicas.py`, `app/infrastructure/llm/factory.py`, `app/core/config.py`, `app/core/cifrado_columnas.py`, `app/core/catalogo_datos_personales.py`, `app/core/servicio_pagado.py` (docstring), `app/domain/models/__init__.py`, `app/domain/models/documento_empresa.py` (docstring), `app/domain/models/evento_seguridad.py` (origen `borrador`), `app/infrastructure/repositories/bitacora_repository.py`, `app/main.py`, `tests/test_hu20_autorizacion.py` (las 8 rutas nuevas en la matriz) y `Proyecto/README.md`.

## Pendiente para el PO

Los textos de las cláusulas son un borrador técnico: igual que el aviso legal de HU-04, deben revisarlos el PO y asesoría legal antes del piloto (cambiar un texto obliga a subir `VERSION_PLANTILLAS`). También queda por confirmar la cuota diaria de borradores con IA (10 por empresa es un valor provisorio). Por último, los borradores son documentos de la empresa (persona jurídica), así que la supresión ARCOP del usuario definitivo no los borra, igual que los informes de Mis documentos (HU-29); si el PO decide lo contrario basta con agregarlos a `anonimizar_usuario_definitivo`.

# HU-15 · Agente IA Tutor del panel de formación (backend)

*Como Oficial de Cumplimiento o Encargado de Datos, quiero interactuar con un Agente IA Tutor especializado dentro de cada ruta formativa, para recibir orientaciones paso a paso, explicaciones normativas adaptadas y recomendaciones contextuales que me permitan cerrar las brechas de gobernanza identificadas.*

Hasta esta historia la capa de IA tenía una sola tarea: el gateway recibía una evidencia y una justificación ya revisadas por la capa de seguridad, las pasaba por el motor NER y le pedía al LLM una clasificación estructurada. El tutor necesitaba algo distinto, una conversación sobre las brechas de la empresa, pero sin perder ninguna de las reglas que ya protegían a la evaluación de evidencias. La decisión fue no crear un segundo camino hacia el LLM, sino convertir la capa de IA en un **agente orquestado con LangGraph** en el que la evaluación de evidencias es una skill más y el tutor es otra. Las dos pasan por el mismo `AIGateway`, así que las reglas R1 a R6 (texto original nunca al LLM, mapa de entidades fuera del proveedor, aborto si falla el NER, métrica con éxito o error, etiquetas fijas, depuración solo fuera de producción) aplican igual a las dos.

## Cómo funciona el agente

El grafo vive en `app/application/ai/agente/grafo.py` y se compila una sola vez por proceso. Las dependencias (el gateway y la guardia de prompt injection) viajan en la configuración de la ejecución y no en el estado, de modo que el estado solo lleva datos.

```
START ─▶ guardia ─┬─(bloqueado)──────────────────────────────▶ END
                  ├─(skill = validar_evidencia)─▶ validar_evidencia ─▶ END
                  └─(skill = tutor)─▶ tutor ─▶ anclar_contexto ─────▶ END
```

El nodo `guardia` revisa el mensaje del tutor con las reglas de `seguridad.py` **antes** de llamar al NER y al LLM; si detecta una inyección, la ejecución termina sin gastar una llamada. En la evaluación de evidencias la guardia no actúa, porque `ProcessEvidenceUseCase` ya hace esa revisión con su modo `bloquear`/`marcar` y no queríamos cambiar ese comportamiento. El router es **determinista** (decisión del PO): la skill la elige el caso de uso, no un modelo, así que no hay una llamada extra para clasificar intenciones. El último nodo del tutor, `anclar_contexto`, limpia la salida: quita las brechas citadas que no están en el contexto, renumera los pasos y acota las sugerencias.

No se usa el checkpointer de LangGraph. El historial de la conversación vive en nuestras tablas, ya anonimizado, y el grafo no guarda nada entre ejecuciones; así no queda texto en tablas que no controlamos. Tampoco se usa `langchain-groq`: el LLM se sigue llamando con el SDK oficial de Groq a través del `GroqProvider`, porque el function calling de LangChain era justamente lo que producía los HTTP 400 intermitentes que motivaron ese adaptador.

`GatewayEvidenceValidator` mantiene su interfaz y ahora invoca la skill `validar_evidencia` del agente. Toda la suite anterior pasó sin modificar ninguna prueba de la capa de IA, que era el criterio para considerar la migración sin regresión.

## La tarea `tutor` en el gateway

Se registró `TareaIA.TUTOR` en `politicas.py` con su propio prompt versionado (`app/application/ai/prompts/tutor.py`, hoy en la versión `tutor/1.1.0`), su schema de salida (`TutorRespuesta`: tipo de respuesta, texto, pasos con responsable y evidencia esperada, brechas citadas y mensajes sugeridos; las referencias normativas las agrega el agente, ver v1.1) y sus límites (`TUTOR_MAX_TOKENS_SALIDA`, `TUTOR_TIMEOUT_S`, `TUTOR_TEMPERATURA`, `TUTOR_MODELO`). El schema funciona en el modo estricto de Groq sin adaptaciones especiales.

Para esto el gateway ganó dos cosas pequeñas. Las reglas post-salida ahora reciben también los datos confiables, y así la política del tutor puede marcar `brecha_fuera_de_contexto` cuando el modelo cita una brecha que no se le entregó; esa advertencia queda en `llamadas_llm` como cualquier otra. Además, `ResultadoIA` devuelve los textos tal como salieron hacia el LLM ya sanitizados, que es lo que el tutor guarda. Cada métrica del tutor se guarda con `tarea = 'tutor'`, el tipo de respuesta en `clasificacion` y la conversación en la nueva columna `llamadas_llm.conversacion_tutor_id`. `GET /api/ia/metricas` suma una sección `tutor` con los mensajes respondidos y fallidos, los bloqueados por inyección (contados desde `eventos_seguridad`, porque nunca llegan al LLM), la tasa fuera de alcance, las advertencias por tipo y la latencia.

## Criterios de aceptación

| Criterio | Dónde se cumple | Pruebas (`tests/test_hu15_tutor.py`) |
|---|---|---|
| 1. Carga aislada del contexto de brechas no conformes de la empresa | `app/application/tutor/contexto.py`: la empresa sale del token, se usa la evaluación más reciente con resultados (la misma regla del panel de formación) y entran solo las brechas `no_cumplido` y `parcialmente_cumplido`, con datos del catálogo y del control; desde v1.1, para las brechas en foco, también la justificación y la última evidencia de la propia empresa (no confiables, pasan por el NER). No van la razón social, el RUT ni datos de contacto. Se recarga en cada mensaje. Una conversación de otra empresa responde 404 en todas sus rutas | `test_contexto_solo_brechas_no_conformes_con_referencia_unica`, `test_api_conversacion_completa_aislada_anonimizada_y_auditada`, `test_api_otra_empresa_no_ve_la_conversacion` |
| 2. Explicaciones y planes de acción por nivel (Inicial, Intermedio, Avanzado) | El prompt tiene un estilo por nivel y tres tipos de respuesta (explicación, plan de acción y recomendación). El nivel por defecto es el de la ruta: la del módulo desde el que se abrió el tutor o, en el panel general, la de la brecha más prioritaria; si no hay ruta, el que corresponde al puntaje. El usuario lo cambia con `PATCH` | `test_nivel_por_defecto_es_el_de_la_ruta`, `test_prompt_versionado_con_contexto_nivel_y_delimitadores`, prueba de API completa |
| 3. Asistencia conversacional en tiempo real en el panel de formación | `POST /api/tutor/conversaciones/{id}/mensajes` responde de forma síncrona con la salida ya validada y anclada; el frontend muestra el indicador "escribiendo" mientras espera | Prueba de API completa, `test_agente_tutor_ancla_la_salida_al_contexto_y_registra_la_metrica` |

## Reglas que se agregaron

Todo el tutor exige **usuario definitivo con contrato vigente**: sus rutas usan `empresa_con_servicio` (HU-30), así que el usuario temporal y el admin reciben 403 `NO_AUTORIZADO` y una empresa sin servicio recibe 403 `CONTRATO_NO_VIGENTE`. La prueba de HU-30 que vigila que el servicio pagado use la guarda también cubre estas rutas.

En `mensaje_tutor` **solo queda texto anonimizado**. El mensaje del usuario que se guarda es exactamente el que vio el LLM después del NER, sin una segunda pasada que pudiera dar un resultado distinto. La respuesta del tutor se vuelve a pasar por el anonimizador antes de guardarse, como defensa en profundidad; si el anonimizador falla no se guarda nada (fail-closed). Cuando un mensaje se bloquea por prompt injection no se guarda su texto: queda una marca, la respuesta fija del tutor y el evento de seguridad con su extracto anonimizado (origen `tutor`), que aparece en la bandeja del Oficial de Cumplimiento.

La cuota la fijó el PO en **60 mensajes por empresa al día** y se cambia con `TUTOR_MENSAJES_DIA_EMPRESA` en el `.env`. Además hay un límite de ráfaga por minuto (`TUTOR_MENSAJES_MINUTO_EMPRESA`, 6) y cada mensaje cuenta para la cuota global del LLM. Si el servicio de IA falla, la cuota se devuelve, porque el usuario no tuvo la culpa. Un mensaje bloqueado sí la consume, para que no sirva probar inyecciones gratis.

Una conversación queda atada a la evaluación con la que se abrió. Si la empresa tiene después una evaluación más reciente, la conversación pasa a **solo lectura** (409 `CONVERSACION_DESACTUALIZADA` al escribir) y el usuario abre otra con sus brechas vigentes. Así el tutor nunca mezcla brechas de dos evaluaciones.

Conservación, según la decisión del PO: las conversaciones se **borran** con la supresión ARCOP del usuario definitivo (`anonimizar_usuario_definitivo` informa cuántas) y con la nueva regla de retención R4, que borra en el cron diario las que llevan más de `TUTOR_RETENCION_DIAS` (30) días sin actividad. El usuario también puede borrar una conversación desde el chat. Las métricas de `llamadas_llm`, que no tienen texto, y la bitácora se conservan. Las columnas nuevas están clasificadas en el inventario de datos personales de T-06.

La bitácora (HU-09) registra la creación, cada mensaje (con el tipo, el nivel, la cantidad de pasos y de brechas citadas, la traza y la versión del prompt), los bloqueos, los cambios de nivel y los borrados, sin el texto de ningún mensaje.

## v1.1 · Ajustes tras la prueba del equipo (28-oct)

La primera prueba en el panel mostró que el tutor resistía bien el abuso (no respondió noticias, matemáticas ni programación, no reveló su modelo ni datos de otras empresas y bloqueó la inyección), pero aportaba poco. El log permitió encontrar cinco causas concretas, todas corregidas.

**Las sugerencias eran preguntas al usuario.** El modelo proponía cosas como "¿Qué controles de acceso ya tiene implementados?". Al hacer clic, el chat las enviaba como si el usuario se las preguntara al tutor, y este contestaba "no dispongo de información" con tipo *Fuera de alcance*. Ahora el schema y el prompt piden mensajes en primera persona, tal como los escribiría el usuario ("¿Cómo armo el inventario del paso 1?").

**El tutor no recordaba sus propios pasos.** El historial solo llevaba el texto principal de cada respuesta, no la lista de pasos, así que "explícame el paso 1" no tenía a qué referirse y el modelo repetía el plan entero (pasó tres veces con GOB-003). Ahora cada turno del tutor viaja con sus pasos numerados (`turno_historial`). El prompt pide explicar solo el paso pedido, con un ejemplo o una plantilla y la evidencia que deja, y no repetir un plan ya entregado. En el chat, cada paso tiene además un botón "Explícame este paso" que hace la pregunta de forma explícita.

**Inventaba artículos.** Citó la Ley 21.719 como art. 20, 15, 5 y 10 en distintas respuestas, porque no tenía la fuente real. Ahora el modelo no escribe referencias: el campo salió del JSON Schema y el agente lo completa con el framework y el artículo **reales** de la matriz de controles (`matriz_controles.framework_fuente` y `articulo_referencia`) de las brechas que cita. El prompt le prohíbe escribir números de artículo que no estén en el contexto, y si igual aparece uno en el texto, la métrica registra la advertencia `articulo_no_verificado`.

**Sabía muy poco de la empresa.** Solo veía el código, la severidad y la acción del catálogo, así que no podía responder "¿qué tengo implementado?" ni "¿por qué me rechazaron la evidencia?". Ahora el contexto distingue las **brechas en foco**: las que el usuario nombra (aunque las escriba en minúsculas, "gob-003"), las que el tutor citó en su respuesta anterior o, si no hay ninguna, las tres más prioritarias. De esas va el detalle del control (obligación, pregunta, evidencia esperada, fuente normativa y recomendación) y los **antecedentes de la empresa**: su justificación y el resultado de su última evidencia, con el motivo del análisis. Las demás brechas van en una línea cada una. Los antecedentes son texto de la empresa, ya anonimizado al guardarse (HU-06). Igual se tratan como no confiables: son un segundo campo de la política (`antecedentes`), así que el gateway los vuelve a pasar por el NER antes del LLM y van escapados entre delimitadores. Siguen siendo solo datos de la evaluación de esa empresa.

**Detalles menores.** Un saludo o un "¿cómo me puedes ayudar?" salía como *Fuera de alcance*; ahora es una orientación con el estado de la empresa. El responsable de un paso era texto libre y el NER confundió un área con un nombre ("Equipo de [NOMBRE_ANON]"). Ahora es una lista cerrada (`ResponsableSugerido`: Encargado de Datos, Oficial de Cumplimiento, Equipo de TI, Seguridad de la información, Gestión de Riesgos, Asesoría legal, Personas / RR. HH., Auditoría interna, Alta dirección, Dueño del proceso o sistema de IA y Compras / Proveedores), que no puede traer datos personales.

El prompt pasó a `tutor/1.1.0`. Las respuestas guardadas con 1.0.0 conservan su versión en `mensaje_tutor.prompt_version` y en `llamadas_llm`, así se pueden comparar las dos en las métricas. No hay variables nuevas: el tope de los antecedentes (6.000 caracteres) es parte de la política. Con esta versión la suite completa da **646 aprobadas y 8 omitidas**; hay seis pruebas nuevas para estos cambios en `tests/test_hu15_tutor.py`.

## Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/api/tutor/contexto?ruta_id=` | Brechas que verá el tutor, nivel sugerido, cuota y largo máximo del mensaje |
| GET | `/api/tutor/conversaciones` | Conversaciones de la empresa, con la evaluación vigente |
| POST | `/api/tutor/conversaciones` | Abre una conversación `{ruta_id?, nivel?}` (201) |
| GET | `/api/tutor/conversaciones/{id}` | La conversación con sus mensajes |
| PATCH | `/api/tutor/conversaciones/{id}` | Cambia el nivel `{nivel}` |
| DELETE | `/api/tutor/conversaciones/{id}` | La borra con sus mensajes (204) |
| POST | `/api/tutor/conversaciones/{id}/mensajes` | `{texto}` → `mensaje_usuario`, `respuesta`, `conversacion` y `cuota` |

Códigos de error nuevos: `MENSAJE_VACIO` y `MENSAJE_DEMASIADO_LARGO` (422), `NIVEL_INVALIDO` (422), `CONVERSACION_NO_ENCONTRADA` y `RUTA_NO_ENCONTRADA` (404), `CONVERSACION_DESACTUALIZADA` y `LIMITE_CONVERSACIONES` (409), `CUOTA_TUTOR_AGOTADA` y `TUTOR_RAFAGA` (429, con `Retry-After`) y `TUTOR_NO_DISPONIBLE` (503).

## Variables de entorno

Todas son opcionales y están documentadas en `Proyecto/.env.example`: `TUTOR_MENSAJES_DIA_EMPRESA` (60), `TUTOR_MENSAJES_MINUTO_EMPRESA` (6), `TUTOR_MAX_CHARS_MENSAJE` (2000), `TUTOR_HISTORIAL_MENSAJES` (6), `TUTOR_MAX_BRECHAS_CONTEXTO` (40), `TUTOR_MAX_CONVERSACIONES` (50), `TUTOR_MODELO` (vacío = `LLM_MODEL`), `TUTOR_MAX_TOKENS_SALIDA` (4096), `TUTOR_TIMEOUT_S` (45), `TUTOR_TEMPERATURA` (0,3) y `TUTOR_RETENCION_DIAS` (30). La configuración rechaza valores fuera de rango al arrancar.

## Archivos

| Archivo | Cambio |
|---|---|
| `requirements.txt` | `langgraph>=1.2,<2` (trae `langchain-core`). |
| `app/application/ai/agente/__init__.py`, `grafo.py` | **Nuevos.** Agente de LangGraph: guardia, router determinista, skills `validar_evidencia` y `tutor`, anclaje de la salida. |
| `app/application/ai/evidence_validator.py` | La validación de evidencias se ejecuta como skill del agente (misma interfaz). |
| `app/application/ai/gateway.py` | Las reglas post-salida reciben los datos; `ResultadoIA.textos_sanitizados`; etiqueta de la métrica por política. |
| `app/application/ai/politicas.py` | `TareaIA.TUTOR` con su política. |
| `app/application/ai/prompts/tutor.py` | **Nuevo.** Prompt versionado `tutor/1.0.0` con estilo por nivel. |
| `app/application/ai/metricas.py`, `app/application/use_cases/obtener_metricas_ia.py` | Sección `tutor` de las métricas. |
| `app/application/schemas/tutor.py` | **Nuevo.** `TutorRespuesta`, `PasoAccion`, niveles y tipos. |
| `app/application/tutor/contexto.py` | **Nuevo.** Contexto aislado y nivel sugerido. |
| `app/application/use_cases/tutor_ia.py` | **Nuevo.** Caso de uso del tutor (conversaciones, mensajes, cuota, bloqueo, bitácora). |
| `app/api/routes/tutor.py`, `app/main.py` | **Nuevo** router `/api/tutor`. |
| `app/domain/models/tutor.py`, `app/domain/models/__init__.py` | **Nuevos** modelos `ConversacionTutor` y `MensajeTutor`. |
| `app/domain/models/llamada_llm.py`, `app/domain/ports/registro_ia_port.py`, `app/infrastructure/repositories/registro_ia_repository.py` | `conversacion_tutor_id` en las métricas. |
| `app/domain/models/evento_seguridad.py` | Origen `tutor`. |
| `app/infrastructure/repositories/tutor_repository.py` | **Nuevo.** Persistencia filtrada por empresa y borrados. |
| `app/infrastructure/repositories/anonimizacion_repository.py` | La supresión ARCOP del usuario definitivo borra sus conversaciones. |
| `app/infrastructure/repositories/bitacora_repository.py` | Acciones `tutor.*`. |
| `app/application/use_cases/aplicar_retencion.py` | Regla R4 (conversaciones inactivas). |
| `app/infrastructure/llm/factory.py` | `crear_agente()`; la política del tutor toma la configuración. |
| `app/core/config.py`, `Proyecto/.env.example` | Variables `TUTOR_*` con validación. |
| `app/core/catalogo_datos_personales.py` | Clasificación de las columnas nuevas (T-06). |
| `migrations/versions/b8f1c3d5e7a2_hu15_tutor_ia.py` | **Nueva.** Tablas `conversacion_tutor` y `mensaje_tutor` y la columna de `llamadas_llm`. `down_revision = a4c7e2f9d1b3` (HU-30). Tiene `downgrade`. |
| `tests/test_hu15_tutor.py` | **Nuevo.** 25 pruebas (lógica pura, grafo, ajustes v1.1 y API en proceso). |
| `tests/test_hu20_autorizacion.py` | Las rutas del tutor en la matriz de autorización. |

## Cómo probarlo

Después de `docker compose up -d --build` (la imagen instala `langgraph`) y de que `migrate` aplique `b8f1c3d5e7a2`, la suite corre con `docker compose exec worker pytest tests -v -rxX`. Para probarlo a mano hace falta una empresa con contrato vigente y una evaluación migrada con brechas: se entra como usuario definitivo, se abre **Capacitación** y se usa la tarjeta "Hablar con el tutor", o el botón "Preguntar al tutor IA" dentro de un módulo. En Swagger el flujo es `POST /api/tutor/conversaciones` y luego `POST /api/tutor/conversaciones/{id}/mensajes`, con el token del cliente.

En este entorno de desarrollo la suite completa dio **646 aprobadas y 8 omitidas** (con v1.1) (las 8 omitidas necesitan spaCy real). LangGraph se verificó con la versión 1.2.18. Falta comprobar en el Docker del equipo que la imagen instale `langgraph` sin conflictos con `pydantic==2.14.0` y hacer una prueba en vivo con Groq, porque aquí el LLM fue un proveedor falso.

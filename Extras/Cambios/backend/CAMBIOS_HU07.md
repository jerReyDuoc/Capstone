# HU-07 · Pruebas de alucinación y verificación sintáctica de las salidas del modelo (OWASP Top 10 for LLM)

*Como Data Engineer, quiero ejecutar pruebas de alucinación y verificación sintáctica en las salidas del modelo local, para mitigar vulnerabilidades del OWASP Top 10 for LLM (Prompt Injection, fuga de contexto).*

Antes de esta historia el backend ya tenía una capa anti prompt-injection en la entrada (HU-02, HU-18, HU-33) y el eventual registro en `eventos_seguridad`. Lo que faltaba era el otro lado: nadie revisaba lo que **devolvía** el modelo al validar una evidencia. Si el modelo inventaba una fecha, citaba una frase que no estaba en el documento, daba por cumplido un archivo vacío o repetía un correo, el backend usaba esa propuesta igual (solo se miraba la confianza). La hoja de historias lo dejaba anotado: *"no existe test-set de evaluación del LLM; falta definir cómo se mide 'alucinación'"*. Esta historia cubre ese hueco, amplía el test-set de ataques de la entrada (multilenguaje e indirectos) y agrega un proveedor de modelo local.

## Qué es una alucinación (T-SM-27)

Una **alucinación** es una afirmación de la salida que no tiene respaldo en lo que recibió el modelo: la evidencia, la justificación del usuario y los datos del control (código, framework, artículo, obligación, evidencia esperada). En concreto:

| Código | Qué detecta |
|---|---|
| `alucinacion.cumplimiento_sin_evidencia` | "cumplido" o "parcial" sobre una evidencia vacía (solo etiquetas, símbolos) o que el propio modelo marca `evidencia_suficiente=false` |
| `alucinacion.cita_inexistente` | un texto entre comillas de 3 o más palabras que no aparece (se toleran mayúsculas, tildes, puntuación y las etiquetas `[X_ANON]`) |
| `alucinacion.dato_inexistente` | un valor de `datos_extraidos` con cifras que no están, o una frase de 3+ palabras sin respaldo |
| `alucinacion.cifra_inexistente` | una cifra de 3 o más dígitos o un porcentaje que no aparece (los conteos chicos, "2 de 3", son razonamiento) |
| `alucinacion.fecha_inexistente` | una fecha que no está, en cualquiera de los formatos (14/03/2025, 2025-03-14, 14 de marzo de 2025, marzo de 2025) |
| `alucinacion.articulo_inexistente` | un artículo, cláusula o sección que no es del control ni aparece en la evidencia |
| `alucinacion.control_ajeno` | el código de otro control de la matriz |
| `alucinacion.norma_no_verificada` | una ley o norma que no es del control ni del prompt (**solo advertencia**) |

Un **error de criterio** (decir "parcial" donde la verdad de referencia dice "cumplido") no es una alucinación: es un error de exactitud. Lo mide el script en vivo y la bandeja de revisión humana (HU-22), no el verificador.

**Umbral (< 2 %).** Se mide de dos formas. En el test-set automatizado, la *tasa residual* (alucinaciones que el verificador deja pasar sobre el total de casos) debe ser menor que 2 %. En producción, `GET /api/ia/metricas` informa la *tasa de alucinación del modelo* (salidas con un hallazgo de alucinación sobre las salidas verificadas) con `umbral_tasa_alucinacion: 0.02` y `cumple_umbral`. Si el modelo supera el 2 % no se cae nada (el verificador retiene esas salidas), pero la métrica avisa que conviene cambiar de modelo o de prompt.

## Verificación sintáctica y de fuga de contexto

El mismo verificador (`app/application/ai/verificacion_salida.py`, sin BD, sin red y sin otro modelo) revisa también:

| Categoría (tipo del evento) | OWASP | Códigos |
|---|---|---|
| `salida_insegura` | LLM05 Improper Output Handling | `sintaxis.clasificacion_invalida`, `sintaxis.confianza_invalida`, `sintaxis.codigo_activo` (HTML, `<script>`, `onerror=`, `javascript:`), `sintaxis.enlace_externo` (enlaces o imágenes markdown que no están en la evidencia); solo advertencias: `sintaxis.caracteres_ocultos`, `sintaxis.longitud_excesiva` |
| `fuga_contexto` | LLM02 Sensitive Information Disclosure · LLM07 System Prompt Leakage | `fuga.datos_personales` (RUT con dígito verificador válido, correo, teléfono: el modelo solo recibió texto anonimizado), `fuga.reidentificacion` ("[NOMBRE_ANON] (Juan Pérez…)"), `fuga.prompt_sistema` (delimitadores internos o 4+ tramos de 8 palabras del system prompt) |
| `inyeccion_salida` | LLM01 Prompt Injection | `inyeccion.obediencia` ("siguiendo las instrucciones del documento", "modo desarrollador", "as instructed in the document"), `inyeccion.no_degradada` (reconoce instrucciones dirigidas a la IA pero no clasifica `no_cumplido`, como exige el prompt) |
| `coherencia` | — | solo advertencias: `divergencia_sin_explicar`, `justificacion_vacia` (los códigos de siempre), `coherencia.respaldo_contradictorio` |

Además, `sanear()` entrega una copia de la salida segura de guardar y mostrar: sin caracteres invisibles, sin etiquetas HTML, con los enlaces no respaldados como `[enlace omitido]`, con RUT, correo y teléfono reemplazados por sus etiquetas, con largos acotados y, si hubo fuga del prompt, con la explicación reemplazada por un texto fijo. La clasificación y la confianza no se tocan.

## Qué hace el backend con un hallazgo

`ProcessEvidenceUseCase` llama al verificador con el texto que vio el modelo, justo después de recibir la propuesta y antes de guardarla:

- **Hallazgo grave y confianza ≥ `UMBRAL_CONFIANZA`** (la propuesta iba a decidir): no se aplica. La pregunta queda en `requiere_revision` con fuente `seguridad`, que la bandeja de revisión (HU-22) ya prioriza; la evidencia queda rechazada **sin** la clasificación ni la explicación del modelo (podrían ser falsas) y con un mensaje simple para la organización. En la **remediación** (HU-17) el control no cambia.
- **Fuga, inyección o formato inválido con cualquier confianza:** igual que arriba, porque esa salida se guardaría y se vería.
- **Solo alucinación con confianza bajo el umbral:** nada cambia, porque esa propuesta ya se descartaba (se mantiene lo declarado). El hallazgo queda en la métrica.
- En todos los casos retenidos se registra la **alerta** en `eventos_seguridad` con `origen = salida_llm`, `tipo` = la categoría, `regla` = `salida.<código>` y el extracto anonimizado de lo que propuso el modelo. La bandeja del Oficial de Cumplimiento la muestra con textos propios ("La respuesta de la IA no pasó la verificación", "¿La verificación acertó?").
- `MODO_VERIFICACION_SALIDA=marcar` solo registra la alerta y deja que la propuesta se aplique (útil para medir antes de activar el bloqueo). Por defecto es `bloquear`.
- Si el verificador fallara por cualquier motivo, se registra en el log y el flujo sigue como antes de esta historia.

Mensajes que ve la organización (sin jerga técnica):

> El análisis automático incluyó datos que no aparecen en tu documento (por ejemplo, fechas, cifras o citas). Para cuidar la calidad del resultado, esta pregunta quedó pendiente de revisión por nuestro equipo.

> El análisis automático incluyó información que no debía mostrarse, así que lo ocultamos. …

El gateway (`AIGateway`) también corre el verificador en las reglas post-salida, con los textos ya anonimizados que salieron hacia el proveedor, y deja los códigos en `llamadas_llm.advertencias`. Así las métricas cuentan todas las salidas, también las que no decidieron nada.

## Saneamiento de entrada (OWASP LLM01)

**Antes del prompt** (`app/application/ai/prompts/base.py`): `escapar_para_prompt` ahora primero quita caracteres de ancho cero, controles bidireccionales, caracteres "tag" (U+E0000) y controles C0, y neutraliza el separador de secciones de los prompts (`═══` → `===`) y los marcadores de turno de otros modelos (`[INST]`, `<<SYS>>`, `<|im_start|>`). Aplica a todas las tareas (evidencias, tutor y borradores). El texto normal no cambia.

**En el detector** (`app/infrastructure/security/seguridad.py`): reglas nuevas para ataques en inglés, portugués, francés, alemán e italiano y mezclas ("Note to the AI reviewer…", "Se você é uma IA…", "Oubliez les instructions précédentes…", "Wenn du eine KI bist…", "Nota per l'IA…"), forzar el resultado ("must classify as compliant", "the correct answer is compliant"), cambio de rol ("a partir de agora você é…"), `Override:`, nombres de campos del schema dentro del documento (`datos_extraidos`, `evidencia_suficiente`…), pedidos de "las reglas que recibiste" y de mostrar el contenido de una etiqueta anonimizada. En el perfil evidencia los verbos multilenguaje cuentan solo como orden al inicio de una cláusula, igual que en HU-33, y "conforme a/al/con" en español no cuenta como "compliant".

| Test-set de ataques (`tests/data/ataques_owasp_evidencias.jsonl`) | Antes | Ahora |
|---|---|---|
| 96 ataques (directos, indirectos, multilenguaje, codificados, ofuscados, delimitadores, fuga, exfiltración) | 71 bloqueados (74 %) | **96 (100 %)** |
| 35 legítimos multilenguaje | 0 falsos positivos | 0 |
| 107 documentos legítimos de HU-33 | 0 falsos positivos | 0 |
| Ataques del test-set de HU-18 que bloquea `seguridad.py` solo | 89 | 92 (el filtro del tutor sigue en 100 %) |

El 100 % hay que leerlo con el mismo cuidado que en HU-18: las reglas se escribieron mirando este set. Por eso la verificación de la salida existe como segunda barrera: si una inyección nueva pasa la entrada y el modelo la obedece, la salida se retiene igual.

## Test-set automatizado (T-SM-28)

`tests/data/alucinaciones_evidencias.jsonl` tiene **124 casos borde** sobre 23 documentos de evidencia sintéticos de 16 controles reales de la matriz (políticas, borradores, RACI, inventarios, registros de capacitación e invitaciones, actas, no conformidades, matrices de riesgo, reportes de métricas, logs, guardrails, DPA, avisos de privacidad, EIPD incompleta, un plan en inglés, un RAT y, como bordes, un archivo vacío, uno solo con etiquetas anonimizadas, uno ilegible, uno irrelevante y uno con inyección). Cada caso trae el control, lo declarado, la justificación, la evidencia tal como la ve el modelo (anonimizada), la **verdad de referencia** (clasificación y si la evidencia sirve), una salida del modelo y el problema esperado:

| Salidas | Casos |
|---|---:|
| Correctas (incluye bordes difíciles: fechas en otro formato, citas con etiquetas, cifras con separador de miles, cláusulas del documento, enlaces que sí están, documentos en inglés, menciones de "alucinaciones" o "inyección" como tema) | 63 |
| Con alucinación | 39 |
| Con fuga de contexto | 8 |
| Con inyección obedecida | 6 |
| Con salida insegura (incluye un enlace inventado) | 8 |

Las salidas son **simuladas** (escritas para cubrir cada tipo de error), así que la prueba mide al verificador, no al modelo. Resultado: 0 alucinaciones sin detectar (residual 0 %, umbral < 2 %), 100 % de fugas, inyecciones y salidas inseguras detectadas y 0 salidas correctas retenidas (umbral ≤ 5 %).

## Prueba con el modelo real (T-SM-29) y modelo local

`scripts/evaluar_alucinaciones.py` envía las evidencias del test-set al modelo real a través de toda la capa de IA (NER local → prompt versionado → proveedor → verificador) y calcula la tasa de alucinación del modelo, la tasa residual (lo que solo detecta la verdad de referencia), la validez sintáctica, la exactitud frente a la verdad de referencia, latencia p50/p95, tokens y costo. Genera `resultado.json` e `informe.md` y termina con código 1 si no se cumple el 2 %. Por defecto manda una vez cada entrada distinta (37); `--todos` manda los 124 casos.

Para el **modelo local** se agregó `OllamaProvider` (`app/infrastructure/llm/ollama_provider.py`), un adaptador más del mismo puerto: el gateway, el NER y el verificador no cambian. Con `LLM_PROVIDER=ollama` el texto no sale del servidor y `GROQ_API_KEY` deja de ser obligatoria.

```
# Levantar el modelo local (no se levanta con el "up" normal)
docker compose --profile modelo-local up -d
docker compose exec ollama ollama pull qwen2.5:7b-instruct

# Medir sin tocar el .env
docker compose exec worker python scripts/evaluar_alucinaciones.py --proveedor ollama --modelo qwen2.5:7b-instruct --salida /tmp/hu07
docker compose exec worker python scripts/evaluar_alucinaciones.py --proveedor groq --salida /tmp/hu07_groq
docker compose cp worker:/tmp/hu07 ./evaluacion_hu07

# Usarlo en la aplicación: en Proyecto/.env
LLM_PROVIDER=ollama
LLM_MODEL=qwen2.5:7b-instruct
```

## Criterios de aceptación

| Criterio | Cómo se cumple |
|---|---|
| 1. Test-set automatizado de 100+ casos borde validando alucinaciones < 2 % | 124 casos con verdad de referencia; la prueba falla si la tasa residual llega al 2 % o si se retiene más del 5 % de las salidas correctas. Métrica `verificacion_salida.tasa_alucinacion` en `/api/ia/metricas` con el umbral del 2 %, y script en vivo contra Groq o el modelo local. |
| 2. Saneamiento de entrada según OWASP Top 10 for LLM contra Prompt Injection | Saneamiento antes del prompt (invisibles, bidi, tag, controles, separadores, marcadores de turno) y reglas multilenguaje e indirectas; 96 ataques al 100 % sin falsos positivos en 142 documentos legítimos. A la salida, la verificación cubre LLM01, LLM02, LLM05, LLM07 y LLM09. |
| 3. Registro de alertas de seguridad | Cada salida retenida queda en `eventos_seguridad` (`origen=salida_llm`, tipo por categoría, regla con el código, extracto anonimizado), aparece en la bandeja del Oficial de Cumplimiento con veredicto "Problema confirmado / Falso positivo" y se suma en `/api/ia/metricas` (`alertas_por_categoria`). |

## Archivos

| Archivo | Cambio |
|---|---|
| `app/application/ai/verificacion_salida.py` | **Nuevo.** Verificador de salida y saneamiento (puro). |
| `app/application/ai/politicas.py`, `gateway.py` | La política de evidencias registra los hallazgos; el gateway le pasa los textos anonimizados que vio el modelo. |
| `app/application/ai/prompts/base.py` | `sanear_texto_no_confiable`, usado por `escapar_para_prompt`. |
| `app/application/ai/metricas.py`, `app/application/use_cases/obtener_metricas_ia.py` | `resumen_verificacion` y bloque `verificacion_salida` en `/api/ia/metricas`. |
| `app/application/use_cases/process_evidence.py` | Verificación antes de usar la propuesta, retención, alerta y modo marcar. |
| `app/application/use_cases/registrar_evento_seguridad.py` | Texto del log genérico ("Alerta de seguridad registrada"). |
| `app/domain/models/evento_seguridad.py` | Origen `salida_llm` (cabe en la columna actual: **sin migración**). |
| `app/infrastructure/security/seguridad.py` | Reglas multilenguaje, indirectas, de schema y de fuga. |
| `app/infrastructure/llm/ollama_provider.py`, `factory.py` | **Nuevo** proveedor local. |
| `app/core/config.py`, `Proyecto/.env.example`, `Proyecto/docker-compose.yml` | `MODO_VERIFICACION_SALIDA`, `LLM_PROVIDER=ollama`, `OLLAMA_URL`, `GROQ_API_KEY` solo con Groq, servicio `ollama` con perfil `modelo-local`. |
| `scripts/evaluar_alucinaciones.py` | **Nuevo.** Prueba en vivo. |
| `tests/data/alucinaciones_evidencias.jsonl`, `tests/data/ataques_owasp_evidencias.jsonl` | **Nuevos.** Test-sets. |
| `tests/test_hu07_verificacion_salida.py`, `test_hu07_owasp_entrada.py`, `test_hu07_integracion.py` | **Nuevos.** 52 funciones de prueba (220 casos). |
| `tests/test_bordes_na_y_evidencia.py` | El riesgo documentado "evidencia insuficiente según el LLM no se considera" quedó resuelto: ahora la prueba exige que esa propuesta quede en revisión. |
| `frontend-next/lib/admin/revision.ts`, `components/admin/BandejaRevision.tsx` | Nombre del origen y de los tipos de evento, descripción de cada hallazgo y textos propios del detalle y del veredicto para los eventos de la respuesta de la IA. |
| `frontend-next/lib/cuestionario/modelo.ts`, `components/cuestionario/Evidencias.tsx` | La organización ve por qué una evidencia quedó sin resultado (aviso de la revisión automática o del bloqueo de seguridad en palabras simples). |
| `frontend-next/tests/verificacion_ia.test.ts` | **Nuevo.** 8 pruebas vitest. |

## Cómo probarlo y qué quedó pendiente

```
docker compose run --rm --no-deps api pytest tests/test_hu07_verificacion_salida.py tests/test_hu07_owasp_entrada.py tests/test_hu07_integracion.py -v
docker compose run --rm --no-deps api pytest tests -q          # suite completa
cd frontend-next && npm test
```

En el entorno donde se desarrolló no había dependencias del backend (SQLAlchemy, FastAPI, spaCy) ni del frontend, ni red para instalarlas. Se ejecutaron y pasaron las pruebas puras: `test_hu07_verificacion_salida.py` y `test_hu07_owasp_entrada.py` (198 casos), `test_hu33_detector_contexto.py`, `test_capa_ia.py`, `test_ner_sanitizer.py` y `test_metricas_ia.py`. Los escenarios de `test_hu07_integracion.py` se ejecutaron con dobles de los modelos y dieron el resultado esperado, pero el archivo en sí, el resto de la suite y `npm test` **hay que correrlos en Docker o en CI** antes del merge. Tampoco se pudo correr `scripts/evaluar_alucinaciones.py` contra Groq ni contra Ollama: la tasa real del modelo queda por medir. Hasta entonces, el < 2 % está demostrado para el verificador sobre salidas simuladas, no para el modelo.

Límites conocidos del verificador: no detecta una afirmación inventada que no lleve comillas, cifras, fechas, artículos ni códigos (por ejemplo, "la política incluye sanciones" cuando no las incluye). Eso es un error de criterio que solo ve la revisión humana o un segundo modelo juez, que se podría agregar más adelante detrás de la misma función sin cambiar el resto. Tampoco reconoce nombres de personas en la salida (eso requiere el NER); sí RUT, correos y teléfonos.

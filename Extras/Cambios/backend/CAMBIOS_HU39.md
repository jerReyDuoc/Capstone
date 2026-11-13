# HU-39 · Asistente de IA para el mapa de datos, el RAT y los informes

*Como Usuario Definitivo (cliente), quiero un agente de IA que me guíe para armar el mapa de datos, el RAT y los informes, para completarlos sin ser experto en protección de datos y en menos tiempo.*

El asistente es una **skill nueva del mismo agente** (LangGraph, HU-15) que pasa por el **mismo gateway** (HU-06/HU-18): no hay otra salida al LLM. Las propuestas se guardan como *sugeridas* y solo entran al mapa (HU-34) o al RAT (HU-35) cuando el usuario las acepta, a través de **sus propios casos de uso**.

## Criterios de aceptación

**C1 · Entrevista por área.** `app/application/asistente/banco.py`: 14 preguntas fijas en 6 áreas (personas, clientes, proveedores, marketing, TI, uso de IA), con ayuda y respuestas de ejemplo. Las preguntas las escribe el equipo, no el LLM: la entrevista funciona igual sin IA y cada respuesta queda ligada a un código de pregunta. Con cada respuesta el agente propone elementos, flujos y actividades con sus campos pre-llenados (`app/application/schemas/asistente_rat.py`).

**C2 · Base, plazos, riesgo e inconsistencias.** El modelo propone y **explica** (`explicaciones` por campo). El backend **calcula**, en `app/application/asistente/inconsistencias.py`, sobre un mapa virtual (lo que existe más lo propuesto) y con las funciones de siempre (`rat.analisis.derivados/completitud`, `mapa_datos.analisis.derivados_flujo`, `rat.riesgos.evaluar`):
- `sensible_sin_base`: datos sensibles sin base para tratarlos,
- `transferencia_sin_garantia`: envío fuera de Chile sin garantía válida (crítica si lleva sensibles o datos de NNA),
- `actividad_sin_plazo`: una categoría sin plazo de conservación,
- `flujo_sin_actividad`: nuevo `app/domain/rat/cobertura.py` (las archivadas no cubren),
- el **riesgo inherente** de cada actividad propuesta (matriz 5×5 de HU-36).
`globales()` hace la misma revisión sobre lo ya guardado (panel «Revisión de tu registro»).

**C3 · Documentos.** `POST /api/asistente/documentos`. Reutiliza HU-17 (`detectar_tipo`, `extraer_texto`, BM25 de `recuperar_fragmentos` con vocabulario de tratamiento) y HU-33 (`seguridad.analizar(..., "evidencia")` línea por línea, política nueva `NEUTRALIZAR_DOCUMENTO` en `grafo.py`). `app/application/asistente/documento.py` clasifica el tipo (política, contrato con proveedor, aviso) y mide la **densidad de entidades personales**: sobre `ASISTENTE_MAX_DENSIDAD_PII` el archivo parece un listado de personas y se rechaza **antes del LLM**. El archivo **no se guarda**: solo su huella SHA-256 y metadatos (`asistente_documento`).

**C4 · Human-in-the-Loop.** `asistente_propuesta` guarda lo propuesto, lo confirmado, los campos que editó el usuario, quién y cuándo decidió, el **modelo**, la **versión del prompt** y la **traza** (`llamadas_llm.traza_id`). Al aceptar se llaman `MapaDatosCasos.crear_elemento/crear_flujo` (`origen="ia"`, `propuesta_ia_id`) o `RegistroActividadesCasos.crear` (entra como **borrador**): mismas validaciones, versionado del mapa, revisión de actividades afectadas y bitácora. Las referencias `nuevo:<clave>` se resuelven al aceptar (409 `DEPENDENCIA_PENDIENTE` si falta aceptar el elemento que usan). En PostgreSQL `trg_asistente_propuesta_decision` impide borrar propuestas y modificar una ya decidida.

**C5 · Guardarraíles del tutor.** Skill `asistente_rat`:
- *scope locking*, ética y canario en `app/application/ai/prompts/asistente_rat.py` (`asistente_rat/1.0.0`);
- filtro de entrada: la **respuesta** se bloquea (sin NER ni LLM); el **documento** y los **nombres del mapa** (texto de la empresa) se neutralizan línea por línea;
- **NER antes del LLM**: los tres textos son `campos_no_confiables` de la política, así que pasan por `AIGateway._sanitizar()` (el gateway rechaza cualquier otro campo). Además las propuestas se vuelven a anonimizar antes de guardarse y lo que se guarda de la respuesta es exactamente lo que vio el LLM;
- salida: `app/application/asistente/salida_ia.py` (canario o fuga del prompt → se descarta todo; código y enlaces se limpian; «fuera de alcance» sin propuestas) y anclaje a catálogos y al mapa (`anclaje.py`, con `normalizar_elemento/normalizar_flujo/rat.modelo.normalizar` de forma tolerante);
- cuota diaria por empresa (respuestas y documentos), ráfaga por minuto y cuota global del LLM; si el servicio falla, la cuota se devuelve;
- bitácora encadenada: `asistente.*` (huellas HMAC, códigos y conteos; nunca texto) y eventos de seguridad con origen `asistente` / `asistente_documento`.

**C6 · Degradación (como HU-16).** IA deshabilitada, caída, limitador caído o cuota agotada → la respuesta se guarda (anonimizada), la entrevista avanza, se avisa por qué (`AVISOS`) y se ofrecen las sugerencias de la evaluación y las plantillas del mapa. Todo se completa a mano con las pantallas de siempre.

## Estructura

| Capa | Archivo | Qué hace |
|---|---|---|
| Aplicación | `app/application/asistente/` | banco, contexto, documento, salida_ia, anclaje, inconsistencias (lógica pura) |
| Aplicación | `app/application/use_cases/asistente_rat.py` | Entrevista, propuestas, documentos, aceptar/descartar |
| IA | `app/application/ai/prompts/asistente_rat.py`, `schemas/asistente_rat.py` | System prompt versionado y salida estructurada |
| IA | `politicas.py`, `agente/grafo.py`, `infrastructure/llm/factory.py` | Tarea, skill, nodos `asistente` y `validar_asistente` |
| Dominio | `app/domain/rat/cobertura.py` | Flujos sin actividad |
| API | `app/api/routes/asistente_rat.py` | 8 rutas bajo `/api/asistente` (`empresa_con_servicio`) |
| Modelos | `app/domain/models/asistente.py` | 4 tablas; `origen='ia'` en mapa y RAT |
| Migración | `migrations/versions/a3f9c1e7b5d2_hu39_asistente_rat.py` | Después de `e8c4b2f6a1d9` |
| Cambios | `mapa_datos.py`, `registro_actividades.py` | `origen` y `propuesta_ia_id` opcionales al crear |
| Inventario | `app/core/catalogo_datos_personales.py` | Columnas nuevas (T-06) |
| Pruebas | `tests/test_hu39_asistente_rat.py` | 34 de lógica y agente + 6 de API en proceso (Docker) |

## Configuración (`.env.example`)

`ASISTENTE_IA_HABILITADA`, `ASISTENTE_RESPUESTAS_DIA_EMPRESA` (60), `ASISTENTE_RESPUESTAS_MINUTO_EMPRESA` (6), `ASISTENTE_DOCUMENTOS_DIA_EMPRESA` (10), `ASISTENTE_MAX_CHARS_RESPUESTA`, `ASISTENTE_MAX_CHARS_DOCUMENTO_LLM`, `ASISTENTE_DOCUMENTO_MAX_MB`, `ASISTENTE_MAX_DENSIDAD_PII`, `ASISTENTE_MAX_PENDIENTES`, `ASISTENTE_MODELO`, `ASISTENTE_MAX_TOKENS_SALIDA`, `ASISTENTE_TIMEOUT_S`, `ASISTENTE_TEMPERATURA`.

## Riesgo residual

El NER cubre RUT, nombres, correos, teléfonos, direcciones y datos codificados; **no** detecta un diagnóstico o un número de cuenta escrito en prosa. La regla «nunca datos de titulares» se sostiene en capas: preguntas sobre procesos (no personas), rechazo de listados por densidad, solo pasajes relevantes del documento, prompt que prohíbe pedir o repetir datos personales y NER de la salida antes de guardar.

## Pendiente de decisión

- Aceptar una propuesta es en dos pasos (el caso de uso del mapa/RAT confirma su propio cambio y luego se cierra la propuesta). Si el segundo paso fallara, el elemento queda creado y la propuesta sigue «por revisar»; aceptarla otra vez da 409 `NOMBRE_DUPLICADO` y se descarta a mano.
- Las inconsistencias que el modelo menciona por su cuenta no se muestran: se muestran solo las que calcula el backend (deterministas).

## v1.1 · Respuestas que fallaban con «La ayuda automática no respondió esta vez»

**Causa.** Cada consulta del asistente pesaba unos 6.000 tokens de entrada y la salida era larga (el modo estricto obliga a escribir todos los campos de cada propuesta: ~35 por propuesta). Con el límite de tokens por minuto del plan del proveedor, dos respuestas seguidas lo superaban (`llamadas_llm.tipo_error = 'rate_limit'`); también podía cortarse la salida (`salida_invalida`).

**Cambios.**
- Salida más corta: cada propuesta trae solo el bloque de su tipo (`elemento`, `flujo` o `actividad`) y los otros van en `null`; máximo 6 propuestas (`schemas/asistente_rat.py`, `anclaje.plano()`).
- Entrada más corta: los catálogos van solo con sus códigos (`contexto.catalogos_texto`). Prompt `asistente_rat/1.1.0`.
- Si la ayuda falla por algo pasajero, **la pregunta no avanza ni se guarda nada**: 503 `AYUDA_NO_DISPONIBLE` con `tipo_error`, la cuota se devuelve y el rechazo queda en la bitácora (`error_ia`). La pantalla ofrece **Volver a intentar** o **Guardar sin ayuda** (`sin_ia: true`, guarda la respuesta anonimizada y avanza). La IA deshabilitada o la cuota diaria agotada siguen degradando sin error (C6).

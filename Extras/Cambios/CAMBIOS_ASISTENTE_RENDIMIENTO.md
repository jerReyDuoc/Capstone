# CAMBIOS · Asistente de registro: deja de responder tras unas 7 preguntas

Corrección sobre HU-39 (asistente de IA del mapa y del RAT). Toca backend y frontend. Sin migración.

## Síntoma

Después de unas 7 respuestas el asistente tardaba cada vez más y terminaba sin responder: los puntitos quedaban
girando y, al reenviar, no pasaba nada.

## Causas encontradas

1. **La sesión quedaba bloqueada mientras trabajaba la IA.** `responder()` leía la entrevista con
   `SELECT … FOR UPDATE` y la mantenía bloqueada durante toda la llamada al LLM. Si el navegador se rendía
   (el BFF espera 90 s) y el usuario reenviaba, la segunda petición quedaba esperando el bloqueo de la primera.
2. **No había un tiempo total.** Cada intento al proveedor esperaba hasta 60 s y, con los reintentos del SDK
   ante un 429 y el reintento por salida inválida, una respuesta podía tardar varios minutos: mucho más que
   los 90 s del navegador.
3. **El prompt crecía con cada pregunta.** Cada respuesta deja hasta 6 propuestas y TODAS las pendientes (y las
   aceptadas) viajaban en cada llamada: de ~3.600 a ~4.900 tokens de entrada tras unas pocas preguntas, más
   6.000 tokens de salida reservados. Con el límite de tokens por minuto del proveedor eso provocaba 429 y
   esperas cada vez más largas.

## Qué se cambió

| Cambio | Dónde |
|---|---|
| La sesión se lee sin bloquear; se bloquea solo al guardar y se confirma que nadie avanzó la pregunta mientras trabajaba la IA (si otra pestaña lo hizo: 409 `PREGUNTA_YA_RESPONDIDA`, no se guarda nada) | `app/application/use_cases/asistente_rat.py` (`responder`, `_responder`, `_sesion` con `populate_existing`) |
| Una respuesta a la vez por entrevista: un segundo envío mientras se analiza el primero responde 409 `RESPUESTA_EN_PROCESO` al instante (antes esperaba); el turno se suelta al terminar | `_tomar_turno` / `_soltar_turno` (limitador, clave `asistente:procesando:<sesión>`) |
| Tiempo total de la ayuda automática por respuesta o documento: `ASISTENTE_TIEMPO_MAXIMO_S` (70 s, entre 10 y 85). Al superarlo: 503 `AYUDA_NO_DISPONIBLE` con `tipo_error: timeout`, la pregunta no avanza, nada se guarda y la cuota se devuelve (el usuario reintenta o guarda sin ayuda, como ya existía) | `_proponer` |
| El modelo ve solo las `ASISTENTE_PENDIENTES_EN_PROMPT` (15) propuestas pendientes más recientes; las aceptadas ya están en el mapa con su id. El anclaje sigue validando contra todas | `_proponer` |
| `ASISTENTE_MAX_TOKENS_SALIDA` 6000 → 4000 y `ASISTENTE_TIMEOUT_S` (por intento) 60 → 45 | `app/core/config.py`, `Proyecto/.env.example` |
| La pantalla explica la espera según los segundos ("Sigo analizando…", "puede demorar hasta un minuto") y, ante una respuesta en curso u otra pestaña, avisa y recarga la entrevista | `lib/asistente.ts` (`textoEspera`, códigos nuevos), `components/empresa/asistente/AsistenteRegistro.tsx`, `asistente.module.css` |

## Pruebas

`tests/test_hu39_asistente_rat.py` (3 nuevas): la ayuda lenta se corta a tiempo sin avanzar ni gastar cuota y
el reintento funciona; una respuesta a la vez (409 y el turno se suelta al terminar); el prompt no crece con
cada pregunta. `tests/asistente.test.ts`: textos de espera y códigos. Suite del backend en este entorno:
1449 aprobadas (las 15 que no pasan aquí son las del SDK de Groq y la cola ARQ, sustituidos en este entorno).

## Si vuelve a pasar

- Revisa en el audit log `asistente.respuesta` con resultado `rechazado`: `error_ia` dice si fue `rate_limit`
  (límite del proveedor) o `timeout`.
- Si es `rate_limit` seguido, baja `ASISTENTE_MAX_TOKENS_SALIDA` (p. ej. 3000) o `ASISTENTE_PENDIENTES_EN_PROMPT`,
  o usa un plan del proveedor con más tokens por minuto.
- La ráfaga propia (`ASISTENTE_RESPUESTAS_MINUTO_EMPRESA`, 6 por minuto) responde 429 `ASISTENTE_RAFAGA` con un
  mensaje claro; no deja la pantalla colgada.

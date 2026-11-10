# HU-33 · Detector de prompt injection con contexto (evidencias vs. ataques)

> Como Oficial de Cumplimiento, quiero que el detector de prompt injection distinga un ataque de un
> documento de cumplimiento legítimo, para que las empresas puedan subir sus políticas, actas y
> registros sin que se bloqueen por usar palabras normales, sin perder la protección contra
> manipulación del LLM.

## Idea

`seguridad.py` revisa ahora cada texto con un **perfil**:

| Perfil | Se usa en | Cómo revisa |
|---|---|---|
| `justificacion` (por defecto) | justificación del cuestionario y de la remediación, chat del tutor, instrucciones de borradores | **Estricto**: todas las reglas con su patrón original (igual que antes de HU-33). |
| `evidencia` | el texto extraído del archivo de evidencia | Las **señales fuertes** se aplican igual. El vocabulario de cumplimiento solo cuenta cuando va **dirigido a la IA o al resultado**. |

Cada regla tiene un identificador (`manipulacion.aprueba`, `oculto.bidi`,
`codificado.base64>inyeccion.ignorar_instrucciones`...). En el perfil evidencia una regla puede ser:

- **fuerte**: el mismo patrón (texto oculto, bidi/"tag", codificado, "si eres una IA", "nota para el asistente", delimitadores falsos, roles de chat, cambio de rol, modo desarrollador, SQL/XSS/comandos, secretos...);
- **en imperativo**: el verbo cuenta solo si abre la cláusula como una orden ("Nota: marca...", "... y ejecuta esto", "• Elimina los registros"). Tras un sujeto ("El comité aprueba", "Se ejecuta", "el proceso elimina") es una descripción y no bloquea. Las etiquetas de tabla ("Aprueba: Gerente", "Ejecuta (R)") tampoco;
- **con objeto explícito**: "aprueba **este control**", "marca **como cumplido**", "ejecuta **la función**", "**tus** reglas";
- **contextual**: la mención solo cuenta si la misma oración se dirige a la IA o al resultado ("si eres", "tus instrucciones", "este control", "como cumplido", "dime", "para el asistente"...). Ej.: "jailbreak", "sudo", "modo mantenimiento", "actúa como", "texto oculto", "base64", líneas de log con fecha y hora.

## Criterios de aceptación

| Criterio | Cómo se cumple | Prueba |
|---|---|---|
| 1. Documentos legítimos no se bloquean | Perfil `evidencia` en `process_evidence.py`. "aprueba" en una RACI, "acciones ejecutadas", "las consultas se ejecutan con un usuario de solo lectura", "se registra la huella del documento", "anular sus reglas" en un informe de seguridad pasan y llegan al LLM. | `test_hu33_detector_contexto.py::test_c1_*`, `test_hu33_integracion.py::test_evidencia_de_cumplimiento_llega_al_llm` |
| 2. Palabras sensibles solo con contexto | Reglas en imperativo / con objeto explícito / contextuales. "aprueba este control", "marca como cumplido", "ejecuta la función", "ignora tus reglas" se siguen bloqueando, también dentro de un documento largo. | `test_c2_*` |
| 3. Señales fuertes igual de estrictas | Bidi, "tag", controles e invisibles se revisan antes que todo; el contenido codificado (base64, hex, base32) se decodifica y se revisa SIEMPRE con el perfil estricto; "si eres una IA", "instrucción para el asistente", delimitadores falsos y cambio de rol son reglas fuertes. | `test_c3_*` |
| 4. Viñetas no son caracteres de control | `normalizar_vinetas()`: `\x7f` como viñeta y U+F020–U+F0FF (Symbol/Wingdings) → "•"; se quitan el guion blando y el BOM. Se aplica en `extraer_texto()` y otra vez dentro del detector. Bidi y "tag" no se tocan; un `\x7f` en medio de una palabra sigue siendo control. | `test_c4_*`, `test_extraer_texto_normaliza_vinetas_y_conserva_bidi` |
| 5. Set de documentos legítimos con umbral | `tests/data/documentos_legitimos.jsonl`: **107 documentos** de 18 tipos (políticas, actas, RACI, registros, informes de seguridad que describen ataques, contratos, avisos, procedimientos...), con viñetas de PDF/Word. La prueba falla si la tasa de falsos positivos supera **5 %**. Resultado: **0/107 (0 %)** en perfil evidencia; con la revisión estricta anterior eran 68/107 (64 %). | `test_c5_*` |
| 6. Los ataques siguen bloqueados | El perfil estricto no cambió: el filtro del tutor (HU-18) mantiene 100 % en todas las categorías del test-set (inyección, fuga, jailbreak, delimitadores, codificado, variantes, multiturno, uso indebido) y los ataques de `test_seguridad_integracion.py` se bloquean. Además el perfil evidencia bloquea lo mismo que el estricto en inyección, fuga, delimitadores y codificado, y pierde a lo más 5 % en jailbreak/ofuscados (hoy pierde 0). | `test_hu18_*` (sin cambios), `test_c6_*` |
| 7. Justificación más estricta que evidencia | `create_respuesta.py`, `remediacion.py` y `process_evidence.py` revisan la justificación con `PERFIL_JUSTIFICACION`; solo la evidencia usa `PERFIL_EVIDENCIA`. | `test_c7_*`, `test_justificacion_estricta_aunque_la_evidencia_lo_permita` |
| 8. Cada bloqueo es trazable | Nueva columna `eventos_seguridad.regla` (migración `d4b8e2f6a9c3`). `RegistrarEventoSeguridad` la recibe y la sanea (solo `[a-z0-9_.:>-]`, máx. 80): nunca guarda texto. La bandeja (HU-22) y `GET /api/seguridad/eventos` la devuelven y el panel la muestra junto a "Falso positivo". El tutor y los borradores registran también la regla del filtro del agente. | `test_c8_*`, `test_el_evento_guarda_la_regla_*`, `test_la_bandeja_muestra_la_regla` |
| 9. Ambos repositorios iguales | El repositorio ComplianceAI-Prompt-Injection **no está publicado** (no existe en GitHub; solo está el repo Capstone), así que la única copia vigente de `seguridad.py` es la de Capstone. El archivo sigue siendo autocontenido (solo biblioteca estándar) y compatible con la API anterior (`detectar_inyeccion(texto)`, `_variantes`, `_controles_sospechosos`, `_sospechoso`), para que pueda copiarse tal cual cuando ese repositorio se publique. Verificación en ese momento: `RUTA_REPO_PROMPT_INJECTION=<repo> pytest tests/test_hu33_detector_contexto.py -k copia` compara los SHA-256 (mientras no exista, la prueba se omite). | `test_c9_*` |
| 10. Suite completa y cobertura | Ver "Cómo probar". | — |

## Archivos

| Archivo | Cambio |
|---|---|
| `app/infrastructure/security/seguridad.py` | Reglas con identificador y perfil; `analizar()` → `Deteccion(bloquear, regla, categoria)`; `detectar_inyeccion(texto, perfil)`; `normalizar_vinetas()`; `REGLAS`; `clasificar_justificacion` informa la regla. |
| `app/domain/ports/prompt_guard_port.py` | `PERFIL_*`, `ResultadoGuard` y `analizar()` con implementación por defecto (los guards antiguos siguen funcionando). |
| `app/infrastructure/security/prompt_guard.py` | `ReglasPromptGuard.analizar(texto, perfil)`. |
| `app/application/use_cases/process_evidence.py` | Justificación estricta, evidencia con perfil `evidencia`; la regla viaja al evento. |
| `app/application/use_cases/create_respuesta.py`, `remediacion.py` | Perfil estricto explícito y regla en el evento. |
| `app/application/use_cases/registrar_evento_seguridad.py` | Parámetro `regla` (saneado) y en el log del servidor. |
| `app/application/use_cases/tutor_ia.py`, `borradores.py` | Pasan la regla del filtro del agente al evento. |
| `app/application/evidencias/archivos.py` | `extraer_texto()` normaliza viñetas (PDF, DOCX y TXT). |
| `app/domain/models/evento_seguridad.py`, `migrations/versions/d4b8e2f6a9c3_hu33_regla_evento_seguridad.py` | Columna `regla` (String 80, NULL, con índice). |
| `app/core/catalogo_datos_personales.py` | `eventos_seguridad.regla` clasificada como sin datos personales (T-06). |
| `app/application/use_cases/bandeja_revision.py`, `app/api/routes/seguridad.py` | Devuelven `regla`. |
| `frontend-next/lib/admin/revision.ts`, `components/admin/BandejaRevision.tsx` | Muestran la regla en el detalle del evento. |
| `tests/data/documentos_legitimos.jsonl` | Corpus de 107 documentos legítimos. |
| `tests/test_hu33_detector_contexto.py` | Pruebas del motor (no requieren BD). |
| `tests/test_hu33_integracion.py` | Pruebas de integración con los dobles de `test_seguridad_integracion.py`. |

## Cómo probar (Docker)

```bash
docker compose build worker
docker compose up -d
docker compose exec worker alembic upgrade head
docker compose exec worker pytest tests --cov=app --cov-report=term-missing
# Solo HU-33:
docker compose exec worker pytest tests/test_hu33_detector_contexto.py tests/test_hu33_integracion.py -v
# Copias idénticas (montando el otro repo en el contenedor o corriendo en local):
RUTA_REPO_PROMPT_INJECTION=../ComplianceAI-Prompt-Injection pytest tests/test_hu33_detector_contexto.py -k copia
```

## Notas

- El extracto anonimizado del evento (HU-22/T-06) se mantiene: la regla se agrega como un campo propio, sin texto del usuario, y es lo que se escribe en el log del servidor.
- Latencia del perfil evidencia: ~0,2 s para un fragmento de 8.000 caracteres (`MAX_CHARS_EVIDENCIA_LLM`), dentro del worker; el perfil estricto no cambia (~5 ms).
- Para afinar: si el Oficial de Cumplimiento marca como **falso positivo** varios eventos con la misma `regla`, esa es la regla a revisar en `seguridad.py`; agregar el documento al corpus evita que el error vuelva.
- El corpus es sintético (escrito para la prueba). Conviene agregarle las evidencias reales de prueba del diagnóstico cuando estén disponibles (una línea JSON por documento: `id`, `tipo`, `texto`).

# HU-22 · Bandeja de revisión del Oficial de Cumplimiento (backend)

> Como Oficial de Cumplimiento, quiero revisar en una bandeja las divergencias del LLM y los
> eventos de seguridad, para confirmar o corregir la clasificación final y tener una verdad de
> referencia para medir el LLM.

| Criterio | Cómo se cumple |
|---|---|
| 1. Listado filtrable de pendientes | `GET /api/admin/revision/bandeja` con vista, estado, motivo, evaluación, dimensión, criticidad, origen del evento, orden y paginación. Devuelve además los contadores de pendientes para las pestañas y los filtros. |
| 2. Confirmar o corregir con comentario | El `PATCH /api/respuestas/{id}/revision` existente ahora exige `comentario` (10 a 1000 caracteres, anonimizado antes de guardar) y responde si la revisión fue **confirmada** (deja la vigente) o **corregida** (la cambia). Nuevo `PATCH /api/seguridad/eventos/{id}/revision` con `resolucion` (`ataque_confirmado` / `falso_positivo`) y comentario. |
| 3. Cada revisión en el audit log | `respuesta.revision_humana` (ya existía) ahora lleva la decisión, lo declarado por el usuario, lo que propuso el LLM, la revisión previa y la **huella HMAC y el largo** del comentario (el log nunca guarda texto libre, regla de HU-09). Nueva acción `seguridad.evento_revisado` (categoría modificación) para los eventos, también desde el `PATCH /revisado` antiguo. El historial de cada respuesta en la bandeja se lee del audit log. |

## Qué entra a la bandeja

Una respuesta entra si el LLM o la capa de seguridad la tocaron. Sus motivos, en orden de urgencia:

1. `seguridad`: tiene eventos de prompt injection o la bloqueó la capa de seguridad.
2. `divergencia`: el LLM propuso una clasificación distinta de la declarada (en remediación HU-17, distinta de la que la empresa dice haber alcanzado).
3. `sin_resolver`: sigue en `requiere_revision`.
4. `baja_confianza`: el LLM respondió bajo `UMBRAL_CONFIANZA` y se mantuvo lo declarado.
5. `resuelta_por_llm`: el usuario declaró `requiere_revision` y la cerró el LLM.
6. `concordante`: el LLM respaldó al usuario. No es urgente: solo aparece filtrando por ese motivo, para muestrear también los aciertos del modelo.

Está **pendiente** si nunca se revisó o si, después de revisada, una evidencia nueva volvió a cambiar su clasificación (la fuente dejó de ser `revision`). Siempre se usa la última evidencia procesada por el LLM.

## Verdad de referencia

`GET /api/admin/revision/resumen` compara la última clasificación del LLM de cada respuesta revisada con la del oficial usando la misma función que `/api/ia/metricas` (accuracy, F1 macro y matriz de confusión), y cuenta confirmadas/corregidas, ataques confirmados, falsos positivos y la precisión de la detección.

## Otros cambios

- Si se **corrige** una respuesta de una evaluación ya cerrada, se recalcula su resumen (puntaje y radar), igual que en la remediación HU-17. Si el recálculo falla, la revisión igual queda guardada y se registra en el log del servidor.
- `GET /api/admin/revision/respuestas/{id}`: detalle con el control, la justificación del usuario (anonimizada), las evidencias con el razonamiento del LLM, los eventos y el historial de revisiones.
- Todas las rutas nuevas son solo `admin_therion` (401 sin token, 403 otros roles) y quedaron en la matriz de `tests/test_hu20_autorizacion.py`.
- T-06: columnas nuevas clasificadas en `app/core/catalogo_datos_personales.py` (los comentarios se escanean en busca de PII).

## Archivos

| Archivo | Cambio |
|---|---|
| `migrations/versions/c7d3e9a1f5b8_hu22_bandeja_revision.py` | **Nuevo.** Columnas `comentario_revision`, `decision_revision`, `revisor_admin_id` en `respuestas`; `resolucion`, `comentario_revision`, `fecha_revision`, `revisor_admin_id` en `eventos_seguridad`; dos índices. Revises `f8c2a6d4e1b7` (HU-24). |
| `app/application/use_cases/bandeja_revision.py` | **Nuevo.** Motivos, prioridad, listado, detalle, historial y verdad de referencia. |
| `app/api/routes/admin_revision.py` | **Nuevo.** Rutas `/api/admin/revision/*`. |
| `app/api/routes/respuestas.py` | PATCH `/revision` con comentario, decisión, auditoría ampliada y recálculo. |
| `app/api/routes/seguridad.py` | PATCH `/eventos/{id}/revision`; `/revisado` ahora auditado. |
| `app/domain/models/respuesta.py`, `evento_seguridad.py` | Columnas nuevas, `DecisionRevision`, `ResolucionEvento`. |
| `app/infrastructure/repositories/bitacora_repository.py` | Acción `seguridad.evento_revisado`. |
| `app/core/catalogo_datos_personales.py` | Columnas nuevas (T-06). |
| `app/main.py` | Registra el router. |
| `tests/test_hu22_bandeja_revision.py` | **Nuevo.** Lógica pura + API en proceso (C1, C2, C3 y eventos). |
| `tests/test_hu20_autorizacion.py` | Rutas nuevas en la matriz de autorización. |
| `tests/test_hu02…`, `test_hu09…`, `test_hu19…`, `test_e2e_capa_ia.py`, `test_live_capa_ia.py` | Agregan el `comentario` ahora obligatorio. |

## Compatibilidad

Cualquier cliente que llame a `PATCH /api/respuestas/{id}/revision` sin comentario recibe ahora `422 COMENTARIO_REQUERIDO`. El frontend nuevo ya lo envía.

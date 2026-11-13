# CAMBIOS · HU-40 — Revisión interna del registro (modo de auditoría interna)

> *Como Usuario Definitivo, en su función de auditoría interna, quiero revisar el mapeo, el RAT y los informes en un
> modo de auditoría interna y dejar constancia de esa revisión, para verificar que el registro es fiel y está al día
> antes de presentarlo, certificarlo o informarlo al directorio.*

Toca backend y frontend. Pantalla: **Registro de actividades › Revisión interna** (`/empresa/registro-actividades/revision`).
Es el mismo usuario definitivo con contrato vigente: no hay roles ni cuentas nuevas.

---

## 1. Criterios de aceptación

| Criterio | Cómo se cumple |
|---|---|
| 1. Modo de revisión sin rol ni cuenta adicional, con lista de verificación por actividad y por elemento del mapa (campos completos, base de licitud, plazos, transferencias con garantía) | `app/domain/rat/revision.py` (lógica pura). **Actividad** (7 puntos): versión vigente y al día · campos obligatorios completos (ambos bloqueantes) · base de licitud · plazos de conservación · transferencias con garantía · terceros con contrato · decisiones automatizadas. **Elemento** (4): ficha completa · confirmado · considerado en el registro · contrato. **Flujo** (5): ficha completa · confirmado · garantía · cifrado · considerado en el registro. Cada punto trae el resultado automático y la pregunta que la persona confirma mirando la realidad. Las rutas usan `empresa_con_servicio` (el mismo usuario). |
| 2. Observaciones por actividad o elemento, se cierran al corregir; con observaciones abiertas no se marca la versión | `rat_observacion` (actividad, elemento, flujo o registro completo; prioridad alta/media/baja). Cierre con nota de qué se corrigió y registro de si el elemento cambió entre apertura y cierre. `requisitos()` bloquea la marca con `OBSERVACIONES_ABIERTAS` (409 `REVISION_INCOMPLETA`). No se borran (trigger). |
| 3. Marca de revisada con fecha y nombre; aparece en el informe RAT y queda en el audit log | `POST /marcar` fija en `rat_revision` la versión, la huella, la fecha, el nombre y cargo, la conclusión y una copia de la lista (inmutable con trigger). `InformeRatCasos.armar()` busca la revisión con la misma huella: el PDF lleva un recuadro «Revisada el … por …» en la portada y la línea en la verificación; el Excel, una fila en Portada y en Verificación; el correo del informe también. Tras marcar se emite el informe con la marca (`rat_informe.revision_id`). Audit log: `revision_rat.version_revisada`. |
| 4. Diferencias entre versiones y paquete de evidencia verificable con hash (como el ZIP de HU-09) | `GET /diferencias` (versión contra versión o contra el registro actual, campo por campo). `GET /revisiones/{id}/paquete`: ZIP determinista con el informe del registro, el informe de la revisión, la lista de verificación y las observaciones (CSV y JSON), las versiones de las actividades con su huella, el historial del audit log (con el hash de cada registro, sin IP), emisiones y diferencias, `manifiesto.json` (SHA-256 de cada archivo) y `verificar_paquete.py` (solo librería estándar: recalcula hashes y la huella del registro). Código `CIA-PAQ-AAAA-NNNNNN-D` y SHA-256 en `rat_paquete_evidencia`; `POST /paquetes/verificacion` confirma un ZIP subido. |
| 5. Recordatorio de revisión periódica (plazo configurable, 12 meses) | `rat_revision_config` (1 a 36 meses, aviso previo, correo sí/no). Estados al día / por vencer / vencida / sin revisión. Aviso en la lista del registro y en la página. Cron diario del worker (`recordar_revision_rat_task`, `REVISION_RAT_HORA_UTC`): un correo por etapa y repetición cada `REVISION_RAT_REPETIR_DIAS` mientras siga vencida; queda como acción del sistema en el audit log. |

Además: **informe de la revisión en PDF** (portada con cifras, conclusión, declaración con espacio para firma, resultado por criterio, detalle por actividad, mapa, aceptados con su justificación, observaciones, cambios desde la revisión anterior y verificación; marca de agua «EN CURSO» mientras no se marca) y **envío por correo** (informe y, si se quiere, el paquete).

## 2. Decisiones

- Se revisa lo que afirmaría el informe del registro: la **versión vigente** de cada actividad (no la copia de trabajo) y el mapa actual.
- **Verificar ≠ aprobar automáticamente**: la plataforma comprueba lo que puede; la persona confirma o acepta con justificación escrita (mín. 10 caracteres). Una falla no se puede "verificar": se corrige o se acepta. Las fallas **bloqueantes** (actividad sin versión vigente o con campos obligatorios vacíos) no se pueden aceptar, porque el informe saldría como borrador.
- Cada elemento revisado guarda su **huella**: si cambia después de verificarlo, su verificación queda «desactualizada» sola (no hay que acordarse de volver a mirarlo).
- Una sola revisión **en curso** por empresa (índice único parcial). Verificar u observar la comienza sola si no existe.
- La marca exige la misma huella que vio la persona (si el registro cambió mientras revisaba, se rechaza con `REGISTRO_CAMBIO`).
- La versión que se marca es la misma que tendrá el informe (correlativo de `rat_informe`). El informe se reemite si la marca es nueva aunque el registro no cambie.
- Minimización: las observaciones, justificaciones y la conclusión rechazan correos, RUT y teléfonos; el nombre de quien revisa solo admite letras. El audit log no guarda textos libres ni el nombre.

## 3. Archivos

**Backend (nuevos):** `app/domain/rat/revision.py`, `app/domain/rat/verificar_paquete.py`, `app/domain/models/rat_revision.py`,
`app/application/use_cases/revision_interna.py`, `app/application/rat/pdf_revision.py`, `paquete_revision.py`,
`correo_revision.py`, `app/api/routes/revision_interna.py`, `migrations/versions/b3e9d5a1c7f4_hu40_revision_interna.py`,
`tests/test_hu40_revision_interna.py`.

**Backend (modificados):** `rat/informe.py` (MarcaRevision), `pdf_rat.py`, `xlsx_rat.py`, `correo_rat.py` (la marca),
`use_cases/informe_rat.py` (busca la marca, reemite si es nueva, `revision_id`), `use_cases/registro_actividades.py`
(estado de la revisión periódica en la lista), `models/rat_informe.py`, `models/__init__.py`, `bitacora_repository.py`
(acciones `revision_rat.*`), `core/config.py` (ajustes `REVISION_RAT_*`), `main.py`, `worker/tasks.py`.

**Frontend (nuevos):** `app/empresa/(espacio)/registro-actividades/revision/page.tsx`,
`components/empresa/rat/revision/{RevisionInterna,ListaVerificacion,PanelesRevision}.tsx`, `revision.module.css`,
`lib/revisionInterna.ts`, `tests/revision_interna.test.ts`.

**Frontend (modificados):** `RegistroActividades.tsx` (botón «Revisión interna» y aviso de la revisión periódica),
`InformeRat.tsx` (muestra la marca o invita a revisar), `lib/informeRat.ts`, `lib/registroActividades.ts`,
`lib/servidor/proxyCliente.ts` (rutas permitidas y ZIP), `app/bff/cliente/api/[...ruta]/route.ts` (código del paquete).

## 4. Base de datos (migración `b3e9d5a1c7f4`, sobre `d7e3f1a9b2c4`)

`rat_revision`, `rat_observacion`, `rat_revision_config`, `rat_paquete_evidencia` y `rat_informe.revision_id`. Triggers en
PostgreSQL: revisión revisada inmutable (solo se le asigna una vez `informe_id`), observaciones sin borrado y con lo
observado fijo, paquetes inmutables y `rat_informe` protege también `revision_id`. Se aplica sola con
`docker compose up -d --build` (servicio `migrate`).

## 5. Ajustes nuevos (`.env`, todos con valor por defecto)

| Variable | Defecto | Para qué |
|---|---|---|
| `REVISION_RAT_PLAZO_MESES` | 12 | Plazo por defecto entre revisiones |
| `REVISION_RAT_AVISO_DIAS` | 30 | Anticipación del aviso |
| `REVISION_RAT_REPETIR_DIAS` | 30 | Repetición del correo si sigue vencida |
| `REVISION_RAT_HORA_UTC` | 12 | Hora del recordatorio diario (09:00 en Chile en verano) |
| `REVISION_RAT_PAQUETES_DIA` / `REVISION_RAT_CORREOS_DIA` | 20 / 5 | Límites diarios por empresa |
| `REVISION_RAT_PAQUETE_CORREO_MB` / `REVISION_RAT_PAQUETE_VERIFICAR_MB` | 8 / 12 | Tamaño del ZIP al correo y al verificar |
| `REVISION_RAT_URL` | `http://localhost:3000/empresa/registro-actividades/revision` | Enlace del recordatorio (en producción, https) |

## 6. Cómo probar

```powershell
docker compose up -d --build
docker compose run --rm --no-deps api pytest tests/test_hu40_revision_interna.py tests/test_hu36_informe_rat.py tests/test_hu35_rat.py -q
cd frontend-next; npm test -- revision_interna
```

Recorrido manual: deja vigente una actividad → Registro de actividades › **Revisión interna** › Comenzar → verifica los
puntos (acepta con justificación las fallas no bloqueantes) → deja una observación e intenta marcar (se bloquea) →
ciérrala → **Marcar como revisada** → abre el informe del registro (lleva la marca) → Constancias y evidencia: descarga el
PDF y el ZIP, ejecuta `python verificar_paquete.py .` en la carpeta descomprimida, súbelo en «Verificar un paquete» y
envíalo por correo (en desarrollo queda en `STORAGE_DIR/correos`). Cambia el plazo a 3 meses y revisa el aviso.

Verificado en este entorno: 15 pruebas puras del backend (más las de HU-35, HU-36, HU-37, HU-38 y HU-41 sin
regresiones), 10 pruebas del frontend y revisión de tipos de los archivos nuevos. Las 2 pruebas de API de HU-40 corren
en Docker (necesitan FastAPI, SQLAlchemy y aiosqlite).

## 7. Evidencias (`Extras/Evidencias/HU40/`)

`informe_revision_interna_ejemplo.pdf`, `informe_revision_en_curso_ejemplo.pdf`, `registro_actividades_con_marca_ejemplo.pdf`
y `.xlsx`, y `paquete_evidencia_ejemplo.zip` (verificable con su script).

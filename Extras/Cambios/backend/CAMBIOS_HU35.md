# HU-35 · Registro de Actividades de Tratamiento (RAT)

*Como Usuario Definitivo (cliente), quiero llevar el Registro de Actividades de Tratamiento (RAT) de mi empresa dentro de la plataforma, para cumplir la caracterización de actividades de tratamiento que exigen la Ley 21.719 y su reglamento.*

El RAT se construye **sobre el mapa de datos (HU-34)**: la actividad no repite sistemas, terceros ni categorías; los elige del mapa y calcula el resto. Se siguió el mismo patrón de la matriz versionada (HU-24) para la inmutabilidad.

## Decisiones del PO (11-nov)

| # | Pregunta | Decisión |
|---|---|---|
| 1 | ¿Quién aprueba (en revisión → vigente)? | El mismo usuario de la empresa |
| 2 | ¿Qué pasa al editar una vigente? | Se abre una **nueva versión en borrador**; la vigente sigue valiendo hasta que la nueva quede vigente |
| 3 | Cambio en el mapa que afecta una actividad | La vigente vuelve **automáticamente** a «en revisión» |
| 4 | Datos del mapa | El usuario elige el **subconjunto** de categorías que usa la actividad |
| 5 | Textos legales | Se redacta una **propuesta** (pendiente de validación legal) |
| 6 | Archivar | Una archivada se **reactiva sin duplicar** |
| 7 | Exportación RAT/RoPA a PDF/Excel | **Fuera de alcance** de esta historia |

## Criterios de aceptación

**C1 · 11 campos + medidas + rol.** `app/domain/rat/catalogo.py:CAMPOS` define los 13 campos (con su paso en el formulario y su texto de ayuda). Los condicionales: interés legítimo (si es la base), base para datos sensibles (si hay sensibles), garantía (si hay transferencias), lógica (si hay decisiones automatizadas) y organización mandante (si la empresa es encargada). «No aplica» se responde de forma explícita (sin destinatarios, sin decisiones automatizadas).

**C2 · Sin doble ingreso.** La actividad guarda solo `{id, categorias_datos, categorias_titulares}` de los elementos y flujos elegidos. `analisis.derivados()` calcula con el mapa actual: tipos de datos (sensibles primero), titulares (NNA), sistemas y bases, países (con `pais_efectivo` del mapa), terceros (elegidos o destino de un flujo elegido) y transferencias internacionales con su garantía. Si el mapa quita una categoría, deja de contarse; si elimina algo elegido, la actividad no puede quedar vigente hasta quitarlo.
`MapaDatosCasos._guardar` llama a `marcar_afectadas_por_mapa()` **antes del commit**: con las diferencias de la versión del mapa (`vinculo_mapa.afectadas`), las actividades que usan un elemento o flujo editado/eliminado —o un elemento que es extremo de un flujo elegido— anotan el motivo («Cambió en el mapa el tercero «Banco» (país)») y, si estaban vigentes, vuelven a revisión. Solo cambiar la marca «por confirmar» o crear algo nuevo no afecta. La respuesta del mapa trae `cambio.actividades_afectadas` y el panel lo avisa.

**C3 · Completitud.** Por actividad (`analisis.completitud`: porcentaje, faltantes con mensaje y paso, advertencias) y global (promedio de las no archivadas). `aprobar` con faltantes → 422 `ACTIVIDAD_INCOMPLETA` (queda `rat.cambio_rechazado` en el log).

**C4 · Estados e inmutabilidad.** `app/domain/rat/estados.py`. Al aprobar se guarda la instantánea completa (lo escrito + lo tomado del mapa con los nombres de ese momento) y su huella SHA-256 en `rat_actividad_version`; si la huella es igual a la última versión, no se crea otra. En PostgreSQL:
- `trg_rat_actividad_version_inmutable` rechaza `UPDATE` y `DELETE` de versiones;
- `trg_rat_actividad_vigente_inmutable` rechaza cambiar contenido, nombre o versión de una actividad mientras sigue vigente, que la versión vigente retroceda y borrar una actividad que estuvo vigente.

Todo cambio queda en el `audit_log` en la misma transacción: `rat.actividad_creada`, `rat.actividad_editada`, `rat.estado_cambiado`, `rat.version_vigente`, `rat.marcada_revision`, `rat.cambio_rechazado` (el detalle lleva ids, estados, códigos de campos y conteos; nunca los textos de la empresa).

**Concurrencia:** cada edición envía la `revision` de la actividad; si cambió (otra pestaña o el mapa) → 409 `ACTIVIDAD_DESACTUALIZADA`. **Minimización:** los textos se rechazan si traen correos, RUT o teléfonos; las tablas están en el inventario de T-06 con escaneo `pii`.

## Estructura

| Capa | Archivo | Qué hace |
|---|---|---|
| Dominio | `app/domain/rat/catalogo.py` | Campos, pasos, bases de licitud (y para sensibles), fuentes, plazos, medidas, roles, estados y textos de ayuda |
| Dominio | `app/domain/rat/modelo.py` | Validación y normalización (ediciones parciales, coherencia de condicionales) |
| Dominio | `app/domain/rat/analisis.py` | Lo que se toma del mapa y la completitud |
| Dominio | `app/domain/rat/estados.py` | Transiciones permitidas |
| Dominio | `app/domain/rat/versiones.py` | Instantánea, huella, diferencias por campo |
| Dominio | `app/domain/rat/vinculo_mapa.py` | Qué actividades afecta un cambio del mapa |
| Aplicación | `app/application/use_cases/registro_actividades.py` | Casos de uso y `marcar_afectadas_por_mapa` |
| API | `app/api/routes/registro_actividades.py` | 8 rutas bajo `/api/registro-actividades` (`empresa_con_servicio`) |
| Modelos | `app/domain/models/rat.py` | `rat_actividad`, `rat_actividad_version` |
| Migración | `migrations/versions/d1e5b8a3c7f2_hu35_registro_actividades.py` | Tablas, índices y triggers (después de `b9e3d7a2c5f1`) |
| Cambios | `app/application/use_cases/mapa_datos.py` | Llama al vínculo con el RAT y devuelve `actividades_afectadas` |
| Cambios | `app/infrastructure/repositories/bitacora_repository.py` | Acciones `rat.*` y su categoría |
| Cambios | `app/core/catalogo_datos_personales.py` | Clasificación T-06 de las tablas nuevas |
| Frontend | `components/empresa/rat/*`, `lib/registroActividades.ts`, `app/empresa/(espacio)/registro-actividades/page.tsx` | Lista, formulario por pasos, estados, historial |
| Frontend | `lib/servidor/proxyCliente.ts`, `components/shell/Sidebar.tsx`, `lib/mapaDatos.ts`, `components/empresa/mapa/MapaDatos.tsx` | Lista blanca, menú «Registro de actividades» y aviso en el mapa |

## Pruebas

- `tests/test_hu35_rat.py`: 38 de lógica pura (catálogo, validación, derivados con subconjunto, transferencias, completitud y condicionales, «no aplica», lo eliminado del mapa, estados y decisiones del PO, versiones y huella, vínculo con el mapa, textos sin códigos internos) + 3 de API en proceso (contrato, ciclo completo con cambio del mapa, versiones inmutables, reactivación sin duplicar y audit log; aislamiento).
- `frontend-next/tests/registro_actividades.test.ts`: vista previa del mapa, cambios del formulario, plazos, lista y filtros, aviso del mapa y lista blanca del proxy.

Correr: `docker compose exec api pytest tests/test_hu35_rat.py tests/test_hu34_mapa_datos.py tests/test_t06_minimizacion.py -q` y `npm test` en `frontend-next`.

---

## Propuesta para revisión de asesoría legal

Todo el texto que ve el cliente sobre el RAT está en `app/domain/rat/catalogo.py`. El catálogo publica `revision_legal.estado = "pendiente_validacion_legal"` y la pantalla muestra el aviso «Los textos de ayuda de este registro son una guía general y no reemplazan la asesoría legal de tu empresa». Para aprobar: ajustar textos y referencias, cambiar `ESTADO_REVISION_LEGAL` a `"validado"`, anotar `FECHA_REVISION_LEGAL` y subir `VERSION_TEXTOS`.

**Puntos a validar en especial:**

1. **Bases de licitud** (referencias orientativas: art. 12 consentimiento; art. 13 demás fuentes): consentimiento, ejecución de contrato, obligación legal, interés legítimo, ejercicio o defensa de un derecho, funciones legales de un organismo público. ¿Falta o sobra alguna? ¿Las referencias a artículos son correctas tras la Ley 21.719?
2. **Bases para datos sensibles** (art. 16 y siguientes): consentimiento expreso, datos que el titular hizo públicos, interés vital o urgencia médica, obligaciones laborales o de seguridad social, ejercicio o defensa de un derecho, autorización legal, fines históricos/estadísticos/científicos. ¿Corresponde separar salud, perfil biológico y biometría con sus propias reglas?
3. **Interés legítimo**: hoy se pide describir el interés y su ponderación; se advierte que no basta para datos sensibles.
4. **Plazos de conservación**: plazo + unidad + desde cuándo se cuenta + fundamento opcional, por categoría de datos. ¿Debe exigirse el fundamento?
5. **Decisiones automatizadas**: se pide la lógica (obligatoria), los efectos y si una persona puede revisar la decisión (recomendación, no bloqueante).
6. **Transferencias internacionales**: se calculan con los países del mapa y la garantía se registra en el flujo; hoy una garantía «válida» es cualquiera distinta de «sin garantía documentada».
7. **Textos de ayuda de los 13 campos y de los 4 estados** (ver `CAMPOS` y `ESTADOS`).

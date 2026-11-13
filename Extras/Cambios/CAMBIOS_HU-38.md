# CAMBIOS · HU-38 — El registro de actividades conectado con el resto del cumplimiento

> *Como Oficial de Cumplimiento, quiero que las actividades de mayor riesgo del RAT se identifiquen solas y se
> conecten con mi evaluación, mis brechas y mis borradores, para que el registro no sea un documento aislado y
> alimente el resto de mi cumplimiento.*

Toca backend y frontend. Pantallas: **Mi empresa** (`/empresa`), **Registro de actividades**
(`/empresa/registro-actividades`) y **Borradores de cumplimiento** (`/empresa/borradores`). Sin tablas nuevas ni
migración.

---

## 1. Qué se hizo

| Criterio | Cómo se cumple |
|---|---|
| 1. Riesgo con reglas explicables; las de mayor riesgo forman la matriz (Decreto 662, art. 3 letra e) y se recomienda una PIA | `app/domain/rat/riesgos.py` (base de HU-36) suma dos factores: **uso de inteligencia artificial** (sistemas con IA, bases vectoriales o proveedores de IA que la actividad elige del mapa o que son extremo de un envío elegido; probabilidad +1) y **gran volumen de personas** (dato nuevo y opcional `volumen` de la actividad; impacto +1 entre 10.000 y 100.000 personas, +2 sobre 100.000). Los demás factores (sensibles, NNA, transferencias sin garantía, decisiones automatizadas…) siguen igual. `motivos_pia()` dice por qué se recomienda una evaluación de impacto (riesgo alto o crítico; decisiones automatizadas o perfilamiento; sensibles o NNA a gran escala; IA con sensibles o NNA) y `matriz_mayor_riesgo()` arma la matriz. Cada actividad trae su `riesgo` en `GET /api/registro-actividades`; el PDF y el Excel del informe del registro agregan la tabla **Actividades de mayor riesgo** con la evaluación de impacto recomendada |
| 2. La PIA se pre-llena con las actividades de alto riesgo y el aviso de privacidad toma finalidades y bases | `app/application/borradores/registro.py` lee el mismo armado del informe del registro (versión **vigente** de cada actividad). **PIA**: actividades con evaluación recomendada (o las que elija la empresa, `actividades` en `POST /api/borradores`, máximo 10): identificación, por qué se recomienda, descripción sistemática (finalidad, titulares, datos, origen, sistemas, proveedores, ubicación, transferencias, decisiones y versión del registro), base de licitud, tabla de riesgos del registro y medidas sugeridas. **Aviso**: tabla finalidad → base que la autoriza, categorías de datos, proveedores, transferencias, sensibles/NNA, uso de IA y plazos, sin nombrar sistemas internos. `generador.generar_markdown(..., registro=)` usa esos textos en vez de la plantilla y del Agente IA, con una nota para revisarlos |
| 3. Un RAT vigente y completo cuenta como evidencia, actualiza puntaje y brechas como una evidencia de HU-17 y nunca baja un control | `app/domain/rat/cumplimiento.py` define qué demuestra el registro **vigente y completo** (todas las actividades vigentes, completas, sin cambios del mapa por revisar y sin envíos del mapa fuera del registro): registro actualizado y base de licitud (cumplido), finalidades (parcial), transferencias con garantía (cumplido, si hay), contratos con encargados (cumplido o parcial, si hay) y medidas reforzadas con sensibles/NNA (parcial). `app/application/use_cases/cumplimiento_rat.py` lo aplica en la evaluación **completada** más reciente **solo si mejora** el estado: respuesta con fuente `rat`, brecha sincronizada, fila en `evidencias` (origen `rat`, sin archivo, huella del registro), resumen y radar recalculados control por control (aparece en la evolución del puntaje de la remediación) y `rat.evidencia_aplicada` en el audit log. Se ejecuta solo al dejar vigente una actividad y con el botón de Mi empresa (`POST /api/registro-actividades/cumplimiento/evidencia`) |
| 4. El espacio de la empresa muestra el estado del mapeo y del RAT y sus brechas con su ruta (HU-12/HU-26) | `GET /api/registro-actividades/cumplimiento` y el componente **Protección de datos personales** de Mi empresa: tarjetas del mapa, del registro, de las actividades de mayor riesgo y de la evaluación; lo que el registro respalda; la matriz de mayor riesgo con acceso a la PIA; y las brechas **actividad sin base de licitud**, **sin plazo**, **transferencia sin garantía** y **envío sin actividad**, cada una con su ruta: corregir (abre la actividad en su paso o el mapa), el **módulo formativo** del plan con su avance y **re-evaluar el control** en la remediación |

## 2. Decisiones (para validar con el PO)

- **Evidencia solo con el registro vigente y completo.** Un registro a medio hacer no mejora nada; el panel dice qué falta. Qué control respalda el registro y con qué estado vive en `APORTES` de `cumplimiento.py` (propuesta: finalidades y medidas reforzadas quedan en *parcial*, porque el registro las documenta pero no demuestra que se informen o se apliquen).
- **Nunca baja un control.** Tampoco toca un control "no aplica" ni lo que ya está igual o mejor. Si después el registro queda incompleto, la evaluación no retrocede (igual que una remediación).
- **Automático al dejar vigente.** Además del botón. Si falla, la aprobación ya quedó hecha y solo se registra el error.
- **Volumen opcional.** No es uno de los 13 campos obligatorios: no cambia la completitud. Solo se guarda si tiene valor, así las huellas de las versiones ya vigentes no cambian.
- **Uso de IA desde el mapa actual.** La instantánea de una versión vigente no guarda el subtipo de los elementos; el riesgo lo calcula con el mapa de hoy.
- **El aviso usa todas las actividades activas** (con aviso si alguna no está vigente); la PIA, las recomendadas o las elegidas.
- **Ruta de remediación**: el módulo formativo es el que el catálogo de brechas asocia al control (HU-12), con el avance de la empresa (HU-26); re-evaluar enlaza a la remediación del control (HU-17) si sigue con brecha.

## 3. Archivos

**Backend (nuevos)**

| Archivo | Qué hace |
|---|---|
| `app/domain/rat/cumplimiento.py` | Lógica pura: estado del registro, aportes a los controles, regla de "solo mejora" y brechas del registro con su paso |
| `app/application/use_cases/cumplimiento_rat.py` | Resumen para Mi empresa, matriz de mayor riesgo, aplicar el registro como evidencia (con recálculo y bitácora) y el disparo al aprobar |
| `app/application/borradores/registro.py` | Textos de la PIA y del aviso de privacidad desde el informe del registro |
| `tests/test_hu38_integracion_rat.py` | 14 pruebas (9 puras y 5 de API) |

**Backend (modificados)**

| Archivo | Cambio |
|---|---|
| `app/domain/rat/riesgos.py` | Factores IA y volumen, `motivos_pia`, `matriz_mayor_riesgo`, `REFERENCIA_MATRIZ`, `METODOLOGIA_PIA` |
| `app/domain/rat/catalogo.py`, `modelo.py`, `versiones.py` | Opción `volumen` (`VOLUMENES`), clave opcional que solo se guarda con valor y su título en el historial |
| `app/domain/rat/analisis.py`, `app/domain/catalogo_tratamiento.py` | `sistemas_ia` en lo que la actividad toma del mapa y `sistemas_ia_en()` para versiones vigentes; `SUBTIPOS_IA` |
| `app/application/rat/informe.py`, `pdf_rat.py`, `xlsx_rat.py`, `app/application/use_cases/informe_rat.py` | El informe sabe del uso de IA de cada actividad, cuenta las de mayor riesgo y las evaluaciones recomendadas, y las muestra en el PDF y el Excel |
| `app/application/use_cases/registro_actividades.py`, `app/api/routes/registro_actividades.py` | Riesgo por actividad y global en la lista, `volumen` en la entrada, evidencia al aprobar y las 2 rutas nuevas |
| `app/application/borradores/generador.py`, `app/application/use_cases/borradores.py`, `app/api/routes/borradores.py` | `registro=` en el generador, lectura del registro para PIA y aviso, `actividades` elegidas, advertencias y `registro` en el catálogo |
| `app/application/use_cases/remediacion.py`, `documentos_empresa.py` | La evidencia del registro cuenta en el historial y la evolución del puntaje; Mis documentos no la lista (no es un archivo) |
| `app/domain/models/evidencia.py`, `respuesta.py`, `app/infrastructure/repositories/bitacora_repository.py` | Origen `rat`, fuente `rat` y acción `rat.evidencia_aplicada` |
| `tests/test_hu20_autorizacion.py` | Las 2 rutas nuevas en la matriz de autorización |

**Frontend**

| Archivo | Cambio |
|---|---|
| `components/empresa/EstadoProteccionDatos.tsx`, `components/empresa/cumplimiento.module.css` | **Nuevo.** Sección de Mi empresa: estado, aporte a la evaluación, matriz de mayor riesgo y brechas con su ruta |
| `components/empresa/rat/RiesgoActividad.tsx` | **Nuevo.** Nivel de riesgo de la actividad con sus factores, qué hacer y la evaluación de impacto recomendada |
| `components/empresa/EspacioEmpresa.tsx` | Acceso al registro y la sección nueva |
| `components/empresa/rat/RegistroActividades.tsx`, `DetalleActividad.tsx`, `Pasos.tsx`, `Ficha.tsx`, `rat.module.css` | Insignia de riesgo en la lista, aviso de actividades de mayor riesgo, enlace `?actividad=&paso=`, aviso de evidencia al dejar vigente, campo de volumen (paso 2) y en la ficha |
| `components/empresa/Borradores.tsx`, `lib/borradores.ts` | `?plantilla=pia&actividad=`, elección de actividades para la evaluación de impacto, qué tomará cada plantilla y advertencias nuevas |
| `lib/registroActividades.ts`, `lib/types.ts` | Tipos y llamadas nuevas, `textoRiesgo`, `rutaRemediacion`, `hrefCorregirBrecha`, `textoEstadoRegistro`, `volumen` |
| `lib/servidor/proxyCliente.ts` | `GET registro-actividades/cumplimiento` y `POST registro-actividades/cumplimiento/evidencia` |
| `tests/registro_conectado.test.ts` | **Nuevo.** 10 pruebas de la lógica de pantalla y del proxy |

## 4. Cómo probar

1. Descomprime el zip **sobre la raíz del repo** (respeta `Proyecto/` y `Extras/`). No hay migración nueva.
2. `docker compose up -d --build` y `docker compose exec api pytest tests -v -rxX`.
3. Con un cliente activado y su evaluación completada: arma el mapa, crea una actividad completa que cubra todos los envíos, déjala vigente → el aviso dice cuántos controles mejoró. En **Mi empresa › Protección de datos personales** aparecen los controles respaldados; en **Cerrar brechas** la evolución del puntaje muestra la mejora.
4. Indica en el paso 2 que la actividad abarca más de 100.000 personas con datos de salud: queda con evaluación de impacto recomendada. Genera una **evaluación de impacto (PIA)** desde Mi empresa o el registro: sale pre-llenada con esa actividad. Genera el **aviso de privacidad**: la tabla de finalidades y bases viene del registro.
5. Quita la base de licitud o un plazo de otra actividad: Mi empresa muestra la brecha con su ruta (corregir en el paso exacto, módulo formativo y re-evaluar).

## 5. Verificación hecha

- **Backend:** suite completa en este entorno (FastAPI, SQLAlchemy y aiosqlite desde sus fuentes): **1446 aprobadas, 10 omitidas**; las 15 que no pasan aquí son las del SDK de Groq y la cola ARQ, que en este entorno se reemplazaron por sustitutos mínimos (fallan igual sin estos cambios). Las 14 nuevas corren completas, incluidas las de API.
- **Frontend:** sin `node_modules` en este entorno. Se compilaron con TypeScript los archivos de `lib/` sin errores y los componentes tocados con tipos sustitutos de React/Next (sin errores propios); `registro_conectado.test.ts`, `registro_actividades.test.ts` y `hu16_borradores.test.ts` pasan con un ejecutor mínimo. Corran `npm run typecheck` y `npm test` en su entorno antes de subir.
- **No se probó en PostgreSQL** (no hay migración; las columnas `evidencias.origen` y `respuestas.fuente_clasificacion` ya admiten `rat`).

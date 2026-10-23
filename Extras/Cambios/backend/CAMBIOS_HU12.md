# CAMBIOS · HU-12 Planes de estudio recomendados + comparativa al completar + PDF directo y por correo

> Como **encargado de capacitación**, quiero recibir planes de estudio recomendados según mis brechas, para elevar las competencias del personal en protección de datos y uso responsable de IA.

Este paquete trae tres cosas:

1. **HU-12** completa en backend (`GET /api/evaluaciones/{id}/plan-formativo`) y en el panel nuevo (`/panel/capacitacion`).
2. **Arreglo de la comparativa** que no aparecía al terminar el cuestionario.
3. **PDF de brechas que se descarga directo** (ya no abre la impresora) y **envío del informe por correo** como respaldo.

## Criterios de aceptación

| Criterio | Dónde se cumple |
|---|---|
| 1. Mapeo automático brechas → catálogo formativo | Cada brecha (no cumplida o parcial) activa la ruta que el catálogo le asigna (`catalogo_brechas.ruta_formativa_id`). Los parciales, que no llevan brecha en la respuesta, se mapean por la brecha de su control. El panel muestra la cobertura ("21/21 brechas con ruta") y avisa qué brechas no tienen ruta. |
| 2. Niveles Inicial / Intermedio / Avanzado con objetivos | Cada dimensión recibe un nivel según su puntaje (≤ 50 Inicial · ≤ 75 Intermedio · > 75 Avanzado) con su objetivo. Cada módulo trae objetivo general, objetivos específicos, contenidos, horas, modalidad y público. La ruta del nivel asignado entra siempre como "Base del nivel". |
| 3. Panel organizado por dimensión normativa | `/panel/capacitacion`: una sección por dimensión, con madurez, nivel del plan, objetivo y módulos ordenados Inicial → Intermedio → Avanzado y por urgencia. Filtros por nivel y "solo los que cierran brechas"; exportación CSV para el LMS. |

## Por qué no salía la comparativa al completar

La comparativa con la industria sale de la tabla `benchmark`, que **solo se recalculaba en el cron de las 02:00 UTC**. Quien completaba la encuesta no tenía benchmark de su rubro hasta el día siguiente, `promedio_industria` venía en `null` y el panel ocultaba la serie. Además, con una sola evaluación en el rubro el "promedio de la industria" era la propia empresa.

Ahora:

- `POST /completar` recalcula el benchmark al terminar (`BENCHMARK_AL_COMPLETAR=true`; si falla, `/completar` responde igual y el cron lo repara).
- `/comparativa` siempre trae la **meta de cumplimiento** (`META_CUMPLIMIENTO_PUNTAJE`, 75 por defecto: "lo que debería cumplir"), la diferencia contra ella y si la cumple. Ya no responde 400 si la evaluación no tiene rubro.
- El promedio del rubro solo se muestra con `COMPARATIVA_MIN_MUESTRAS` evaluaciones o más (3 por defecto). Mientras tanto el panel explica: "El promedio del rubro aparece con al menos 3 evaluaciones completadas (hoy hay 1, la tuya)". Para la demo, `COMPARATIVA_MIN_MUESTRAS=1` lo muestra siempre.
- Radar, barras y tarjetas de Dominios dibujan la meta (línea de puntos amarilla, forma distinta de la del rubro) y dicen cuántos puntos faltan.

## PDF y correo

- `GET /api/evaluaciones/{id}/informe/pdf` genera el informe en el servidor (reportlab) y el botón **Descargar PDF** lo baja directo. Acepta los mismos filtros del listado (`severidad`, `dominio`, `estado`, `q`), así en Brechas se descarga lo que se está viendo. Incluye resultado, comparativa con meta y rubro, brechas priorizadas y plan formativo.
- `POST /api/evaluaciones/{id}/informe/enviar` envía **ese mismo PDF** como adjunto. El PDF lo arma siempre el servidor con datos de la BD (no se aceptan archivos del cliente), así la API no sirve para mandar contenido arbitrario. Máximo 3 envíos por evaluación y 10 por IP al día. El encuestado puede dejar el correo vacío (se usa el que registró) o marcar "guardar este correo".
- Los botones están en Diagnóstico, Brechas y Capacitación. En modo demo, Descargar PDF vuelve a la impresión.
- Por el BFF pasan solo para la evaluación de la sesión; el PDF se reenvía como binario.

### Configurar el correo (`backend/.env`)

```
# desarrollo (por defecto): el .eml con el PDF queda en STORAGE_DIR/correos, no sale nada
CORREO_MODO=archivo

# producción / prueba real, por ejemplo con Gmail (contraseña de aplicación)
CORREO_MODO=smtp
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USUARIO=cuenta@gmail.com
SMTP_PASSWORD=xxxx xxxx xxxx xxxx
CORREO_REMITENTE=ComplianceIA <cuenta@gmail.com>
```

Con `APP_ENV=production`, `CORREO_MODO=archivo` está prohibido (falla al iniciar).

## Arreglo de paso

`/api/brechas` devolvía siempre `ruta_formativa: null` (el schema leía `ruta_formativa` y el modelo tenía `ruta_formativa_rel`). Se agregó la propiedad en `CatalogoBrechas`: ahora el listado de brechas muestra su ruta.

## Archivos

**Backend** (`Proyecto/backend`)

| Archivo | |
|---|---|
| `app/application/informes/analisis.py` | Nuevo. Lógica pura: severidad (igual a `lib/severidad.ts`), brechas priorizadas, filtros y plan formativo |
| `app/application/informes/carga.py` | Nuevo. Lee la BD y arma las entradas |
| `app/application/informes/pdf_informe.py` | Nuevo. PDF del informe |
| `app/application/informes/correo.py` | Nuevo. SMTP o archivo `.eml` |
| `app/api/routes/informes.py` | Nuevo. `plan-formativo`, `informe/pdf`, `informe/enviar` |
| `migrations/versions/a9d3e5f7c1b2_hu12_catalogo_formativo.py` | Nueva. Columnas del catálogo formativo y contenido de las 12 rutas |
| `tests/test_hu12_plan_formativo.py` | Nuevo. 32 pruebas (lógica, PDF y API) |
| `app/api/routes/reportes.py` | Comparativa con meta y umbral de muestras; benchmark al completar |
| `app/core/config.py` | `META_CUMPLIMIENTO_PUNTAJE`, `COMPARATIVA_MIN_MUESTRAS`, `BENCHMARK_AL_COMPLETAR`, `CORREO_*`, `SMTP_*`, `INFORME_CORREOS_*` |
| `app/domain/models/ruta_formativa.py`, `catalogo_brechas.py` | Campos HU-12 y arreglo de `ruta_formativa` |
| `app/application/schemas/api_schemas.py`, `app/core/catalogo_datos_personales.py`, `app/main.py`, `requirements.txt` | Schema, inventario T-06 (las columnas nuevas no son datos personales), router y `reportlab` |

**Frontend** (`Proyecto/frontend-next`)

| Archivo | |
|---|---|
| `app/panel/capacitacion/page.tsx`, `components/vistas/VistaCapacitacion.tsx` | Nuevos. Pantalla HU-12 |
| `components/informe/AccionesInforme.tsx` | Nuevo. Descargar PDF + diálogo de correo |
| `hooks/usePlanFormativo.ts`, `lib/planFormativo.ts` | Nuevos. Carga, filtros, "Empieza por", CSV |
| `tests/hu12_capacitacion.test.ts` | Nuevo. 13 pruebas |
| `components/charts/RadarMadurez.tsx`, `BarrasDominio.tsx`, `components/vistas/VistaDominios.tsx`, `VistaDiagnostico.tsx` | Meta de cumplimiento y explicación cuando no hay promedio del rubro |
| `components/vistas/VistaBrechas.tsx` | PDF directo con filtros y correo (sale la impresión) |
| `lib/api.ts`, `lib/types.ts`, `lib/adaptadores.ts`, `lib/madurez.ts`, `lib/demo.ts`, `lib/exportar.ts` | Contratos, meta, plan demo, descarga de blobs |
| `lib/servidor/proxy.ts`, `app/bff/api/[...ruta]/route.ts` | Rutas nuevas del BFF, filtros del PDF, PDF binario, IP para el límite de correos |
| `components/shell/Sidebar.tsx`, `components/ui/Icon.tsx`, `app/globals.css` | Menú "Capacitación", íconos y estilos |
| `tests/encuesta.test.ts` | `toEqual` → `toMatchObject` (la autorización del proxy ahora trae más campos) |
| `docs/capturas/hu12_*.png`, `docs/hu12_informe_ejemplo.pdf` | Evidencia |

## Cómo aplicarlo

1. Descomprime el zip **sobre** `Proyecto/` (respeta las rutas; reemplaza los modificados).
2. Si tu head de Alembic no es `e2b7c9d4f8a1` (`alembic heads`), cambia `down_revision` en la migración nueva.
3. `docker compose up -d --build` (hay que reconstruir api y worker por `reportlab`) y `docker compose exec api alembic upgrade head`.
4. Pruebas: `docker compose exec worker pytest tests -v -rxX` y en `frontend-next`: `npm test && npm run typecheck && npm run build`.

## Qué se verificó antes de entregar

El entorno no tenía acceso a PyPI ni npm, así que **no se pudo correr la suite completa del backend ni `next build`**. Sí:

- Backend: las 25 pruebas de lógica y PDF de `test_hu12_plan_formativo.py` pasan; las 7 de API se omitieron (sin FastAPI/SQLAlchemy aquí) y quedan para tu Docker. El correo se probó en modo archivo (multipart con el PDF adjunto). PDF revisado con el catálogo real de la semilla (40 controles, 30 brechas).
- Frontend: las 5 suites pasan (66 pruebas: las 53 existentes + 13 nuevas) y los archivos tocados pasan `tsc --strict`.
- Navegador (Chromium) contra respuestas generadas con la lógica real del backend: Capacitación, Diagnóstico, Dominios y Brechas a 1440, 1024 y 720 px sin scroll horizontal ni errores de consola; descarga de un PDF real sin abrir la impresión; diálogo de correo con validación, error 429 y éxito; Esc y foco de vuelta al botón; filtros del plan, CSV y enlace de una brecha al listado.
- Accesibilidad (WCAG 2.1 AA): contrastes nuevos ≥ 5,9:1 en texto y ≥ 3,4:1 en bordes de controles; diálogo nativo con foco atrapado; objetivos táctiles de 44 px; meta y rubro distinguibles por forma, no solo por color.

## Checklist en Docker

- [ ] Completar una evaluación nueva desde `/comenzar` → el panel muestra la meta en radar y barras y, con 1 sola evaluación en el rubro, el aviso de cuántas faltan para el promedio.
- [ ] Con `COMPARATIVA_MIN_MUESTRAS=1` en `.env` y reiniciando api → aparece la barra punteada del rubro.
- [ ] `/panel/capacitacion` muestra 4 dimensiones con nivel, objetivo y módulos; "Exportar plan CSV" abre bien en Excel.
- [ ] Brechas → filtrar "Crítica" → Descargar PDF baja `informe_evaluacion-<id>_<fecha>.pdf` con solo las críticas.
- [ ] Enviar por correo con `CORREO_MODO=archivo` → aparece un `.eml` en `storage/correos` del contenedor; al cuarto envío del día responde que se alcanzó el máximo.
- [ ] `GET /api/brechas` trae `ruta_formativa` con nombre.

## Decisiones para validar con el PO

1. **Meta = 75** (techo de "gestionado"). Si el PO prefiere exigir "optimizado", es `META_CUMPLIMIENTO_PUNTAJE=76`.
2. **Mínimo 3 evaluaciones** para mostrar el promedio del rubro.
3. **Cortes de nivel del plan** (≤ 50 / ≤ 75 / > 75) y el **contenido de las 12 rutas** (objetivos, horas, modalidad): los escribí a partir del catálogo y la Ley 21.719; conviene que el equipo los revise. Se editan en la migración o directo en la tabla `ruta_formativa`.

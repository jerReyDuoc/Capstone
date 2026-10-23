# ComplianceAI · Panel web (HU-13)

Frontend en **Next.js 15 + React 19 + TypeScript**. Reemplazó al prototipo HTML, que quedó como evidencia en `Extras/frontend-prototipo/`.
Muestra la madurez en gobernanza de IA por dominio (radar y barras), el resumen de brechas priorizadas y una
navegación pensada para computadores y tablets (≥ 1024 px), con la paleta del sitio TherionLabs.

## Puesta en marcha

```bash
cd Proyecto/frontend-next
npm install                     # la configuración sale de Proyecto/.env (un solo .env para todo)
npm run dev                     # http://localhost:3000/panel
```

Sin backend levantado puedes revisar el diseño en modo demo: `NEXT_PUBLIC_DEMO=1 npm run dev`.

### Con Docker (junto al resto del sistema)

El `docker-compose.yml` de `Proyecto/` ya trae el servicio `web`. Desde `Proyecto/`:

```bash
docker compose up -d --build
```

El panel queda en http://localhost:3000/panel (puerto configurable con `WEB_PORT` en `Proyecto/.env`). Next reenvía `/api/*` al servicio `api`, así que no hace falta CORS.

### Pruebas

```bash
npm test          # vitest: adaptadores API → modelo de vista
npm run typecheck
npm run build
```

## Encuesta pública (HU-19)

| Ruta | Contenido |
|---|---|
| `/` | Landing estática con el CTA al autodiagnóstico |
| `/comenzar` | Aviso legal → rubro + verificación (Turnstile) → número y clave de la evaluación (+ email opcional) |
| `/retomar` | Continuar desde cualquier dispositivo con número + clave |
| `/encuesta` | Evaluación propia del encuestado (requiere sesión) |
| `/aviso-legal` | Texto del aviso legal (HU-04) |

El navegador habla con el BFF (`/bff/*`), que guarda el token en una cookie httpOnly y lo agrega como Bearer
hacia FastAPI. Detalles, variables y checklist en `Extras/Cambios/frontend/CAMBIOS_HU19.md` (raíz del repositorio).

## Rutas del panel

| Ruta | Contenido |
|---|---|
| `/panel?evaluacion=ID` | Diagnóstico: KPIs, radar de madurez, brechas por prioridad, comparativa con la industria y top de brechas |
| `/panel/dominios` | Detalle por dominio: puntaje, nivel, marca del promedio del rubro y acceso a sus brechas |
| `/panel/brechas?criticidad=&dominio=&estado=` | Listado filtrable y ordenable; los filtros viven en la URL |

Si no viene `evaluacion` en la URL se elige la última evaluación **completada**.

## Endpoints que consume (sin cambios en el backend)

| Endpoint | Uso |
|---|---|
| `GET /api/evaluaciones` | Selector de evaluación |
| `GET /api/evaluaciones/{id}/resumen` | Puntaje general, nivel y puntaje por dominio |
| `GET /api/evaluaciones/{id}/comparativa` | Promedio del rubro (opcional: si falla, se oculta la serie) |
| `GET /api/evaluaciones/{id}/respuestas` | Respuestas paginadas para armar las brechas |
| `GET /api/brechas` | Catálogo: criticidad, acción sugerida y ruta formativa |

**Regla de brecha:** respuesta con estado efectivo (`estado_clasificacion_final` si existe, si no `estado_clasificacion`)
`no_cumplido` o `parcialmente_cumplido`. Si no tiene brecha de catálogo asociada se muestra igual como
"Sin clasificar" para no esconder riesgo. Los niveles usan los mismos cortes del backend (25/50/75).

## Estructura

```
app/                 rutas (App Router) y estilos globales con los tokens de diseño
components/charts/   RadarMadurez, BarrasCriticidad, BarrasDominio (SVG propio, sin librerías)
components/shell/    Sidebar y PageHeader (selector de evaluación)
components/vistas/   Diagnóstico, Dominios, Brechas
components/ui/       KPIs, badges, estados de carga/vacío/error, íconos
hooks/usePanel.tsx   contexto: evaluación seleccionada y datos del panel
lib/                 tipos de la API, adaptadores, cliente HTTP, datos demo
tests/               pruebas de los adaptadores
docs/                handoff de diseño, auditoría WCAG y capturas
```

Los gráficos son SVG propios en vez de una librería para controlar por completo teclado, lectores de pantalla y la
paleta, y para no sumar dependencias. Ver `docs/ACCESIBILIDAD.md` y el handoff histórico en `Extras/Cambios/frontend/HU-13_HANDOFF.md`.

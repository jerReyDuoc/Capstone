# CAMBIOS · HU-11 Listado priorizado de brechas normativas

**Qué se agrega:** severidad Crítica/Alta/Media/Baja, listado numerado por prioridad, filtros combinables en la URL,
exportación a PDF y CSV, y "Fijar en Diagnóstico" (exportar al dashboard).
**Qué NO cambia:** el backend (usa endpoints existentes, ahora también `GET /api/controles`), `docker-compose.yml`
ni `package.json` (sin dependencias nuevas).

## Archivos

Nuevos:
- `lib/severidad.ts` — matriz impacto × estado y utilidades de severidad
- `lib/filtrosBrechas.ts` — filtros, URL y descripción legible
- `lib/exportar.ts` — CSV seguro, nombre de archivo, impresión a PDF
- `lib/vistasFijadas.ts`, `hooks/useVistasFijadas.ts` — vistas fijadas en el Diagnóstico
- `components/brechas/` — `TarjetasSeveridad`, `MatrizPriorizacion`, `InformeBrechas`, `VistasFijadas`
- `tests/brechas_hu11.test.ts` — 13 pruebas por criterio de aceptación
- `docs/HU-11_HANDOFF.md`, `docs/capturas/hu11_*.png`, `docs/hu11_informe_ejemplo.pdf`, `docs/hu11_export_ejemplo.csv`

Modificados:
- `lib/types.ts` (Severidad, ControlApi, campos nuevos), `lib/adaptadores.ts` (análisis y orden), `lib/api.ts`
  (carga controles), `lib/demo.ts` (caso con respaldo por control)
- `components/vistas/VistaBrechas.tsx` (rediseño), `VistaDiagnostico.tsx`, `ResumenBrechas.tsx`
- `components/charts/BarrasCriticidad.tsx` (ahora por severidad), `components/ui/Basicos.tsx`, `components/ui/Icon.tsx`
- `app/globals.css` (tokens `--critico`, `--naranja`, estilos HU-11 y hoja de impresión)

## Cómo aplicarlo

1. Descomprime el zip **sobre** `Proyecto/` (respeta las rutas `frontend-next/...`; reemplaza los modificados).
2. `cd Proyecto/frontend-next && npm test && npm run typecheck && npm run build`
3. Docker: `docker compose up -d --build` y abre http://localhost:3000/panel/brechas
   (modo demo sin backend: `NEXT_PUBLIC_DEMO=1 npm run dev`).

## Qué se verificó antes de entregar

El entorno no tenía acceso al registro de npm, así que **no se pudo correr `tsc` ni `next build`**. Sí se verificó:

- Pruebas: 13 nuevas de HU-11 + 8 de adaptadores + 18 de encuesta, todas pasan (las existentes no se rompieron).
- Render real con React 19 de Diagnóstico y Brechas: sin errores ni advertencias de consola; sin scroll horizontal
  en 1440, 1280, 1024 y 720 px (zoom 200 %).
- Flujos en Chromium: filtro por tarjeta con Enter (foco conservado), multi-severidad, búsqueda, CSV descargado,
  fijar → aparece en Diagnóstico → "Abrir listado" restaura filtros, barra del gráfico abre Brechas filtrado,
  "Limpiar filtros", y PDF generado con la hoja de impresión (2 páginas, encabezados repetidos).

Si `typecheck` o `build` reportan algo, envíame la salida y lo corrijo.

## Decisión para validar con el PO

La "Crítica" no existe en el catálogo (solo Alta/Media/Baja), por lo que se deriva: **impacto alto + no cumplido =
Crítica**. Ver la matriz completa en `docs/HU-11_HANDOFF.md`; cambiarla es editar `MATRIZ_SEVERIDAD`.

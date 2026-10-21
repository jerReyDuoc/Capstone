# CAMBIOS · HU-13 Panel web responsivo

**Qué se agrega:** carpeta nueva `Proyecto/frontend-next/` con el panel en Next.js 15 + React 19 + TypeScript.
**Qué NO cambia:** el backend (usa endpoints existentes) ni `Proyecto/frontend/` (prototipo).
**Se actualiza aparte:** `Proyecto/docker-compose.yml` (servicio `web` y puertos configurables).

## Cómo aplicarlo

1. Descomprime el zip dentro de `Proyecto/` (debe quedar `Proyecto/frontend-next/package.json`).
2. `cd Proyecto/frontend-next && npm install` (genera `package-lock.json`; súbelo al repo).
3. Verifica: `npm test`, `npm run typecheck` y `npm run build`.
4. Con Docker (usa el `docker-compose.yml` actualizado que trae el servicio `web`): `docker compose up -d --build`
   y abre http://localhost:3000/panel.

## Qué se verificó antes de entregar

El entorno donde se construyó no tenía acceso al registro de npm, así que **no se ejecutó `next build` ni `tsc`**.
Sí se verificó:

- Las 8 pruebas de `tests/adaptadores.test.ts` (reglas de brecha, cortes de madurez, panel sin benchmark).
- Renderizado real con React 19 de las tres pantallas en 1024 px y 1440 px, sin errores de consola ni scroll
  horizontal (capturas en `docs/capturas/`).
- Teclado: orden de Tab, Enter en barras y puntos del radar, foco conservado al ordenar, tooltip con foco.
- Zoom 200 %, nombres accesibles, tamaño de objetivos, contraste (ver `docs/ACCESIBILIDAD.md`).

Si `typecheck` o `build` reportan algo en tu máquina, envíame la salida y lo corrijo.

## Criterios de aceptación

Ver tabla de trazabilidad en `docs/HU-13_HANDOFF.md`.

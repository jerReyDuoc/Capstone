# Extras

Material de apoyo y evidencia del proyecto. Nada de esta carpeta se ejecuta ni entra en las imágenes de Docker: el sistema vive en `Proyecto/`.

| Carpeta / archivo | Qué contiene |
|---|---|
| `Cambios/backend/` | Un `CAMBIOS_*.md` por historia de usuario o tarea técnica del backend (HU-01, HU-02, HU-06, HU-19, HU-20, ARCOP, T-04, T-06, T-08): qué se cambió, decisiones del PO, cómo probarlo |
| `Cambios/frontend/` | Lo mismo para `frontend-next` (cuestionario, HU-11, HU-13, HU-19) y los handoffs de diseño de HU-11 y HU-13 |
| `Cambios/CAMBIOS_HU12.md` | HU-12, que tocó backend y frontend a la vez |
| `Evidencias/` | Reportes de latencia en vivo, capturas de pantalla e informes PDF/CSV de ejemplo que respaldan los criterios de aceptación |
| `frontend-prototipo/` | Prototipo HTML/JS original (API simulada en `localStorage`), reemplazado por `Proyecto/frontend-next/`. Se guarda como evidencia del diseño inicial |
| `Guia_ComplianceAI_PromptInjection.docx.pdf` | Guía del módulo anti prompt-injection |

Los documentos conservan las rutas tal como eran cuando se escribieron (por ejemplo `backend/CAMBIOS_HU06.md` o `docs/HU-11_HANDOFF.md`): describen el estado del repositorio en ese momento.

## Regla para documentos nuevos

Cada documento de cambios de una HU o tarea (`CAMBIOS_<HU o tarea>.md`) se crea **directamente aquí**, nunca dentro de `Proyecto/`:

- backend → `Extras/Cambios/backend/CAMBIOS_HU-XX.md`
- frontend → `Extras/Cambios/frontend/CAMBIOS_HU-XX.md`
- si toca los dos → `Extras/Cambios/CAMBIOS_HU-XX.md`
- reportes, capturas y archivos de ejemplo que sirvan de evidencia → `Extras/Evidencias/`

Desde el código o el README se enlazan con su ruta completa (`Extras/Cambios/backend/...`).

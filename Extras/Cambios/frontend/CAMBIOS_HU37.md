# HU-37 · Informe RoPA — cambios de frontend

Implementa el prototipo aprobado (`Extras/frontend-prototipo/ropa.html`, versión 2): una sola pantalla con scroll,
sin menciones a RGPD/UE, sin textos explicativos (la ayuda va en el ícono ⓘ junto al título) y botón
**«Informe RoPA»** en Registro de actividades.

## Archivos

**Nuevos**
- `components/empresa/rat/InformeRopa.tsx` — ventana (Dialogo `lg`):
  - Título «Informe RoPA», chip «Versión N.º X» e ícono ⓘ (se cierra con clic fuera o Escape, sin cerrar la ventana).
  - Secciones: Incluir (como responsable / como encargado, con conteos; deshabilitada si no hay actividades
    vigentes de ese rol) → Datos de la empresa (razón social y RUT de solo lectura, dirección, correo, teléfono
    opcional, delegado Sí/No con cargo y correo) → Organizaciones para las que actúas como encargado (se oculta
    al desmarcar esa parte) → Vista previa (pestañas por parte + Transferencias, chips por actividad) →
    Informes emitidos (con descargas).
  - Pie fijo: «Generar PDF y Excel» bloqueado con el motivo («Completa Grupo Sur S.A.»); al generar guarda
    primero solo lo que cambió (PATCH) y luego emite; el resultado (código y descargas) aparece en el pie.
  - Al cerrar, lo escrito (si está bien escrito) se guarda para la próxima vez.
  - Estado vacío: «Aún no hay actividades vigentes».
- `lib/informeRopa.ts` — tipos, llamadas y lógica pura: `faltantes()` y `erroresFormato()` (misma regla que
  el servidor), `textoFaltantes()`, `cambiosDatos()` (solo lo modificado), `textoPartes()`.
- `tests/informe_ropa.test.ts` — 9 pruebas (faltantes, formatos, cambios, proxy).

**Modificados**
- `components/empresa/rat/RegistroActividades.tsx` — botón «Informe RoPA».
- `components/empresa/rat/rat.module.css` — estilos `ropa*` (responsive a una columna bajo 640 px).
- `components/empresa/MisDocumentos.tsx`, `lib/empresa.ts` — los RoPA aparecen en la pestaña Registro de
  actividades como «Informe RoPA · versión N (PDF|Excel)» con partes y código.
- `lib/servidor/proxyCliente.ts` — lista blanca: `GET/POST registro-actividades/ropa`, `PATCH …/ropa/datos`,
  `GET …/ropa/{id}/descarga` (binario PDF o Excel).

## Verificación hecha en esta entrega

Sin `node_modules` (no se generó `package-lock.json`), se usó TypeScript 6 y tsx del sistema:
- `tsc --noEmit` estricto sobre los archivos tocados (con declaraciones mínimas de React/Next): sin errores.
- Pruebas `informe_ropa`, `informe_rat`, `hu28_acceso` y `hu29_historial_documentos`: todas pasan.
- Render real con React 19 y datos simulados (capturas en `Extras/Evidencias/HU37/`): flujo completar → guardar
  (PATCH solo con lo cambiado) → generar → resultado en el pie, sin errores de consola.

Antes de integrar: `npm run typecheck && npm test` en el contenedor.

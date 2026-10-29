# HU-29 · Mis evaluaciones y Mis documentos (frontend-next)

El espacio de la empresa (`/empresa`) cambia la tabla de evaluaciones migradas por dos secciones nuevas y suma una pantalla para responder la reevaluación. Todo pasa por el BFF del cliente (`/bff/cliente/api/*`); la autorización real sigue en FastAPI.

**Mis evaluaciones** (`components/empresa/MisEvaluaciones.tsx`) muestra el nivel y el puntaje actuales, la evolución desde la primera evaluación y cuántas hay completadas; el gráfico de evolución; y la tabla con todas las evaluaciones de la empresa (las del autodiagnóstico y las reevaluaciones), con fecha, estado, puntaje global, nivel y variación. Cada evaluación completada tiene **Ver resultados** (el panel de siempre en modo cliente) y **Guardar informe** (archiva el PDF en Mis documentos). El botón **Nueva evaluación** crea la reevaluación y lleva a contestarla; si ya hay una en curso, el botón pasa a **Continuar evaluación N.º X**. Sin servicio activo el historial se sigue viendo, pero el botón queda deshabilitado.

**Gráfico de evolución** (`components/charts/EvolucionMadurez.tsx`) es una línea sobre el eje 0–100 con las bandas de nivel de madurez de fondo y una posición por evaluación completada, rotulada con su fecha y número. Tiene dos vistas con un solo eje: **Global**, con el verde de marca, y **Por dimensión**, con una línea por dimensión y botones para mostrar u ocultar cada una. Los colores de las dimensiones están en orden fijo y siguen a su dimensión aunque se oculten otras; se validaron con el script de dataviz contra la superficie oscura (separación para daltonismo y contraste aprobados). La identidad nunca depende solo del color: leyenda con nombres, rótulos al final de cada línea, puntos enfocables con teclado con su lectura completa y la vista en tabla de `ChartFrame`. Una dimensión que no aplicó en alguna evaluación corta la línea en vez de inventar un valor.

**Mis documentos** (`components/empresa/MisDocumentos.tsx`) tiene pestañas para informes PDF, borradores, evidencias y constancias, cada una con su conteo. Cada fila se descarga o se elimina; eliminar pide confirmación en la misma fila y explica qué se borra (en una evidencia, que el puntaje se conserva; en una constancia, que el módulo sigue completado). Muestra hasta cuándo se pueden descargar durante el plazo de gracia.

**Reevaluación** (`/empresa/evaluacion/[id]`) monta el mismo cuestionario del autodiagnóstico. `Cuestionario` recibe ahora `base="/bff/cliente/api"` y `lib/cuestionario/api.ts` usa esa base en todas sus llamadas (por defecto sigue siendo `/bff/api`, así que la encuesta pública no cambia). Al completar se va a los resultados, como siempre.

Con el servicio cortado (HU-30), la vista `SinServicio` muestra ahora Mis evaluaciones y, durante el plazo de gracia, Mis documentos (antes solo una lista de constancias).

| Archivo | Cambio |
|---|---|
| `app/empresa/evaluacion/[id]/page.tsx` | **Nuevo.** Pantalla de la reevaluación |
| `components/empresa/ReevaluacionEmpresa.tsx` | **Nuevo.** Encabezado y cuestionario por el BFF del cliente |
| `components/empresa/MisEvaluaciones.tsx` | **Nuevo** |
| `components/empresa/MisDocumentos.tsx` | **Nuevo** |
| `components/charts/EvolucionMadurez.tsx` | **Nuevo** |
| `components/empresa/EspacioEmpresa.tsx` | Usa las dos secciones nuevas (también en `SinServicio`) |
| `components/cuestionario/Cuestionario.tsx`, `lib/cuestionario/api.ts` | Base del BFF configurable |
| `lib/empresa.ts` | Tipos y llamadas de historial, reevaluación y documentos; descarga de binarios; formatos; paleta de dimensiones |
| `lib/encuesta/contratos.ts` | El error 409 trae `evaluacionId` para retomar la reevaluación en curso |
| `lib/servidor/proxyCliente.ts` | Lista blanca: rutas de HU-29 y del cuestionario (filtro, respuestas, evidencias, completar). Siguen fuera `PUT` de respuestas, `/cerrar` y borrar evaluaciones. Descargas de PDF, texto o DOCX según la regla. JSON hasta 64 KB |
| `app/bff/cliente/api/[...ruta]/route.ts` | Respuestas binarias con los tipos de la regla |
| `tests/hu29_historial_documentos.test.ts` | **Nuevo** |
| `tests/hu28_acceso.test.ts`, `tests/hu26_formacion.test.ts` | Ajustadas: el cliente ya puede responder el cuestionario (el backend rechaza cambios en las evaluaciones completadas) |

No se pudo correr `npm run typecheck` ni `npm test` en este entorno (sin acceso a npm). Se revisaron los tipos de los archivos nuevos con `tsc` sobre stubs de React y Next, pero **corran `npm run typecheck`, `npm test` y revisen la pantalla en el navegador antes de subir**, en especial el gráfico con 1, 2 y varias evaluaciones y en 1366×768.

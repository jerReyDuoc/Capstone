# HU-26 y HU-17 · Panel de formación, recorrido del módulo y cerrar brechas (frontend)

Parte de frontend de HU-26 (registrar el avance de los módulos formativos) y HU-17 (re-evaluar un control con evidencia). El backend está en `Extras/Cambios/backend/CAMBIOS_HU26_HU17.md`. Todo funciona para el **usuario definitivo** (modo `cliente` del panel, por `/bff/cliente/api/*`); el encuestado ve su plan gratis y un aviso de que los módulos son del servicio contratado.

## Qué cambia en pantalla

**Capacitación (`/panel/capacitacion`).** Arriba aparece el avance de la empresa: una frase ("3 de 9 módulos completados y 2 en curso"), las horas hechas, cuántas brechas tienen la formación completa y un botón al siguiente paso ("Continúa con…" o "Empieza por…"). Debajo, una fila por dimensión con un medidor **segmentado**: cada segmento es un módulo, relleno si está completado, rayado si está en curso y solo con contorno si no se empezó. El estado se lee por la forma, no solo por el color. Luego el avance por nivel y, si hay brechas con la formación hecha, un aviso que explica que el puntaje no cambia por completar módulos y lleva a "Cerrar brechas". Cada tarjeta de módulo del plan suma su estado, el avance de lecciones y la acción (Empezar módulo / Continuar / Hacer la actividad / Ver módulo y constancia); en las completadas, las brechas llevan un ✓ y un enlace "Subir evidencia".

**Recorrido del módulo (`/panel/capacitacion/[ruta]`).** A la izquierda, un riel con las lecciones en orden (son una secuencia real), la actividad de verificación (bloqueada hasta ver todas) y, al aprobar, la constancia. A la derecha, el paso actual: la lección con su contenido y el material de apoyo (marcado "En preparación"), y el botón "Marcar como vista y seguir"; la actividad con preguntas de selección única, validación de las que faltan y el resultado por pregunta; y el cierre con la fecha, la nota, el código, "Descargar constancia (PDF)" y las brechas del módulo con "Subir evidencia", porque es el siguiente paso.

**Cerrar brechas (`/panel/remediacion`, nuevo en el menú del cliente).** El puntaje general actual y los controles con brecha, primero los que ya tienen la formación hecha. Cada uno muestra la evidencia que sirve, si falta preparar al equipo (con el enlace al módulo) y su última evidencia. "Subir evidencia" abre el formulario: archivo (PDF, Word o texto), a qué estado llegó el control y, opcional, qué cambió. Mientras la IA analiza, la vista consulta el resultado con espera creciente; si el control mejora, recarga el panel para que el radar y las barras muestren el puntaje nuevo, y muestra los términos del control que encontró y, si el documento era largo, cuántos pasajes analizó la IA (RAG local).

**Brechas (`/panel/brechas`).** En modo cliente, las brechas con la formación hecha llevan "Formación hecha · subir evidencia".

## Archivos

| Archivo | |
|---|---|
| `app/panel/capacitacion/[ruta]/page.tsx`, `components/formacion/RecorridoModulo.tsx` | **Nuevos.** Recorrido del módulo |
| `components/formacion/AvanceEmpresa.tsx`, `hooks/useAvanceFormativo.ts` | **Nuevos.** Avance de la empresa |
| `app/panel/remediacion/page.tsx`, `components/remediacion/VistaRemediacion.tsx` | **Nuevos.** Cerrar brechas |
| `lib/formacion.ts`, `lib/remediacion.ts` | **Nuevos.** API del BFF y lógica de presentación |
| `components/vistas/VistaCapacitacion.tsx`, `components/vistas/VistaBrechas.tsx` | Avance, estado por módulo y brechas con la formación hecha |
| `components/shell/Sidebar.tsx`, `components/ui/Icon.tsx` | "Cerrar brechas" (solo cliente) e íconos nuevos |
| `lib/servidor/proxyCliente.ts`, `app/bff/cliente/api/[...ruta]/route.ts` | Lista blanca de las rutas nuevas, constancia binaria y subida multipart (12 MB) |
| `middleware.ts` | `/api/formacion` y `/api/remediacion` solo por el BFF (el token vive en la cookie httpOnly) |
| `lib/types.ts`, `app/globals.css` | Contratos y estilos |
| `tests/hu26_formacion.test.ts` | **Nuevo.** 14 pruebas |
| `tests/hu28_acceso.test.ts` | La autorización del proxy del cliente ahora trae `archivo` |
| `docs/capturas/hu26_*.png`, `docs/capturas/hu17_*.png`, `docs/hu26_constancia_ejemplo.pdf` | Evidencia |

## Verificación hecha

Sin npm en este entorno, se usaron los tipos de React 19 desde DefinitelyTyped y un TypeScript local: **todo el proyecto pasa `tsc --strict`** (el único aviso restante viene de los tipos simulados de Next, no del código). Las **9 suites de pruebas pasan (115 pruebas: 101 existentes + 14 nuevas)** con un ejecutor compatible con vitest. Las pantallas se armaron con React 19 real y esbuild, con datos simulados con la forma exacta de la API, y se revisaron en Chromium a 1440, 1024 y 720 px: sin scroll horizontal ni errores de consola. Igual corran en Docker `npm test && npm run typecheck && npm run build`.

## Especificación de diseño (handoff)

### Pasada de diseño aplicada

Se hizo una crítica sobre capturas reales, con revisión de UX copy y accesibilidad WCAG 2.1 AA. Lo que se corrigió:

| Hallazgo | Severidad | Corrección |
|---|---|---|
| En una página larga, el siguiente módulo por hacer quedaba enterrado entre las tarjetas | 🟡 | Botón "Continúa con / Empieza por" en el avance |
| Al reprobar, el resultado salía dos veces (aviso verde de la página y resumen del formulario) y en verde | 🟡 | Solo el resumen del formulario, en tono de aviso, con foco en él |
| El cuadro "Qué cambió" mostraba el texto de ejemplo en monoespaciada | 🟢 | `textarea` hereda la fuente |
| La frase secundaria repetía la acción ("· continuar") | 🟢 | "2 de 3 lecciones vistas" |
| "Remediación" es jerga | 🟢 | El menú y el título dicen "Cerrar brechas" |

### Tokens

Se usan los del sistema existente (`globals.css`); no hay colores nuevos. Estados del módulo: completado = `--accent` relleno; en curso = rayado 135° de `--accent` (3 px / 4 px); sin empezar = contorno `--line-control` (3,6:1 sobre `--surface`, WCAG 1.4.11). Severidad en las tarjetas de remediación: franja izquierda de 4 px con `--sev` (mismo patrón que Brechas). Radios: tarjetas `--radius-lg`, ítems internos `--radius-md`, chips `--radius-pill`.

### Componentes y estados

| Componente | Estados |
|---|---|
| `MedidorSegmentado` | completado / en_curso / no_iniciado por segmento; `role="img"` con "N de M módulos completados, K en curso" |
| Tarjeta de módulo (`.modulo-progreso`) | Sin empezar (botón primario "Empezar módulo"), En curso (barra de lecciones + "Continuar" o "Hacer la actividad"), Completado (código + botón secundario "Ver módulo y constancia") |
| Paso del riel (`.riel-paso`) | pendiente, actual (`aria-current="step"`), hecho (✓ sobre `--accent`), bloqueado (actividad con candado, `disabled` + motivo en `aria-describedby`) |
| Actividad | sin responder, faltan respuestas (`aria-invalid`, foco al resumen), enviando (`aria-busy`), reprobada (✓/✗ por pregunta, sin revelar la correcta), sin intentos (botón deshabilitado + motivo) |
| Evidencia de remediación | analizando (borde punteado, consulta 1,5 s → 8 s, se detiene a los ~3 min), mejoró (fondo `--ok-soft`, términos encontrados, recarga del panel), sin cambio / error (ícono en `--medio`, motivo del backend) |

### Responsivo

| Ancho | Comportamiento |
|---|---|
| ≥ 1280 px | Riel de 240-300 px fijo (sticky) + paso; tarjetas de módulo en grilla automática de 300 px |
| 1024-1279 px | Igual, con la barra lateral compacta del panel |
| < 1024 px | El riel pasa arriba del paso (una columna); niveles en una columna |
| < 720 px | La tabla de avance por dimensión se apila (nombre, medidor y cifra en líneas) y el material de apoyo pone la insignia debajo |

### Accesibilidad (WCAG 2.1 AA)

Contrastes nuevos medidos: texto del paso actual 8,3:1, texto atenuado sobre fondo activo 7,1:1, metadatos del riel 6,5:1, "Respuesta incorrecta" 6,0:1, contorno del segmento 3,6:1. Al cambiar de paso el foco va al título del paso (comprobado en Chromium); al enviar la actividad incompleta, al resumen del error. Cada pregunta es un `fieldset` con `legend`; las opciones son `label` de 44 px de alto (el área táctil es la fila completa). Todos los controles tienen nombre accesible (0 sin nombre en la revisión automática); los enlaces repetidos ("Subir evidencia", "Continuar") llevan el nombre del control o del módulo en texto solo para lectores de pantalla. Los cambios de estado se anuncian en regiones `aria-live`. El rayado del medidor y el ✓ hacen que el estado no dependa solo del color.

### Casos borde

Módulo sin lecciones (cierre con "Therion Labs está preparando su contenido"), módulo fuera del plan o de otra empresa (estado con "Volver a Capacitación"), servicio no activo (mensaje para contactar a Therion Labs; HU-30), encuestado o equipo interno en estas páginas (explicación y enlace a contratar o a ingresar), evaluación sin brechas abiertas ("No quedan brechas abiertas"), sesión vencida (mensaje para volver a ingresar).

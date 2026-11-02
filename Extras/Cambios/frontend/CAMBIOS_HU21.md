# HU-21 · Página "Informe" del panel (frontend-next)

## Qué ve el usuario

Hay una página nueva, **Informe** (`/panel/informe`), en el grupo "Gobernanza de IA" de la barra lateral, después de Capacitación. La ven quien hizo la evaluación sin cuenta y la empresa cliente, porque el informe es parte de lo gratuito. Responde a lo que necesita un director de riesgos antes de llevar el documento a una sesión de directorio: qué va a decir el PDF, con qué datos se identifica y cómo se lo explica a un auditor.

En escritorio, a la izquierda va un **facsímil de la página 1 del PDF**, con los colores del papel y no los del panel, y detrás asoman las páginas siguientes. A la derecha, de arriba abajo, van la tarjeta **Descargar el informe** (descarga directa y envío por correo, los mismos botones de HU-12), la **Ficha del informe** (código de evaluación con botón para copiarlo, fecha de la evaluación, versión de la matriz, versión del aviso legal y rubro) y **Qué incluye** (aviso legal, los 5 puntajes, cuántas brechas y de qué severidad, cuántos módulos y horas). Abajo, **Si se lo presenta a un auditor** explica en lenguaje simple qué es la huella de los resultados y permite copiarla completa.

Nada se calcula en el navegador: todo sale de `GET /api/evaluaciones/{id}/informe/ficha`, que el backend arma con el mismo código que el PDF. Lo que se ve en la página es lo que dirá la portada impresa (criterio 1).

## Decisiones de diseño

La hoja es el único elemento llamativo de la página. Se dibuja en blanco, con la tipografía Helvetica y el verde `#0b7a5a` del PDF, para que quien la revisa vea lo que va a imprimir y no una versión "del panel". El resto reutiliza las tarjetas, botones y tokens existentes, para que no parezca otro producto.

En pantallas de menos de 1100 px la columna de acciones pasa arriba de la hoja: en el teléfono lo primero es poder descargar. Bajo 720 px la hoja oculta la columna de barras (el número ya dice lo mismo) y la ficha de la portada se apila.

### Accesibilidad (WCAG 2.1 AA)

La hoja es una `<figure>` con su leyenda; su tabla de puntajes tiene `caption`, encabezados de fila y de columna, y las barras van con `aria-hidden` porque el número está al lado. En el papel, el texto gris `#5b6b64` y el verde `#0b7a5a` superan 4,5:1 sobre el fondo. Los mensajes de las acciones (PDF descargado, código copiado) se anuncian en una región `aria-live` y además se ven en pantalla. Los botones de copiar tienen un nombre accesible que contiene su texto visible (2.5.3) y área táctil de 44 px. La carga usa un esqueleto con `role="status"` y los errores un aviso con `role="alert"` y botón para reintentar. La hoja crece si no cabe (zoom al 200 %) en vez de cortar el texto.

### Textos

Se habla de "preguntas" y no de controles, y no se muestra ningún código interno. Los botones dicen exactamente qué hacen ("Descargar PDF", "Copiar huella") y los mensajes de error dicen qué pasó y qué hacer ("El servidor todavía no entrega la ficha del informe. Actualiza el backend a la versión con HU-21.").

## Archivos

Nuevos: `app/panel/informe/page.tsx`, `components/vistas/VistaInforme.tsx`, `components/informe/HojaPortada.tsx`, `components/informe/informe.module.css`, `hooks/useFichaInforme.ts`, `lib/informe.ts`, `tests/hu21_informe.test.ts`.

Modificados: `components/shell/Sidebar.tsx` (ítem "Informe"), `lib/api.ts` (`cargarFichaInforme`), `lib/servidor/proxy.ts` y `lib/servidor/proxyCliente.ts` (el BFF deja pasar `GET …/informe/ficha`; para el encuestado, solo de su evaluación).

## Modo demo

Con `NEXT_PUBLIC_DEMO=1` la página muestra una ficha de ejemplo construida con el panel de demostración (código válido y los 5 puntajes); el texto del aviso indica que es una demo.

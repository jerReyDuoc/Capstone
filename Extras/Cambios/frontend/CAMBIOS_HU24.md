# HU-24 · Mantenedor de la matriz normativa (frontend)

Página nueva del panel interno: **`/admin/matriz`**, solo para el administrador de Therion Labs (la protege `middleware.ts` y FastAPI exige el rol `admin_therion` en cada llamada). El encabezado del panel ahora tiene navegación entre **Empresas cliente** y **Matriz normativa**.

## Cómo está pensada la pantalla

Se diseñó con las skills del plugin Design (frontend-design para la dirección visual, accessibility-review para la auditoría WCAG 2.1 AA y los criterios de ux-copy para los textos), sobre los tokens de `globals.css` para que se vea parte del mismo panel.

Lo primero que responde la página es la pregunta con que llega el admin: qué usa hoy el cuestionario y qué cambié yo. Por eso arriba hay una franja dividida en dos. A la izquierda, la **versión vigente** con su etiqueta en grande (es el nombre con que todos se refieren a la matriz y el que sale en los informes), la huella, quién y cuándo la publicó, cuánto contiene y cuántas evaluaciones cerradas la usan. A la derecha, el **borrador en edición**, marcado con un borde punteado y un rayado tenue que lo distinguen como trabajo sin publicar, con el resumen de cambios en lenguaje natural ("2 controles nuevos, 1 brecha modificada"), los errores que impiden publicar y las acciones Revisar y publicar o Descartar. Sin borrador, la misma zona explica que se está en modo lectura y ofrece crearlo.

Debajo hay una pestaña por cada parte de la matriz: **Controles**, **Brechas**, **Rutas formativas** y **Filtro inicial**, con búsqueda por código o texto y filtros Activos, Con cambios, Retirados y Todos. Cada fila muestra su estado frente a la vigente (Nuevo, Modificado, Retirado, Restaurado) con texto, no solo color. Las acciones son Editar, Retirar (o Quitar, si el elemento todavía no se publica) y Restaurar. Editar abre un diálogo con el formulario completo; el código de un elemento ya publicado aparece bloqueado y se explica por qué.

El elemento más propio de la página es la pestaña **Árbol de aplicabilidad**. Reemplaza el árbol que estaba escrito en el código por una grilla: una fila por control (agrupados por dimensión) y una columna "Siempre" más una por cada pregunta del filtro, con la compuerta señalada. Cada celda es un botón que activa o desactiva la regla. Arriba, un **simulador** deja marcar qué respondería una organización (F1 Sí, F2 No…) y muestra cuántos controles le preguntaría el cuestionario con el borrador, con el mismo cálculo que el backend (`aplicables()` en `lib/admin/matriz.ts`). Los controles sin ninguna regla se marcan como "nunca se pregunta".

La pestaña **Historial de versiones** es una línea de tiempo con cada versión publicada, su nota de cambio, autor, fecha y evaluaciones que la usan. Cada una permite ver qué cambió frente a la anterior y, si no hay borrador abierto, crear un borrador desde ella para volver atrás.

Publicar abre un diálogo que primero pide al backend la validación: muestra qué cambia, los errores (que bloquean el botón) y las advertencias, y pide la etiqueta (viene sugerida, por ejemplo `2026.2`) y una nota del cambio normativo de al menos 10 caracteres. El texto del diálogo recuerda que las evaluaciones cerradas conservan su versión y que las nuevas y en curso usarán la publicada.

## Accesibilidad (WCAG 2.1 AA)

Pestañas con el patrón WAI-ARIA (`tablist`, `aria-selected`, `aria-controls`, foco itinerante y navegación con flechas, Inicio y Fin). Los diálogos son `<dialog>` nativos con `showModal()`, que atrapan el foco y se cierran con Escape. Cada campo tiene su `label`, los errores se asocian con `aria-describedby` y `aria-invalid`, y los requeridos llevan `aria-required`. Las celdas del árbol son botones con `aria-pressed` y una etiqueta que se entiende sola ("GOB-001 se suma si responden SÍ a F3"); en modo lectura el visto lleva título accesible. El área táctil de las celdas llega a 44 px con un pseudo-elemento sin agrandar la grilla. Los avisos usan `role="status"` y los errores `role="alert"`; el resultado del simulador está en una región `aria-live`. Los estados nunca dependen solo del color (texto en cada insignia y tachado en lo retirado). Los colores son los de `globals.css`, que ya superan 4,5:1 sobre las superficies. La grilla y las tablas hacen scroll dentro de su contenedor, así que la página no se rompe a 200 % de zoom ni en 1366×768, y la franja pasa a una columna bajo 900 px.

## Archivos

Nuevos: `app/admin/matriz/page.tsx`, `components/admin/MantenedorMatriz.tsx`, `components/admin/matriz.module.css`, `lib/admin/matriz.ts` (contratos, formularios, diferencias y simulador del árbol), `tests/hu24_matriz.test.ts`.

Modificados: `lib/servidor/proxyAdmin.ts` (lista blanca de las rutas de HU-24, hasta 6 segmentos y cuerpos de 64 KB), `lib/servidor/backendAdmin.ts` (pasa al navegador los problemas de validación y los elementos que impiden retirar), `components/admin/PanelClientes.tsx` y `components/admin/admin.module.css` (navegación del panel interno).

## Pruebas

`npm test` incluye `tests/hu24_matriz.test.ts`: el simulador del árbol (compuerta, base, filtros y retirados), el formulario (solo envía lo que cambió y nunca el código de un elemento publicado), la validación previa, los estados de cada fila, el resumen de cambios y la lista blanca del proxy.

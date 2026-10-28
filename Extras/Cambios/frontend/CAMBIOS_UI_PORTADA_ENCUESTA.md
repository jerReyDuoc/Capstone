# Mejora de interfaz · Portada, preguntas iniciales y cuestionario (frontend-next)

## Portada (`/`)

La portada anterior era la composición típica de una landing generada: una etiqueta en mayúsculas sobre el título, una palabra del título destacada en color, un radar de ejemplo al lado y bloques de tarjetas iguales. Ahora la pieza central es una **lámina** con un mapa topográfico de gobernanza, enmarcada como una carta topográfica. Cada cima es uno de los cuatro dominios y su número de curvas de nivel es la madurez (valores de ejemplo). Gestión de Riesgos aparece en rojo como brecha prioritaria y una ruta punteada va del punto de partida al diagnóstico. La lámina tiene una franja superior que explica cómo leerla y una escala de madurez al pie, así se entiende como un objeto y no como líneas sueltas detrás del texto, que fue lo que se veía raro en la primera versión.

Arriba, el título va a la izquierda y la bajada con los botones a la derecha. Así el texto ocupa poca altura y la lámina se ve en la primera pantalla incluso en un notebook de 1366 × 768. En teléfonos las etiquetas del mapa no se leerían, así que la misma información aparece como lista dentro de la lámina.

El mapa es SVG generado al compilar la página con una fórmula fija (`components/publico/MapaGobernanza.tsx`): no hay imágenes que descargar ni JavaScript en el navegador. Las curvas se dibujan una sola vez al cargar; con "reducir movimiento" activado en el sistema aparece completo de inmediato. Los titulares usan **Archivo** en su versión ancha (se carga solo en la portada); el resto del sitio sigue con Space Grotesk e Inter. La paleta TherionLabs no cambia.

## Preguntas iniciales (filtro F1–F7)

Se siguen respondiendo de a una, con la misma lógica, pero ahora:

- **Sí** y **No** son dos botones grandes, con atajos de teclado **S** y **N**.
- El avance es una barra segmentada, con una marca por pregunta.
- Debajo de los botones se explica qué pasa con cada respuesta (por ejemplo, "si respondes Sí, se suman 4 controles").
- A la derecha está el panel **"Tu cuestionario"**: cuántos controles aplican hasta ahora y lo ya respondido, con un clic para volver a cualquier pregunta. En pantallas angostas el panel va debajo.

## Cuestionario (controles)

El problema original era que al elegir un estado la justificación y la evidencia quedaban debajo de cinco tarjetas altas, y "Guardar y continuar" al fondo, así que había que bajar con la rueda en cada control. Ahora:

- Las cinco opciones son **botones compactos**. El número del atajo nunca se sale del botón: si la etiqueta no cabe, pasa a dos líneas dentro del botón. La explicación de cada opción se muestra en una sola línea al pasar el cursor, al enfocarla o al elegirla; los lectores de pantalla siguen recibiendo la explicación completa.
- Si la tarjeta tiene al menos 860 px de ancho, la **pregunta va a la izquierda y la respuesta a la derecha**. Por debajo de ese ancho van una sobre la otra. Se decide con el ancho real de la tarjeta (container query), no con el de la pantalla. Las dos columnas se desplazan con la página: la primera versión dejaba la pregunta fija y su texto se deslizaba dentro de la tarjeta al hacer scroll.
- Al elegir un estado, la vista **baja sola** lo justo para mostrar la justificación.
- La barra **Anterior / Guardar y continuar** queda siempre visible al pie de la tarjeta.
- **Atajos**: 1 a 5 eligen el estado y Ctrl + Enter (⌘ + Enter en Mac) guarda y continúa. En pantallas táctiles o angostas no se muestran.
- Lo que va sobre el cuestionario (número de evaluación, aviso de guardado y límites del día) ahora es **una sola línea**. El aviso completo de límites aparece solo cuando se agotan las validaciones o las evidencias. En pantallas bajas el espaciado se compacta.

La lógica de guardado, la validación de la justificación y la subida de evidencias no cambiaron.

## Errores corregidos de paso

- **Contenido pegado al borde de la ventana** en todas las páginas del flujo (`/encuesta`, `/comenzar`, `/retomar`…). La regla `.flujo { padding: X 0 Y }` borraba el margen lateral del contenedor. Ya estaba antes de esta mejora.
- **El índice lateral quedaba tapado** por el encabezado al hacer scroll.
- **El encabezado se desbordaba** en teléfonos de 360 px y separaba "Retomar" de "evaluación".

## Tamaños revisados

Las tres pantallas (portada, preguntas iniciales y un control) se probaron con el tamaño real de ventana, es decir, la pantalla menos la barra del navegador y de Windows. En todos se verificó que no haya desborde horizontal ni errores en consola:

| Pantalla | Ventana probada |
|---|---|
| Monitor Full HD | 1920 × 950 |
| Notebook Full HD con escala de Windows al 125 % | 1536 × 730 |
| Notebook 1440 × 900 | 1440 × 780 |
| Notebook 1366 × 768 | 1366 × 657 |
| Notebook 1280 × 720 | 1280 × 600 |
| Tablet horizontal | 1024 × 650 |
| Tablet vertical | 820 × 1100 |
| Teléfonos | 414 × 780 y 360 × 680 |

## Archivos

| Archivo | Cambio |
|---|---|
| `app/page.tsx` | Portada nueva (título y botones arriba, lámina del mapa a todo el ancho). |
| `components/publico/MapaGobernanza.tsx` | **Nuevo.** Lámina con el mapa topográfico (SVG generado al compilar). |
| `components/publico/mapa.module.css` | **Nuevo.** Estilos y animación de la lámina. |
| `components/publico/portada.module.css` | **Nuevo.** Estilos de la portada (antes estaban en `publico.module.css`). |
| `components/publico/publico.module.css` | Sin los estilos de la portada; contenedor ancho para `/encuesta`; corrige el margen lateral del flujo; encabezado más corto en teléfonos; compactación en pantallas bajas. |
| `components/publico/Marco.tsx` | En teléfonos el botón dice "Retomar". |
| `app/encuesta/page.tsx` | Contenedor ancho y texto de introducción más corto. |
| `components/encuesta/InicioEncuesta.tsx` | Evaluación, guardado y límites en una sola línea. |
| `components/encuesta/BannerLimites.tsx` | Modo `compacto`: una línea de texto cuando no hay nada agotado. |
| `components/cuestionario/PasoFiltro.tsx` | Rediseño de las preguntas iniciales (Sí/No grandes, atajos S/N y panel "Tu cuestionario"). |
| `components/cuestionario/PasoControl.tsx` | Dos columnas, opciones compactas, desplazamiento automático y atajos. |
| `components/cuestionario/cuestionario.module.css` | Estilos de todo lo anterior. |

## Cómo probarlo

```powershell
docker compose up -d --build
```

Abre `http://localhost:3000` (recarga con Ctrl + F5). La compilación del contenedor web revisa los tipos de TypeScript; si la imagen se construye, no hay errores de tipos.

# HU-15 · Agente IA Tutor en el panel de formación (frontend-next)

El chat con el tutor vive dentro del panel de formación y solo aparece para el usuario definitivo de una empresa cliente (modo `cliente` del panel). El encuestado y el equipo interno no lo ven, porque el tutor es parte del servicio pagado y el backend igual les respondería 403.

## Dónde aparece

En **Capacitación** se agregó una tarjeta "Tutor IA de gobernanza", debajo del avance de la empresa, con el botón "Hablar con el tutor". Esa conversación usa todas las brechas de la evaluación vigente y el nivel que sugiere el backend: el de la ruta de la brecha más prioritaria. Dentro de cada **módulo** (`/panel/capacitacion/[ruta]`) hay un botón "Preguntar al tutor IA" que abre el mismo tutor con ese módulo como foco, así que el nivel por defecto es el del módulo y las sugerencias de inicio lo mencionan.

El tutor se abre en un panel lateral hecho con `<dialog>` modal. Así el foco queda atrapado dentro del panel, Esc lo cierra y el foco vuelve al botón que lo abrió. En pantallas angostas ocupa todo el ancho.

## Cómo se usa

Arriba se ve sobre qué trabaja el tutor ("Basado en tus 12 brechas de la evaluación N.º 34") y un selector de nivel Inicial / Intermedio / Avanzado. El selector es un grupo de radio accesible, marca cuál es el nivel sugerido y explica en una línea qué cambia en cada nivel. Cambiar el nivel guarda la preferencia en la conversación (`PATCH`).

Al abrir, el tutor retoma la conversación activa más reciente del mismo módulo. Si no hay ninguna, muestra una bienvenida con preguntas sugeridas armadas con las brechas reales del contexto (por ejemplo, "Dame un plan de acción para cerrar DAT-001"); nunca inventa brechas. La conversación se crea con el primer mensaje, para no dejar conversaciones vacías.

Las respuestas del tutor muestran su tipo (Explicación, Plan de acción, Recomendación o Fuera de alcance) y el nivel con que se respondieron. Los planes de acción salen como una lista numerada con el responsable sugerido y la evidencia esperada de cada paso. Las brechas citadas enlazan al listado de brechas, al módulo que las cierra y a "Subir evidencia" (HU-17), que es lo que de verdad mejora el puntaje. Las preguntas de seguimiento se pueden enviar con un clic.

Mientras el tutor responde aparece un indicador "escribiendo", que también se anuncia a lectores de pantalla. La conversación es una región `role="log"` con `aria-live`, así que cada respuesta nueva se lee sin mover el foco. Enter envía el mensaje y Mayús+Enter agrega un salto de línea. Bajo el cuadro se ve la cuota del día ("Te quedan 57 mensajes de 60 hoy") y un contador cuando el mensaje se acerca al máximo.

Si el envío falla, el texto vuelve al cuadro para no perderlo y se explica el error en lenguaje simple: cuota agotada, ráfaga, servicio de IA no disponible o contrato no vigente. Si la empresa ya tiene una evaluación más reciente, la conversación queda de solo lectura y se ofrece abrir una nueva. El historial lista las conversaciones guardadas, permite abrirlas o borrarlas (con confirmación) y recuerda que se borran solas a los 30 días sin actividad.

## v1.1 · Ajustes tras la prueba del equipo (28-oct)

Cada paso de un plan de acción tiene ahora un botón **"Explícame este paso"**. El botón envía una pregunta explícita sobre ese paso, para que el tutor no vuelva a escribir el plan completo. Las sugerencias del tutor aparecen bajo el título "Puedes preguntarme:", porque desde esta versión están redactadas como mensajes del usuario y no como preguntas hacia él. Las referencias normativas se muestran como "Fuente del control", porque ya no las escribe el modelo: son el framework y el artículo reales de la matriz de controles.

## BFF

La lista blanca del proxy del cliente (`lib/servidor/proxyCliente.ts`) suma las siete rutas de `/api/tutor`, y el handler `/bff/cliente/api/[...ruta]` ahora acepta `PATCH` y `DELETE`, con la misma verificación de mismo origen que los `POST`. Un `DELETE` responde 204 sin cuerpo. El envío de un mensaje tiene un tiempo máximo de 60 s, porque espera al LLM, y nunca se reintenta solo: cada intento gasta cuota.

## Archivos

| Archivo | Cambio |
|---|---|
| `components/formacion/TutorIA.tsx` | **Nuevo.** Tarjeta o botón de entrada, panel lateral, chat, mensajes estructurados e historial. |
| `components/formacion/tutor.module.css` | **Nuevo.** Estilos con los tokens de `globals.css`. |
| `hooks/useTutor.ts` | **Nuevo.** Estado del chat: contexto, conversación, nivel, envío optimista y errores. |
| `lib/tutor.ts` | **Nuevo.** Llamadas al BFF y presentación (validación, cuota, sugerencias, errores). |
| `lib/types.ts` | Tipos de la API del tutor. |
| `lib/servidor/proxyCliente.ts`, `app/bff/cliente/api/[...ruta]/route.ts` | Rutas del tutor; `PATCH` y `DELETE`. |
| `components/vistas/VistaCapacitacion.tsx`, `components/formacion/RecorridoModulo.tsx`, `app/globals.css` | Entrada al tutor en Capacitación y en cada módulo. |
| `components/ui/Icon.tsx` | Íconos `mensaje`, `enviar`, `basura`, `historial` y `mas`. |
| `tests/hu15_tutor.test.ts` | **Nuevo.** Validación, cuota, sugerencias, retomar conversación, errores y lista blanca del BFF. |

La lógica nueva y los componentes tocados pasan `tsc` en modo estricto, y las pruebas de `lib` pasan, junto con las anteriores del cliente. Falta revisar el panel en el navegador con `npm run dev` o en Docker, porque en este entorno no se pudo levantar Next.js.

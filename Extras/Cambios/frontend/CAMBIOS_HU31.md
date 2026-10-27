# HU-31 · "Contratar la plataforma" en los resultados y bandeja del admin (frontend-next)

Pantallas del encuestado para pedir la contratación desde sus resultados, sin cuenta, y ajuste de la bandeja del administrador a los estados nuevos. El backend está descrito en `Extras/Cambios/backend/CAMBIOS_HU31.md`.

## Qué ve el encuestado

Al final del **Diagnóstico** (`/panel`), después de los gráficos y del resumen de brechas, aparece una tarjeta "Siguiente paso" con el título "Cierra tus N brechas con ComplianceIA", los tres beneficios del servicio pagado (cursos por dimensión, tutor IA y documentos que cierran brechas) y el botón **Contratar la plataforma**. Va después de los resultados a propósito: primero la persona recibe el diagnóstico gratis y luego se le ofrece el siguiente paso, sin interrumpir la lectura. La barra lateral suma el enlace "Contratar" junto a "Mi evaluación". Si ya pidió contratar, la tarjeta reemplaza el botón por el estado de su solicitud ("Solicitud enviada", "Ya estamos en contacto", "Contratación confirmada"), así no la envía dos veces. Nada de esto aparece para el equipo interno.

El botón lleva a **`/panel/contratar`**, dentro del mismo panel para que no se sienta como salir de los resultados. A la izquierda explica qué incluye el servicio y cómo sigue el proceso en tres pasos; a la derecha está el formulario: nombre y apellido, cargo, empresa, correo de trabajo y teléfono opcional, y un grupo "Autorizaciones" con los dos consentimientos en tarjetas separadas, cada uno con su casilla, su texto completo y la versión del texto. Los textos vienen de la API, así que si el PO los cambia el formulario muestra el nuevo sin tocar el frontend. Abajo está la verificación de Turnstile (normalmente invisible), una nota de privacidad con enlace al aviso legal y el botón **Enviar solicitud**.

Al enviar, el formulario valida en el navegador con las mismas reglas del backend. Si falta algo, aparece arriba un resumen con enlaces a cada campo y el foco va a ese resumen; cada campo marcado muestra su error con icono y texto. Si el backend rechaza algo (un consentimiento cuyo texto cambió, el teléfono, el límite diario), el error se muestra con el mismo componente de la encuesta pública, incluida la cuenta regresiva cuando hay que esperar, y el campo afectado queda marcado. Cuando el texto de un consentimiento cambió, se recarga y su casilla se desmarca para que la persona lo lea de nuevo. Con éxito, el formulario se reemplaza por una confirmación ("Listo, recibimos tu solicitud") que recibe el foco y recuerda que los resultados, el informe y el plan siguen disponibles sin costo.

## Bandeja del administrador (`/admin/clientes`)

La pestaña *Solicitudes* ahora abre en **Nuevas** y los filtros son Nueva, Contactada, Contratada, Contratada · migrada, Descartada y Todas, cada uno con su conteo. La tabla muestra el cargo bajo el nombre del contacto y, en la columna *Autorizaciones*, los dos consentimientos con su versión y fecha. Las acciones dependen del estado: una nueva se marca contactada (acción principal), contratada o descartada; una contactada, contratada o descartada; una contratada puede volver a contactada. Descartar pide confirmación porque borra el contacto y no se puede deshacer. La elección de solicitudes para el alta de HU-27 no cambia: solo contratadas, autorizadas y con la evaluación completada. HU-28 puede integrar esta bandeja en el panel interno completo.

## Seguridad

Todo pasa por el BFF. La lista blanca de `lib/servidor/proxy.ts` agrega solo tres rutas: leer los consentimientos, leer la solicitud de la evaluación de la sesión y enviar la solicitud. El envío reenvía la IP real (para los límites del backend) y el proxy comprueba que el `evaluacion_id` del cuerpo sea el de la sesión, igual que ya hacía con las respuestas. `middleware.ts` agrega un filtro de ráfagas para el envío y trata `/panel/contratar` como página del flujo, con CSP con nonce para poder cargar Turnstile. El CAPTCHA usa la acción `solicitar_contratacion`, distinta de la del inicio de la encuesta.

## Diseño, textos y accesibilidad

Se aplicaron las pautas de *ux-copy* y una revisión *WCAG 2.1 AA* (skills de diseño) sobre las dos pantallas.

**Textos.** Los botones dicen lo que hacen ("Contratar la plataforma", "Enviar solicitud", "Marcar contactada", "Volver a mis resultados"), nunca "Aceptar" o "Enviar" a secas. Los errores siguen la estructura qué pasó y cómo arreglarlo ("Revisa el teléfono. Usa solo números, espacios o +, por ejemplo +56 9 1234 5678."). Se baja la ansiedad del paso comercial con "No pagas nada al enviarlos" y "Enviar la solicitud no tiene costo ni te compromete". Los consentimientos dicen en lenguaje claro qué datos, para qué, qué pasa después y cómo se retiran; siguen siendo provisorios hasta que el PO los apruebe. Se usa siempre el mismo término para lo mismo: "solicitud", "autorización", "evaluación".

**Accesibilidad.**

| Criterio WCAG | Cómo se cumple |
|---|---|
| 1.3.1 Información y relaciones | Etiquetas `<label>` visibles, las autorizaciones en `<fieldset>` con `<legend>`, pasos en `<ol>`, secciones con `aria-labelledby` |
| 1.3.5 Propósito de los campos | `autocomplete` `name`, `organization-title`, `organization`, `email` y `tel` |
| 1.4.1 Uso del color | Errores con icono y texto además del borde rojo; el estado de la solicitud es una insignia con texto |
| 1.4.3 / 1.4.11 Contraste | Solo tokens de `globals.css` (texto ≥ 6,2:1, error `--alto` ≈ 5,4:1 sobre las tarjetas, bordes de control ≥ 3:1) |
| 1.4.10 Reflujo | Una columna bajo 1024 px y campos apilados bajo 640 px; sin desplazamiento horizontal a 200 % |
| 2.4.3 Orden del foco | El foco va al resumen de errores al fallar y al título de la confirmación al enviar |
| 2.5.5 Área táctil | Controles y filas de casillas de al menos 44 px |
| 3.3.1 / 3.3.3 Identificación y sugerencia de errores | Resumen con enlaces a cada campo, `aria-invalid` y `aria-describedby` hacia el error y la ayuda |
| 3.3.2 Etiquetas o instrucciones | "Todos los campos son obligatorios, salvo el teléfono"; "(opcional)" en la etiqueta |
| 4.1.3 Mensajes de estado | Confirmación y estado de la solicitud con `role="status"`; errores del servidor con `role="alert"` |

Pendiente de probar con lector de pantalla real (NVDA o VoiceOver) en el Docker del equipo; el widget de Turnstile tiene su propia accesibilidad, a cargo de Cloudflare.

## Archivos

| Archivo | Cambio |
|---|---|
| `app/panel/contratar/page.tsx` | **Nueva.** Página del formulario (Server Component con nonce y clave de Turnstile). |
| `components/contratacion/CtaContratar.tsx` | **Nuevo.** Tarjeta "Contratar la plataforma" en el diagnóstico. |
| `components/contratacion/FormContratacion.tsx` | **Nuevo.** Formulario, estados (cargando, ya enviada, evaluación sin terminar, error) y confirmación. |
| `components/contratacion/contratacion.module.css` | **Nuevo.** Estilos con los tokens existentes. |
| `hooks/useSolicitudContratacion.ts` | **Nuevo.** Llamadas al BFF y estado de la solicitud. |
| `lib/contratacion.ts` | **Nuevo.** Lógica pura: validación, cuerpo, parseo, textos de estados y errores. |
| `components/vistas/VistaDiagnostico.tsx`, `components/shell/Sidebar.tsx` | CTA en los resultados y enlace "Contratar". |
| `lib/encuesta/contratos.ts`, `lib/encuesta/errores.ts` | El error del backend conserva `campo` y `consentimiento`; mensajes de los códigos nuevos. |
| `lib/servidor/proxy.ts`, `app/bff/api/[...ruta]/route.ts` | Rutas de contratación en la lista blanca; control del `evaluacion_id` del cuerpo generalizado. |
| `middleware.ts` | Ráfagas del envío y CSP con nonce en `/panel/contratar`. |
| `lib/admin/api.ts`, `lib/servidor/proxyAdmin.ts`, `components/admin/PanelClientes.tsx` | Estados de la bandeja, conteo, cargo, consentimientos y acciones por estado. |
| `tests/hu31_contratacion.test.ts` | **Nuevo.** 15 pruebas. |
| `tests/hu27_admin.test.ts` | `pendiente` → `nueva`. |

## Cómo probarlo

```bash
docker compose up -d --build web
docker compose exec web npm run typecheck
docker compose exec web npm test
```

Completa una evaluación desde `/comenzar`, abre `/panel`, baja hasta "Siguiente paso" y envía la solicitud. Luego entra a `/admin/clientes` con el admin y revisa la pestaña de nuevas. En este entorno no hubo acceso a npm: el chequeo de tipos se hizo con `tsc` usando los tipos reales de React y declaraciones mínimas de Next, sin errores nuevos (los dos que aparecen también aparecen en `main` y vienen de esas declaraciones), y las pruebas de `lib/` se corrieron con un ejecutor compatible con vitest: 15/15 de HU-31 y 75/75 de las suites existentes. Corran `npm run typecheck` y `npm test` en Docker antes de subir.

# HU-39 · Asistente de registro (frontend)

Nueva página **/empresa/asistente** («Asistente de registro», grupo *Privacidad* de la barra lateral, solo cliente con servicio).

| Archivo | Qué hace |
|---|---|
| `app/empresa/(espacio)/asistente/page.tsx` | Página |
| `components/empresa/asistente/AsistenteRegistro.tsx` | Entrevista tipo chat por áreas, subida de documentos, panel de propuestas y revisión del registro |
| `components/empresa/asistente/EditorPropuesta.tsx` | Edición de una propuesta (solo los campos de su tipo, con los catálogos del mapa y del registro) |
| `components/empresa/asistente/asistente.module.css` | Estilos (tokens de `globals.css`) |
| `lib/asistente.ts` | Llamadas y lógica pura de presentación |
| `lib/servidor/proxyCliente.ts` | Lista blanca `asistente/*` (respuestas 90 s, documentos multipart 120 s) |
| `lib/mapaDatos.ts` | Origen `ia`: «Sugerido por IA y aceptado por tu equipo» en el mapa |
| `components/shell/Sidebar.tsx` | Enlace «Asistente de registro» |
| `tests/asistente.test.ts` | Proxy, etiqueta de la IA, filas de la tarjeta, dependencias, edición y validaciones |

**Human-in-the-Loop en la interfaz.** Cada tarjeta muestra la etiqueta **«Sugerido por IA · Modelo X · Guía vY»**, el tipo, el riesgo calculado, los campos con un «¿Por qué?» desplegable, las alertas (dato sensible sin base, envío sin garantía, datos sin plazo, envío sin actividad) y los botones **Aceptar / Editar / Descartar** (con motivo). «Aceptar» se deshabilita mientras falte aceptar el elemento del que depende. Lo aceptado enlaza al mapa o al registro (las actividades entran como borrador).

**Sin ayuda automática.** La entrevista sigue igual, un aviso explica por qué y se enlaza a completar el mapa a mano (sugerencias de la evaluación y plantillas por rubro).

**Lenguaje.** Ningún texto visible menciona códigos internos; el chat pide describir procesos, no personas. Accesibilidad: `role="log"` y `aria-live` en el chat, foco visible, etiquetas en todos los campos.

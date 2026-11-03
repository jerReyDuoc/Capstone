# HU-16 · Borradores de cumplimiento (frontend-next)

La historia se usa desde una página nueva del espacio de la empresa, **`/empresa/borradores`**, que aparece en la barra lateral del grupo "Mi empresa" (como "Borradores") y como acceso directo en "Mi empresa". Solo la ve el usuario definitivo; si el contrato de su empresa no está vigente, la página lo explica y, durante el plazo de gracia, lo manda a Mis documentos, donde siguen sus borradores consolidados.

## La página

Arriba está el formulario **Nuevo borrador**: el usuario elige el documento (Política de uso de LLM, Aviso de privacidad o Evaluación de impacto), ve las dimensiones del modelo que cubre y sus secciones, puede escribir indicaciones para el Agente IA (con un recordatorio de no escribir datos personales, porque se anonimizan y quedan como campos por completar) y decide si lo adapta con IA. La casilla muestra la cuota que le queda a la empresa ese día. Mientras el agente redacta se indica que puede tardar hasta un minuto; si el borrador se armó sin IA (cuota agotada, servicio caído o IA deshabilitada) se muestra el aviso que devuelve el backend.

Debajo está **Mis borradores**, con el estado (En revisión / Consolidado), la versión, si se adaptó con IA y cuántos campos quedan por completar, y las acciones Revisar/Ver y Descartar (con confirmación en la misma fila, como en Mis documentos).

Al abrir uno aparece el **editor**: el Markdown a la izquierda y la vista previa a la derecha (en pantallas de menos de 1200 px, como el notebook de 1366×768 con la barra lateral, pasan a pestañas). Arriba se listan las sugerencias de revisión del Agente IA y las advertencias que le sirven al usuario, y un contador de campos `[COMPLETAR: …]` con el botón **Ir al siguiente**, que selecciona el próximo marcador en el editor para reemplazarlo. Los botones son Guardar cambios, Descargar PDF, Descargar Markdown y Consolidar. Descargar o consolidar con cambios sin guardar guarda primero; salir de la página con cambios sin guardar pide confirmación al navegador. Consolidar se confirma en la misma tarjeta y, si quedan campos por completar, exige marcar "Consolidar aunque queden N campos por completar". Un borrador consolidado se abre de solo lectura con el enlace a Mis documentos.

La vista previa no inserta HTML: `lib/borradores.ts` convierte el Markdown en bloques y segmentos que React pinta como texto, con el mismo subconjunto que el PDF del backend. Lo que el usuario escriba (incluido HTML) se muestra tal cual y no se ejecuta.

## BFF

`lib/servidor/proxyCliente.ts` agrega las rutas de `/api/borradores` (generar con 90 s de espera, `PATCH` de la edición, `DELETE`, consolidación y la descarga binaria, que admite `application/pdf` y `text/markdown`). `lib/servidor/proxy.ts` deja pasar el parámetro `formato` (hasta 5 caracteres) y el proxy del cliente devuelve los `text/*` con `charset=utf-8`.

## Archivos

Nuevos: `app/empresa/(espacio)/borradores/page.tsx`, `components/empresa/Borradores.tsx`, `components/empresa/borradores.module.css`, `lib/borradores.ts`, `tests/hu16_borradores.test.ts`.

Modificados: `components/shell/Sidebar.tsx`, `components/empresa/EspacioEmpresa.tsx`, `lib/servidor/proxyCliente.ts`, `lib/servidor/proxy.ts`, `app/bff/cliente/api/[...ruta]/route.ts`.

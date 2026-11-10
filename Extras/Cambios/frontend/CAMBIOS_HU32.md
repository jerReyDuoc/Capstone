# HU-32 · Derechos ARCOP en la página web

*Como Usuario Registrado quiero realizar una petición de mis derechos ARCOP en la página web,
para acceder, rectificar, traspasar o eliminar mis datos.*

El backend de ARCOP ya existía (ciclo de vida, plazos legales, código de seguimiento,
anonimización al aprobar una supresión; ver `Extras/Cambios/backend/CAMBIOS_ARCOP.md` y
`CAMBIOS_HU30.md`). Esta HU agrega **las pantallas** para los tres actores y **un solo endpoint
nuevo** en el backend: la descarga de los datos del titular (acceso y portabilidad).

## Decisiones acordadas con el PO (10-nov)

| Pregunta | Decisión |
|---|---|
| ¿"Acceder" y "traspasar" entregan los datos? | Sí: endpoint nuevo de exportación en JSON y CSV, disponible cuando el admin **resuelve** la solicitud |
| ¿Cómo se aplica la rectificación? | El admin corrige el dato a mano y cierra la solicitud con su respuesta |
| ¿Se puede tocar el backend? | Solo para agregar ese endpoint |
| ¿Qué es el "código de retorno" del usuario temporal? | El **N.º de evaluación + clave** de `/retomar` (el invitado por id + correo queda fuera de la web) |
| ¿Cuántos derechos se muestran? | Los 6 de la Ley 21.719: acceso, rectificación, supresión, oposición, portabilidad y bloqueo |

## Criterios de aceptación

| Criterio | Dónde se cumple |
|---|---|
| 1. Usuarios temporales gestionan sus derechos con su código de retorno | `/mis-derechos` (pública) y `/retomar` llevan al mismo ingreso (N.º de evaluación + clave, `FormRetomar destino="derechos"`) y de ahí a **`/panel/mis-derechos`**, dentro del panel y con "Mis derechos" en la barra lateral. Todo pasa por `/bff/api` (cookie httpOnly) |
| 2. Usuarios definitivos gestionan sus derechos desde la interfaz contratada | **`/empresa/mis-derechos`**, en la barra lateral del espacio de la empresa (grupo "Privacidad"). Disponible con o sin contrato vigente (HU-30). Pasa por `/bff/cliente/api` |
| 3. El admin maneja las peticiones desde el panel de administrador | **`/admin/arcop`** ("Solicitudes ARCOP" en la barra del panel interno). Pasa por `/bff/admin/api` |

## Lo que ve cada uno

### Titular (temporal o definitivo): `components/arcop/DerechosTitular.tsx`

La pantalla responde tres preguntas, en orden:

1. **¿Tengo algo pendiente?** Si el responsable pidió información, un aviso arriba con el botón
   "Responder ahora".
2. **¿Qué quiero hacer?** Seis tarjetas en lenguaje claro ("Ver qué datos tienen de mí",
   "Corregir un dato", "Llevarme mis datos", "Eliminar mis datos"…), con el nombre legal del
   derecho debajo. Al elegir una aparece un formulario adaptado: qué escribir, un ejemplo, el
   plazo de respuesta, la nota de descarga (acceso/portabilidad) y, en la supresión, una casilla
   obligatoria que explica qué se borra según sea temporal o definitivo. Al enviar se muestra el
   **código de seguimiento** con botón para copiarlo.
3. **¿Cómo van mis solicitudes?** Lista con derecho, código, fecha, plazo y estado. Al abrir una:
   avance en 4 hitos (Enviada → En revisión → En proceso → Respondida), qué significa el estado,
   la respuesta del responsable, **Descargar JSON / Descargar CSV** si corresponde, lo que pidió,
   el historial (en segunda persona: "Enviaste la solicitud", "Te pidieron más información") y
   "cancelar solicitud" con confirmación.

### Público: `/mis-derechos`

Tres puertas: *Hice el autodiagnóstico* (N.º + clave), *Tengo cuenta de empresa* (a `/ingresar`)
y *Ya envié una solicitud* (consulta del estado con el código, sin ingresar; sirve aunque una
supresión ya haya revocado el acceso). Debajo, los seis derechos explicados. Enlazada desde la
portada (sección Privacidad), el pie de las páginas públicas y `/retomar`.

### Admin: `components/arcop/BandejaArcop.tsx`

Mismo esquema que la Bandeja de revisión (HU-22), para no aprender otra pantalla:

- **Franja de cifras** clicables: Nuevas, En revisión, Esperando al titular, En proceso y
  **Plazo vencido** (en rojo si hay).
- **Filtros**: estado, derecho, evaluación n.º y "solo con plazo vencido"; "Limpiar filtros".
- **Lista | detalle**. El detalle muestra el titular (autodiagnóstico con su N.º de evaluación o
  usuario de empresa cliente), el avance, el plazo, una **guía según el derecho** (p. ej. en la
  rectificación: "corrige a mano el dato y resuelve contando qué se corrigió"), lo que pidió el
  titular y el historial.
- **Un panel "¿Qué quieres hacer?"** que solo ofrece las acciones válidas en ese estado
  (`transiciones_posibles` del backend) con el siguiente paso preseleccionado: pasar a revisión,
  pedir información (comentario obligatorio), pasar a proceso, prorrogar (una vez, antes de vencer,
  nunca en bloqueo), resolver o rechazar (respuesta obligatoria, con el aviso de no incluir datos
  personales). **Aprobar una supresión** exige marcar una confirmación y el botón es rojo:
  "Aprobar supresión y anonimizar".
- Si otra persona cambió la solicitud (409), se avisa y se recarga.

## Backend: endpoint nuevo

`GET /api/arcop/solicitudes/{id}/exportacion?formato=json|csv` (solo el titular dueño).

- 404 si la solicitud es de otro titular; 403 al admin; 409 `EXPORTACION_NO_DISPONIBLE` si no es
  de acceso/portabilidad o aún no está `resuelta`; 400 con un formato inválido.
- **JSON** (portabilidad, lectura mecánica) y **CSV largo** `seccion,referencia,campo,valor` con
  BOM para Excel y neutralización de fórmulas (CSV injection).
- Contenido: datos del titular (correo, rubro y aviso legal aceptado; o nombre, correo, estado de
  la cuenta y empresa del usuario definitivo), sus evaluaciones (filtro de aplicabilidad,
  respuestas con su justificación, evidencias vigentes y resultados por dominio) y sus
  solicitudes ARCOP. Las evaluaciones de una empresa cliente **no** van: son de la persona
  jurídica (HU-30) y se descargan en "Mis documentos". Los textos salen como están guardados
  (anonimizados desde HU-06): se explica en `notas`.
- Nunca salen hashes, claves, contraseñas, tokens, rutas en disco ni ids de administradores.
- Cada descarga queda en el audit log como `arcop.datos_exportados` (categoría acceso) con el tipo
  de solicitud, el formato y conteos, sin datos personales.

## Seguridad en el BFF

- `/bff/api` (temporal): + la descarga como binario; la respuesta binaria ahora admite una lista
  de tipos por regla (por defecto sigue siendo solo PDF; la exportación admite `application/json`
  y `text/csv`).
- `/bff/cliente/api` (definitivo): + catálogo, listado, detalle, crear, cancelar, aportar
  información y descarga. Nada de lo del admin.
- `/bff/admin/api`: + listado, detalle, cambio de estado, prórroga y resolución. El admin no puede
  crear, cancelar, aportar ni descargar por el titular. Filtros nuevos en la lista blanca de la
  query: estados ARCOP, `tipo` y `vencidas`.
- `POST /bff/arcop/seguimiento` (público): valida y normaliza el código antes de llamar al
  backend, lo recibe en el cuerpo (no en la URL), devuelve solo una lista blanca de campos y tiene
  límite de ráfagas por IP en `middleware.ts` (20/min).

## Archivos

| Tipo | Archivo |
|---|---|
| nuevo | `backend/app/application/use_cases/exportar_datos_arcop.py` |
| modificado | `backend/app/api/routes/arcop.py` (solo la ruta nueva y sus imports) |
| nuevo | `backend/tests/test_hu32_exportacion_arcop.py` |
| modificado | `backend/tests/test_hu20_autorizacion.py` (clasifica la ruta nueva: exige token) |
| nuevo | `frontend-next/lib/arcop.ts` (textos, reglas y llamadas) |
| nuevo | `frontend-next/components/arcop/` (`DerechosTitular`, `BandejaArcop`, `SeguimientoPublico`, `PanelMisDerechos`, `Comunes`, `arcop.module.css`) |
| nuevo | `frontend-next/app/mis-derechos/page.tsx`, `app/panel/mis-derechos/page.tsx`, `app/empresa/(espacio)/mis-derechos/page.tsx`, `app/admin/arcop/page.tsx`, `app/bff/arcop/seguimiento/route.ts` |
| modificado | `frontend-next/lib/servidor/proxy.ts`, `proxyCliente.ts`, `proxyAdmin.ts`, `app/bff/api/[...ruta]/route.ts` |
| modificado | `frontend-next/components/shell/Sidebar.tsx` (grupo "Privacidad"), `components/admin/BarraAdmin.tsx` (sección nueva), `components/inicio/FormRetomar.tsx` (prop `destino`), `components/publico/Marco.tsx` (enlace en el pie), `app/page.tsx`, `app/retomar/page.tsx`, `middleware.ts` |
| nuevo / modificado | `frontend-next/tests/hu32_arcop.test.ts` (21 pruebas) · `tests/hu28_acceso.test.ts` (el cliente ahora sí llega a ARCOP) |
| modificado | `Proyecto/README.md` |

## Cómo probarlo

```bash
docker compose exec worker pytest tests/test_hu32_exportacion_arcop.py tests/test_solicitudes_arcop.py tests/test_hu20_autorizacion.py tests/test_hu30_contrato.py -v
cd frontend-next && npm test && npm run build
```

Recorrido manual:

1. **Temporal:** comienza un autodiagnóstico en `/comenzar` y guarda N.º y clave. En
   `/mis-derechos` ingresa con ellos, elige "Llevarme mis datos" y envía. Copia el código.
2. **Admin:** en `/admin/arcop` aparece en "Nuevas". Ábrela, pásala a revisión, pide información.
3. **Temporal:** el aviso "Una solicitud necesita tu respuesta" lleva al formulario; responde.
4. **Admin:** pásala a proceso y resuélvela. **Temporal:** descarga JSON y CSV.
5. Consulta el código en `/mis-derechos#seguimiento` sin sesión.
6. **Definitivo:** con un cliente activado, `/empresa/mis-derechos` (también con el contrato
   suspendido). Pide una supresión y apruébala desde el admin: la cuenta se cierra y el código
   sigue respondiendo.

## Verificación hecha

En este entorno no hubo acceso a PyPI ni a npm, así que **pytest, vitest y `next build` no se
pudieron ejecutar con las dependencias reales**: córranlos en Docker con los comandos de arriba
antes de integrar. Sí se hizo:

- `py_compile` del Python modificado y prueba de las funciones puras de la exportación (CSV, JSON,
  conteos, nombre de archivo y reglas de disponibilidad) con módulos simulados.
- `tsc --strict` de todos los archivos nuevos y modificados del frontend, con declaraciones mínimas
  de React y Next (sin errores).
- Las 21 pruebas de `hu32_arcop.test.ts` y las de los proxies existentes (`hu28`, `hu22`, `hu24`,
  `hu29`, `hu30`, `hu16`, `hu26`, `hu21`) con un sustituto mínimo de vitest: pasan.
- Hallazgo previo a esta HU: `hu31_contratacion.test.ts` espera que `estado=pendiente` se descarte
  en la query del admin, pero HU-22 lo agregó a la lista blanca (bandeja de revisión). Esa prueba
  ya fallaba antes de este cambio.

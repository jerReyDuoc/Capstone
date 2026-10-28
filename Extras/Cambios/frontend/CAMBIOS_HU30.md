# HU-30 · Vigencia del contrato (frontend-next, ajuste mínimo)

Con HU-30 el usuario definitivo puede iniciar sesión aunque su contrato no esté vigente, y el backend le responde 403 `CONTRATO_NO_VIGENTE` al pedir el espacio de la empresa. Sin este ajuste el espacio mostraba el error genérico "No pudimos cargar el espacio de tu empresa". Ahora, ante ese 403 (o `PLAZO_GRACIA_VENCIDO`), `EspacioEmpresa` consulta `GET /api/cliente/contrato` y muestra el mensaje de la situación del contrato, el acceso a los resultados de sus evaluaciones (siguen gratis), las constancias para descargar mientras dure el plazo de gracia y el recordatorio de que sus derechos ARCOP siguen disponibles.

| Archivo | Cambio |
|---|---|
| `lib/servidor/proxyCliente.ts` | Lista blanca: `GET cliente/contrato`. |
| `lib/empresa.ts` | Tipos `ContratoApi` y `ContratoClienteApi`, `cargarContratoCliente()` y `SIN_SERVICIO`. |
| `components/empresa/EspacioEmpresa.tsx` | Estado `sin_servicio` y vista `SinServicio`. |
| `tests/hu30_contrato.test.ts` | **Nuevo.** Lista blanca y códigos de corte. |

No se pudo correr `npm run typecheck` ni `npm test` en este entorno (sin acceso a npm): córranlos antes de subir.

Queda para después: los botones de renovar, suspender, reactivar y terminar en el panel interno (`components/admin/PanelClientes.tsx`) y una pantalla de ARCOP para el cliente (el backend ya lo admite; falta abrir las rutas `arcop/solicitudes` en la lista blanca del proxy del cliente).

# HU-27 · Pantalla del administrador y activación de cuenta (frontend-next)

Pantalla del panel interno para dar de alta a la empresa cliente y su usuario definitivo a partir de una solicitud contratada, y la página donde ese usuario define su contraseña. El backend está descrito en `Extras/Cambios/backend/CAMBIOS_HU27.md`.

## Páginas

**`/admin/login`** es el inicio de sesión del administrador. Usa el login que ya existía (`POST /api/auth/login`) a través del BFF, y el token queda en una cookie httpOnly propia del admin (`cai_admin`, `__Host-cai_admin` en producción) con `SameSite=Strict`, distinta de la cookie del encuestado.

**`/admin/clientes`** tiene tres pestañas. En *Solicitudes de contratación* el administrador filtra por estado, marca solicitudes como contratadas (o las vuelve a pendiente o las descarta) y elige con una casilla las que pasarán a la empresa; solo se pueden elegir las contratadas, autorizadas y con la evaluación completada. Debajo está el formulario de alta: razón social, RUT (validado con dígito verificador), rubro, fechas del contrato, y nombre y correo del usuario definitivo. Se prellena con lo que dejó el usuario temporal en la solicitud, y también permite traspasar las solicitudes a una empresa existente. Al terminar muestra qué se migró de cada evaluación y si el enlace de activación salió. En *Empresas* se ve el contrato, el estado del usuario y el botón para reenviar la activación, y en *Bitácora* las últimas 100 acciones registradas.

**`/activar#token=…`** es la página del enlace del correo. Lee el token del fragmento, lo quita de la barra de direcciones, valida el enlace sin consumirlo y muestra el formulario de contraseña con confirmación. Las reglas se anticipan en el navegador, pero la validación real la hace el backend, y si este rechaza la contraseña el enlace no se consume.

## Seguridad

Todo pasa por el BFF. `middleware.ts` redirige `/admin/*` a `/admin/login` sin sesión de admin, bloquea el uso directo de `/api/admin`, `/api/auth/login` y `/api/auth/activacion` a través del rewrite (así la API recibe la IP real para sus límites de intentos y el token del admin nunca llega al JavaScript), agrega límites de ráfagas para el login del admin y la activación, y marca `/admin` y `/activar` como `no-store`. El proxy `/bff/admin/api/*` solo reenvía la lista blanca de `lib/servidor/proxyAdmin.ts` y exige mismo origen en todo lo que no sea GET.

## Archivos

| Archivo | Cambio |
|---|---|
| `app/admin/page.tsx`, `app/admin/login/page.tsx`, `app/admin/clientes/page.tsx` | **Nuevas.** |
| `app/activar/page.tsx` | **Nueva.** |
| `app/bff/admin/login`, `logout`, `api/[...ruta]` | **Nuevos.** BFF del panel interno. |
| `app/bff/activacion/verificar`, `activar` | **Nuevos.** BFF de la activación. |
| `components/admin/PanelClientes.tsx`, `FormLoginAdmin.tsx`, `admin.module.css` | **Nuevos.** |
| `components/activacion/FormActivacion.tsx` | **Nuevo.** |
| `lib/admin/api.ts`, `lib/activacion.ts` | **Nuevos.** Contratos, llamadas y lógica pura. |
| `lib/servidor/sesionAdmin.ts`, `proxyAdmin.ts`, `backendAdmin.ts` | **Nuevos.** Cookie del admin, lista blanca y errores. |
| `middleware.ts` | Protección de `/admin`, rutas solo-BFF y límites nuevos. |
| `tests/hu27_admin.test.ts` | **Nuevo.** Lista blanca, sesión del admin, token del fragmento, reglas de contraseña, RUT y selección. |

## Cómo probarlo

```bash
docker compose up -d --build web
docker compose exec api python -m app.core.crear_admin --email admin@ejemplo.cl
```

Abre `http://localhost:3000/admin`, inicia sesión y sigue el flujo. Con `CORREO_MODO=archivo`, el enlace de activación queda en el `.eml` de `storage/correos` del contenedor `api`; ábrelo y pega la URL en el navegador. En este entorno no hubo acceso a npm, así que `npm run typecheck` y `npm test` no se pudieron ejecutar: córranlos antes de subir. La lógica pura de `tests/hu27_admin.test.ts` sí se verificó (9/9) con un ejecutor mínimo, y los archivos nuevos se revisaron con `tsc` usando declaraciones mínimas de Next y React.

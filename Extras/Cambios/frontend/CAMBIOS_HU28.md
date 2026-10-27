# HU-28 · Pantallas de inicio de sesión, cierre de sesión y recuperación de contraseña (frontend-next)

Pantallas del usuario definitivo de una empresa cliente y del administrador de Therion Labs para entrar con su correo y contraseña, salir y recuperar la contraseña, más el espacio de la empresa al que entra el cliente. El backend está descrito en `Extras/Cambios/backend/CAMBIOS_HU28.md`.

## Páginas

**`/ingresar`** es el inicio de sesión del usuario definitivo. El formulario envía correo y contraseña en el cuerpo de un POST a `/bff/cliente/login`, y el BFF guarda el token de FastAPI en una cookie httpOnly propia del cliente (`cai_cliente`, `__Host-cai_cliente` en producción). Los errores dicen "Correo o contraseña incorrectos." exista o no el correo, y si la API bloquea por intentos fallidos el formulario dice cuántos minutos esperar. La página acepta `?motivo=` para avisar que la sesión terminó, que se cerró, que la cuenta quedó activa o que la contraseña se restableció; cualquier otro valor se ignora. Con una sesión vigente, `/ingresar` lleva directo a `/empresa`. El encabezado público tiene un botón **Clientes** que lleva aquí, y la página de activación de HU-27 ahora termina con un botón **Iniciar sesión**.

**`/empresa`** es el espacio de la empresa: saludo, aviso si el contrato termina en 30 días o menos, la tabla de evaluaciones migradas (estado, puntaje general, fecha de traspaso) con **Ver resultados**, los datos de la empresa y **Cerrar sesión**. Ver resultados abre el panel de siempre (`/panel?evaluacion=ID`) en un modo nuevo, `cliente`, que lee todo por `/bff/cliente/api/*`; en la barra lateral aparecen **Mi empresa** y **Cerrar sesión**. HU-29 agregará aquí los cursos y el tutor IA.

**`/admin/login` → `/admin/clientes`** es el panel interno, que ahora se titula así y tiene cuatro pestañas: Solicitudes de contratación, Empresas, **Evaluaciones** (nueva: todas las evaluaciones con origen, rubro, estado, puntaje y empresa cliente si se migró, con filtro por estado) y Bitácora, donde ya se ven los inicios de sesión. El login del admin muestra los mismos mensajes que el del cliente y el enlace "¿Olvidaste tu contraseña?". Con sesión de admin vigente, `/admin/login` lleva directo al panel.

**`/recuperar`** (y `/recuperar?tipo=admin` desde el login del admin) pide el correo y muestra siempre el mismo mensaje, exista o no la cuenta. **`/restablecer#token=…`** es la página del enlace del correo: igual que `/activar`, lee el token del fragmento, lo quita de la barra de direcciones, valida el enlace sin consumirlo y pide la contraseña nueva con confirmación. Al terminar avisa que se cerraron todas las sesiones y lleva al login que corresponde según el tipo de cuenta.

## Seguridad

El token nunca llega al JavaScript del navegador: vive en cookies httpOnly que solo el BFF lee (una por tipo de sesión, así una misma persona puede tener abierta la encuesta pública y el servicio pagado). La cookie del cliente es `SameSite=Lax` porque el cliente llega desde enlaces de correo; todos los POST del BFF exigen mismo origen contra CSRF, como en HU-19 y HU-27.

**Cerrar sesión revoca el token en el servidor.** `/bff/cliente/logout` y `/bff/admin/logout` llaman primero a `POST /api/auth/logout` con el token de la cookie y después la borran (la borran igual si la API no responde). Restablecer la contraseña también borra la cookie de ese tipo en el navegador donde se hizo.

`middleware.ts` redirige `/empresa` a `/ingresar` sin sesión de cliente, bloquea el uso directo a través del rewrite `/api/*` de `/api/auth/cliente`, `/api/auth/logout`, `/api/auth/recuperacion*` y `/api/cliente/*` (así la API recibe la IP real para sus límites y el token no pasa por el JavaScript), agrega límites de ráfagas para el login del cliente y las tres llamadas de recuperación, y marca `/ingresar`, `/recuperar`, `/restablecer` y `/empresa` como `no-store`. Los límites reales de intentos fallidos los aplica FastAPI con Redis. El proxy `/bff/cliente/api/*` solo reenvía la lista blanca de `lib/servidor/proxyCliente.ts`: el espacio de la empresa y las **lecturas** de sus evaluaciones (más el informe PDF y su envío por correo); nada que cambie una evaluación migrada.

## Archivos

| Archivo | Cambio |
|---|---|
| `app/ingresar/page.tsx`, `app/empresa/page.tsx`, `app/recuperar/page.tsx`, `app/restablecer/page.tsx` | **Nuevas.** |
| `app/bff/cliente/login`, `logout`, `sesion`, `api/[...ruta]` | **Nuevos.** BFF del usuario definitivo. |
| `app/bff/recuperacion/solicitar`, `verificar`, `restablecer` | **Nuevos.** BFF de la recuperación de contraseña. |
| `app/bff/admin/logout/route.ts` | Revoca la sesión en el servidor antes de borrar la cookie. |
| `app/admin/login/page.tsx` | Acepta los motivos nuevos. |
| `components/acceso/FormIngresar.tsx`, `FormRecuperar.tsx`, `FormRestablecer.tsx`, `BotonCerrarSesion.tsx` | **Nuevos.** |
| `components/empresa/EspacioEmpresa.tsx` | **Nuevo.** Espacio de la empresa. |
| `components/admin/FormLoginAdmin.tsx` | Mensajes de HU-28, motivos y enlace de recuperación. |
| `components/admin/PanelClientes.tsx` | Pestaña Evaluaciones, título "Panel interno" y salida con aviso. |
| `components/shell/Sidebar.tsx` | En modo cliente: Mi empresa y Cerrar sesión. |
| `components/activacion/FormActivacion.tsx` | Al activar, botón para iniciar sesión. |
| `components/publico/Marco.tsx` | Botón **Clientes** en el encabezado público. |
| `components/informe/AccionesInforme.tsx`, `hooks/usePlanFormativo.ts` | Leen por la base de la API que corresponde al modo del panel (también cliente). |
| `hooks/usePanel.tsx`, `lib/api.ts` | Modo `cliente` del panel (`/bff/cliente/api`), `sesionCliente()` y `base` en el contexto. |
| `lib/acceso.ts`, `lib/empresa.ts` | **Nuevos.** Lógica pura de acceso (mensajes, motivos, rutas) y del espacio de la empresa. |
| `lib/servidor/sesionCliente.ts`, `backendCliente.ts`, `proxyCliente.ts` | **Nuevos.** Cookie del cliente, errores y lista blanca. |
| `lib/servidor/backend.ts` | `cerrarSesionEnBackend()`. |
| `lib/servidor/proxyAdmin.ts`, `lib/admin/api.ts` | Ruta y filtros de `admin/evaluaciones`; mensajes de login. |
| `middleware.ts` | Protección de `/empresa`, redirecciones del login con sesión, rutas solo-BFF, límites y `no-store`. |
| `tests/hu28_acceso.test.ts` | **Nuevo.** Cookie y sesión del cliente, lista blanca del proxy, filtros del admin, mensajes, motivos y fechas. |

## Cómo probarlo

```bash
docker compose up -d --build web
```

Con un cliente activado (flujo de HU-27), abre `http://localhost:3000/ingresar`, entra y revisa `/empresa`; con **Ver resultados** se abre el panel de esa evaluación. Cierra sesión y vuelve a `/empresa`: te devuelve al login. Equivócate 5 veces con la contraseña y el formulario te pedirá esperar. Para la recuperación, entra a `/recuperar`, pide el enlace y, con `CORREO_MODO=archivo`, copia la URL del `.eml` de `storage/correos` del contenedor `api` en el navegador. El panel interno está en `http://localhost:3000/admin` (pestaña Evaluaciones y, en Bitácora, los inicios y cierres de sesión).

En este entorno no hubo acceso a npm, así que `npm run typecheck` y `npm test` no se pudieron ejecutar: córranlos antes de subir. Se revisó el proyecto completo con `tsc` usando declaraciones mínimas de Next y React (los únicos errores fueron los esperables de esas declaraciones, en archivos antiguos y nuevos por igual, como los parámetros de eventos JSX) y la lógica pura de `tests/hu28_acceso.test.ts` pasó 11/11 con un ejecutor mínimo.

# HU-28 · Inicio y cierre de sesión con email y contraseña (backend)

*Como Usuario definitivo de una empresa cliente o Administrador de Therion Labs, quiero iniciar y cerrar sesión en la plataforma web con mi email y contraseña, para acceder de forma segura a las funciones que corresponden a mi rol.*

HU-27 ya dejaba el login del cliente (`POST /api/auth/cliente`) y el del administrador (`POST /api/auth/login`), pero el token era puramente stateless: "cerrar sesión" solo podía borrar la cookie del navegador y una copia del token seguía sirviendo hasta vencer. Tampoco había recuperación de contraseña, el login del admin no tenía límite de intentos y en la bitácora solo quedaba el ingreso exitoso del cliente. HU-28 completa esas tres piezas sin cambiar el formato del token ni romper los demás accesos (encuestado y referente siguen igual). La parte del frontend está en `Extras/Cambios/frontend/CAMBIOS_HU28.md`.

## Cómo funciona

**Sesiones revocables.** Cuando un administrador o un usuario definitivo inicia sesión se crea una fila en la tabla nueva `sesion_usuario` y el token HMAC lleva un identificador de sesión (`sid`, 24 bytes aleatorios). En la BD solo queda el SHA-256 del `sid`. En cada petición, `obtener_actor()` comprueba además que esa sesión exista, sea de ese mismo usuario, no haya vencido y no se haya cerrado. `POST /api/auth/logout` marca la sesión como cerrada y desde ese instante el token responde 401, aunque falten horas para su `exp` y aunque alguien lo hubiera copiado. Cerrar sesión en un dispositivo no afecta a las otras sesiones del mismo usuario; restablecer la contraseña, en cambio, las cierra todas. Los tokens sin `sid` (la CLI de pruebas `python -m app.core.autenticacion` o los emitidos antes de esta HU) se siguen aceptando hasta su vencimiento, así no se cae nada al desplegar.

**Intentos fallidos limitados.** Los dos logins con contraseña usan `ProteccionLogin` (en `iniciar_sesion.py`), que cuenta solo los intentos **fallidos** en Redis, por cuenta y por IP, en una ventana fija de 15 minutos. Con 5 fallos sobre el mismo correo, o 20 desde la misma IP, el login responde 429 `DEMASIADOS_INTENTOS` (con `reintentar_en_s` y `Retry-After`) hasta que la ventana termine, aunque la contraseña sea la correcta. La cuenta se identifica por la huella HMAC del correo **escrito**, exista o no: si solo se bloquearan los correos registrados, el bloqueo mismo revelaría cuáles existen. Entrar bien reinicia el contador de la cuenta, y restablecer la contraseña también (quien recupera su cuenta puede entrar de inmediato). Este límite reemplaza al de HU-27, que contaba también los ingresos exitosos. Si Redis no responde, el login responde 503, igual que los demás límites del sistema.

**Mensajes que no revelan si el email existe.** Un correo inexistente, una contraseña incorrecta, una cuenta sin activar o una cuenta bloqueada responden exactamente lo mismo (401 `CREDENCIALES_INVALIDAS`) y tardan lo mismo, porque cuando la cuenta no existe se verifica contra un hash señuelo (ahora fuera del event loop también en el login del admin). El 429 tiene el mismo texto para todos. La única respuesta distinta es `CONTRATO_NO_VIGENTE`, que solo recibe quien escribió la contraseña correcta.

**Cada inicio de sesión en la bitácora (HU-09).** Se registran el ingreso exitoso (`cliente.inicio_sesion`, que ya existía, y el nuevo `admin.inicio_sesion`, ambos con el id de la sesión), el fallido (`sesion.inicio_fallido`, con el motivo y si ese fallo activó el bloqueo), el rechazado por bloqueo (`sesion.inicio_bloqueado`) y el cierre (`sesion.cierre`). En los fallidos el actor es `anonimo` y `entidad_id` es el id de la cuenta solo si existe; nunca se guarda el correo escrito ni la contraseña. Los intentos rechazados se confirman con su propio commit antes de responder, así no se pierden aunque la petición termine en error.

**Recuperación de contraseña.** `POST /api/auth/recuperacion` recibe el tipo de cuenta (`cliente` o `admin`) y el correo, y responde **siempre** 202 con el mismo mensaje. Si la cuenta está activa, se revocan los enlaces anteriores sin usar, se crea uno nuevo en `token_recuperacion` (solo su SHA-256) y el correo sale en segundo plano, después de responder, para que el tiempo de respuesta tampoco delate si la cuenta existe. El enlace (`/restablecer#token=…`, con el token en el fragmento como la activación de HU-27) sirve una vez y vence a los 30 minutos. `POST /api/auth/recuperacion/verificar` lo comprueba sin consumirlo y `POST /api/auth/recuperacion/restablecer` aplica las mismas reglas de contraseña de HU-27, marca el enlace como usado con un `UPDATE` condicional (dos clics simultáneos no lo usan dos veces), revoca los demás enlaces de la cuenta, cierra todas sus sesiones y envía un aviso de "tu contraseña cambió". Una contraseña débil devuelve 422 sin consumir el enlace. Hay un máximo de 3 correos por cuenta y hora (pasado el límite se responde igual, sin enviar) y de 10 solicitudes por IP y hora (429). Un usuario definitivo que aún no activa su cuenta no recibe enlace de recuperación: usa su enlace de activación o pide uno nuevo a Therion Labs.

**Espacio de la empresa y panel interno.** `GET /api/cliente/empresa` (solo rol `cliente`) es la puerta de entrada del usuario definitivo: su nombre y correo, la empresa con su contrato y las evaluaciones migradas, con su puntaje general. El detalle de cada evaluación se sigue leyendo con las rutas de `/api/evaluaciones`, que ya limitan al cliente a lo de su empresa. Para el administrador se agrega `GET /api/admin/evaluaciones`, que completa el panel interno (empresas, solicitudes de contratación y evaluaciones) con todas las evaluaciones, su rubro, puntaje y la empresa a la que se migraron, sin datos de contacto del encuestado.

## Criterios de aceptación

| Criterio | Dónde se cumple | Prueba (`tests/test_hu28_sesion.py`) |
|---|---|---|
| 1. Inicio, cierre de sesión y recuperación de contraseña; la sesión viaja en cookie httpOnly por el BFF y el token nunca llega al navegador | `sesiones.py`, `POST /api/auth/logout`, `recuperacion_contrasena.py`; la cookie y el BFF están en frontend-next | `test_cliente_entra_a_su_empresa_y_cerrar_sesion_revoca_el_token`, `test_admin_inicia_sesion_…`, `test_un_sid_inventado_…`, `test_recuperacion_de_contrasena_del_cliente_de_punta_a_punta`, `test_recuperacion_del_admin_revoca_enlaces_anteriores_y_vence` |
| 2. El cliente entra al espacio de su empresa; el admin, al panel interno con empresas, solicitudes y evaluaciones | `GET /api/cliente/empresa`, `GET /api/admin/evaluaciones` (más las rutas de HU-27/HU-31) | `test_cliente_entra_a_su_empresa_…`, `test_admin_inicia_sesion_ve_el_panel_interno_y_cierra_sesion` |
| 3. Intentos fallidos limitados, errores que no revelan si el email existe y cada inicio de sesión en la bitácora | `ProteccionLogin` e `IniciarSesionUseCase` en `iniciar_sesion.py`, acciones nuevas en `bitacora_repository.py` | `test_los_intentos_fallidos_se_limitan_sin_revelar_si_el_email_existe`, `test_…_por_ip_y_en_el_login_del_admin`, `test_cuenta_pendiente_bloqueada_o_sin_contrato_…`, `test_recuperacion_limitada_por_cuenta_…` |

## Archivos

| Archivo | Cambio |
|---|---|
| `migrations/versions/f3a8d1c6e4b2_hu28_sesiones_recuperacion.py` | **Nuevo.** Tablas `sesion_usuario` y `token_recuperacion` (con `CHECK` del rol e índice por cuenta). `down_revision = c9e2f4a7b1d6` (HU-31). Tiene `downgrade`. |
| `app/domain/models/sesion.py` | **Nuevo.** `SesionUsuario`, `TokenRecuperacion` y `MotivoCierre`. |
| `app/domain/models/__init__.py` | Registra los modelos nuevos. |
| `app/application/use_cases/sesiones.py` | **Nuevo.** Abrir, comprobar y cerrar sesiones (una o todas las de una cuenta). |
| `app/application/use_cases/recuperacion_contrasena.py` | **Nuevo.** Solicitar, verificar y usar el enlace; correos de recuperación y de aviso. |
| `app/application/use_cases/iniciar_sesion.py` | Login del admin y del cliente con sesión revocable, `ProteccionLogin` y auditoría de cada intento. |
| `app/core/autenticacion.py` | `Actor.sid`; `emitir_token(..., sid=)`; `verificar_token` lee el `sid`; `_sigue_habilitado` exige sesión abierta cuando el token la trae. |
| `app/api/routes/auth.py` | `POST /logout`, `/recuperacion`, `/recuperacion/verificar`, `/recuperacion/restablecer`; límites nuevos en `/login` y `/cliente`. |
| `app/api/routes/cliente.py` | **Nuevo.** `GET /api/cliente/empresa`. |
| `app/api/routes/admin_clientes.py` | `GET /api/admin/evaluaciones`. |
| `app/main.py` | Registra el router `cliente`. |
| `app/infrastructure/cache/limitador.py` | `restante_s()` y `reiniciar()` en Redis y en memoria. |
| `app/infrastructure/repositories/bitacora_repository.py` | Acciones `admin.inicio_sesion`, `sesion.inicio_fallido`, `sesion.inicio_bloqueado`, `sesion.cierre` y `recuperacion.*`. |
| `app/core/config.py` | Variables `LOGIN_*` y `RECUPERACION_*` con sus validaciones. |
| `app/core/catalogo_datos_personales.py` | Clasificación T-06 de las columnas nuevas. |
| `tests/test_hu28_sesion.py` | **Nuevo.** 10 pruebas (reutiliza la preparación de `test_hu27_empresa_cliente.py`). |
| `tests/test_hu20_autorizacion.py` | Clasifica las 6 rutas nuevas en la matriz de HU-20. |
| `Proyecto/.env.example`, `Proyecto/README.md` | Variables, endpoints, rol 🏢 y códigos nuevos. |

## Variables de entorno

| Variable | Por defecto | Uso |
|---|---|---|
| `LOGIN_MAX_FALLOS_CUENTA` | `5` | Fallos sobre el mismo correo antes de bloquear por la ventana. |
| `LOGIN_MAX_FALLOS_IP` | `20` | Fallos desde la misma IP antes de bloquear por la ventana. |
| `LOGIN_VENTANA_FALLOS_MIN` | `15` | Duración de la ventana (y del bloqueo). |
| `RECUPERACION_URL_BASE` | `http://localhost:3000/restablecer` | Página que recibe el enlace. Con `APP_ENV=production` y `CORREO_MODO=smtp` debe ser `https://` (se comprueba al arrancar, no al enviar, para que un error no delate qué correos existen). |
| `RECUPERACION_TTL_MIN` | `30` | Vigencia del enlace. |
| `RECUPERACION_CORREOS_CUENTA_HORA` | `3` | Correos por cuenta y hora (pasado el límite se responde igual, sin enviar). |
| `RECUPERACION_SOLICITUDES_IP_HORA` | `10` | Solicitudes por IP y hora (429). |

## Cómo probarlo en Docker

```bash
docker compose exec api alembic upgrade head
docker compose exec worker pytest tests/test_hu28_sesion.py tests/test_hu27_empresa_cliente.py tests/test_hu20_autorizacion.py tests/test_t06_minimizacion.py -v
docker compose exec worker pytest tests -v -rxX
```

Por Swagger (`/docs`): con un cliente ya activado (flujo de HU-27), entra con `POST /api/auth/cliente`, consulta `GET /api/cliente/empresa` con ese token, llama a `POST /api/auth/logout` y vuelve a consultar: ahora responde 401. Para la recuperación, llama a `POST /api/auth/recuperacion` con `{"tipo": "cliente", "email": "..."}`, abre el `.eml` de `storage/correos` (con `CORREO_MODO=archivo`), copia el token del enlace `/restablecer#token=…` y úsalo en `POST /api/auth/recuperacion/restablecer`. Para ver el bloqueo, equivócate 5 veces seguidas con el mismo correo: el sexto intento responde 429 aunque la contraseña sea correcta, y en `GET /api/admin/bitacora` quedan todos los intentos.

## Verificación hecha

En este entorno no hubo acceso a PyPI ni a npm, así que **la suite de pytest no se pudo ejecutar aquí**: córranla en Docker con los comandos de arriba antes de subir. Sí se compiló todo el código Python modificado (`py_compile`) y se revisaron a mano las pruebas contra los caminos del código. Por ser una HU de seguridad, conviene además correr la suite completa, porque el login del admin ahora crea una fila de sesión y eso toca a las pruebas de ARCOP y de HU-20 que inician sesión.

## Pendientes y decisiones abiertas

- **Depuración de sesiones y enlaces vencidos**: `sesion_usuario` y `token_recuperacion` crecen con cada inicio de sesión y cada pedido. Falta que el PO fije un plazo para que el cron de T-06 borre las filas vencidas (quedó anotado en el catálogo de datos personales).
- **Bloqueo de cuentas por un admin**: el estado `bloqueado` del usuario definitivo sigue sin endpoint (pendiente de HU-27). Cuando exista, conviene que al bloquear se llame a `cerrar_todas()` para cortar las sesiones abiertas.
- **Resultado del correo de recuperación en la bitácora**: el envío corre después de responder, sin sesión de BD, así que su resultado queda solo en el log de la API (`seguridad`). El pedido y la emisión del enlace sí quedan en la bitácora.
- **Recuperación del admin**: se agregó porque el criterio la pide para todo inicio de sesión con contraseña. Si el equipo prefiere que el admin solo cambie su contraseña con `crear_admin`, basta con quitar el tipo `admin` en `recuperacion_contrasena.TIPOS`.
- **HU-29** completa el espacio de la empresa (cursos y tutor IA); HU-28 deja la entrada con el contrato y las evaluaciones migradas.

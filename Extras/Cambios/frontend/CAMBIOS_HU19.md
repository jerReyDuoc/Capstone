# HU-19 · Autodiagnóstico desde la landing, sin invitación (frontend)

*Como visitante de la landing quiero iniciar el autodiagnóstico sin invitación ni registro y poder retomarlo más tarde, para evaluar la madurez de mi organización en gobernanza de IA sin barreras de entrada.*

Incluye el aviso legal de HU-04 (texto en borrador). El backend está en `backend/CAMBIOS_HU19.md`.

## Cómo funciona

```
Navegador ──(sin token)──▶ Next.js BFF /bff/* ──(Bearer + X-BFF-Secret + X-Cliente-IP)──▶ FastAPI /api/*
              cookie httpOnly __Host-cai_sesion ◀── el token se guarda aquí y nunca llega al JS
```

1. **`/` (landing):** estática (`force-static`), sin componentes cliente ni CAPTCHA. Los CTA llevan `prefetch={false}`, así el JavaScript del flujo no se descarga en segundo plano.
2. **`/comenzar`:** el servidor trae los rubros y el nonce de la CSP. El flujo tiene tres pasos:
   - aviso legal (checkbox obligatorio);
   - rubro + Turnstile invisible → `POST /bff/encuesta/iniciar`;
   - número de evaluación y clave (copiar, descargar .txt, confirmar que la guardó) + **email opcional** → `/encuesta`.
3. **`/retomar`:** número + clave desde cualquier dispositivo → `POST /bff/encuesta/retomar` (usa `POST /api/auth/encuestado`).
4. **`/encuesta`:** exige sesión (middleware + Server Component). Muestra la evaluación propia, el progreso, los límites del día y el email opcional. Aquí se montará el cuestionario (HU-01/02).

## Archivos

| Archivo | Qué hace |
|---|---|
| `app/page.tsx` | Landing estática (antes redirigía a `/panel`; el panel sigue en `/panel`) |
| `app/aviso-legal/page.tsx`, `lib/avisoLegal.ts` | Aviso legal HU-04 y su versión (debe coincidir con `AVISO_LEGAL_VERSION` del backend) |
| `app/comenzar/page.tsx`, `components/inicio/FlujoInicio.tsx` | Flujo de inicio |
| `components/inicio/Turnstile.tsx` | Widget CAPTCHA con carga diferida del script |
| `components/inicio/AvisoError.tsx`, `lib/encuesta/errores.ts` | Mensaje y acción por código de error (espera, hora de reinicio, retomar, recargar) |
| `components/inicio/FormEmailOpcional.tsx` | Email opcional, nunca bloqueante |
| `app/retomar/page.tsx`, `components/inicio/FormRetomar.tsx` | Retomar con clave |
| `app/encuesta/page.tsx`, `components/encuesta/*` | Zona del encuestado y banner de cuota |
| `app/bff/encuesta/{iniciar,retomar,sesion,email}/route.ts` | BFF: maneja la cookie y nunca devuelve el token |
| `app/bff/api/[...ruta]/route.ts`, `lib/servidor/proxy.ts` | Proxy autenticado con **lista blanca** y verificación del id de evaluación |
| `lib/servidor/{backend,sesion,peticion}.ts` | Llamadas al backend, cookie, IP del cliente y verificación de mismo origen |
| `lib/encuesta/{contratos,cliente}.ts` | Contratos validados y `fetch` con reintentos acotados |
| `hooks/useSesionEncuestado.ts`, `useIniciarEvaluacion.ts`, `useLimitesEncuesta.ts` | Hooks de sesión, inicio y límites |
| `middleware.ts` | CSP (con nonce en el flujo), filtro de ráfagas, protección de `/encuesta` y bloqueo de `/api/encuesta-publica/*` por el rewrite |
| `next.config.mjs` | Cabeceras de seguridad (nosniff, no-referrer, DENY, COOP, Permissions-Policy, HSTS en producción) |
| `tests/encuesta.test.ts` | 18 pruebas de contratos, sesión, proxy, IP/origen y errores |

## Contratos (navegador ⇄ BFF)

| Ruta | Envía | Recibe |
|---|---|---|
| `POST /bff/encuesta/iniciar` | `{rubroId, avisoVersion, avisoAceptado: true, captchaToken}` (sin email) | 201 `{evaluacionId, clave, expiraEn}` + cookie |
| `POST /bff/encuesta/retomar` | `{evaluacionId, clave}` | 200 `{evaluacionId, expiraEn}` + cookie |
| `GET /bff/encuesta/sesion` | — | `{activa: true, evaluacionId, expiraEn}` \| `{activa: false}` (confirma con `/api/auth/me`) |
| `DELETE /bff/encuesta/sesion` | — | 204, borra la cookie |
| `PATCH /bff/encuesta/email` | `{email: string \| null}` | 204 |
| `* /bff/api/<ruta>` | igual que la API | igual que la API; errores como `{error: {codigo, mensaje, reintentarEnS?, reiniciaEn?}}` |

## Decisiones de seguridad

- **Cookie httpOnly y no localStorage**, porque un XSS puede leer localStorage. La cookie lleva `__Host-` en producción, `Secure`, `SameSite=Lax` y `Path=/`.
- **CSRF:** toda mutación exige `Sec-Fetch-Site: same-origin` (o un `Origin` igual al host).
- **Sin secretos en URLs ni logs.** La clave viaja solo en el cuerpo de un POST y se muestra una vez, desde el estado de React (no se guarda en storage). Las respuestas usan `no-store`, el sitio envía `Referrer-Policy: no-referrer` y los logs del BFF registran solo el tipo de error.
- **Doble barrera de aislamiento:**
  - el proxy solo reenvía las rutas del encuestado y con su id de evaluación;
  - el backend vuelve a verificarlo (`app/core/alcance.py`).
- **Límites reales en el backend** (Redis). El middleware solo es un pre-filtro en memoria.
  - `@upstash/ratelimit` no se usó porque exige Upstash Redis (REST) y el proyecto corre con el Redis de Docker. Si despliegan en Vercel, se reemplaza `permitir()` en `middleware.ts`.
- **Sin dependencias nuevas.** Los contratos se validan a mano en `lib/encuesta/contratos.ts` (reemplazables 1:1 por Zod si el equipo lo adopta).

## Variables

`Proyecto/.env` (lo lee docker compose para `api` y `web`):

```
BFF_SHARED_SECRET=<python -c "import secrets; print(secrets.token_urlsafe(48))">
TURNSTILE_SITE_KEY=<clave pública de Turnstile>      # vacío en local = clave de prueba
TRUSTED_PROXY_HOPS=0                                 # 1 detrás de nginx / balanceador
```

`backend/.env`: `TURNSTILE_SECRET_KEY` (en local se puede usar `1x0000000000000000000000000000000AA`, que siempre aprueba, o dejarla vacía).

> `BFF_SHARED_SECRET` va en `Proyecto/.env`, no en `backend/.env`: el `environment` del compose tiene prioridad sobre el `env_file`.

## Checklist de verificación

Todo se prueba en Docker: `docker compose up -d --build` y luego http://localhost:3000.

**Criterio 1. Inicio sin invitación**
- [ ] `/` carga sin errores y en DevTools → Network **no** aparece `challenges.cloudflare.com` ni el chunk de `/comenzar`.
- [ ] "Comenzar autodiagnóstico" abre `/comenzar`. Sin marcar el aviso, "Continuar" está deshabilitado.
- [ ] Al elegir un rubro y esperar "Verificación de seguridad lista", "Comenzar evaluación" muestra el número y la clave.
- [ ] En BD, `SELECT origen, es_prueba FROM evaluacion ORDER BY id DESC LIMIT 1;` devuelve `publica | f`, y el `usuario_temporal` tiene `email` NULL, el rubro elegido y `aviso_legal_version`.

**Criterio 2. Token, retomar y aislamiento**
- [ ] La respuesta de `/bff/encuesta/iniciar` (Network → Response) **no** contiene `access_token`. En Application → Cookies, `cai_sesion` (`__Host-cai_sesion` en producción) aparece como HttpOnly.
- [ ] En la consola, `document.cookie` no muestra la cookie de sesión.
- [ ] En otra ventana privada, `/encuesta` redirige a `/retomar?motivo=sesion`. Con el número y la clave entra a la misma evaluación.
- [ ] El email se puede omitir. Si se escribe uno inválido aparece un error; si es válido, "Correo guardado".
- [ ] Con dos evaluaciones públicas, `GET /bff/api/evaluaciones/<id de la otra>/progreso` → 404.
- [ ] En Swagger, `GET /api/evaluaciones/<id pública>` sin token → 401; `GET /api/evaluaciones` no la lista.
- [ ] `pytest tests/test_hu19_encuesta_publica.py -k "aislamiento or propia or retoma or email"` pasa.

**Criterio 3. Abuso y cuota del LLM**
- [ ] Más de 5 envíos seguidos de "Comenzar" en un minuto → aviso "Demasiados intentos" con cuenta regresiva.
- [ ] Con `ENCUESTA_EVALUACIONES_IP_DIA=1` en `backend/.env`, la segunda evaluación del día muestra el aviso de límite con el botón "Retomar con mi clave".
- [ ] Con el secreto de prueba de Cloudflare que **siempre falla** (`TURNSTILE_SECRET_KEY=2x0000000000000000000000000000000AA` en `backend/.env`), "Comenzar evaluación" muestra "No pudimos completar la verificación" (`CAPTCHA_INVALIDO`).
- [ ] Con `LLM_CUOTA_DIARIA_EVALUACION=1`, la segunda evidencia responde 429 `CUOTA_LLM_AGOTADA` con `reinicia_en`, y el banner de `/encuesta` dice "en pausa por hoy" con la hora de reinicio.
- [ ] `curl -X POST http://localhost:3000/api/encuesta-publica/iniciar` → 404 (bloqueado por el middleware).
- [ ] `pytest tests/test_hu19_encuesta_publica.py -k "limite or captcha or bff or cuota or rechazado"` pasa.

**Criterio 4. Benchmark**
- [ ] `pytest tests/test_hu19_encuesta_publica.py -k benchmark` pasa (cuenta completadas, excluye en curso y de prueba).
- [ ] `PATCH /api/evaluaciones/{id}/prueba` sin token de admin → 401.

**General**
- [ ] `npm test`, `npm run typecheck` y `npm run build` en `frontend-next` sin errores.
- [ ] `docker compose exec worker pytest tests -v -rxX` mantiene en verde la suite anterior.
- [ ] Sin errores de CSP en la consola en `/`, `/comenzar`, `/retomar` y `/encuesta` (con `npm run build && npm start`, no solo en `dev`).

## Supuestos (aplicados con la opción más recomendable)

1. **"Cerrada y completa"** = `estado_progreso = 'completada'`, al que solo se llega por `POST /completar` (todas las aplicables respondidas y sin evidencias en validación). `cerrada` no cuenta para el benchmark, igual que antes.
2. **"De prueba"** = `es_prueba` marcado por un admin. Nunca lo decide el frontend.
3. **Cuota del LLM:** 1 evidencia = 1 validación. Son 40 por evaluación y día y 2000 en total, con reinicio a medianoche en Chile. Al agotarse se **rechaza** la subida (429) sin perder respuestas; encolar para el día siguiente queda como mejora.
4. **Límites:** 10 intentos de inicio por IP cada 10 min, 10 evaluaciones por IP y día (holgado por el NAT de oficinas), 30 evidencias por evaluación y 100 por IP y día. Solo aplican a la encuesta pública.
5. **Retomar desde otro dispositivo** con número y clave. El email se guarda para el informe (HU-21); por ahora no se envían correos, porque el proyecto no tiene servicio de correo, y un enlace mágico de un solo uso queda como mejora.
6. **Duración de la sesión:** 8 h (`AUTH_TOKEN_TTL_MIN`). Al vencer se pide la clave de nuevo.
7. **Texto del aviso legal:** borrador técnico que debe aprobar el PO.

## Preguntas abiertas para el PO

- ¿Validan los valores de los límites y de la cuota, o los ajustamos con el piloto?
- ¿Cuántos días se conserva una evaluación pública abandonada antes de anonimizarla (HU-25)? Hoy el usuario temporal vence a los 30 días.
- ¿El email requiere doble confirmación antes de enviar el informe?
- En producción, ¿qué proxy irá delante de Next? De eso depende `TRUSTED_PROXY_HOPS`; sin la IP real todos compartirían el cupo por IP.

## Pendiente fuera de esta HU

- La pantalla del cuestionario (HU-01/02) dentro de `/encuesta`. Debe consumir `/bff/api/...` y, ante `CUOTA_LLM_AGOTADA` o `LIMITE_EVIDENCIAS`, mostrar `<AvisoError>` y llamar a `refrescar()` de `useLimitesEncuesta`.
- El panel `/panel` (HU-13) todavía lista evaluaciones sin login. Las públicas ya no aparecen ahí; mostrar al encuestado su propio panel vía BFF es parte de HU-20.

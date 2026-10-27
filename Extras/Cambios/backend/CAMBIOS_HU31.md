# HU-31 · Solicitud de contratación desde los resultados (backend)

*Como Encuestado, quiero solicitar desde mis resultados que Therion Labs me contacte para contratar el servicio, para acceder a los cursos, al tutor IA y a la generación de documentos que cierran mis brechas.* Prioridad alta · 2 SP.

HU-27 había dejado una base mínima de la solicitud de contratación (tabla `solicitud_contratacion`, un consentimiento y los estados `pendiente/contratada/migrada/descartada`). HU-31 la completa sin romper lo que HU-27 necesita: la migración sigue dependiendo solo de `evaluacion_id`, `autoriza_migracion`, `estado = 'contratada'` y del borrado del contacto al migrar. La pantalla del encuestado y los cambios de la bandeja del admin están en `Extras/Cambios/frontend/CAMBIOS_HU31.md`.

## Cómo funciona

Cuando el encuestado termina su autodiagnóstico, sus resultados le ofrecen "Contratar la plataforma". El formulario envía nombre, cargo, empresa, correo y, si quiere, teléfono, junto con dos consentimientos que se aceptan por separado: uno para que Therion Labs lo contacte comercialmente y otro que autoriza asociar la evaluación a su empresa si contrata. Cada uno viaja con la versión del texto que la persona leyó y queda guardado con su propia versión y su propia fecha. Si la versión no es la vigente (porque el PO cambió el texto mientras la persona tenía el formulario abierto) la API responde 409 y el formulario muestra el texto nuevo para aceptarlo de nuevo.

La solicitud entra a la bandeja del administrador como `nueva`, con la evaluación vinculada (rubro, puntaje y si está completada). Desde ahí el admin la pasa a `contactada`, `contratada` o `descartada`. Solo `contratada` habilita la migración de HU-27, que después la deja en el estado técnico `migrada` (al encuestado se le muestra como contratada). Descartar es final y borra el contacto, porque sin contrato no hay finalidad para conservarlo. Cada cambio queda en la bitácora.

Después de guardar la solicitud se envía un aviso por correo al equipo comercial (`CONTRATACION_AVISO_EMAIL`). Se envía después del commit, así que un correo caído nunca deja sin registrar la solicitud ni muestra un error a la persona; el resultado (enviado, omitido por no tener destinatario, o fallido) queda en la bitácora. Por minimización, el aviso no lleva el nombre, el correo ni el teléfono de la persona: trae el número de solicitud, la empresa declarada, el cargo, el puntaje y el enlace a la bandeja, donde el equipo ve el contacto con su sesión de administrador. Así los datos de contacto no quedan copiados en buzones ni reenvíos.

El formulario tiene el mismo límite contra abuso que el inicio de la encuesta pública (HU-19): intentos por IP en 10 minutos (también los fallidos, con `ENCUESTA_INTENTOS_IP_10MIN`), CAPTCHA de Turnstile validado en el servidor con una acción propia (`solicitar_contratacion`, para que un token de `/comenzar` no sirva aquí) y un máximo de solicitudes por IP y día (`CONTRATACION_SOLICITUDES_IP_DIA`, que por defecto toma el valor de `ENCUESTA_EVALUACIONES_IP_DIA`). Un formulario rechazado por validación devuelve el cupo diario. Con `BFF_SHARED_SECRET` configurado solo se acepta desde el BFF, que reenvía la IP real.

Como el texto del consentimiento promete que se puede retirar ejerciendo los derechos sobre datos personales, una supresión ARCOP (o la retención de T-06) del encuestado ahora también borra el contacto de sus solicitudes aún no migradas y las descarta.

## Criterios de aceptación

| Criterio | Dónde se cumple | Prueba (`tests/test_hu31_solicitud_contratacion.py`) |
|---|---|---|
| 1. En los resultados (sin cuenta) aparece "Contratar la plataforma" con nombre, cargo, empresa, email y teléfono opcional | `POST /api/contratacion/solicitudes`; columnas `cargo_contacto` (nueva) y `razon_social_declarada` (ahora obligatoria). El botón y el formulario están en `frontend-next` | `test_c1_formulario_con_nombre_cargo_empresa_email_y_telefono_opcional`, `test_c1_campos_obligatorios_y_formato` (6 casos), `test_c1_solo_con_la_evaluacion_terminada_y_propia` |
| 2. Dos consentimientos separados, cada uno con su versión y fecha; sin el segundo no hay migración | `consentimientos_contratacion.py` (textos y versiones), columnas `consentimiento_contacto_version` y `fecha_consentimiento_contacto` (nuevas) junto a `consentimiento_version` y `fecha_autorizacion` (de HU-27); la regla de HU-27 en `migrar_evaluacion.py` sigue exigiendo `autoriza_migracion` | `test_c2_los_textos_son_dos_y_cada_uno_trae_su_version`, `test_c2_sin_cualquiera_de_los_dos_no_se_envia` (×2), `test_c2_cada_consentimiento_queda_con_su_version_y_fecha…`, `test_c2_sin_el_segundo_consentimiento_hu27_no_migra` |
| 3. Bandeja del admin con evaluación vinculada y estado (nueva, contactada, contratada, descartada); aviso por correo; mismo límite que HU-19 | `GET/PATCH /api/admin/contrataciones` con `conteo_por_estado` y los dos consentimientos; `aviso_contratacion.py`; límites en `app/api/routes/contratacion.py` | `test_c3_bandeja_con_evaluacion_vinculada_estados_y_conteo`, `test_c3_aviso_por_correo_a_therion_sin_datos_de_contacto`, `test_c3_sin_destinatario_o_con_el_correo_caido…`, `test_c3_limite_de_intentos_por_ip…`, `test_c3_limite_diario_por_ip…`, `test_c3_captcha_en_el_servidor_con_su_propia_accion`, `test_c3_con_secreto_del_bff…` |

## Estados y transiciones

| Desde | Hacia (admin) | Nota |
|---|---|---|
| `nueva` | `contactada`, `contratada`, `descartada` | Estado inicial (antes se llamaba `pendiente`) |
| `contactada` | `contratada`, `descartada` | |
| `contratada` | `contactada`, `descartada` | Volver a `contactada` corrige un "contratada" marcado por error. Habilita HU-27 |
| `migrada` | — | Lo fija HU-27 al traspasar. Final |
| `descartada` | — | Borra nombre, cargo, correo y teléfono. Final |

## Archivos

| Archivo | Cambio |
|---|---|
| `migrations/versions/c9e2f4a7b1d6_hu31_solicitud_contratacion.py` | **Nuevo.** Columnas `cargo_contacto`, `consentimiento_contacto_version`, `fecha_consentimiento_contacto`; `pendiente` → `nueva`; nuevo CHECK con `contactada`; índice por estado. Tiene `downgrade` (`nueva`/`contactada` vuelven a `pendiente`). `down_revision = b7e4d2a9c6f1` (HU-27). |
| `app/domain/models/solicitud_contratacion.py` | Estados `nueva` y `contactada`, campos nuevos, índice en `estado`. |
| `app/application/use_cases/consentimientos_contratacion.py` | **Nuevo.** Los dos textos (provisorios) y sus versiones. |
| `app/application/use_cases/aviso_contratacion.py` | **Nuevo.** Aviso por correo a Therion sin datos de contacto, con resultado en la bitácora. |
| `app/application/use_cases/contratacion_empresa.py` | `crear()` con cargo, empresa y los dos consentimientos; transiciones de la bandeja; `conteo_por_estado()`; al descartar también se borra el cargo. |
| `app/application/use_cases/migrar_evaluacion.py` | Al migrar también se borra `cargo_contacto`. |
| `app/api/routes/contratacion.py` | Esquema nuevo del formulario, límites de HU-19, CAPTCHA, origen BFF y aviso después del commit. `GET /consentimiento` devuelve `{contacto, migracion}`. |
| `app/api/routes/admin_clientes.py` | La bandeja devuelve cargo, los dos consentimientos y `conteo_por_estado`. |
| `app/infrastructure/repositories/anonimizacion_repository.py` | La supresión del encuestado descarta sus solicitudes no migradas y borra su contacto. |
| `app/infrastructure/repositories/bitacora_repository.py` | Acción `solicitud_contratacion.aviso_comercial`. |
| `app/infrastructure/security/captcha.py` | Acción `solicitar_contratacion`. |
| `app/core/config.py` | `CONSENTIMIENTO_CONTACTO_VERSION`, `CONTRATACION_AVISO_EMAIL`, `CONTRATACION_BANDEJA_URL`, `CONTRATACION_SOLICITUDES_IP_DIA`; `CONSENTIMIENTO_CONTRATACION_VERSION` sube a `2026-10-v2` porque cambió el texto. |
| `app/core/catalogo_datos_personales.py` | Clasificación T-06 de las columnas nuevas. |
| `tests/test_hu31_solicitud_contratacion.py` | **Nuevo.** 22 pruebas. |
| `tests/test_hu27_empresa_cliente.py` | Usa el formulario nuevo (`cuerpo_solicitud`) y los estados nuevos; la prueba "sin autorización" simula una fila anterior a HU-31. |
| `Proyecto/.env.example`, `Proyecto/README.md` | Variables y endpoints. |

## Variables de entorno

| Variable | Por defecto | Uso |
|---|---|---|
| `CONSENTIMIENTO_CONTACTO_VERSION` | `2026-10-v1` | Versión del texto de contacto comercial. Súbela si el PO cambia el texto. |
| `CONSENTIMIENTO_CONTRATACION_VERSION` | `2026-10-v2` | Versión del texto de traspaso (ya existía; subió porque HU-31 reescribió el texto). |
| `CONTRATACION_AVISO_EMAIL` | vacío | Bandeja comercial que recibe el aviso. Vacío = sin aviso (queda como omitido en la bitácora). |
| `CONTRATACION_BANDEJA_URL` | `http://localhost:3000/admin/clientes` | Enlace que lleva el aviso. |
| `CONTRATACION_SOLICITUDES_IP_DIA` | sin definir | Máximo por IP y día. Sin definir usa `ENCUESTA_EVALUACIONES_IP_DIA`. Si no la cambias, déjala comentada en el `.env` (una línea vacía no es válida). |

## Cómo probarlo en Docker

```bash
docker compose exec api alembic upgrade head
docker compose exec worker pytest tests/test_hu31_solicitud_contratacion.py tests/test_hu27_empresa_cliente.py tests/test_t06_minimizacion.py -v
docker compose exec worker pytest tests -v -rxX
```

Por la web: completa una evaluación pública, entra a `/panel` y usa "Contratar la plataforma". Con `CORREO_MODO=archivo` y `CONTRATACION_AVISO_EMAIL` definido, el aviso queda como `.eml` en `storage/correos` del contenedor `api`. Luego entra a `/admin/clientes` y mueve la solicitud de `Nueva` a `Contactada` y `Contratada`.

## Verificación hecha

Suite completa en proceso (SQLite): 529 aprobadas y 9 omitidas, contra 507 antes del cambio (las 22 nuevas de HU-31; todas las de HU-27, HU-20 y T-06 siguen pasando). La migración se probó con Alembic sobre SQLite partiendo de la tabla de HU-27 con filas en `pendiente` y `contratada`: upgrade (quedan en `nueva`, el CHECK acepta `contactada` y rechaza `pendiente`, el valor por defecto es `nueva`), downgrade (vuelven a `pendiente` y el CHECK rechaza `contactada`) y un segundo upgrade. **No se probó en PostgreSQL**: corran `alembic upgrade head` y `alembic downgrade -1 && alembic upgrade head` en su Docker antes de subir.

## Decisiones y pendientes

- **Los dos consentimientos son obligatorios para enviar**, como dice el criterio 2. Si el PO prefiere que el segundo sea opcional (la persona pide contacto pero no autoriza el traspaso y, si contrata, repite el autodiagnóstico), basta con quitar `MIGRACION` del bucle de `crear()` en `contratacion_empresa.py` y guardar `autoriza_migracion = consentimiento_migracion.aceptado`; HU-27 ya bloquea la migración sin él.
- **Textos de consentimiento**: siguen siendo provisorios hasta que el PO los apruebe. Están en un solo archivo (`consentimientos_contratacion.py`) y el frontend los lee de la API.
- **HU-28** puede integrar la bandeja en el panel interno completo: los estados, el conteo y los dos consentimientos ya vienen en `GET /api/admin/contrataciones`. Si se quieren notas del comercial o una fecha de contacto, conviene agregarlas como columnas nuevas en lugar de usar la bitácora.
- **HU-27** no cambia de contrato. Las solicitudes creadas con la base de HU-27 quedan en `nueva` y sin consentimiento de contacto (NULL); en la bandeja aparecen con "Contacto: no".

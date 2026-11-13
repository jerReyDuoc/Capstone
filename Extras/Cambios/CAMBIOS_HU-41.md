# CAMBIOS · HU-41 — Registro de tratamiento de la propia plataforma

> *Como Administrador de Therion Labs, quiero generar el mapeo de datos y el RAT de la propia plataforma ComplianceAI
> desde el inventario, auditar internamente el tratamiento que hace la plataforma y demostrarlo con las mismas
> herramientas que vendemos.*

Toca backend y frontend. Pantalla: **Panel interno › Privacidad de la plataforma** (`/admin/privacidad`, solo `admin_therion`).

---

## 1. Qué se hizo

| Criterio | Cómo se cumple |
|---|---|
| 1. Actividades desde `catalogo_datos_personales.py` con finalidad, base y plazo | Nueva sección HU-41 del inventario: `ACTIVIDADES_PLATAFORMA` con 9 actividades (las 8 de la historia + *Herramientas de registro de las empresas*). Las categorías de datos y los plazos se calculan de las columnas personales de cada tabla; la base de licitud se comprueba contra las bases de esas columnas |
| 2. Plazos = `RETENCION_*` configurados; prueba que falla si difieren o si aparece una tabla sin actividad | `AJUSTE_POR_CONSERVACION` enlaza cada conservación con su ajuste (`RETENCION_DATOS_TITULAR_DIAS`, `RETENCION_ARCOP_CERRADAS_DIAS`, `RETENCION_EVENTOS_SEGURIDAD_DIAS`, `TUTOR_RETENCION_DIAS`, `CONTRATO_GRACIA_DIAS`). El generador usa el **valor vigente** (el de titulares, el del panel de retención si se fijó allí). `tests/test_hu41_registro_plataforma.py` falla si una tabla no está en una actividad ni en `TABLAS_SIN_TRATAMIENTO`, si una conservación nombra un ajuste sin enlazarlo o si los plazos generados no son los configurados |
| 3. Proveedores (LLM, Azure, correo) como encargados con país y garantía | `PROVEEDORES_PLATAFORMA`: Microsoft Azure, Groq, proveedor de correo y Cloudflare Turnstile, con rol *encargado*, país y garantía. Solo figuran los que usa la configuración activa. Las transferencias y sus garantías las calcula el mismo análisis del mapa del cliente |
| 4. RAT y RoPA con el mismo formato que los clientes | Se usan sin cambios `pdf_rat`, `xlsx_rat`, `pdf_ropa`, `xlsx_ropa` (y `pdf_mapa` para el mapa). Códigos propios `CIA-PLAT-REG-…` y `CIA-PLAT-ROPA-…` para no confundirlos con los de un cliente |

Además: **revisión interna** con revisiones automáticas y hallazgos priorizados (qué hacer en cada uno), descarga del **PDF del mapa** de la plataforma, historial de emisiones y verificación de códigos.

## 2. Decisiones (aprobadas en el plan)

- No se crea una empresa ficticia: el registro se genera en memoria desde el código; solo se guardan las emisiones.
- Toda tabla está en una actividad o en `TABLAS_SIN_TRATAMIENTO`; una tabla con datos personales no puede estar en esa lista.
- Plazo por categoría de datos: si varias conservaciones nombran ajustes, rige el más largo y el fundamento los nombra todos. Sin valor (regla desactivada o plazo que depende de un evento), el plazo queda **sin número**, la actividad incompleta y aparece un hallazgo. No se inventan números.
- El RAT es **oficial** solo si todas las actividades están completas; si no, sale como **borrador** con los motivos exactos. El RoPA incluye todas las actividades (muestra "Sin plazo definido" donde falta).
- Therion Labs figura como **responsable** en todas las actividades (coherente con las bases del inventario). Si el área legal define otro rol para alguna, se cambia `rol` en el generador.
- La plataforma (quien la opera) se ubica en Chile; la base, los archivos y las colas en `PLATAFORMA_PAIS_ALOJAMIENTO` (por defecto `US`, Azure North Central US).
- Azure, Groq y Turnstile parten con garantía *cláusulas contractuales tipo* y contrato **por confirmar**; el país y la garantía del correo se declaran en la configuración. Lo que falte sale como hallazgo.

## 3. Estado con la configuración por defecto

Con los plazos de `.env.example` el registro sale como **borrador**, a propósito: tres actividades tienen datos sin un plazo con número.

| Actividad | Qué falta |
|---|---|
| Solicitud de contratación | Plazo de eliminación de las solicitudes descartadas |
| Derechos ARCOP | Plazo de los metadatos de la solicitud (código de seguimiento, historial) |
| Auditoría y seguridad | Plazo de los datos de contacto del RoPA de la plataforma |

Además salen como hallazgos: la purga del registro de auditoría y la depuración de sesiones vencidas (pendientes del PO), los contratos por confirmar y, con `CORREO_MODO=smtp`, el país y la garantía del correo si no se declaran.

## 4. Archivos

**Backend (nuevos)**

| Archivo | Qué hace |
|---|---|
| `app/application/plataforma/registro.py` | Generador puro: ajustes vigentes, proveedores activos, plazos por categoría, mapa, contenido de cada actividad, informes RAT y RoPA, códigos y vistas del panel |
| `app/application/plataforma/revision.py` | Revisión interna: revisiones automáticas y hallazgos |
| `app/application/use_cases/privacidad_plataforma.py` | Resumen, datos del RoPA, emitir (reutiliza si no cambió), descargar, verificar y PDF del mapa |
| `app/api/routes/admin_privacidad.py` | 7 rutas bajo `/api/admin/privacidad-plataforma` (solo admin) |
| `app/domain/models/plataforma.py` | `plataforma_informe` (emisiones) y `plataforma_registro` (contacto cifrado, fila única) |
| `migrations/versions/d7e3f1a9b2c4_hu41_registro_plataforma.py` | Tablas nuevas y trigger de inmutabilidad en PostgreSQL. Revisa `down_revision` (`c5e8a2d7f3b1`) |
| `tests/test_hu41_registro_plataforma.py` | 28 pruebas (23 puras y 5 de modelo y API) |

**Backend (modificados)**

| Archivo | Cambio |
|---|---|
| `app/core/catalogo_datos_personales.py` | Sección HU-41 (actividades, tablas sin tratamiento, elementos, proveedores, enlaces de plazos, `problemas_de_cobertura()`) y las 2 tablas nuevas clasificadas |
| `app/core/config.py` | `THERION_RAZON_SOCIAL`, `THERION_RUT`, `PLATAFORMA_PAIS_ALOJAMIENTO`, `CORREO_PROVEEDOR_NOMBRE/PAIS/GARANTIA`, `PROVEEDORES_CONTRATO_CONFIRMADO`, `PLATAFORMA_INFORMES_DIA`, con validación al arrancar |
| `app/application/rat/informe.py`, `pdf_rat.py`, `xlsx_rat.py` | El texto final del recuadro de borrador pasa a `InformeRat.nota_borrador` (mismo texto por defecto: el informe del cliente no cambia) |
| `app/infrastructure/repositories/bitacora_repository.py` | Acciones `plataforma.informe_generado`, `informe_descargado`, `informe_verificado`, `mapa_descargado`, `ropa_datos_actualizados` |
| `app/domain/models/__init__.py`, `app/main.py` | Registro del modelo y de la ruta |
| `tests/test_hu20_autorizacion.py` | Las 7 rutas nuevas en la matriz de autorización |
| `.env.example`, `README.md` | Ajustes nuevos, sección 5.21, rutas y pruebas |

**Frontend**

| Archivo | Cambio |
|---|---|
| `app/admin/privacidad/page.tsx`, `components/admin/PanelPrivacidadPlataforma.tsx`, `components/admin/privacidad.module.css` | Pantalla con 4 pestañas: Revisión interna, Mapa de datos, Actividades (con ficha lateral) e Informes (generar, datos de contacto, historial y verificación) |
| `lib/admin/privacidad.ts` | Tipos, llamadas, descarga de archivos y textos de pantalla |
| `components/admin/BarraAdmin.tsx` | Entrada "Privacidad de la plataforma" |
| `lib/servidor/proxyAdmin.ts`, `app/bff/admin/api/[...ruta]/route.ts` | Rutas permitidas, parámetros `codigo` y `formato`, y descargas binarias (PDF y Excel) con su `Content-Disposition` |
| `tests/privacidad_plataforma.test.ts` | 12 pruebas de la lógica de pantalla y del proxy |

## 5. Cómo probar

```bash
docker compose exec api alembic upgrade head
docker compose exec worker pytest tests/test_hu41_registro_plataforma.py tests/test_t06_minimizacion.py tests/test_hu20_autorizacion.py -v
cd frontend-next && npm run typecheck && npx vitest run tests/privacidad_plataforma.test.ts
```

En el navegador: entrar al panel interno › **Privacidad de la plataforma**, revisar los hallazgos, abrir una actividad, pasar a **Informes**, generar el RAT, completar los datos de Therion Labs, generar el RoPA, descargar PDF y Excel y verificar un código.

Para que el registro salga **oficial** hay que definir los plazos pendientes (sección 3) y declarar en el `.env` el país y la garantía del correo y los contratos confirmados.

## 6. Verificación hecha al desarrollar

- Pruebas puras de HU-41: **23 aprobadas**. Junto con las de HU-35, HU-36 y HU-37: 86 aprobadas (las de modelo y API se omiten sin SQLAlchemy).
- Caso de uso ejecutado de punta a punta con dobles de BD y almacenamiento: emite, reutiliza, rechaza el RoPA sin datos, valida el formato, descarga (PDF válido), verifica, genera el mapa y registra todo en la bitácora sin correos ni teléfonos.
- PDF y Excel del RAT y del RoPA de la plataforma generados con los mismos generadores del cliente; la planilla tiene las mismas hojas.
- Frontend: las 12 pruebas pasan (compiladas con TypeScript estricto) y el componente compila contra declaraciones mínimas de React.
- **No se pudieron correr aquí** (el entorno no tenía FastAPI, SQLAlchemy, pydantic-settings ni `node_modules`, y no permite instalar): las 5 pruebas de modelo y API, `test_t06_minimizacion.py`, `test_hu20_autorizacion.py`, la migración en PostgreSQL y `npm run typecheck`. Correrlas en Docker o en CI antes de integrar.

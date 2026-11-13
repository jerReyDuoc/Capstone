# ComplianceIA — Plataforma de Evaluación de Gobernanza de IA

> Proyecto Capstone para **Therion Labs**. Autodiagnóstico de madurez en gobernanza de Inteligencia Artificial para empresas, con validación de evidencias asistida por LLM, reportes de madurez, rutas formativas y panel de estadísticas comparativas por rubro.

| | |
|---|---|
| **Cliente** | Therion Labs (Seguridad y Gobernanza de IA, miembro de la Comisión de Seguridad IA – CCHIA) |
| **Marcos normativos** | Ley N.º 21.719 (Chile), ISO/IEC 42001, NIST AI RMF 100-1, NIST AI 600-1, OWASP Top 10 for LLM |
| **Metodología** | Scrumban (Por hacer → En curso → Listo, con límite WIP) |
| **Meta de madurez** | TRL 5 — validación de componentes en entorno representativo (local, simulando uso real) |
| **Stack** | FastAPI · SQLAlchemy 2.0 async · PostgreSQL 16 · Redis 7 · ARQ · Groq · spaCy · Next.js 15 + React 19 · Docker Compose |
| **Última actualización** | 13-nov-2026 (HU-40: revisión interna del registro —lista de verificación por actividad y por elemento del mapa, observaciones que bloquean la marca, versión marcada como revisada con fecha y nombre en el informe del registro, diferencias entre versiones, paquete de evidencia ZIP verificable con hash, envío por correo y recordatorio de revisión periódica—) · 13-nov-2026 (HU-38: el registro de actividades conectado con la evaluación, las brechas y los borradores —riesgo explicable por actividad, matriz de mayor riesgo, PIA y aviso de privacidad pre-llenados, el registro vigente como evidencia y su estado en Mi empresa—) · 13-nov-2026 (HU-41: registro de tratamiento de la propia plataforma —mapa, RAT y RoPA de ComplianceAI— generado desde el inventario de datos, con revisión interna) · 13-nov-2026 (HU-37: informe RoPA desde el registro de actividades, en PDF y Excel, como responsable y como encargado) · 12-nov-2026 (HU-36: informe del registro de actividades en PDF y Excel, con código verificable, matriz de riesgos y marca de agua de borrador; mapa de datos con ficha en ventana, asistentes por pasos y guía) |

---

## Tabla de contenidos

1. [Contexto del proyecto](#1-contexto-del-proyecto)
2. [Estado actual](#2-estado-actual)
3. [Arquitectura](#3-arquitectura)
4. [Estructura del repositorio](#4-estructura-del-repositorio)
5. [Flujos funcionales](#5-flujos-funcionales)
6. [Base de datos](#6-base-de-datos)
7. [Endpoints de la API](#7-endpoints-de-la-api)
8. [Capa de Políticas e IA](#8-capa-de-políticas-e-ia)
9. [Seguridad y privacidad (Ley 21.719)](#9-seguridad-y-privacidad-ley-21719)
10. [Frontend](#10-frontend)
11. [Datos maestros](#11-datos-maestros)
12. [Puesta en marcha](#12-puesta-en-marcha)
13. [Variables de entorno](#13-variables-de-entorno)
14. [Pruebas y calidad](#14-pruebas-y-calidad)
15. [Comandos útiles y solución de problemas](#15-comandos-útiles-y-solución-de-problemas)
16. [Backlog, deuda técnica y riesgos](#16-backlog-deuda-técnica-y-riesgos)
17. [Documentación complementaria](#17-documentación-complementaria)

---

## 1. Contexto del proyecto

### Problema

La IA corporativa se está adoptando sin políticas de seguridad, las auditorías se hacen a mano en hojas de cálculo y la entrada en vigencia de la **Ley 21.719** (protección de datos personales) presiona a las organizaciones a demostrar cumplimiento. Como resume el cliente: *la IA no falla por falta de tecnología, sino por falta de capacidad interna para gobernarla.*

### Solución: tres funciones principales

| Función | Qué entrega |
|---|---|
| **Autodiagnóstico** | Cuestionario con filtro de aplicabilidad (7 preguntas) y hasta 40 controles; las evidencias se validan con un LLM; produce un reporte de madurez y de brechas. |
| **Rutas formativas** | Formación en 3 niveles (Inicial, Intermedio, Avanzado) × 4 dominios, asignada según las brechas detectadas. |
| **Panel de estadísticas** | Benchmark por rubro y dominio (promedio, mediana, máx., mín.) sin exponer datos de ninguna organización. |

### Equipo

| Integrante | Rol |
|---|---|
| Jerson Reyes | Product Owner |
| Jason Sánchez | Scrum Master |
| Ángel Muñoz | Developer Lead |
| Rodrigo Álvarez | Docente guía |

### Épicas y sprints

**Épicas:** (1) Motor de Autodiagnóstico y Motor de Reglas · (2) Procesamiento Inteligente y Privacidad de Datos con IA · (3) Rutas formativas e Interfaz Dashboard.

| Sprint | Objetivo |
|---|---|
| Sprint 1 | Desarrollo e implementación del backend y reglas de cálculo |
| Sprint 2 | Desplegar motor NER, gestión de derechos ARCOP y cifrado |
| Sprint 3 | Implementar IA, controles, detección de brechas y benchmarking |
| Sprint 4 | Despliegue del frontend, automatización del pipeline y staging para pruebas |

---

## 2. Estado actual

| Área | Estado | Detalle |
|---|---|---|
| Backend FastAPI (Clean Architecture) | ✅ Hecho | 13 routers, 51 endpoints |
| Base de datos y migraciones | ✅ Hecho | 19 tablas, 18 migraciones Alembic, seeds de catálogos, controles y filtro |
| Filtro de aplicabilidad (F1–F7) | ✅ Hecho | Árbol de decisión aditivo (22 controles base + 18 condicionales) |
| Respuestas y reglas de clasificación | ✅ Hecho | Matriz de 5 estados declarables (HU-02): `requiere_revision` la elige el usuario y la resuelve el LLM; justificación obligatoria en parcial y revisión |
| Validación de evidencias con LLM (worker ARQ + Groq) | ✅ Hecho | Asíncrona; el backend decide, el LLM solo propone |
| Capa de Políticas e IA (gateway, prompts versionados, métricas) | ✅ Hecho | `GET /api/ia/metricas`, revisión humana. HU-15: agente de **LangGraph** que orquesta las skills `validar_evidencia` y `tutor` (el gateway sigue siendo la única salida al LLM) |
| Gobernanza del Agente IA (HU-18) | ✅ Hecho | Scope locking en el system prompt (`tutor/1.2.0`) con canario por llamada, filtro de entrada por categoría de ataque (inyección, jailbreak, fuga del prompt, delimitadores, codificado, uso indebido, varios turnos), validación de la salida, advertencia tras 3 bloqueos y bitácora encadenada con HMAC verificable. Ver [5.13](#513-gobernanza-del-agente-ia-hu-18) y `Extras/Cambios/backend/CAMBIOS_HU18.md` |
| Log inmutable para el Auditor Externo (HU-09) | ✅ Hecho | `audit_log` de solo inserción (el rol de la app no tiene UPDATE/DELETE/TRUNCATE y los triggers frenan al dueño), IP obligatoria en cada registro, sellos SHA-256 por lote verificables por un tercero, rol `auditor_externo` con exportación ZIP y cobertura de modificaciones y supresiones (ARCOP, retención, respuestas, HU-06). Ver [5.14](#514-log-inmutable-para-el-auditor-externo-hu-09) y `Extras/Cambios/backend/CAMBIOS_HU09.md` |
| Agente IA Tutor (HU-15) | ✅ Hecho | Chat en el panel de formación para el usuario definitivo con contrato vigente: explicaciones y planes de acción por nivel (Inicial/Intermedio/Avanzado) sobre las brechas no conformes de la evaluación más reciente de **su** empresa; mensajes anonimizados, cuota diaria por empresa (60), borrado a los 30 días sin actividad y con la supresión ARCOP. Ver [5.12](#512-agente-ia-tutor-hu-15) y `Extras/Cambios/backend/CAMBIOS_HU15.md` |
| Motor NER de anonimización + cifrado del mapa de entidades | ✅ Hecho | spaCy `es_core_news_md` + reglas; fail-closed. **v1.1.0 optimizada (T-04): 25 ms por página (p95), precisión 0,988, cobertura de PII 100 %** |
| PII → tokens antes de persistir (HU-06) | ✅ Hecho | Justificaciones y nombres de archivo anonimizados al guardar; evidencias cifradas en disco y reemplazadas por su texto anonimizado; mapa de entidades irreversible; textos ARCOP cifrados (excepción); prueba de regresión sobre BD, disco y logs. Ver `Extras/Cambios/backend/CAMBIOS_HU06.md` |
| Minimización de datos y plazos de conservación (T-06) | ✅ Hecho | Inventario de las 171 columnas (26 con datos personales, en 9 tablas) con finalidad, base de licitud y plazo; auditoría de solo lectura sobre la BD real (DER, matriz, escaneo de contenido); anonimización por plazo vencido (cron diario, plazos pendientes del PO). Ver `Extras/Cambios/backend/CAMBIOS_T06.md` |
| Capa anti prompt-injection | ✅ Hecho | Bloqueo preventivo y bandeja de eventos. HU-07: reglas multilenguaje (inglés, portugués, francés, alemán, italiano) e indirectas, y saneamiento de caracteres invisibles, separadores y marcadores de turno antes del prompt |
| Verificación de las salidas del modelo (HU-07) | ✅ Hecho | Cada propuesta del modelo sobre una evidencia se revisa antes de usarla: formato (LLM05), afirmaciones sin respaldo en el documento (alucinaciones, LLM09), fuga de datos personales o del system prompt (LLM02/LLM07) e inyecciones que llegaron al modelo (LLM01). Con un hallazgo grave la pregunta queda para revisión humana y se registra una alerta (`origen=salida_llm`). Test-set de 124 casos borde (alucinación residual < 2 %), set de 131 ataques/legítimos OWASP, métricas en `GET /api/ia/metricas` y prueba en vivo con `scripts/evaluar_alucinaciones.py` contra Groq o un **modelo local** (Ollama, perfil `modelo-local`). Ver `Extras/Cambios/backend/CAMBIOS_HU07.md` |
| Reportes: cierre, resumen por dominio, comparativa, benchmark | ✅ Hecho | Benchmark recalculado **al completar cada evaluación** y por cron diario; la comparativa trae siempre la **meta de cumplimiento** (75) y el promedio del rubro solo con ≥ 3 evaluaciones (ver [5.7](#57-benchmark-sectorial-y-meta-de-cumplimiento)) |
| Planes de estudio recomendados (HU-12) | ✅ Hecho | Mapeo automático brecha → ruta del catálogo formativo, nivel Inicial/Intermedio/Avanzado por dimensión con objetivos, panel `/panel/capacitacion` organizado por dimensión normativa y exportación CSV. Ver [5.10](#510-plan-formativo-hu-12) y `Extras/Cambios/CAMBIOS_HU12.md` |
| Informe PDF y envío por correo | ✅ Hecho | El servidor genera el PDF (resultado, comparativa, brechas priorizadas y plan formativo): se **descarga directo** desde el panel (ya no abre la impresión) y se **envía por correo** como adjunto (SMTP, p. ej. Gmail). Ver [5.11](#511-informe-pdf-y-envío-por-correo) y la guía `frontend-next/docs/Guia_envio_informe_por_correo.pdf` |
| Derechos ARCOP (Ley 21.719) + autenticación por roles | ✅ Hecho | Titular y administrador; anonimización al aprobar una supresión |
| Derechos ARCOP en la página web (HU-32) | ✅ Hecho | Usuario temporal (N.º de evaluación + clave) en `/panel/mis-derechos`, usuario definitivo en `/empresa/mis-derechos` (con o sin contrato), bandeja del admin en `/admin/arcop`, seguimiento público en `/mis-derechos` y descarga de datos en JSON/CSV al resolverse un acceso o una portabilidad. Ver `Extras/Cambios/frontend/CAMBIOS_HU32.md` |
| Dockerización completa | ✅ Hecho | `docker compose up -d --build` levanta los 6 servicios; un solo `Proyecto/.env` para todo, con los puertos del host configurables (ver 12.1) |
| Suite de pruebas (pytest) | ✅ Hecho | 133 funciones de prueba (212 casos) + prueba en vivo, prueba de latencia y pruebas de rendimiento del NER |
| Panel web (HU-13, HU-11, HU-12) | ✅ Hecho | `frontend-next/` (Next.js 15 + React 19): diagnóstico, dominios, brechas priorizadas por severidad (HU-11) y capacitación (HU-12), con radar y barras interactivos, meta de cumplimiento, descarga del informe PDF y envío por correo; conectado a la API real; responsivo ≥ 1024 px y WCAG 2.1 AA. Ver [sección 10.1](#101-panel-web-hu-13-hu-11-hu-12) |
| Resto del frontend (backoffice de matriz y árbol) | 🟡 Demo estática | Cuestionario (HU-01/02), landing (HU-19), informe y formación ya están en `frontend-next/`; el backoffice solo existía en el prototipo HTML (API **simulada** en `localStorage`), archivado en `Extras/frontend-prototipo/` |
| Alta de invitaciones (usuario temporal) y evaluaciones por API | 🔴 Pendiente | Hoy se crean por SQL |
| Autenticación en todos los endpoints (HU-20) | ✅ Hecho | Evaluaciones, respuestas, evidencias y reportes exigen el token del encuestado/referente dueño o de un admin (404 en lo ajeno); métricas de IA, eventos de seguridad y revisión humana solo admin; catálogos, controles y landing públicos. Ver `Extras/Cambios/backend/CAMBIOS_HU20.md` |
| CRUD de administración de matriz/árbol (backend) | 🔴 Pendiente | Existe solo en la demo del frontend |
| Mapa de datos personales (HU-34) | ✅ Hecho | `/empresa/mapa-datos` (contrato vigente): sistemas, bases de datos, terceros y flujos con proveedor, país de alojamiento y responsable interno; categorías de datos (sensibles) y de titulares (NNA) de un **catálogo común con el RAT/RoPA**; transferencias internacionales calculadas; mapa navegable con filtros, hallazgos de riesgo, inicio desde plantilla por rubro o desde la evaluación, versiones inalterables con restauración, audit log, informe PDF, PNG, CSV y envío por correo. Ver [5.17](#517-mapa-de-datos-personales-hu-34) y `Extras/Cambios/backend/CAMBIOS_HU34.md` |
| Registro de actividades de tratamiento (HU-35) | ✅ Hecho | `/empresa/registro-actividades` (contrato vigente): cada actividad con los 11 campos mínimos del reglamento de la Ley 21.719, medidas de seguridad y rol (responsable o encargado); sistemas, bases, terceros y flujos **elegidos del mapa de datos** (sin doble ingreso) y vuelta automática a revisión cuando el mapa cambia; completitud por actividad y global; estados borrador → en revisión → vigente → archivada con **versiones vigentes inmutables** (trigger) y audit log. Textos legales como propuesta pendiente de validación. Ver [5.18](#518-registro-de-actividades-de-tratamiento-hu-35) y `Extras/Cambios/backend/CAMBIOS_HU35.md` |
| Informe del registro de actividades (HU-36) | ✅ Hecho | Botón **Informe del registro** en `/empresa/registro-actividades`: PDF (motor de informes de HU-21) y Excel armados en el servidor desde la **versión vigente** de cada actividad, con portada, resumen (actividades, datos sensibles, transferencias internacionales, decisiones automatizadas), detalle por actividad y **matriz de riesgos** 5 × 5 (base de HU-38); fecha, **versión del RAT**, **código verificable** `CIA-REG-AAAA-NNNNNN-D` y aviso legal; ambos en **Mis documentos** y cada emisión, descarga, envío y verificación en el audit log; con actividades no vigentes sale como **borrador** con marca de agua. Envío por correo. Ver [5.19](#519-informe-del-registro-de-actividades-hu-36) |
| Informe RoPA (HU-37) | ✅ Hecho | Botón **Informe RoPA** en `/empresa/registro-actividades`: una sola pantalla con lo que se incluye (**como responsable** / **como encargado**, según el rol de cada actividad), los datos que el registro no tiene (contacto de la empresa, delegado de protección de datos y organizaciones mandantes, guardados cifrados para la próxima vez), vista previa e historial. PDF y Excel desde la **versión vigente** de cada actividad, con fecha, versión, código `CIA-ROPA-AAAA-NNNNNN-D` y aviso legal; en **Mis documentos** y en el audit log. Ver [5.20](#520-informe-ropa-hu-37) |
| Registro conectado con el cumplimiento (HU-38) | ✅ Hecho | Cada actividad del registro recibe un **nivel de riesgo explicable** (datos sensibles, de NNA, transferencias sin garantía, decisiones automatizadas, **uso de IA** y **volumen** de personas); las de mayor riesgo forman la **matriz de riesgos** (Decreto 662, art. 3 letra e) con la **evaluación de impacto recomendada** y sus motivos. La **PIA** de borradores se pre-llena con esas actividades y el **aviso de privacidad** toma las finalidades y bases de licitud del registro. Un registro **vigente y completo** cuenta como **evidencia** de los controles de protección de datos (estado, brecha y puntaje, como una remediación; **nunca baja** un control). **Mi empresa** muestra el estado del mapa y del registro y sus brechas con la ruta de remediación (corregir, módulo formativo y re-evaluar). Ver [5.22](#522-registro-conectado-con-el-cumplimiento-hu-38) |
| Revisión interna del registro (HU-40) | ✅ Hecho | Registro de actividades › **Revisión interna** (`/empresa/registro-actividades/revision`): el mismo usuario de la empresa recorre la lista de verificación (7 puntos por actividad, 4 por elemento y 5 por flujo del mapa), deja observaciones, las cierra al corregir y marca la versión como revisada (fecha, nombre y cargo; la marca sale en el PDF y el Excel del registro). Diferencias entre versiones, informe de la revisión en PDF, paquete de evidencia ZIP con script de verificación, envío por correo y recordatorio periódico configurable. Ver [5.23](#523-revisión-interna-del-registro-hu-40) |
| Privacidad de la plataforma (HU-41) | ✅ Hecho | Panel interno › **Privacidad de la plataforma** (`/admin/privacidad`, solo admin): el mapa de datos, el RAT y el RoPA de ComplianceAI se generan desde `catalogo_datos_personales.py` (9 actividades con finalidad, base y plazo), con los plazos **vigentes** de la retención, los proveedores activos como encargados (país y garantía) y una **revisión interna** con hallazgos. PDF y Excel con los mismos generadores que el cliente y código `CIA-PLAT-REG/ROPA-AAAA-NNNNNN-D`. Ver [5.21](#521-privacidad-de-la-plataforma-hu-41) |
| Pipeline CI/CD y staging (HU-23) | ✅ Hecho | En cada pull request: pytest + cobertura, TypeScript + vitest y construcción de las imágenes sin secretos (check **CI aprobado**). Al integrar en `main`: despliegue automático a staging en Azure Container Apps (migraciones, `api`, `worker` y `web`, prueba de humo HTTPS y vuelta atrás automática). Datos semilla idempotentes. Ver [14.1](#141-integración-y-despliegue-continuo-hu-23) y [`docs/DESPLIEGUE_STAGING.md`](docs/DESPLIEGUE_STAGING.md) |

El detalle priorizado de lo pendiente está en la [sección 16](#16-backlog-deuda-técnica-y-riesgos).

---

## 3. Arquitectura

### Vista de componentes

```mermaid
flowchart LR
    U[Usuario<br/>navegador] -->|:3000| P[web<br/>Next.js 15]
    P -->|/api/* proxy| A
    P -->|BFF /bff/api/* + Bearer| A[api<br/>FastAPI + uvicorn :8000]
    A -->|SQL async| DB[(db<br/>PostgreSQL 16)]
    A -->|encola job| R[(redis<br/>Redis 7)]
    A -->|guarda archivo| S[[volumen storage]]
    W[worker<br/>ARQ] -->|toma job| R
    W -->|lee archivo| S
    W -->|SQL async| DB
    W -->|texto ANONIMIZADO<br/>HTTPS| G[Groq LLM]
    M[migrate<br/>alembic upgrade head] --> DB
```

| Servicio Docker | Imagen | Puerto (solo `127.0.0.1`) | Función |
|---|---|---|---|
| `web` | `complianceai-web` | 3000 | Frontend en Next.js (`frontend-next/`): landing, cuestionario y panel; reenvía `/api` al servicio `api` (mismo origen, sin CORS) |
| `api` | `complianceai-backend` | 8000 | FastAPI (`/docs` para Swagger) |
| `worker` | `complianceai-backend` | — | ARQ: valida evidencias y recalcula el benchmark (cron 02:00 UTC) |
| `migrate` | `complianceai-backend` | — | `alembic upgrade head` y termina |
| `db` | `postgres:16` | 5433 | Base de datos `complaince_db` |
| `redis` | `redis:7-alpine` | 6379 | Cola de trabajos de ARQ |

Orden de arranque: `db` sano → `migrate` termina bien → `api` y `worker` → `web`. Toda la configuración vive en un solo archivo, `Proyecto/.env` (plantilla `Proyecto/.env.example`), y ahí mismo se cambia cada puerto del host (`WEB_PORT`, `API_PORT`, `DB_PORT`, `REDIS_PORT`). El prototipo HTML que corría en `:8088` quedó archivado en `Extras/frontend-prototipo/`. La API y el worker comparten el volumen `storage` (evidencias). La imagen del backend es única (multi-stage, Python 3.13-slim, usuario sin privilegios) e incluye spaCy con el modelo `es_core_news_md`.

### Clean Architecture

```
┌────────────────────────────────────────────────────────────────┐
│ api/            Rutas FastAPI, validación de entrada, errores  │
├────────────────────────────────────────────────────────────────┤
│ application/    Casos de uso, filtros, schemas, capa de IA     │
├────────────────────────────────────────────────────────────────┤
│ domain/         Modelos (entidades) y puertos (interfaces ABC) │
├────────────────────────────────────────────────────────────────┤
│ infrastructure/ Adaptadores: repositorios SQLAlchemy, Groq,    │
│                 storage local, NER, cifrado, prompt guard      │
├────────────────────────────────────────────────────────────────┤
│ core/           Configuración, BD, autenticación               │
│ worker/         Tareas ARQ                                     │
└────────────────────────────────────────────────────────────────┘
```

**Regla de dependencia:** las capas externas dependen de las internas, nunca al revés. Cambiar el LLM (Groq → otro proveedor) o el storage (local → S3) es reemplazar un adaptador sin tocar la lógica de negocio. Puertos definidos: `LLMProviderPort`, `SanitizerPort`, `RegistroIAPort`, `PromptGuardPort`, `EvidenceValidatorPort`, `FileStoragePort`.

### Principios de diseño

1. **El LLM nunca accede a la BD.** Solo recibe texto (prompt) y devuelve JSON validado con Pydantic. El backend es el único que lee y escribe.
2. **El backend decide, el LLM propone.** Umbral de confianza, degradación y asignación de brechas son reglas de negocio del backend.
3. **Ningún dato personal sale en claro.** Todo texto no confiable pasa por el motor NER antes de llegar al proveedor; si la sanitización falla, se aborta (*fail-closed*).
4. **Nada se guarda con PII en claro (HU-06).** Justificaciones y nombres de archivo se anonimizan antes de escribirse; los archivos de evidencia viven cifrados hasta que el worker los reemplaza por su texto anonimizado; los textos ARCOP se cifran (excepción documentada).
5. **Todo queda auditado.** Cada llamada al LLM se registra en `llamadas_llm`; cada mapa de entidades (tipos, huellas HMAC y conteos, sin valores: HU-06) en `sanitizaciones`; cada intento de inyección en `eventos_seguridad`; cada cambio ARCOP en `eventos_solicitud_arcop`.

---

## 4. Estructura del repositorio

```
Capstone/
├── Documentos/                     # Entregables académicos por fase e integrante
│   ├── Fase 1/                     # Guía, formativa, bitácora CPCITT, presentación, autoevaluaciones
│   └── Fase 2/                     # Diarios de reflexión
├── Extras/                         # Evidencia y documentación de apoyo (no se ejecuta). Ver Extras/README.md
│   ├── Cambios/                    # Documentos CAMBIOS_*.md de cada HU/tarea (backend/, frontend/, HU-12)
│   ├── Evidencias/                 # Reportes de latencia, capturas e informes de ejemplo
│   ├── frontend-prototipo/         # Prototipo HTML/JS original (con su nginx.conf), reemplazado por frontend-next
│   └── Guia_ComplianceAI_PromptInjection.docx.pdf
└── Proyecto/
    ├── README.md                   # ← este documento
    ├── .env.example                # Plantilla del ÚNICO .env (compose, backend y frontend)
    ├── docker-compose.yml          # Sistema completo (6 servicios)
    ├── docs/DESPLIEGUE_STAGING.md  # HU-23: CI/CD, staging en Azure, secretos, vuelta atrás y verificación
    ├── infra/azure/preparar_staging.sh  # HU-23: preparación única del staging (Cloud Shell)
    ├── frontend-next/              # Panel web Next.js (HU-13, ver sección 10.1)
    │   ├── app/                    # /panel, /panel/dominios, /panel/brechas, /panel/capacitacion (HU-12),
    │   │                           # landing y cuestionario (/, /comenzar, /encuesta, /retomar), bff/ + globals.css
    │   ├── components/             # charts/, shell/, vistas/, ui/, brechas/ (HU-11), cuestionario/,
    │   │                           # informe/ (Descargar PDF + diálogo de correo)
    │   ├── hooks/                  # usePanel, usePlanFormativo (HU-12), useCuestionario, …
    │   ├── lib/                    # Tipos de la API, adaptadores, cliente HTTP, severidad, planFormativo, datos demo
    │   ├── tests/                  # vitest (adaptadores, HU-11, cuestionario, encuesta, HU-12)
    │   ├── docs/                   # ACCESIBILIDAD.md
    │   └── Dockerfile              # Build standalone (node 22)
    └── backend/
        ├── Dockerfile              # Imagen única para migrate, api y worker
        ├── requirements.txt
        ├── alembic.ini
        ├── migrations/versions/    # 18 migraciones Alembic
        ├── scripts/benchmark_ner.py  # Benchmark y profiling del motor NER (T-04)
        ├── scripts/auditoria_minimizacion.py  # T-06: DER, matriz y escaneo de la BD (solo lectura)
        ├── scripts/retencion_datos.py         # T-06: plazos de conservación (simulación / --aplicar)
        ├── scripts/sql/t06_rol_auditor.sql    # T-06: rol de solo lectura para auditar
        ├── tests/                  # Suite pytest (ver sección 14); data/evidencias_ejemplo/ para pruebas manuales
        └── app/
            ├── main.py             # App FastAPI, routers y pool ARQ
            ├── core/
            │   ├── config.py       # Settings (pydantic-settings) + validaciones de producción
            │   ├── database.py     # Engine async, sesión, Base
            │   ├── autenticacion.py# Tokens HMAC, roles, hash de contraseñas, dependencias
            │   └── crear_admin.py  # CLI para crear/desactivar administradores
            ├── api/routes/         # arcop, auth, catalogos, controles, encuesta_publica, evaluaciones,
            │                       # evidencias, filtro, informes (HU-12), metricas_ia, reportes,
            │                       # respuestas, seguridad
            ├── application/
            │   ├── ai/             # gateway.py, politicas.py, metricas.py, evidence_validator.py,
            │   │                   # prompts/ (base.py, validar_evidencia.py)
            │   ├── filters/control_tree.py   # Árbol de aplicabilidad F1–F7
            │   ├── informes/       # HU-12: analisis.py (severidad, brechas, plan formativo; lógica pura),
            │   │                   # carga.py, pdf_informe.py (reportlab), correo.py (SMTP / .eml)
            │   ├── schemas/        # api_schemas, arcop_schemas, evidence_validation
            │   └── use_cases/      # create_respuesta, upload_evidence, process_evidence,
            │                       # responder_filtro, generate_resumen, update_benchmark,
            │                       # obtener_metricas_ia, registrar_evento_seguridad,
            │                       # gestionar_solicitud_arcop, iniciar_sesion
            ├── domain/
            │   ├── models/         # 19 entidades SQLAlchemy (ver sección 6)
            │   └── ports/          # Interfaces ABC
            ├── infrastructure/
            │   ├── llm/            # groq_provider.py, factory.py
            │   ├── repositories/   # 10 repositorios
            │   ├── security/       # ner_sanitizer.py, cifrado.py, prompt_guard.py, seguridad.py
            │   └── storage/        # local_storage.py, archivo_cifrado_storage.py (HU-06)
            └── worker/tasks.py     # process_evidence_task + cron update_benchmark_task
```

---

## 5. Flujos funcionales

### 5.1 Recorrido completo de un diagnóstico

```mermaid
flowchart TD
    A[Invitación: usuario_temporal + rubro] --> B[Crear evaluación]
    B --> C[Filtro de aplicabilidad<br/>POST /evaluaciones/id/filtro]
    C -->|F1 = NO| Z[Ningún control aplica]
    C -->|F1 = SI| D[Controles aplicables<br/>22 base + condicionales]
    D --> E[Responder cada control<br/>POST /respuestas]
    E -->|cumplido / parcial| F[Subir evidencia<br/>POST /respuestas/id/evidencias]
    E -->|no_cumplido| G[Brecha asignada al instante]
    E -->|no_aplica| H[Sin brecha, fuera del puntaje]
    F --> I[Worker: seguridad → NER → LLM → reglas]
    I --> J[Clasificación final]
    G --> K
    H --> K
    J --> K[Cerrar evaluación<br/>POST /evaluaciones/id/cerrar]
    K --> L[Resumen por dominio + puntaje general + nivel]
    L --> M[Comparativa vs. benchmark del rubro]
    L --> N[Brechas → plan formativo por dimensión<br/>GET /evaluaciones/id/plan-formativo]
    L --> P[Informe PDF: descarga y correo<br/>GET /informe/pdf · POST /informe/enviar]
    O[Oficial de Cumplimiento] -.->|PATCH /respuestas/id/revision| J
```

> Los pasos A y B aún no tienen endpoint: se crean por SQL (ver [12.3](#123-preparar-datos-de-prueba)).

### 5.2 Filtro de aplicabilidad (preguntas de compuerta)

Las 7 preguntas se responden SI/NO y deben venir **todas** en un mismo envío (se puede rehacer: las anteriores se reemplazan). F1 es la compuerta raíz; F2–F7 suman controles al conjunto base.

| Código | Pregunta | Controles que activa (si SI) |
|---|---|---|
| F1 | ¿La organización utiliza, desarrolla o integra algún sistema, modelo o herramienta de IA? | **Base (22):** DAT-001, 003, 004, 005, 006, 010 · GOB-001, 002, 003, 004, 005, 007, 009, 010 · RIE-001, 003, 004, 008, 010 · SEG-006, 007, 009. Si es NO no aplica ninguno |
| F2 | ¿Procesa datos sensibles (salud, biométricos o perfilamiento de personas/menores)? | DAT-002, DAT-009 |
| F3 | ¿Usa servicios, APIs, SaaS o plataformas de IA de terceros o en nube internacional? | DAT-007, DAT-008, GOB-008, SEG-008 |
| F4 | ¿Usa LLM, IA generativa o arquitecturas RAG / bases vectoriales? | RIE-002, SEG-001, SEG-002, SEG-005 |
| F5 | ¿La IA genera código/SQL/HTML o ejecuta acciones/agentes conectados a otros sistemas? | RIE-009, SEG-003, SEG-004 |
| F6 | ¿La IA toma decisiones que afectan derechos, personas, crédito o contrataciones? | RIE-005, RIE-006, SEG-010 |
| F7 | ¿La empresa desarrolla, entrena o adapta internamente modelos o agentes de IA? | RIE-007, GOB-006 |

La tabla es la **semilla** (versión `2026.1`). Desde HU-24 el árbol vive en la BD (`regla_aplicabilidad` y `preguntas_filtro.es_compuerta`) y el administrador lo cambia desde `/admin/matriz`, con versionado (ver 5.16). `app/application/filters/control_tree.py` conserva la semilla y la evaluación del árbol; en ejecución se usa `app/infrastructure/cache/arbol_aplicabilidad.py`.

### 5.3 Respuesta a un control

Matriz de **5 estados** que el usuario elige (HU-02):

| Clasificación declarada | Valor | ¿Justificación obligatoria? | ¿Lleva evidencia? | ¿Pasa por el LLM? | Brecha |
|---|---|---|---|---|---|
| Cumplido | `cumplido` | No | Sí | Sí | Solo si el LLM la degrada a `no_cumplido` |
| Parcialmente cumplido | `parcialmente_cumplido` | **Sí** (mín. 20 caracteres) | Sí | Sí | Solo si el LLM la degrada a `no_cumplido` |
| No cumplido | `no_cumplido` | No | No | No | **Se asigna al crear la respuesta** |
| No aplica | `no_aplica` | No | No (subirla da 400) | No | No |
| Requiere revisión | `requiere_revision` | **Sí** (mín. 20 caracteres) | **Sí, obligatoria para completar** | Sí: **el LLM decide** `cumplido`, `parcialmente_cumplido` o `no_cumplido` | Si el LLM decide `no_cumplido` |

- **Requiere revisión** (decisión del PO, 16-oct): el usuario la elige cuando no sabe cómo clasificar el control. Adjunta evidencia y el LLM la clasifica (prompt `validar_evidencia/1.2.0`). Si el LLM no alcanza el umbral de confianza, el control queda en `requiere_revision` para la **revisión humana** (`PATCH /revision`). Mientras no se resuelva puntúa 0. La capa de seguridad también puede asignar este estado (`fuente = seguridad`).
- **Justificación obligatoria** en `parcialmente_cumplido` y `requiere_revision`: al menos `JUSTIFICACION_MIN_CARACTERES` (20) caracteres, sin contar espacios repetidos ni de los extremos, y con letras (no solo signos o números). Si no, `422 JUSTIFICACION_OBLIGATORIA` en `POST` y `PUT`.

Al crear la respuesta, la **justificación** pasa por el detector de prompt injection: si es sospechosa se rechaza con `422 PROMPT_INJECTION` y se registra un evento de seguridad.

**Reglas del cuestionario (HU-01):**

- **Una respuesta por control y evaluación** (restricción única `uq_respuesta_evaluacion_control`). `POST /api/respuestas/` es un *upsert*: la primera vez crea (201) y luego actualiza la misma fila (200, mismo `id_respuesta`). Si se reenvía exactamente la misma declaración no se modifica nada (el guardado automático no borra la validación del LLM); si cambia, la declaración nueva pasa a ser el estado vigente (`fuente = usuario`) y se descarta la validación anterior (LLM o revisión). Las evidencias ya subidas se conservan.
- Solo se aceptan respuestas a evaluaciones **existentes** (404 `EVALUACION_NO_ENCONTRADA`), **abiertas** (409 `EVALUACION_CERRADA` si `estado_progreso` es `completada` o `cerrada`), **con el filtro completado** (409 `FILTRO_PENDIENTE`) y a controles **aplicables** según F1–F7 (422 `CONTROL_NO_APLICABLE`; 404 `CONTROL_NO_ENCONTRADO`). Una evaluación cerrada tampoco permite rehacer el filtro ni subir evidencias. Se cierra con `POST /api/evaluaciones/{id}/completar`.
- `GET /api/evaluaciones/{id}/progreso` devuelve respondidos / aplicables, el avance por dimensión, el siguiente control pendiente y el estado declarado de cada control ya respondido, para **reanudar** el cuestionario. Si se rehace el filtro, las respuestas de controles que dejan de aplicar no cuentan (`respuestas_fuera_de_alcance`).

### 5.4 Validación asíncrona de evidencias

```mermaid
sequenceDiagram
    autonumber
    participant C as Cliente
    participant API as API FastAPI
    participant FS as Storage
    participant Q as Redis (ARQ)
    participant W as Worker
    participant G as Capa IA (AIGateway)
    participant L as Groq
    participant DB as PostgreSQL

    C->>API: POST /api/respuestas/{id}/evidencias (archivo)
    API->>DB: valida respuesta (solo cumplido/parcial)
    API->>FS: guarda archivo (uuid_nombre) + hash SHA-256
    API->>DB: evidencia estado=pending
    API->>Q: enqueue process_evidence_task
    API-->>C: 202 Accepted
    Q->>W: job
    W->>DB: evidencia → processing; carga respuesta, control y brecha
    W->>W: prompt guard sobre justificación y evidencia
    alt inyección detectada (modo bloquear)
        W->>DB: evidencia rejected, respuesta requiere_revision, evento_seguridad
    else texto limpio
        W->>G: ejecutar(VALIDAR_EVIDENCIA, textos, datos)
        G->>G: NER anonimiza (falla ⇒ aborta)
        G->>DB: mapa de entidades CIFRADO (sanitizaciones)
        G->>L: prompt versionado SOLO con texto anonimizado
        L-->>G: JSON (clasificación, confianza, justificación…)
        G->>DB: métrica (llamadas_llm)
        G-->>W: resultado validado
        W->>W: reglas de decisión del backend
        W->>DB: evidencia + clasificación final de la respuesta
    end
```

**Reglas de decisión** (`ProcessEvidenceUseCase._apply_classification_decision`), con `UMBRAL_CONFIANZA = 0.8` por defecto:

| # | Condición | Resultado en la respuesta | Evidencia | Fuente |
|---|---|---|---|---|
| 0 | Evidencia marcada como sospechosa y confianza < umbral | `requiere_revision` | `rejected` | `seguridad` |
| 1 | Confianza < umbral | Se mantiene lo declarado por el usuario | `rejected` | `usuario` |
| 2 | Confianza ≥ umbral | Clasificación propuesta por el LLM | `validated` | `llm` |
| 3 | Clasificación final = `no_cumplido` | Se asigna la brecha del control; con cualquier otro estado final se **quita** (`Respuesta.sincronizar_brecha`) | — | — |
| — | Error de la capa de IA (NER, timeout, rate limit, salida inválida…) | Sin cambios | `error` con mensaje sin PII | — |

Estados de una evidencia: `pending` → `processing` → `validated` | `rejected` | `error`. El worker reintenta hasta 3 veces y cada job tiene 300 s de límite.

### 5.5 Revisión humana

`PATCH /api/respuestas/{id}/revision` permite al Oficial de Cumplimiento fijar la clasificación final (`fuente_clasificacion = revision`). Si queda en `no_cumplido` se asigna la brecha. Esa revisión es la **verdad de referencia** para medir la precisión del LLM en `/api/ia/metricas`.

### 5.6 Cierre, puntaje y nivel de madurez

`POST /api/evaluaciones/{id}/cerrar` (re)genera la tabla `resumen`:

1. Considera solo controles **aplicables** según el filtro y con respuesta registrada.
2. Excluye `no_aplica`.
3. Puntúa: `cumplido` = 1 · `parcialmente_cumplido` = 0,5 · `no_cumplido` = 0 · `requiere_revision` = 0 (cuenta en el denominador, para que inyectar texto nunca suba el puntaje).
4. Puntaje del dominio = promedio × 100. Puntaje general = promedio ponderado por cantidad de controles.

| Puntaje | Nivel de madurez |
|---|---|
| 0 – 25 | `inicial` |
| > 25 – 50 | `en_desarrollo` |
| > 50 – 75 | `gestionado` |
| > 75 – 100 | `optimizado` |

Si todos los controles quedan fuera (F1 = NO o 100 % `no_aplica`), no se genera resumen y `GET /resumen` responde 404.

### 5.7 Benchmark sectorial y meta de cumplimiento

`UpdateBenchmarkUseCase` borra y recalcula `benchmark` agrupando los resúmenes por **rubro × dominio** (promedio, mediana, máximo, mínimo, cantidad) de las evaluaciones con `estado_progreso = 'completada'` (sin las de prueba). Se ejecuta **al completar cada evaluación** (`BENCHMARK_AL_COMPLETAR=true`; si falla, `/completar` responde igual) y en el cron diario de ARQ (02:00 UTC), que lo repara.

> Antes solo corría el cron: quien terminaba el cuestionario no veía la comparativa hasta el día siguiente. Ese era el motivo de que "no saliera la comparativa con la industria".

`GET /api/evaluaciones/{id}/comparativa` devuelve por dominio:

- la **meta de cumplimiento** (`META_CUMPLIMIENTO_PUNTAJE`, 75 = techo de *gestionado*): lo que debería alcanzar cada dimensión, la diferencia y si la cumple. Está siempre, aunque no haya benchmark ni rubro;
- el **sector (rubro)** con k-anonimato (HU-10): el promedio solo se publica si la cohorte tiene `K_ANONIMATO_MINIMO` **empresas distintas** o más (5 por defecto, mínimo 5 en production; una empresa que se reevalúa cuenta una vez). Con menos, todas las métricas del sector salen en `null`, no se revela cuántas empresas hay y `sector.advertencia` trae el aviso para la interfaz. Mediana y percentiles 25/75 solo con `K_ANONIMATO_DISTRIBUCION` (10); máximo y mínimo nunca se publican. Detalle en `Extras/Cambios/backend/CAMBIOS_HU10.md`.

### 5.8 Solicitudes de derechos ARCOP (Ley 21.719)

Historia de usuario: *como Titular de Datos Personales quiero registrar solicitudes formales de Acceso, Rectificación, Supresión, Oposición, Portabilidad o Bloqueo.* Tipos: `acceso`, `rectificacion`, `supresion`, `oposicion`, `portabilidad`, `bloqueo`.

```mermaid
stateDiagram-v2
    [*] --> recibida: titular crea
    recibida --> en_revision: admin
    recibida --> rechazada: admin
    recibida --> cancelada: titular
    en_revision --> en_proceso: admin
    en_revision --> pendiente_informacion: admin (comentario obligatorio)
    en_revision --> rechazada: admin
    en_revision --> cancelada: titular
    pendiente_informacion --> en_revision: titular aporta información
    pendiente_informacion --> rechazada: admin
    pendiente_informacion --> cancelada: titular
    en_proceso --> resuelta: admin
    en_proceso --> rechazada: admin
    resuelta --> [*]
    rechazada --> [*]
    cancelada --> [*]
```

- Cada cambio queda en `eventos_solicitud_arcop` en la misma transacción.
- Una **supresión resuelta** anonimiza de forma irreversible los datos del titular (email, justificaciones, evidencias y sus archivos, mapas de entidades, extractos de seguridad, descripciones ARCOP) y conserva clasificaciones y puntajes sin vínculo personal. El titular pierde el acceso al instante.
- Cada solicitud tiene un **código de seguimiento único** (`ARC-XXXX-XXXX`); el estado se consulta sin login en `GET /api/arcop/seguimiento/{codigo}`, sin datos personales.
- **Plazos legales por defecto (Ley 21.719):** respuesta en 30 días corridos, prórroga única de 30 días con motivo, bloqueo temporal en 2 días hábiles (configurables con `ARCOP_PLAZO_*`). Se informa `plazo_vencido` y el filtro `?vencidas=true`.
- El titular puede ser un **invitado** o un **encuestado anónimo** de la encuesta pública (entra con la clave de su evaluación).
- **HU-32:** con una solicitud de **acceso** o **portabilidad** resuelta, el titular descarga sus datos en JSON (estructurado, para traspasarlos) o CSV (`GET /api/arcop/solicitudes/{id}/exportacion?formato=json|csv`); cada descarga queda en el audit log. La rectificación la aplica el admin a mano y la cierra con su respuesta. Páginas web en la [sección 10.1](#101-panel-web-hu-13-hu-11-hu-12).
- Detalle completo, tabla de anonimización y decisiones pendientes: [`Extras/Cambios/backend/CAMBIOS_ARCOP.md`](../Extras/Cambios/backend/CAMBIOS_ARCOP.md).

### 5.9 Autenticación y roles

| Rol | Quién | Cómo obtiene el token |
|---|---|---|
| `referente` | Usuario temporal (titular de sus datos) | `POST /api/auth/titular` con `{usuario_temporal_id, email}`; requiere invitación vigente y no anonimizada |
| `encuestado` | Encuestado anónimo de la encuesta pública (titular de sus datos) | `POST /api/auth/encuestado` con `{evaluacion_id, clave}`; la clave se genera por evaluación (`POST /api/auth/encuestado/clave`, admin; luego HU-19) |
| `admin_therion` | Administrador de Therion Labs (tabla `usuarios_admin`) | `POST /api/auth/login` con `{email, password}` |
| `cliente` | Usuario definitivo de una empresa cliente (HU-27; uno por empresa, tabla `usuario_definitivo`). Ve las evaluaciones migradas a su empresa | `POST /api/auth/cliente` con `{email, password}`, tras definir su contraseña con el enlace de activación |

- Token bearer firmado con HMAC-SHA256 (`AUTH_SECRET`), vigencia `AUTH_TOKEN_TTL_MIN` (480 min por defecto). Respuesta: `{access_token, token_type, rol, usuario_id, expira_en_min}`.
- Contraseñas con PBKDF2-SHA256 (600 000 iteraciones); verificación en tiempo constante y hash señuelo para no revelar emails existentes.
- En cada petición se comprueba en BD que el admin siga activo o que el titular no esté anonimizado (401 `USUARIO_DESHABILITADO`).
- HU-28: los logins con contraseña (admin y cliente) abren una **sesión revocable** (`sesion_usuario`); el token lleva su `sid` y `POST /api/auth/logout` o restablecer la contraseña la cierran. Los intentos **fallidos** se limitan por cuenta (`LOGIN_MAX_FALLOS_CUENTA`, 5) y por IP (`LOGIN_MAX_FALLOS_IP`, 20) en ventanas de `LOGIN_VENTANA_FALLOS_MIN` (15) minutos → 429 `DEMASIADOS_INTENTOS`; el contador de la cuenta usa la huella del correo escrito, exista o no. Cada intento (exitoso, fallido o bloqueado) queda en la bitácora.
- HU-28: recuperación de contraseña por enlace de un solo uso (`/restablecer#token=…`, vence en `RECUPERACION_TTL_MIN`); la respuesta no revela si el correo existe.
- En el navegador el token nunca es visible: el BFF de Next.js lo guarda en cookies httpOnly (`cai_sesion` del encuestado, `cai_admin` del admin y `cai_cliente` del cliente; `__Host-` en producción).
- Administradores: `docker compose exec api python -m app.core.crear_admin --email admin@therionlabs.cl` (contraseña mínima de 12 caracteres; `--desactivar` corta el acceso).
- Token de prueba solo para desarrollo: `python -m app.core.autenticacion --usuario 1 --rol referente`.

### 5.10 Plan formativo (HU-12)

`GET /api/evaluaciones/{id}/plan-formativo` arma el plan de estudio a partir de las brechas de la evaluación (lógica pura en `application/informes/analisis.py`, la misma que usa el PDF):

1. **Mapeo automático:** cada brecha (no cumplida o parcial) activa la ruta que el catálogo le asigna (`catalogo_brechas.ruta_formativa_id`). Los parciales, que no llevan brecha en la respuesta, se mapean por la brecha de su control. Las brechas sin ruta se informan aparte (cobertura del mapeo).
2. **Nivel por dimensión** según el puntaje del dominio: ≤ 50 **Inicial** · ≤ 75 **Intermedio** · > 75 **Avanzado**, con su objetivo. La ruta de ese nivel entra siempre como "Base del nivel".
3. **Agrupado por dimensión normativa** (el dominio de la ruta, que puede no ser el de la brecha: `ERR-DAT-002` → *Gestión de Riesgos – Intermedio*). Módulos ordenados Inicial → Intermedio → Avanzado y por severidad (Crítica primero).

Cada módulo trae objetivo general, objetivos específicos, contenidos, horas, modalidad, público objetivo y las brechas que cierra.

### 5.11 Informe PDF y envío por correo

- `GET /api/evaluaciones/{id}/informe/pdf` genera el informe con **reportlab**: resultado general, comparativa con meta y rubro, brechas priorizadas (HU-11) y plan formativo (HU-12). Acepta los filtros del listado (`severidad`, `dominio`, `estado`, `q`). El panel lo **descarga directo** (`Content-Disposition: attachment`).
- HU-21: la portada del PDF lleva la **ficha de identificación** (código de evaluación con dígito verificador, fecha de la evaluación, fecha de emisión y **versión de la matriz**, que `POST /completar` guarda en `evaluacion.version_matriz` como `MATRIZ_VERSION+huella`), el **aviso legal** completo (y resumido en el pie de cada página, con "Página X de Y") y los **5 puntajes** (Global y las 4 dimensiones, siempre). Cierra con una huella SHA-256 de los resultados que coincide con `GET /informe/ficha`.
- `POST /api/evaluaciones/{id}/informe/enviar` `{email?, recordar?, filtros…}` envía **ese mismo PDF** como adjunto, para que quede en la bandeja si se pierde el archivo. El PDF siempre lo genera el servidor con datos de la BD (no se aceptan archivos del cliente). El encuestado puede omitir el correo (se usa el registrado) o guardarlo con `recordar`. Límite: 3 envíos por evaluación y 10 por IP al día.
- `CORREO_MODO`: `archivo` (defecto en desarrollo: el `.eml` queda en `STORAGE_DIR/correos`, no sale nada), `smtp` (envío real) o `desactivado`. Configuración en [12.1, paso 4](#121-con-docker-recomendado).

### 5.12 Agente IA Tutor (HU-15)

La capa de IA pasó a ser un **agente de LangGraph** (`application/ai/agente/`). El grafo tiene un nodo `guardia` (prompt injection, antes del LLM y del NER), un router **determinista** que elige la skill según lo que pide el caso de uso, y una skill por tarea: `validar_evidencia` (la evaluación de evidencias de siempre, sin cambios de comportamiento) y `tutor` (con un nodo final que ancla la salida a las brechas del contexto). Cada skill llama al `AIGateway` con su `TareaIA`, así que sanitización, prompt versionado (`tutor/1.2.0` desde HU-18), schema estricto y métricas siguen en un solo lugar. El LLM no tiene herramientas ni toca la BD: el caso de uso `TutorIA` carga el contexto, invoca el agente y persiste.

1. **Contexto aislado:** la empresa sale del token; se usan solo las brechas `no_cumplido` y `parcialmente_cumplido` de la evaluación más reciente con resultados, con datos de catálogo y del control; para las brechas en foco van además la obligación, la evidencia esperada y la fuente normativa real del control, y los antecedentes de la propia empresa (su justificación y su última evidencia, que pasan otra vez por el NER). No van la razón social ni datos de contacto. Se recarga en cada mensaje, así que el tutor ve las mejoras de la remediación (HU-17).
2. **Nivel:** por defecto el de la ruta (la del módulo desde el que se abrió o la de la brecha más prioritaria); el usuario lo cambia con `PATCH`.
3. **Chat síncrono** con la respuesta ya validada; texto anonimizado en `mensaje_tutor`; cuota `TUTOR_MENSAJES_DIA_EMPRESA` (60) y ráfaga por minuto; conversaciones de una evaluación anterior quedan de solo lectura.

### 5.13 Gobernanza del Agente IA (HU-18)

El agente se somete a los mismos controles que el sistema exige a las empresas. El system prompt del tutor fija una función única (explicar brechas, armar planes de remediación y orientar hacia las rutas formativas) y lleva un código de control distinto en cada llamada; si ese código o un trozo largo del prompt aparece en la respuesta, la respuesta se reemplaza antes de guardarse. Antes del LLM, el nodo `guardia` pasa el mensaje por `FiltroAgente` (reglas locales, sin costo): si es un ataque se responde según la categoría sin llamar al modelo, y los antecedentes guardados por la empresa que traen instrucciones se omiten línea por línea sin bloquear al usuario. Después del LLM, `validar_salida` quita código y enlaces externos y limpia las respuestas fuera de alcance.

Toda interacción (respondida, bloqueada o rechazada por cuota, largo o permisos) queda en la bitácora con la huella del mensaje y las entidades que el NER enmascaró, nunca con el texto. Cada fila de la bitácora guarda el HMAC de la anterior, de modo que una modificación, un borrado o una inserción en medio se detectan con `GET /api/admin/bitacora/verificacion`. Con 3 bloqueos de la misma empresa en 10 minutos aparece una advertencia en el chat, sin cortar el servicio. El test-set de ataques está en `backend/tests/data/ataques_tutor.jsonl`; la prueba automática mide el filtro y `scripts/evaluar_ataques_tutor.py` lo corre contra Groq.

### 5.14 Log inmutable para el Auditor Externo (HU-09)

La bitácora de HU-27/HU-18 pasó a llamarse **`audit_log`** y quedó cerrada en tres capas. La API y el worker ya no se conectan como `postgres`: usan el rol **`complianceia_app`** (`DB_APP_USER`), sin superusuario, que en `audit_log` y `audit_log_sello` solo tiene `SELECT` e `INSERT`; las migraciones siguen corriendo con el dueño. Además, unos triggers impiden `UPDATE`, `DELETE` y `TRUNCATE` aunque los intente el dueño, y si alguien con superusuario los desactiva, la cadena HMAC de cada fila y los sellos por lote lo dejan en evidencia.

Cada registro trae fecha (UTC), actor (rol e id, o `sistema`), **IP** (la del visitante que reenvía el BFF, o `sistema:worker`/`sistema:cli`), acción, entidad y resultado (`ok`, `rechazado`, `error`, `omitido`); en PostgreSQL lo exigen restricciones `CHECK`. El worker sella cada 15 minutos las filas nuevas en lotes de 500: cada lote recibe un `hash_lote` SHA-256 y un sello encadenado al anterior que **un tercero puede recalcular** sin claves. El Auditor Externo entra con `POST /api/auth/auditor` (cuenta de solo lectura que vence), filtra el historial por categoría (`modificacion`, `supresion`…), verifica la integridad y descarga un ZIP con los lotes completos, el manifiesto de hashes y `verificar_exportacion.py`, que corre con la librería estándar de Python. Cada consulta y exportación queda en el propio log.

### 5.15 Borradores de cumplimiento (HU-16)

El usuario definitivo (con contrato vigente) genera desde `/empresa/borradores` una **Política de uso de LLM**, un **Aviso de privacidad** o una **Evaluación de impacto (PIA/EIPD)**. Cada plantilla (`application/borradores/plantillas.py`) es una lista de cláusulas atadas a una dimensión del modelo de madurez y a los controles de la matriz que ayudan a cerrar. El backend arma el Markdown con la evaluación más reciente de la empresa: las cláusulas que tratan una brecha abierta llevan una *medida prioritaria*, cada una cierra con su fundamento real (framework y artículo de `matriz_controles`) y el documento termina con el Anexo A (alineación por dimensión) y el Anexo B (plan de implementación). La razón social y el RUT los escribe el backend; el LLM nunca los ve.

Si se pide, la skill `borrador` del agente adapta hasta 6 cláusulas al rubro, a las brechas y a las indicaciones de la empresa. Las indicaciones pasan por la guardia (un ataque bloquea sin llamar al NER ni al LLM) y por el NER del gateway; la salida se ancla a la plantilla (`borradores/salida_ia.py`: sin cláusulas inventadas ni fijas, sin artículos no verificados, sin código, enlaces ni códigos internos) y una fuga del system prompt descarta todo lo del modelo. Si la IA no está habilitada, falla o se agotó `BORRADORES_IA_DIA_EMPRESA`, el borrador se arma igual con la plantilla y se avisa.

El borrador queda **en revisión** (`borrador_documento`, contenido cifrado): se edita con control de versión, se descarga en Markdown o en PDF con marca de agua y, al **consolidarlo** (si quedan campos `[COMPLETAR: …]` hay que confirmarlo), pasa a solo lectura y su PDF final se guarda en **Mis documentos** (HU-29). Todo queda en el audit log sin el texto del borrador ni de las indicaciones.

### 5.16 Matriz normativa editable con versionado (HU-24)

El administrador mantiene la matriz desde `/admin/matriz` sin tocar código. Trabaja sobre un **borrador** (copia completa de la versión vigente): agrega, modifica, retira o restaura controles, brechas, rutas formativas y preguntas del filtro, y fija las reglas del árbol de cada control (aplica siempre o se suma con ciertas preguntas). Al **publicar** con una etiqueta (`2026.2`) y una nota, las tablas del catálogo quedan iguales al borrador en una sola transacción, la versión anterior pasa a `reemplazada` y su contenido ya no cambia (trigger en PostgreSQL).

Cada versión se guarda completa en `matriz_version` (JSON + huella SHA-256). Retirar no borra: deja `activo=false`, porque las evaluaciones anteriores siguen referenciando ese elemento; el código de un elemento publicado no se cambia. `POST /completar` guarda en `evaluacion.matriz_version_id` la versión con que se respondió, y el informe, el plan formativo, los borradores y el recálculo por remediación de una evaluación cerrada leen **esa** versión. Las evaluaciones en curso pasan a la nueva al publicar. Cada creación, edición, descarte, publicación e intento rechazado queda en el `audit_log` (acciones `matriz.*`). Detalle en `Extras/Cambios/backend/CAMBIOS_HU24.md`.

### 5.17 Mapa de datos personales (HU-34)

El usuario definitivo (con contrato vigente) registra en `/empresa/mapa-datos` **dónde trata datos personales su empresa**: sistemas, bases de datos y terceros (nombre, categoría, proveedor, país de alojamiento ISO 3166 y responsable interno como cargo o área) y los **flujos** entre ellos. Cada elemento y flujo lleva categorías de datos y de titulares de `app/domain/catalogo_tratamiento.py`, el **catálogo común con el RAT y el RoPA** (mismos códigos; las sensibles siguen la Ley 21.719 y los titulares marcan a niños, niñas y adolescentes). Las **transferencias internacionales no se declaran: se calculan** con el país de cada extremo.

El backend (`app/domain/mapa_datos/`) calcula el resumen, la completitud y **10 reglas de hallazgos de riesgo** priorizados (transferencias sin garantía, proveedor de IA con datos sensibles, terceros sin contrato, sensibles sin cifrar, NNA, sin responsable, sin país…), con recomendación y referencia. El panel dibuja un **mapa navegable** (disposición por capas con puntos de paso, zoom, arrastre, teclado) con filtros por dato sensible, NNA, transferencia, tercero, país y tipo, y lo exporta a **PDF** (A4 horizontal, generado por el servidor con diagrama, inventario, transferencias, riesgos y base para el RAT), **PNG**, **CSV** y por **correo**.

Se inicia desde una **plantilla por rubro** (8, más una base común) o desde las **respuestas de la evaluación** (F2–F7: si declaró usar un LLM externo se sugiere el flujo hacia ese proveedor). Todo lo agregado así queda «por confirmar». **Cada cambio crea una versión** (`mapa_datos_version`: instantánea completa + huella SHA-256 + diferencias; un trigger impide modificarla) y queda en el `audit_log` en la misma transacción; las versiones se pueden ver y restaurar. Toda edición envía la versión que vio el usuario (409 si cambió). Detalle en `Extras/Cambios/backend/CAMBIOS_HU34.md` y `Extras/Cambios/frontend/CAMBIOS_HU34.md`.

### 5.18 Registro de actividades de tratamiento (HU-35)

El usuario definitivo (con contrato vigente) lleva en `/empresa/registro-actividades` el **registro de actividades de tratamiento** de su empresa. Cada actividad cubre los **11 campos mínimos del reglamento** (tipos de datos con los sensibles, ámbito territorial, bases de datos, categorías de titulares, finalidades, fuentes y si son de acceso público, base de licitud e interés legítimo, terceros destinatarios, transferencias internacionales y garantías, plazos de conservación por categoría, decisiones automatizadas o perfilamiento con su lógica) más **medidas de seguridad** y **rol de la empresa** (responsable o encargado), en un formulario de 6 pasos.

**Sin doble ingreso:** sistemas, bases, terceros y flujos se eligen del mapa de datos (con el subconjunto de categorías que usa la actividad); tipos de datos, titulares, países, terceros y transferencias **se calculan** con el mapa actual (`app/domain/rat/analisis.py`). Cuando el mapa cambia algo que una actividad usa, en la **misma transacción** la actividad vigente vuelve a «en revisión» con el motivo (y el mapa avisa cuántas actividades afectó).

**Completitud** por actividad (13 campos, con condicionales: interés legítimo, base para sensibles, garantías, lógica de decisiones, organización mandante) y global (promedio de las activas). **Estados** borrador → en revisión → vigente → archivada: aprueba el mismo usuario; no queda vigente con datos obligatorios vacíos (422 `ACTIVIDAD_INCOMPLETA`); al quedar vigente se guarda una **versión inmutable** (`rat_actividad_version`, instantánea + huella SHA-256; un trigger impide `UPDATE`/`DELETE`). Editar una vigente abre una nueva versión en borrador y la vigente sigue valiendo; aprobar sin cambios no crea otra versión; una archivada se reactiva sin duplicarla. Cada cambio queda en el `audit_log` (`rat.*`). Los textos de ayuda y el catálogo de bases de licitud (`app/domain/rat/catalogo.py`) son una **propuesta pendiente de validación por asesoría legal**. Detalle en `Extras/Cambios/backend/CAMBIOS_HU35.md`.

### 5.19 Informe del registro de actividades (HU-36)

Desde `/empresa/registro-actividades` › **Informe del registro**, el usuario definitivo (contrato vigente) ve una vista previa (si saldrá **oficial** o **borrador** y por qué, las cifras del resumen y la matriz de riesgos) y descarga el informe en **PDF** o **Excel**, lo envía por correo, revisa el historial de emisiones y **verifica un código**.

- **Armado** (`app/application/rat/informe.py`, lógica pura): entra la **instantánea inmutable** de la versión vigente de cada actividad no archivada (aunque esté en revisión o tenga una nueva versión en preparación); las que nunca estuvieron vigentes entran con su contenido actual, marcadas. Huella SHA-256 de lo que afirma el registro (no de la fecha). Textos legibles de los 13 campos compartidos por el PDF y el Excel.
- **PDF** (`app/application/rat/pdf_rat.py`) con el motor común `app/application/informes/motor_pdf.py` (paleta, ficha de identificación, aviso legal, pie con «Página X de Y» y marca de agua): portada, resumen ejecutivo, índice, detalle por actividad con plazos por categoría, matriz de riesgos (mapa de calor 5 × 5, factores y tratamientos) y verificación.
- **Excel** (`app/application/rat/xlsx_rat.py`, openpyxl): Portada, Resumen, Actividades (el RAT), Datos y plazos, Destinatarios, Transferencias, Decisiones, Matriz de riesgos y Verificación. Ningún texto se escribe como fórmula.
- **Matriz de riesgos** (`app/domain/rat/riesgos.py`): riesgo inherente = probabilidad × impacto (1–5 cada uno) calculado con lo registrado (sensibles, NNA, decisiones automatizadas, transferencias sin garantía, terceros sin contrato, medidas, información incompleta). Pesos en un solo archivo para que HU-38 los ajuste.
- **Emisión** (`rat_informe`): versión del RAT correlativa por empresa (sube cuando cambia la huella), código verificable con dígito módulo 11, ambos archivos con el mismo código en **Mis documentos** (`documento_empresa` tipos `rat_pdf` y `rat_xlsx`). Si el registro no cambió, se reutiliza la última emisión. Un trigger impide modificar o borrar una emisión. Límites: `RAT_INFORMES_DIA_EMPRESA` (20) y `RAT_CORREOS_DIA_EMPRESA` (5).
- **Borrador** (criterio 4): si alguna actividad incluida no está vigente, marca de agua «BORRADOR» en todas las páginas, aviso en el encabezado de cada página y recuadro con los motivos en la portada (también en el Excel).
- **Auditoría**: `rat.informe_generado`, `rat.informe_descargado`, `rat.informe_enviado`, `rat.informe_verificado` (sin textos del registro ni correos).


### 5.20 Informe RoPA (HU-37)

Desde `/empresa/registro-actividades` › **Informe RoPA**, el usuario definitivo (contrato vigente) genera el registro en formato RoPA sin volver a ingresar las actividades. Todo está en una ventana con scroll; las explicaciones van en el ícono ⓘ junto al título.

- **Traducción** (`app/application/ropa/informe.py`, lógica pura): parte del armado del informe del registro y toma **solo las actividades con versión vigente** (las demás se cuentan y no entran). Cada campo se traduce a los del RoPA (estructura del art. 30 usada como estándar de formato; los documentos no citan RGPD ni la UE): responsable y delegado, finalidades, categorías de titulares y de datos, destinatarios, transferencias internacionales, plazos de supresión y medidas de seguridad. Como encargado: organización por cuenta de la cual se actúa (agrupado), categorías de tratamientos, transferencias y medidas.
- **Datos que faltan** (`app/domain/ropa/datos.py`): dirección y correo de la empresa (teléfono opcional), delegado de protección de datos (sí/no; cargo o área y correo) y dirección y correo de cada organización mandante. Se guardan en `ropa_datos` **cifrados en reposo** (`TextoCifradoRopa`, subclave `ropa`) y vuelven prellenados. Sin ellos no se emite (422 `ROPA_DATOS_INCOMPLETOS`).
- **PDF** (`app/application/ropa/pdf_ropa.py`) y **Excel** (`app/application/ropa/xlsx_ropa.py`): portada (empresa, código, versión, fecha, partes), organización, una sección/hoja por parte, transferencias y aviso legal. Se puede generar solo una parte.
- **Emisión** (`ropa_informe`): versión correlativa por empresa (sube cuando cambia la huella: versiones vigentes, partes y datos de contacto), ambos archivos en **Mis documentos** (`documento_empresa` tipos `ropa_pdf` y `ropa_xlsx`, pestaña Registro de actividades). Si nada cambió, se reutiliza la última. Un trigger impide modificar o borrar una emisión. Límite diario: `RAT_INFORMES_DIA_EMPRESA`.
- **Auditoría**: `ropa.datos_actualizados` (solo nombres de campos), `ropa.informe_generado`, `ropa.informe_descargado`. Nunca direcciones ni correos.

**Mapa de datos (mejoras de usabilidad):** el diagrama va primero y los indicadores debajo; una **guía** compacta indica el siguiente paso; al elegir un recuadro o una flecha se abre su **ficha en una ventana centrada** (con lo que falta completar, conexiones navegables y riesgos); agregar un elemento o un flujo son **asistentes por pasos** con explicaciones, vista previa del recorrido y los riesgos que se detectarán; el inventario tiene vistas por tipo, estado de cada registro y tarjetas en el teléfono. Las ventanas se ajustan al contenido (sin espacio vacío).

### 5.21 Privacidad de la plataforma (HU-41)

El administrador de Therion Labs genera el registro de tratamiento de la **propia** plataforma y lo demuestra con las mismas herramientas que se venden (Panel interno › **Privacidad de la plataforma**).

- **Fuente única** (`app/core/catalogo_datos_personales.py`, sección HU-41): `ACTIVIDADES_PLATAFORMA` (encuesta pública, contratación, cuentas, tutor, evidencias, borradores, ARCOP, auditoría y herramientas de registro de las empresas), `TABLAS_SIN_TRATAMIENTO` (catálogos y agregados), `ELEMENTOS_PLATAFORMA`, `PROVEEDORES_PLATAFORMA` y `AJUSTE_POR_CONSERVACION` (cada conservación enlazada al ajuste que la ejecuta). Las categorías de datos y los plazos salen de las columnas personales de cada tabla.
- **Generador** (`app/application/plataforma/registro.py`, lógica pura): arma `Elemento`, `Flujo`, contenido de actividad e instantánea con el mismo formato del cliente y usa `rat/analisis.py`, `rat/informe.py`, `pdf_rat`, `xlsx_rat`, `pdf_ropa`, `xlsx_ropa` y `pdf_mapa` sin cambiarlos. El plazo de cada categoría es el **valor vigente** del ajuste (el de titulares, el del panel de retención si se fijó allí); sin valor, queda sin número y se informa.
- **Proveedores**: Microsoft Azure (alojamiento), Groq (con `LLM_PROVIDER=groq`), proveedor de correo (con `CORREO_MODO=smtp`) y Cloudflare Turnstile (con `TURNSTILE_SECRET_KEY`), como encargados con país y garantía. Los flujos desde la plataforma (operada desde Chile) hacia el alojamiento y los proveedores se calculan como transferencias internacionales. Ajustes nuevos: `THERION_RAZON_SOCIAL`, `THERION_RUT`, `PLATAFORMA_PAIS_ALOJAMIENTO`, `CORREO_PROVEEDOR_NOMBRE/PAIS/GARANTIA`, `PROVEEDORES_CONTRATO_CONFIRMADO`, `PLATAFORMA_INFORMES_DIA`.
- **Revisión interna** (`app/application/plataforma/revision.py`): cobertura del inventario, reglas de retención desactivadas, plazos pendientes de decisión (registro de auditoría, sesiones, contrataciones descartadas), actividades incompletas, proveedores sin país o garantía, contratos por confirmar, última ejecución de la retención y capa de IA.
- **Informes**: el RAT es **oficial** solo si todas las actividades están completas; si no, sale como borrador con los motivos exactos. El RoPA (Therion Labs como responsable) pide una vez los datos de contacto (cifrados en `plataforma_registro`). Cada emisión queda en `plataforma_informe` (archivos cifrados en `STORAGE_DIR`, inmutable en PostgreSQL) y en el audit log (`plataforma.*`, sin datos de contacto).
- **Prueba de cobertura** (`tests/test_hu41_registro_plataforma.py`): falla si una tabla nueva no está en una actividad ni en `TABLAS_SIN_TRATAMIENTO`, si una conservación nombra un ajuste sin enlazarlo o si los plazos generados difieren de los ajustes configurados.

### 5.22 Registro conectado con el cumplimiento (HU-38)

El registro de actividades deja de ser un documento aislado: alimenta la evaluación, las brechas y los borradores.

- **Riesgo explicable** (`app/domain/rat/riesgos.py`): probabilidad × impacto (1–5) con factores que dicen por qué y qué hacer. Nuevos: **uso de inteligencia artificial** (sistemas con IA, bases vectoriales o proveedores de IA del mapa; se calcula con el mapa actual, también para las versiones vigentes) y **gran volumen de personas** (dato opcional `volumen` de la actividad, paso 2; solo se guarda si tiene valor, así las versiones y huellas anteriores no cambian). Cada actividad trae su `riesgo` en `/api/registro-actividades`.
- **Matriz de mayor riesgo y evaluación de impacto**: `matriz_mayor_riesgo()` (Decreto 662, art. 3 letra e) y `motivos_pia()`: se recomienda con riesgo alto o crítico, decisiones automatizadas o perfilamiento, datos sensibles o de NNA a gran escala (10.000 personas o más) o IA con esos datos. El PDF y el Excel del informe del registro la incluyen.
- **Borradores** (`app/application/borradores/registro.py`): la **PIA** toma las actividades con evaluación recomendada (o las que elija la empresa, máximo 10: `POST /api/borradores {tipo: "pia", actividades}`) y completa identificación, motivos, descripción sistemática, base de licitud, riesgos del registro y medidas sugeridas; el **aviso de privacidad** toma finalidades y bases (tabla), datos, proveedores, transferencias, sensibles/NNA, IA y plazos, sin nombrar sistemas internos. Se usa la versión vigente de cada actividad; esas cláusulas no las reescribe el Agente IA y el LLM no las ve.
- **El registro como evidencia** (`app/domain/rat/cumplimiento.py`, `app/application/use_cases/cumplimiento_rat.py`): con el registro **vigente y completo** (todas las actividades vigentes, completas, sin cambios del mapa por revisar y sin envíos del mapa fuera del registro) se mejoran, en la evaluación completada más reciente, los controles que respalda (registro actualizado, base de licitud, finalidades —parcial—, transferencias, contratos con encargados, medidas reforzadas —parcial—). Igual que una remediación: fila en `evidencias` (origen `rat`, sin archivo), brecha sincronizada, resumen y radar recalculados control por control (aparece en la evolución del puntaje) y `rat.evidencia_aplicada` en el audit log. **Nunca baja** un control ni toca un "no aplica". Se aplica al dejar vigente una actividad y con el botón de Mi empresa.
- **Mi empresa**: tarjetas del mapa, del registro, de las actividades de mayor riesgo y de la evaluación; lo que el registro respalda; la matriz de mayor riesgo con acceso a la PIA; y las **brechas del registro** (actividad sin base de licitud, sin plazo, transferencia sin garantía, envío sin actividad) con su ruta: corregir (abre la actividad en su paso), el módulo formativo del plan con su avance y re-evaluar el control.
- Sin tablas nuevas ni migración: `evidencias.origen` admite `rat` y `respuestas.fuente_clasificacion` admite `rat`.

**Asistente de registro (corrección 13-11):** el asistente ya no se cuelga tras varias preguntas. La sesión no queda bloqueada mientras trabaja la IA (se bloquea solo al guardar), hay **una respuesta a la vez** por entrevista (409 `RESPUESTA_EN_PROCESO`; 409 `PREGUNTA_YA_RESPONDIDA` si otra pestaña avanzó), la ayuda automática tiene un **tiempo total** (`ASISTENTE_TIEMPO_MAXIMO_S`, 70 s, menor que los 90 s del BFF; al superarlo responde 503 `AYUDA_NO_DISPONIBLE` con `tipo_error: timeout` y devuelve la cuota) y el prompt **no crece** con cada pregunta: el modelo ve solo las `ASISTENTE_PENDIENTES_EN_PROMPT` (15) propuestas pendientes más recientes. `ASISTENTE_MAX_TOKENS_SALIDA` baja a 4000 y `ASISTENTE_TIMEOUT_S` (por intento) a 45. La pantalla explica la espera con el tiempo que lleva.

### 5.23 Revisión interna del registro (HU-40)

El usuario definitivo, en su función de **auditoría interna**, verifica que el registro sea fiel y esté al día antes de presentarlo, certificarlo o informarlo al directorio. No hay roles ni cuentas nuevas: es el mismo usuario con contrato vigente.

- **Lista de verificación** (`app/domain/rat/revision.py`, lógica pura). Se revisa lo que afirmaría el informe (la versión vigente de cada actividad) y el mapa actual:
  - *Actividades*: versión vigente y al día · campos obligatorios completos (ambos **bloqueantes**) · base de licitud (interés legítimo ponderado, base para sensibles) · plazos por categoría (con fundamento) · transferencias con garantía válida · terceros encargados con contrato · revisión humana de decisiones automatizadas.
  - *Elementos*: ficha completa · confirmado (no una propuesta) · considerado en alguna actividad · contrato (terceros encargados). *Flujos*: ficha completa · confirmado · garantía si sale de Chile · cifrado · considerado en el registro.
  - Cada punto trae el **resultado automático** (cumple, advertencia, falla, no aplica) y la **pregunta** que la persona confirma mirando la realidad. La persona lo marca *verificado*, lo *acepta con justificación* (fallas no bloqueantes y advertencias, mínimo 10 caracteres) o lo deja pendiente. Cada elemento guarda su **huella**: si cambia después de verificarlo, la verificación queda *desactualizada* sola.
- **Observaciones** (`rat_observacion`): por actividad, elemento, flujo o el registro completo, con prioridad. Se cierran con una nota de qué se corrigió; se registra si el elemento cambió entre la apertura y el cierre. **Con alguna abierta no se puede marcar la versión** (409 `REVISION_INCOMPLETA`). No se borran (trigger).
- **Marca de revisada** (`POST /marcar`): exige lista completa, sin bloqueos, sin observaciones abiertas y la misma huella que vio la persona. Fija versión del RAT, huella, fecha, nombre y cargo, conclusión y una copia de la lista (`rat_revision`, inmutable en PostgreSQL). Luego emite el informe del registro, que imprime «Revisada el … por …» en la portada y en la verificación (`rat_informe.revision_id`; el informe se reemite si la marca es nueva aunque el registro no cambie). Queda `revision_rat.version_revisada` en el audit log.
- **Diferencias** (`GET /diferencias`): entre dos versiones del registro o hasta el registro actual (actividades nuevas, quitadas y campo por campo antes/después, desde las versiones inmutables).
- **Informe de la revisión** (`app/application/rat/pdf_revision.py`): portada con cifras, conclusión, declaración con espacio para firma y alcance; resultado por criterio, detalle por actividad, mapa, puntos aceptados con su justificación, observaciones, cambios desde la revisión anterior y verificación. En curso lleva la marca de agua «EN CURSO».
- **Paquete de evidencia** (`app/application/rat/paquete_revision.py`), como el ZIP del Auditor Externo: informe del registro (PDF y Excel), informe de la revisión, lista de verificación y observaciones (CSV y JSON), versiones de las actividades con su huella, historial del audit log (con el hash de cada registro, sin IP), emisiones, diferencias, `manifiesto.json` (SHA-256 de cada archivo) y `verificar_paquete.py` (solo librería estándar: recalcula hashes y la huella del registro). ZIP determinista; su SHA-256 y el código `CIA-PAQ-AAAA-NNNNNN-D` quedan en `rat_paquete_evidencia` para verificar un ZIP subido (`POST /paquetes/verificacion`).
- **Correo**: el informe de la revisión y, opcionalmente, el paquete (hasta `REVISION_RAT_PAQUETE_CORREO_MB`).
- **Revisión periódica** (`rat_revision_config`): plazo de 1 a 36 meses (12 por defecto), aviso previo y recordatorio por correo. Estados: al día, por vencer, vencida, sin revisión (se cuenta desde la primera actividad vigente). Aviso en la lista del registro y en la página; el worker envía un correo por etapa a las `REVISION_RAT_HORA_UTC` (y lo repite cada `REVISION_RAT_REPETIR_DIAS` si sigue vencida), como acción del sistema en el audit log.
- **Auditoría**: `revision_rat.*` (iniciada, verificación, observación creada/cerrada/reabierta, version_revisada, marca_rechazada, paquete exportado/verificado, constancia descargada, enviada, configuración, recordatorio). Solo ids, claves, criterios, conteos y prefijos de huella: nunca el texto de las observaciones ni el nombre de quien revisa.
- **Ajustes**: `REVISION_RAT_PLAZO_MESES`, `REVISION_RAT_AVISO_DIAS`, `REVISION_RAT_REPETIR_DIAS`, `REVISION_RAT_HORA_UTC`, `REVISION_RAT_PAQUETES_DIA`, `REVISION_RAT_CORREOS_DIA`, `REVISION_RAT_PAQUETE_CORREO_MB`, `REVISION_RAT_PAQUETE_VERIFICAR_MB`, `REVISION_RAT_URL`. Migración `b3e9d5a1c7f4`.

---

## 6. Base de datos

PostgreSQL 16, **19 tablas** + `alembic_version`, **27 claves foráneas**. Los nombres de algunas columnas FK están en mayúscula inicial (`"Rubro_id"`, `"Evaluacion_id"`…): en `psql` hay que escribirlas entre comillas dobles.

### 6.1 Tablas por capa

**Catálogos (datos maestros, sembrados por migración)**

| Tabla | Filas | Descripción |
|---|---|---|
| `dominio` | 4 | Dominios temáticos |
| `rubro` | 8 | Sectores económicos |
| `ruta_formativa` | 12 | 4 dominios × 3 niveles. HU-12: dimensión, nivel, objetivo, objetivos específicos, contenidos, horas, modalidad y público objetivo |
| `catalogo_brechas` | 40 | Brechas `ERR-XXX-NNN`: comportamiento detectado, criticidad, acción del sistema y ruta formativa |
| `matriz_controles` | 40 | Controles `DAT/GOB/RIE/SEG-NNN`: marco, artículo, obligación, pregunta, evidencia esperada, criticidad, recomendación, test asociado, dominio y brecha |
| `preguntas_filtro` | 7 | Preguntas de compuerta F1–F7 |

**Operacionales**

| Tabla | Descripción |
|---|---|
| `usuario_temporal` | Invitado por link, con expiración, rubro y `fecha_anonimizacion` |
| `evaluacion` | Sesión de diagnóstico: estado, `filtro_completado`, fechas |
| `respuestas_filtro` | Respuesta SI/NO a cada pregunta de compuerta (única por evaluación y pregunta) |
| `respuestas` | Respuesta a un control (única por evaluación y control): clasificación declarada, justificación, clasificación final, fuente (`usuario`/`llm`/`seguridad`/`revision`), confianza, brecha, revisión humana |
| `evidencias` | Archivo de respaldo: ruta, MIME, hash, estado de validación, resultado del LLM |

**Analíticas**

| Tabla | Descripción |
|---|---|
| `resumen` | Puntaje y nivel por evaluación × dominio |
| `benchmark` | Promedio, mediana, máximo, mínimo y cantidad por rubro × dominio |

**Capa de IA y seguridad (auditoría)**

| Tabla | Descripción |
|---|---|
| `llamadas_llm` | Una fila por ejecución de la capa de IA: tarea, proveedor, modelo, versión de prompt, éxito/tipo de error, tokens, costo, latencia, entidades anonimizadas, clasificación y confianza. **Nunca guarda texto del usuario** |
| `sanitizaciones` | Mapa de entidades por texto: metadatos sin PII (`entidades` con huella HMAC) y conteos. `mapa_cifrado` queda en NULL (HU-06: irreversible; solo se llena con `GUARDAR_MAPA_ENTIDADES_CIFRADO=true`). **Nunca se envía al LLM** |
| `eventos_seguridad` | Intentos de prompt injection: origen (justificación/evidencia), extracto anonimizado, hash, revisado |

**Derechos ARCOP y administración**

| Tabla | Descripción |
|---|---|
| `solicitudes_arcop` | Solicitud del titular: tipo, estado, descripción, plazos, respuesta, fechas |
| `eventos_solicitud_arcop` | Historial: tipo de evento, estado anterior/nuevo, rol e id del actor, comentario |
| `usuarios_admin` | Administradores `admin_therion`: email único, hash de contraseña, activo, último acceso |

### 6.2 Modelo entidad-relación

```mermaid
erDiagram
    rubro ||--o{ usuario_temporal : "Rubro_id"
    rubro ||--o{ benchmark : "Rubro_id"
    dominio ||--o{ matriz_controles : "dominio_id"
    dominio ||--o{ benchmark : "dominio_id"
    dominio ||--o{ resumen : "dominio_id"
    ruta_formativa ||--o{ catalogo_brechas : "ruta_formativa_id"
    catalogo_brechas ||--o{ matriz_controles : "catalogo_brechas_id_brecha"
    catalogo_brechas ||--o{ respuestas : "Catalogo_brechas_id_brecha"
    usuario_temporal ||--o{ evaluacion : "Usuario_temporal_id"
    usuario_temporal ||--o{ solicitudes_arcop : "Usuario_temporal_id"
    evaluacion ||--o{ solicitudes_arcop : "Evaluacion_id"
    evaluacion ||--o{ respuestas : "Evaluacion_id"
    evaluacion ||--o{ resumen : "Evaluacion_id"
    evaluacion ||--o{ respuestas_filtro : "Evaluacion_id"
    preguntas_filtro ||--o{ respuestas_filtro : "pregunta_id"
    matriz_controles ||--o{ respuestas : "Matriz_controles_id_control"
    respuestas ||--o{ evidencias : "Respuestas_id_respuesta"
    solicitudes_arcop ||--o{ eventos_solicitud_arcop : "Solicitudes_arcop_id_solicitud"
    evaluacion ||--o{ eventos_seguridad : "Evaluacion_id"
    matriz_controles ||--o{ eventos_seguridad : "Matriz_controles_id_control"
    respuestas ||--o{ eventos_seguridad : "Respuestas_id_respuesta"
    evidencias ||--o{ eventos_seguridad : "Evidencias_id_evidencia"
    evaluacion ||--o{ llamadas_llm : "Evaluacion_id"
    respuestas ||--o{ llamadas_llm : "Respuestas_id_respuesta"
    evidencias ||--o{ llamadas_llm : "Evidencias_id_evidencia"
    evaluacion ||--o{ sanitizaciones : "Evaluacion_id"
    respuestas ||--o{ sanitizaciones : "Respuestas_id_respuesta"
    evidencias ||--o{ sanitizaciones : "Evidencias_id_evidencia"
```

`usuarios_admin` no tiene relaciones (el actor de un evento ARCOP se guarda como `actor_rol` + `actor_id`).

### 6.3 Migraciones (Alembic)

Cadena lineal; la cabeza actual es **`a9d3e5f7c1b2`**.

| # | Revisión | Contenido |
|---|---|---|
| 1 | `84d29cadfb28` | Esquema inicial: `evaluacion`, `matriz_controles`, `respuestas`, `evidencias` |
| 2 | `20674abc0fc2` | `dominio`, `rubro`, `ruta_formativa`, `usuario_temporal`, `catalogo_brechas`, `benchmark`, `resumen` |
| 3 | `b54cdc747a36` | Amplía `matriz_controles` y `catalogo_brechas` |
| 4 | `2e398c9a9b2e` | **Seed:** dominios, rubros, rutas, 40 brechas y 40 controles |
| 5 | `24ce495af093` | `preguntas_filtro`, `respuestas_filtro`, estado del filtro en `evaluacion` |
| 6 | `2d93373ba237` | **Seed:** preguntas F1–F7 |
| 7 | `7c1e5a9d3f20` | `eventos_seguridad` |
| 8 | `a53fb924d0ac` | Ajustes en `eventos_seguridad` y `resumen` |
| 9 | `c4f2a8e1b7d3` | Capa de IA: `llamadas_llm`, `sanitizaciones`, revisión humana en `respuestas` |
| 10 | `b25cc4eed4b0` | Vacía (sin cambios) |
| 11 | `a168283ff2b8` | Clasificaciones a `VARCHAR(25)` y ajustes de columnas de IA |
| 12 | `e5a1c9d4b2f7` | `solicitudes_arcop`, `eventos_solicitud_arcop` |
| 13 | `f7b2d1a8c3e9` | `usuarios_admin`, plazos ARCOP, `usuario_temporal.fecha_anonimizacion` |
| 14 | `9a4e2c7b1f05` | HU-01: una respuesta por evaluación y control |
| 15 | `b3c8e5d2a7f1` | HU-08: código de seguimiento y plazos del encuestado |
| 16 | `d4a7c2e9b8f3` | HU-02: la brecha sigue al estado vigente (corrige filas) |
| 17 | `e2b7c9d4f8a1` | HU-19: encuesta pública (origen, clave de acceso, aviso legal, evaluaciones de prueba) |
| 18 | `a9d3e5f7c1b2` | HU-12: catálogo formativo (columnas de `ruta_formativa` y contenido de las 12 rutas) |

Alembic toma la URL de `DATABASE_URL_SYNC` (`migrations/env.py`).

### 6.4 Minimización y conservación de datos personales (T-06)

Cada columna del modelo está clasificada en `app/core/catalogo_datos_personales.py` con su categoría, tratamiento (en claro, anonimizado, cifrado, hash, HMAC o no se guarda), finalidad, base de licitud y plazo de conservación. `tests/test_t06_minimizacion.py` falla si una migración agrega una columna sin clasificarla. La auditoría sobre la BD real se corre con un rol de solo lectura y genera el DER, la matriz en CSV y un informe de controles; nunca imprime valores, solo conteos:

```powershell
docker compose cp backend/scripts/sql/t06_rol_auditor.sql db:/tmp/t06_rol_auditor.sql
docker compose exec db psql -U postgres -d complaince_db -v "clave='UNA-CLAVE'" -f /tmp/t06_rol_auditor.sql
docker compose exec worker python scripts/auditoria_minimizacion.py --url "postgresql+psycopg2://auditor_t06:UNA-CLAVE@db:5432/complaince_db" --salida /tmp/t06
docker compose cp worker:/tmp/t06 ./auditoria_t06
```

Los plazos `RETENCION_*` (vacíos por defecto) los aplica el worker cada día a las 03:00 UTC con las mismas reglas de una supresión ARCOP: se borran correos, textos, archivos y huellas, y se conservan los puntajes. Detalle en [`Extras/Cambios/backend/CAMBIOS_T06.md`](../Extras/Cambios/backend/CAMBIOS_T06.md).

---

## 7. Endpoints de la API

Base: `http://localhost:8000` (o a través del proxy del frontend en `http://localhost:3000`). Documentación interactiva en `/docs`. Columna **Auth**: 🔓 público · 🔑 cualquier token válido · 👤 titular (`referente` o `encuestado`) · 📋 dueño de la evaluación (su `encuestado` o su `referente`) o `admin_therion` · 🛡️ `admin_therion` · 🏢 `cliente` (usuario definitivo, HU-28).

**HU-20 (confidencialidad):** las rutas 📋 responden 401 sin token y **404** con el token de otra organización (no 403, para no confirmar ids correlativos). Las rutas 🛡️ responden 401 sin token y 403 con otro rol. `EXIGIR_TOKEN_EVALUACIONES=false` (solo desarrollo, prohibido en production) vuelve a abrir sin token las evaluaciones por invitación. Matriz completa por endpoint: `backend/tests/test_hu20_autorizacion.py`; detalle en `Extras/Cambios/backend/CAMBIOS_HU20.md`.

### Sistema

| Método | Ruta | Auth | Descripción |
|---|---|---|---|
| GET | `/health` | 🔓 | Health check (`{"status":"ok"}`) |
| GET | `/docs` | 🔓 | Swagger UI (botón *Authorize* para el token) |

### Autenticación — `/api/auth`

| Método | Ruta | Auth | Body / Respuesta |
|---|---|---|---|
| POST | `/api/auth/login` | 🔓 | `{email, password}` → token de admin |
| POST | `/api/auth/titular` | 🔓 | `{usuario_temporal_id, email}` → token de referente |
| POST | `/api/auth/encuestado` | 🔓 | `{evaluacion_id, clave}` → token de encuestado |
| POST | `/api/auth/encuestado/clave` | 🛡️ | `{evaluacion_id}` → 201 `{clave}` (se muestra una vez; invalida la anterior) |
| GET | `/api/auth/me` | 🔑 | `{usuario_id, rol}` |
| POST | `/api/auth/cliente` | 🔓 | HU-27: `{email, password}` → token del rol `cliente`. HU-30: entra también sin contrato vigente; la respuesta trae `contrato` con su situación |
| POST | `/api/auth/auditor` | 🔓 | HU-09: `{email, password}` → token del rol `auditor_externo` (solo lectura del audit_log; la sesión no dura más que la cuenta) |
| POST | `/api/auth/activacion/verificar` | 🔓 | HU-27: `{token}` → ¿el enlace sigue válido? (no lo consume) |
| POST | `/api/auth/activacion` | 🔓 | HU-27: `{token, password}` → define la contraseña; el enlace queda usado (400 `ENLACE_INVALIDO`, 410 `ENLACE_VENCIDO`, 422 `CONTRASENA_DEBIL`) |
| POST | `/api/auth/logout` | 🔑 | HU-28: 204; cierra la sesión del token (admin o cliente): desde ese momento el token responde 401 |
| POST | `/api/auth/recuperacion` | 🔓 | HU-28: `{tipo: cliente\|admin, email}` → SIEMPRE 202 con el mismo mensaje; si la cuenta está activa, envía el enlace (en segundo plano) |
| POST | `/api/auth/recuperacion/verificar` | 🔓 | HU-28: `{token}` → `{tipo, email (enmascarado), password_min}` sin consumir el enlace |
| POST | `/api/auth/recuperacion/restablecer` | 🔓 | HU-28: `{token, password}` → contraseña nueva; enlace usado, todas las sesiones de la cuenta cerradas y aviso por correo (400, 410, 422 como la activación) |

### Catálogos y controles

| Método | Ruta | Auth | Descripción |
|---|---|---|---|
| GET | `/api/dominios` | 🔓 | 4 dominios |
| GET | `/api/rubros` | 🔓 | 8 rubros |
| GET | `/api/rutas-formativas` | 🔓 | 12 rutas |
| GET | `/api/brechas` | 🔓 | 40 brechas con su ruta anidada (corregido: antes `ruta_formativa` venía siempre `null`) |
| GET | `/api/controles?dominio_id=&criticidad=` | 🔓 | 40 controles con dominio y brecha anidados (filtros opcionales; `criticidad` = `Alta`/`Media`/`Baja`) |
| GET | `/api/controles/{id}` | 🔓 | Detalle de un control |

### Evaluaciones, filtro y reportes — `/api/evaluaciones`

| Método | Ruta | Auth | Descripción |
|---|---|---|---|
| GET | `/api/evaluaciones?page=&size=&estado_progreso=` | 🔑 | Lista paginada: el admin ve todas; el encuestado solo la suya y el referente solo las de su invitación |
| GET | `/api/evaluaciones/{id}` | 📋 | Detalle |
| GET | `/api/evaluaciones/{id}/respuestas?page=&size=&estado_final=&fuente=` | 📋 | Respuestas paginadas (filtra por clasificación final o fuente) |
| GET | `/api/evaluaciones/{id}/filtro` | 📋 | Preguntas F1–F7, respuestas guardadas y cantidad de controles aplicables |
| POST | `/api/evaluaciones/{id}/filtro` | 📋 | `{"respuestas":[{"codigo":"F1","respuesta":true}, …]}` (las 7) → controles aplicables |
| GET | `/api/evaluaciones/{id}/controles-aplicables` | 📋 | Controles que aplican (400 si el filtro no está completo). El catálogo sale de una caché en memoria (TTL 5 min) |
| GET | `/api/evaluaciones/{id}/progreso` | 📋 | Progreso del cuestionario para reanudar: `etapa` (`filtro`/`cuestionario`/`completo`/`cerrada`), respondidos / aplicables, `por_dimension`, `siguiente_control`, `pendientes`, `respondidos` |
| POST | `/api/evaluaciones/{id}/cerrar` | 📋 | Genera resumen por dominio, puntaje y nivel general (vista previa: **no** cierra la evaluación, se puede repetir) |
| POST | `/api/evaluaciones/{id}/completar` | 📋 | **Cierre definitivo:** exige filtro completo, todos los controles aplicables respondidos y ninguna evidencia en validación; genera el resumen y marca `estado_progreso = completada` (entra al benchmark). 409 `CUESTIONARIO_INCOMPLETO`, `EVIDENCIAS_EN_PROCESO`, `REVISION_SIN_EVIDENCIA` (control en `requiere_revision` sin evidencia), `FILTRO_PENDIENTE` o `EVALUACION_CERRADA`; 404 si no existe |
| GET | `/api/evaluaciones/{id}/resumen` | 📋 | Resumen guardado (404 si no se ha cerrado) |
| GET | `/api/evaluaciones/{id}/comparativa` | 📋 | Resumen vs. **meta de cumplimiento** (siempre) y sector del rubro con k-anonimato (HU-10, solo con ≥ `K_ANONIMATO_MINIMO` empresas); trae `meta_puntaje`, `diferencia_vs_meta`, `cumple_meta`, `sector` (general, `posicion`, `advertencia`) y por dimensión `cohorte_suficiente`, `promedio_industria`, `posicion` |
| GET | `/api/evaluaciones/{id}/plan-formativo` | 📋 | HU-12: plan de estudio por dimensión (nivel asignado, objetivo, módulos y brechas que cubren); 404 `SIN_RESULTADOS` si no hay resumen |
| GET | `/api/evaluaciones/{id}/informe/pdf?severidad=&dominio=&estado=&q=` | 📋 | Informe en PDF para descargar. HU-21: portada con código de evaluación, fechas, versión de la matriz, aviso legal (también en el pie de cada página) y los 5 puntajes; luego comparativa, brechas, plan formativo y huella de verificación |
| GET | `/api/evaluaciones/{id}/informe/ficha` | 📋 | HU-21: la portada del PDF en JSON (código `CIA-AAAA-NNNNNN-D`, `version_matriz`, aviso legal, 5 puntajes, resumen de brechas y rutas, `huella`); 404 `SIN_RESULTADOS` |
| POST | `/api/evaluaciones/{id}/informe/enviar` | 📋 | `{email?, recordar?, severidad?, …}` → envía el mismo PDF por correo; 422 `EMAIL_REQUERIDO`/`EMAIL_INVALIDO`, 429 `LIMITE_CORREOS`, 502 `CORREO_FALLIDO`, 503 `CORREO_NO_DISPONIBLE` |
| GET | `/api/evaluaciones/benchmark?rubro_id=` | 🔑 | HU-10: promedios por rubro × dominio y general del rubro (`dominio_id` null), con supresión k < 5; sin máximo ni mínimo |
| PATCH | `/api/evaluaciones/{id}/prueba` | 🛡️ | `{es_prueba}` — excluye/incluye la evaluación del benchmark (HU-19) |

Paginación: `page` ≥ 1, `size` 1–100; respuesta `{items, total, page, size, pages}`.

### Respuestas y evidencias

| Método | Ruta | Auth | Descripción |
|---|---|---|---|
| POST | `/api/respuestas/` | 📋 | `{evaluacion_id, matriz_control_id, estado_clasificacion, justificacion}` (1 de 5 estados) → **upsert**: 201 si crea, 200 si el control ya estaba respondido; cuerpo `{id_respuesta, creada, actualizada}`. 400 estado inválido, 404 evaluación/control inexistente, 409 evaluación cerrada o filtro pendiente, 422 `JUSTIFICACION_OBLIGATORIA`, `CONTROL_NO_APLICABLE` o `PROMPT_INJECTION` |
| PUT | `/api/respuestas/{id}` | 📋 | `{estado_clasificacion, justificacion}` — modifica una respuesta existente (mismas validaciones) |
| GET | `/api/respuestas/{id}` | 📋 | Respuesta con clasificación final, fuente, confianza y evidencias |
| PATCH | `/api/respuestas/{id}/revision` | 🛡️ | `{clasificacion_revisada}` — revisión humana; acepta `cumplido`, `parcialmente_cumplido`, `no_cumplido` o `no_aplica` (no `requiere_revision`). Asigna la brecha si queda `no_cumplido` y la quita en otro caso |
| POST | `/api/respuestas/{id}/evidencias` | 📋 | `multipart/form-data` campo `file` → 202 (procesamiento asíncrono); 400 si la respuesta no es `cumplido`/`parcialmente_cumplido` o el archivo está vacío; 409 `EVALUACION_CERRADA` si la evaluación está completada/cerrada |
| GET | `/api/evidencias/{id}` | 📋 | Estado de validación y resultado del LLM |

### Capa de IA y seguridad

| Método | Ruta | Auth | Descripción |
|---|---|---|---|
| GET | `/api/ia/metricas?desde=&hasta=&tarea=&modelo=` | 🛡️ | `operacion_modelo` (tasa de error global y por tipo, latencia p50/p95, tokens, costo), `precision_modelo` (LLM vs. revisión humana: accuracy, P/R/F1, matriz de confusión) y `sanitizacion` (entidades por tipo, fallos, truncados) |
| GET | `/api/seguridad/eventos?solo_pendientes=&limit=` | 🛡️ | Bandeja de intentos de prompt injection |
| PATCH | `/api/seguridad/eventos/{id}/revisado` | 🛡️ | Marca un evento como revisado |

### Derechos ARCOP — `/api/arcop`

| Método | Ruta | Auth | Descripción |
|---|---|---|---|
| GET | `/api/arcop/catalogo` | 🔓 | Tipos, estados, transiciones y plazos configurados |
| POST | `/api/arcop/solicitudes` | 👤 | `{tipo, descripcion}` → 201, estado `recibida` |
| GET | `/api/arcop/seguimiento/{codigo}` | 🔓 | Estado y plazos por código de seguimiento (sin datos personales) |
| GET | `/api/arcop/solicitudes?page=&size=&estado=&tipo=&usuario_temporal_id=&evaluacion_id=&vencidas=` | 👤 🛡️ | Titular: solo las suyas. Admin: todas, con filtros |
| GET | `/api/arcop/solicitudes/{id}` | 👤 🛡️ | Detalle e historial (404 si es de otro titular) |
| PATCH | `/api/arcop/solicitudes/{id}/estado` | 🛡️ | `{estado, comentario?}` → `en_revision` / `pendiente_informacion` / `en_proceso` |
| POST | `/api/arcop/solicitudes/{id}/prorroga` | 🛡️ | `{motivo}` → prórroga única del plazo (+30 días), antes de que venza |
| POST | `/api/arcop/solicitudes/{id}/resolucion` | 🛡️ | `{resultado: resuelta\|rechazada, respuesta}` |
| POST | `/api/arcop/solicitudes/{id}/cancelacion` | 👤 | `{motivo?}` |
| POST | `/api/arcop/solicitudes/{id}/informacion` | 👤 | `{informacion}` → vuelve a `en_revision` |
| GET | `/api/arcop/solicitudes/{id}/exportacion?formato=json\|csv` | 👤 | HU-32: descarga de los datos del titular; solo acceso/portabilidad `resuelta` (si no, 409 `EXPORTACION_NO_DISPONIBLE`) |

### Contratación (HU-31) y empresas cliente (HU-27, con la base de HU-09)

| Método | Ruta | Auth | Descripción |
|---|---|---|---|
| GET | `/api/contratacion/consentimiento` | 🔓 | HU-31: los DOS textos (provisorios) con su versión: `{contacto, migracion}` |
| POST | `/api/contratacion/solicitudes` | 👤 | HU-31 "Contratar la plataforma": `{evaluacion_id, nombre, cargo, empresa, email, telefono?, consentimiento_contacto: {version, aceptado}, consentimiento_migracion: {version, aceptado}, captcha_token}`. Mismo límite que la encuesta pública (intentos por IP, CAPTCHA y máximo diario por IP); avisa por correo a `CONTRATACION_AVISO_EMAIL` |
| GET | `/api/contratacion/evaluaciones/{id}/solicitud` | 👤 | Estado de su solicitud (`nueva`, `contactada`, `contratada`, `descartada`) |
| GET | `/api/admin/contrataciones?estado=` | 🛡️ | Bandeja: solicitudes con contacto, consentimientos, evaluación vinculada y `conteo_por_estado` |
| GET / PATCH | `/api/admin/contrataciones/{id}` | 🛡️ | Detalle / `{estado: contactada\|contratada\|descartada}` (solo `contratada` habilita la migración) |
| POST | `/api/admin/empresas` | 🛡️ | Alta en UNA transacción: empresa + usuario definitivo (rol `cliente`) + migración de las solicitudes `contratadas` + enlace de activación por correo |
| GET | `/api/admin/empresas`, `/api/admin/empresas/{id}` | 🛡️ | Empresas con su usuario y evaluaciones |
| POST | `/api/admin/empresas/{id}/evaluaciones` | 🛡️ | `{solicitudes_ids}` → asociar más evaluaciones autorizadas |
| POST | `/api/admin/empresas/{id}/usuario/activacion` | 🛡️ | Reenvía el enlace (revoca el anterior) |
| POST | `/api/admin/empresas/{id}/contrato/renovacion` | 🛡️ | HU-30: `{fecha_termino_contrato}` → nueva fecha; deja el contrato activo |
| POST | `/api/admin/empresas/{id}/contrato/suspension` | 🛡️ | HU-30: `{motivo}` → corta el servicio pagado sin terminar el contrato |
| POST | `/api/admin/empresas/{id}/contrato/reactivacion` | 🛡️ | HU-30: levanta la suspensión |
| POST | `/api/admin/empresas/{id}/contrato/terminacion` | 🛡️ | HU-30: `{motivo}` → termina el contrato y abre el plazo de gracia (`CONTRATO_GRACIA_DIAS`) |
| GET | `/api/admin/evaluaciones?estado=&origen=&empresa_id=` | 🛡️ | HU-28: todas las evaluaciones con rubro, puntaje general y empresa (si migró); sin contacto del encuestado |
| GET | `/api/admin/bitacora?entidad=&entidad_id=&accion=` | 🛡️ | audit_log (HU-09): solo inserción; cada fila con IP y categoría |
| GET | `/api/admin/bitacora/verificacion` | 🛡️ | HU-18: recalcula la cadena de hashes de la bitácora; devuelve si está íntegra, la primera falla y el último hash (ancla) |
| GET | `/api/cliente/empresa` | 🏢 | HU-28: espacio del cliente: su empresa, contrato y evaluaciones migradas (HU-30: 403 `CONTRATO_NO_VIGENTE` sin contrato vigente) |
| GET | `/api/cliente/contrato` | 🏢 | HU-30: situación del contrato, documentos que aún puede descargar y acceso a ARCOP (responde siempre) |
| GET | `/api/cliente/evaluaciones` | 🏢 | HU-29: "Mis evaluaciones": historial (migradas y reevaluaciones) con fecha, estado, puntaje global, nivel y evolución global y por dimensión; `puede_reevaluar`. Responde también sin contrato vigente |
| POST | `/api/cliente/evaluaciones` | 🏢 | HU-29: inicia una reevaluación de la empresa (origen `empresa`, sin usuario temporal) → 201 `{evaluacion_id}`; 409 `EVALUACION_EN_CURSO` (trae `evaluacion_id`); 403 `CONTRATO_NO_VIGENTE`. Se responde con las rutas de siempre del cuestionario |
| GET | `/api/cliente/documentos` | 🏢 | HU-29: "Mis documentos": informes PDF, borradores (HU-16), evidencias y constancias (con contrato vigente, suspendido o en plazo de gracia) |
| POST | `/api/cliente/documentos/informes` | 🏢 | HU-29: `{evaluacion_id}` → 201; archiva el informe PDF de una evaluación completada (409 `EVALUACION_NO_COMPLETADA`, `LIMITE_INFORMES`) |
| GET / DELETE | `/api/cliente/documentos/{id}/descarga` · `/api/cliente/documentos/{id}` | 🏢 | HU-29: descargar o eliminar un informe o borrador (204; queda en la bitácora) |
| GET / DELETE | `/api/cliente/documentos/evidencias/{id}/descarga` · `/api/cliente/documentos/evidencias/{id}` | 🏢 | HU-29: texto anonimizado de la evidencia; eliminar borra el archivo y conserva la clasificación y los puntajes (409 `EVIDENCIA_EN_PROCESO`) |
| DELETE | `/api/cliente/documentos/constancias/{ruta_id}` | 🏢 | HU-29: anula la constancia del módulo (el módulo sigue completado) |
| GET | `/api/formacion/avance?evaluacion_id=` | 🏢 | HU-26: avance de la empresa por módulo, dimensión y nivel; brechas con la formación hecha |
| GET | `/api/formacion/modulos/{ruta_id}` | 🏢 | HU-26: lecciones, material de apoyo y actividad de verificación (sin las respuestas correctas) |
| POST | `/api/formacion/modulos/{ruta_id}/lecciones/{orden}/vista` | 🏢 | HU-26: marca la lección como vista (el primer llamado inicia el módulo) |
| POST | `/api/formacion/modulos/{ruta_id}/verificacion` | 🏢 | HU-26: `{respuestas: {pregunta_id: opcion_id}}` → nota; aprobada = módulo completado con fecha y código de constancia |
| GET | `/api/formacion/modulos/{ruta_id}/constancia` | 🏢 | HU-26: constancia PDF del módulo completado |
| GET | `/api/admin/empresas/{id}/formacion` | 🛡️ | HU-26: el mismo avance para el panel interno |
| GET | `/api/remediacion/evaluaciones/{id}` | 🏢 | HU-17: controles con brecha, su formación y su última evidencia |
| POST | `/api/remediacion/respuestas/{id}/evidencias` | 🏢 | HU-17: multipart `file` (PDF/DOCX/TXT) + `estado_declarado` + `justificacion` opcional → 202; el worker re-evalúa y recalcula el puntaje |
| GET | `/api/remediacion/evidencias/{id}` | 🏢 | HU-17: resultado del análisis y puntaje recalculado |
| GET | `/api/tutor/contexto?ruta_id=` | 🏢 | HU-15: brechas que verá el tutor (evaluación vigente de la empresa), nivel sugerido y cuota |
| GET / POST | `/api/tutor/conversaciones` | 🏢 | HU-15: lista / abre una conversación `{ruta_id?, nivel?}` |
| GET / PATCH / DELETE | `/api/tutor/conversaciones/{id}` | 🏢 | HU-15: conversación con mensajes / cambia el nivel `{nivel}` / la borra |
| POST | `/api/tutor/conversaciones/{id}/mensajes` | 🏢 | HU-15: `{texto}` → respuesta estructurada del tutor (tipo, pasos, brechas citadas, referencias, sugerencias) y la cuota |
| GET | `/api/borradores/plantillas` | 🏢 | HU-16: plantillas (Política de uso de LLM, Aviso de privacidad, PIA), cuota de IA y límites |
| GET / POST | `/api/borradores` | 🏢 | HU-16: borradores de la empresa / genera uno `{tipo, instrucciones?, usar_ia?, evaluacion_id?}` (201) |
| GET / PATCH / DELETE | `/api/borradores/{id}` | 🏢 | HU-16: borrador con su Markdown / guarda la edición `{contenido, version}` (409 si la versión cambió) / lo descarta |
| GET | `/api/borradores/{id}/descarga?formato=md\|pdf` | 🏢 | HU-16: descarga previa (PDF con marca «BORRADOR») |
| POST | `/api/borradores/{id}/consolidacion` | 🏢 | HU-16: `{version, confirmar_pendientes}` → solo lectura y PDF final en Mis documentos (409 `CAMPOS_PENDIENTES` sin confirmar) |
| GET | `/api/mapa-datos/catalogo` | 🏢 | HU-34: catálogo común con el RAT (categorías de datos con sensibles, titulares con NNA, tipos, roles, garantías, países) |
| GET | `/api/mapa-datos` | 🏢 | HU-34: el mapa (elementos, flujos con transferencias calculadas, resumen, hallazgos, completitud) |
| POST / PATCH / DELETE | `/api/mapa-datos/elementos[/{id}]` | 🏢 | HU-34: sistema, base de datos o tercero `{version, …}` (DELETE con `?version=`; 409 `MAPA_DESACTUALIZADO`) |
| POST / PATCH / DELETE | `/api/mapa-datos/flujos[/{id}]` | 🏢 | HU-34: flujo entre elementos `{version, origen_id, destino_id, …}` |
| POST | `/api/mapa-datos/revision` | 🏢 | HU-34: confirma lo que vino de plantillas o sugerencias |
| GET / POST | `/api/mapa-datos/plantillas[/aplicar]` | 🏢 | HU-34: plantillas por rubro / aplica una `{codigo, version}` |
| GET / POST | `/api/mapa-datos/sugerencias[/{clave}/aceptar\|descartar, /restablecer]` | 🏢 | HU-34: propuestas desde la evaluación |
| GET / POST | `/api/mapa-datos/versiones[/{n}[/restaurar]]` | 🏢 | HU-34: historial, instantánea con diferencias y restauración |
| GET / POST | `/api/mapa-datos/informe/pdf` · `/informe/enviar` | 🏢 | HU-34: informe PDF con los filtros del mapa / el mismo PDF por correo |
| GET | `/api/registro-actividades/catalogo` | 🏢 | HU-35: bases de licitud, medidas, fuentes, plazos, estados, campos y textos de ayuda |
| GET | `/api/registro-actividades` | 🏢 | HU-35: actividades con su completitud y la completitud global |
| POST | `/api/registro-actividades/actividades` | 🏢 | HU-35: crea una actividad en borrador `{nombre, …}` (201; 409 `NOMBRE_DUPLICADO`) |
| GET / PATCH | `/api/registro-actividades/actividades/{id}` | 🏢 | HU-35: la actividad con lo que toma del mapa / edita `{revision, …}` (409 `ACTIVIDAD_DESACTUALIZADA` o `ACTIVIDAD_NO_EDITABLE`) |
| POST | `/api/registro-actividades/actividades/{id}/estado` | 🏢 | HU-35: `{revision, accion}` enviar_revision · volver_borrador · aprobar (422 `ACTIVIDAD_INCOMPLETA`) · nueva_version · archivar · reactivar |
| GET | `/api/registro-actividades/actividades/{id}/versiones[/{n}]` | 🏢 | HU-35: versiones vigentes inmutables e instantánea verificada de una |
| GET | `/api/registro-actividades/informes` | 🏢 | HU-36: vista previa del informe (oficial o borrador y por qué), última emisión e historial |
| POST | `/api/registro-actividades/informes` | 🏢 | HU-36: `{forzar?}` genera PDF y Excel con el mismo código y los guarda en Mis documentos (200 si reutiliza la última; 409 `RAT_VACIO`; 429 `LIMITE_INFORMES`) |
| GET | `/api/registro-actividades/informes/{id}/descarga?formato=pdf\|xlsx` | 🏢 | HU-36: descarga de una emisión (410 `ARCHIVO_ELIMINADO` si se borró de Mis documentos) |
| POST | `/api/registro-actividades/informes/{id}/enviar` | 🏢 | HU-36: `{email?, formatos}` por correo (429 `LIMITE_CORREOS`) |
| GET | `/api/registro-actividades/informes/verificacion?codigo=…` | 🏢 | HU-36: confirma un código verificable de la empresa y si el registro cambió desde esa emisión |
| GET | `/api/registro-actividades/cumplimiento` | 🏢 | HU-38: estado del mapa y del registro, matriz de mayor riesgo con evaluaciones de impacto recomendadas, brechas del registro con su ruta de remediación y lo que el registro aporta a la evaluación |
| POST | `/api/registro-actividades/cumplimiento/evidencia` | 🏢 | HU-38: usa el registro vigente y completo como evidencia en la evaluación más reciente (solo mejora controles; recalcula puntaje y brechas) |
| GET | `/api/registro-actividades/ropa` | 🏢 | HU-37: vista previa (como responsable / como encargado), datos guardados, lo que falta e historial |
| PATCH | `/api/registro-actividades/ropa/datos` | 🏢 | HU-37: guarda contacto de la empresa, delegado y organizaciones (solo los campos enviados; 422 `DATOS_INVALIDOS`) |
| POST | `/api/registro-actividades/ropa` | 🏢 | HU-37: `{partes?, forzar?}` genera PDF y Excel y los guarda en Mis documentos (200 si reutiliza; 409 `ROPA_SIN_ACTIVIDADES`; 422 `ROPA_DATOS_INCOMPLETOS`; 429 `LIMITE_INFORMES`) |
| GET | `/api/registro-actividades/ropa/{id}/descarga?formato=pdf\|xlsx` | 🏢 | HU-37: descarga de una emisión (410 `ARCHIVO_ELIMINADO`) |

El rol `cliente` (🏢) ve con las rutas 📋 (resumen, comparativa, plan formativo, informe PDF…) solo las evaluaciones migradas a su empresa. HU-30: sin contrato vigente las rutas 🏢 de cursos, remediación y espacio de la empresa responden 403 `CONTRATO_NO_VIGENTE`; lo gratuito y ARCOP (`/api/arcop/solicitudes`, ahora también para el cliente) siguen disponibles, y la constancia se descarga durante el plazo de gracia. Detalle en `Extras/Cambios/backend/CAMBIOS_HU27.md`, `CAMBIOS_HU31.md`, `CAMBIOS_HU28.md` y `CAMBIOS_HU30.md`.

### Revisión interna del registro — `/api/registro-actividades/revision` (HU-40)

Usuario definitivo con contrato vigente (🏢). Lo de otra empresa responde 404. Todo queda en el audit log.

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/api/registro-actividades/revision` | Lista de verificación consolidada, observaciones, requisitos para marcar, periodicidad, revisiones y versiones |
| POST | `/api/registro-actividades/revision` | Comienza la revisión (o retoma la en curso) |
| POST | `…/revision/verificaciones` | `{clave, criterios?, decision: verificado\|aceptado\|pendiente, nota?}` (422 `FALLA_SIN_JUSTIFICAR`, `FALLA_BLOQUEANTE`, `JUSTIFICACION_REQUERIDA`) |
| POST | `…/revision/observaciones` | `{clave, criterio?, prioridad, texto}` (`registro:0` = registro completo; 422 `DATOS_DE_CONTACTO`) |
| POST | `…/revision/observaciones/{id}/cerrar` · `/reabrir` | Cierra con `{nota}` o reabre (409 si la revisión ya está marcada) |
| POST | `…/revision/marcar` | `{revisor_nombre, revisor_cargo?, conclusion?, huella, confirmo}` (409 `REVISION_INCOMPLETA` con `faltan`) |
| GET | `…/revision/diferencias?desde=&hasta=` | Diferencias entre versiones (sin `hasta`: el registro actual) |
| PATCH | `…/revision/configuracion` | `{plazo_meses, aviso_dias, recordatorio_correo}` |
| GET | `…/revision/revisiones/{id}` · `/constancia` · `/paquete` | Detalle, informe PDF y paquete ZIP (429 `LIMITE_PAQUETES`) |
| POST | `…/revision/revisiones/{id}/enviar` | `{email?, con_paquete}` (429 `LIMITE_CORREOS`) |
| POST | `…/revision/paquetes/verificacion` | Multipart `file`: confirma que el ZIP es el exportado y que ningún archivo cambió |

### Privacidad de la plataforma — `/api/admin/privacidad-plataforma` (HU-41)

Solo admin (🛡️). Cada emisión, descarga, verificación y cambio de los datos del RoPA queda en el audit log.

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/api/admin/privacidad-plataforma` | Registro generado del inventario: actividades, mapa, proveedores, plazos vigentes, revisión interna, datos del RoPA y emisiones |
| GET | `/api/admin/privacidad-plataforma/actividades/{clave}` | Ficha de una actividad (404 `ACTIVIDAD_NO_ENCONTRADA`) |
| PATCH | `/api/admin/privacidad-plataforma/ropa-datos` | Contacto de Therion Labs y delegado (solo los campos enviados; 422 `DATO_INVALIDO` con `campo`) |
| POST | `/api/admin/privacidad-plataforma/informes` | `{tipo: rat\|ropa, forzar?}`: PDF y Excel con el mismo código (200 si reutiliza; 409 `ROPA_DATOS_INCOMPLETOS`; 429 `LIMITE_INFORMES`) |
| GET | `/api/admin/privacidad-plataforma/informes/verificacion?codigo=…` | Confirma un código `CIA-PLAT-…` y si el registro sigue igual |
| GET | `/api/admin/privacidad-plataforma/informes/{id}/descarga?formato=pdf\|xlsx` | Descarga una emisión (410 `ARCHIVO_ELIMINADO`) |
| GET | `/api/admin/privacidad-plataforma/mapa/descarga` | PDF del mapa de datos de la plataforma |

### Matriz normativa — `/api/admin/matriz` (HU-24)

Solo admin (🛡️). Las rutas que modifican el borrador aceptan `revision` y responden 409 `BORRADOR_CAMBIADO` si otro admin lo cambió.

| Método | Ruta | Auth | Descripción |
|---|---|---|---|
| GET | `/api/admin/matriz` | 🛡️ | Versión vigente, borrador en edición y etiqueta sugerida |
| GET | `/api/admin/matriz/versiones` / `/versiones/{id}` | 🛡️ | Historial / contenido, árbol y diferencias con la anterior |
| POST / GET | `/api/admin/matriz/borrador` | 🛡️ | Crea el borrador (`desde_version_id?`) / lo devuelve con cambios, errores y advertencias |
| GET | `/api/admin/matriz/borrador/validacion` | 🛡️ | Problemas y diferencias antes de publicar |
| POST | `/api/admin/matriz/borrador/descartar` · `/publicar` | 🛡️ | Descarta / publica `{etiqueta, nota_cambio, revision}` |
| POST / PATCH | `/api/admin/matriz/borrador/{entidad}[/{id}]` | 🛡️ | Crea / modifica (`controles`, `brechas`, `rutas`, `preguntas-filtro`) `{datos, revision}` |
| POST | `/api/admin/matriz/borrador/{entidad}/{id}/retirar` · `/restaurar` | 🛡️ | Retira (o quita, si es nuevo) / restaura |
| PATCH | `/api/admin/matriz/borrador/controles/{id}/aplicabilidad` | 🛡️ | `{aplica_siempre, filtros}`: reglas del árbol |

### Log inmutable — `/api/auditoria` (HU-09)

Rol `auditor_externo` o admin (🔍). Fechas en UTC; `hasta` no se incluye.

| Método | Ruta | Auth | Descripción |
|---|---|---|---|
| GET | `/api/auditoria/registros?desde=&hasta=&categoria=&accion=&entidad=&entidad_id=&resultado=&actor_rol=` | 🔍 | Historial con fecha, actor, IP, acción, resultado y hash; `categoria`: modificacion, supresion, creacion, acceso, seguridad, auditoria |
| GET | `/api/auditoria/verificacion` | 🔍 | Cadena HMAC + hash por lote: `integra`, lotes con falla (motivo) y ancla (último lote y sello) |
| GET | `/api/auditoria/lotes` | 🔍 | Sellos de los lotes (para anotar el ancla) |
| GET | `/api/auditoria/exportacion?desde=&hasta=` | 🔍 | ZIP: lotes completos (`audit_log.jsonl` y `.csv`), `lotes.json`, `verificacion.json`, `manifiesto.json` y `verificar_exportacion.py`. Cabecera `X-Audit-Export-SHA256` |
| GET | `/api/auditoria/catalogo` | 🔍 | Acciones y su categoría |
| GET / POST | `/api/admin/auditores` | 🛡️ | Lista / crea una cuenta `{email, organizacion, password, dias_vigencia}` |
| PATCH | `/api/admin/auditores/{id}` | 🛡️ | `{activo?, dias_vigencia?, password?}`; desactivar cierra sus sesiones |

### Códigos de error

| HTTP | Código (`detail.codigo`) | Cuándo |
|---|---|---|
| 400 | — (texto) | Validación de negocio |
| 401 | `NO_AUTENTICADO`, `TOKEN_INVALIDO`, `CREDENCIALES_INVALIDAS`, `USUARIO_DESHABILITADO` | Autenticación (también una sesión cerrada con logout o por cambio de contraseña, HU-28) |
| 429 | `DEMASIADOS_INTENTOS` (incluye `reintentar_en_s` y `Retry-After`) | HU-28: demasiados inicios de sesión fallidos para esa cuenta o IP |
| 403 | `NO_AUTORIZADO` | Rol insuficiente |
| 404 | `EVALUACION_NO_ENCONTRADA` u otro | Recurso no encontrado o de otra organización (HU-20) |
| 409 | `TRANSICION_INVALIDA` (incluye `estado_actual` y `permitidas`) | Cambio de estado ARCOP no permitido |
| 422 | `PROMPT_INJECTION` | Justificación bloqueada |
| 503 | `AUTH_NO_CONFIGURADA` | Falta `AUTH_SECRET` |
| 503 | `ANONIMIZACION_NO_DISPONIBLE` | HU-06: el motor NER falló; no se guardó la justificación ni la evidencia |
| 503 | `CIFRADO_NO_CONFIGURADO` | HU-06: falta `ENTITY_MAP_KEY` para cifrar evidencias |

---

## 8. Capa de Políticas e IA

Intermediario entre la lógica de negocio y el LLM (`app/application/ai/`). Los casos de uso solo piden una **tarea** (`TareaIA.VALIDAR_EVIDENCIA`); la capa se encarga del resto.

```
caso de uso ─► AIGateway.ejecutar(tarea, textos, datos, contexto)
   1. Router        PoliticaTarea: prompt versionado, schema, límites, campos no confiables
   2. Sanitización  motor NER sobre cada texto no confiable ── falla ⇒ ABORTA (no llama al LLM)
   3. Auditoría     mapa de entidades CIFRADO en `sanitizaciones` ── no se puede guardar ⇒ ABORTA
   4. Prompt        plantilla versionada (validar_evidencia/1.2.0) SOLO con texto sanitizado
   5. Proveedor     LLMProviderPort → GroqProvider (reintentos 429/5xx, timeout)
   6. Validación    schema Pydantic + reglas post-salida (HU-07: formato, alucinaciones, fuga de contexto e inyección)
   7. Métricas      una fila en `llamadas_llm` por ejecución, con éxito o con tipo de error
```

**Reglas de negocio:** R1 el texto original nunca llega al LLM · R2 el mapa de entidades se guarda en BD y no va al proveedor · R3 si la sanitización falla se aborta y se registra · R4 si el LLM falla se registra `exito=False` con el tipo de error (`sanitizacion`, `auditoria`, `timeout`, `rate_limit`, `autenticacion`, `conexion`, `proveedor`, `salida_invalida`, `desconocido`) · R5 etiquetas fijas por tipo · R6 `SANITIZER_ENABLED=false` solo para depurar (prohibido con `APP_ENV=production`).

**Salida esperada del LLM** (`EvidenceValidation`): `clasificacion` (`cumplido` | `parcialmente_cumplido` | `no_cumplido`), `confianza` (0–1), `justificacion`, `respalda_clasificacion_usuario`, `divergencia_explicada`, `evidencia_suficiente`, `datos_extraidos`, `errores`.

**Modelo por defecto:** `openai/gpt-oss-safeguard-20b` vía Groq (debe soportar *structured outputs*), temperatura 0.

**Motor NER** (`infrastructure/security/ner_sanitizer.py`, versión 1.1.0): híbrido reglas + spaCy `es_core_news_md`. Detecta primero todos los spans, fusiona solapados y reemplaza en una sola pasada, lo que permite devolver el mapa (tipo, valor, inicio, fin) para auditoría. Etiquetas: `[RUT_ANON]` (con validación de dígito verificador), `[NOMBRE_ANON]`, `[CORREO_ANON]` (incluye ofuscaciones tipo "arroba"/"punto"), `[TEL_ANON]`, `[DIRECCION_ANON]`, `[DATO_CODIFICADO_ANON]` (Base64/Hex/Binario/Base32 hasta 3 niveles). El worker no arranca si falta el modelo de spaCy.

**Rendimiento (T-04, < 2,0 s por página):** el motor procesa una página de 3.000 caracteres en **25 ms (p95)** dentro del Docker del proyecto. Para eso: (1) carga solo el componente `ner` del modelo (mismas entidades, ~45 % menos de CPU); (2) la segunda pasada para nombres en MAYÚSCULAS solo revisa ventanas alrededor de nombres de 2 o más palabras, no el documento entero; (3) un único modelo por proceso, compartido con `seguridad.py`; (4) el modelo se precarga al iniciar el worker y la API; (5) la anonimización corre en un hilo (`asyncio.to_thread`) para no bloquear el event loop. En precisión, las referencias normativas ("Ley 21.719", "artículo 14") ya no se toman como direcciones, los cargos ("Presidenta del Directorio") se recortan de los nombres, y se anonimizan correos con tildes, "cargo + nombre" marcados como organización y direcciones tipo "Los Leones 456". Se evaluó ONNX y no se adoptó: el cuello de botella no era la inferencia. Detalle y mediciones en [`Extras/Cambios/backend/CAMBIOS_T04.md`](../Extras/Cambios/backend/CAMBIOS_T04.md).

**Cifrado:** Fernet con `ENTITY_MAP_KEY`; las entidades además llevan una huella HMAC que permite buscar coincidencias sin descifrar. Guarda la clave fuera del repositorio: sin ella los mapas ya guardados no se pueden descifrar.

**Verificación de la salida (HU-07):** `app/application/ai/verificacion_salida.py` revisa cada respuesta de `validar_evidencia` contra lo que recibió el modelo. El gateway deja los códigos en `llamadas_llm.advertencias` y `ProcessEvidenceUseCase` decide: con un hallazgo grave (cita, cifra, fecha, artículo o dato sin respaldo; "cumplido" sobre evidencia vacía; datos personales o system prompt en la salida; inyección obedecida; formato inválido) la propuesta no se aplica, la pregunta queda en `requiere_revision` (en la remediación, el control no cambia) y se registra el evento `salida_llm`. Una alucinación con confianza bajo el umbral no se retiene porque esa propuesta ya se descarta. `GET /api/ia/metricas` trae `verificacion_salida` con la tasa de alucinación (umbral 2 %).

**Modelo local (HU-07):** `LLM_PROVIDER=ollama` usa `infrastructure/llm/ollama_provider.py` (salida estructurada con el JSON Schema en `format`). Se levanta con `docker compose --profile modelo-local up -d` y `docker compose exec ollama ollama pull qwen2.5:7b-instruct`.

**Agregar una tarea nueva** (p. ej. recomendación de ruta formativa): crear su prompt en `ai/prompts/<tarea>.py` con `PROMPT_VERSION`, su schema Pydantic y registrar una `PoliticaTarea` en `crear_politicas`. **Cambiar de proveedor:** crear un adaptador de `LLMProviderPort` en `infrastructure/llm/`, registrarlo en `factory.py` y cambiar `LLM_PROVIDER`/`LLM_MODEL`.

---

## 9. Seguridad y privacidad (Ley 21.719)

| Riesgo | Control implementado | Dónde |
|---|---|---|
| Datos personales enviados a un tercero (LLM) | Anonimización NER obligatoria, fail-closed; recorte después de sanitizar para no cortar PII a medias | `ner_sanitizer.py`, `gateway.py` |
| Re-identificación desde la auditoría | Mapa de entidades sin valores originales (solo huellas HMAC y conteos, HU-06); métricas sin texto del usuario | `cifrado.py`, `registro_ia_repository.py` |
| PII guardada en BD, disco o logs (HU-06) | Justificación y nombre de archivo anonimizados antes de persistir (503 si el motor falla); evidencias cifradas en reposo y reemplazadas por su texto anonimizado tras validar; nombres de archivo en disco = UUID; textos ARCOP cifrados (excepción); prueba de regresión que siembra PII | `anonimizador.py`, `archivo_cifrado_storage.py`, `cifrado_columnas.py`, `test_hu06_regresion_pii.py` |
| Prompt injection en justificaciones | Detector por reglas con normalización (URL-decode, NFKC, homoglifos, invisibles, leetspeak, datos codificados); perfil **estricto**; bloqueo 422 y registro con la regla que disparó | `seguridad.py`, `prompt_guard.py`, `create_respuesta.py` |
| Prompt injection en evidencias | Perfil **evidencia** (HU-33): el vocabulario de cumplimiento (aprobar, ejecutar, registrar, marcar...) solo bloquea si va dirigido a la IA o al resultado; las señales fuertes (texto oculto, bidi/"tag", codificado, "si eres una IA", delimitadores, cambio de rol) siempre. `MODO_SEGURIDAD_EVIDENCIA=bloquear` (no se llama al LLM, respuesta en `requiere_revision`) o `marcar` (se registra y no hay fallback al usuario) | `seguridad.py`, `process_evidence.py`, `test_hu33_*.py` |
| Prompt injection multilenguaje e indirecta (HU-07) | Reglas en inglés, portugués, francés, alemán e italiano (notas para la IA, "si eres una IA", ignorar instrucciones, forzar el resultado, cambio de rol), nombres de campos del schema, pedidos de reglas recibidas y de datos anonimizados; antes del prompt se quitan caracteres invisibles, bidi, "tag" y de control y se neutralizan separadores (`═══`) y marcadores de turno (`[INST]`, `<<SYS>>`, `<\|...\|>`) | `seguridad.py`, `prompts/base.py`, `test_hu07_owasp_entrada.py` |
| Alucinaciones y salidas inseguras del modelo (HU-07) | Verificador determinista de cada salida: formato, citas, cifras, fechas, artículos, códigos de control y datos extraídos sin respaldo; datos personales, reidentificación y system prompt en la salida; señales de inyección obedecida. Salida saneada antes de guardarla; con un hallazgo grave la pregunta queda en `requiere_revision` y se registra la alerta `salida_llm` | `verificacion_salida.py`, `process_evidence.py`, `test_hu07_*.py` |
| Que una inyección suba el puntaje | `requiere_revision` vale 0 y cuenta en el denominador | `generate_resumen.py` |
| Derechos del titular | Solicitudes ARCOP con trazabilidad completa y anonimización irreversible al aprobar una supresión | `gestionar_solicitud_arcop.py`, `anonimizacion_repository.py` |
| Credenciales | PBKDF2-SHA256 600k, tokens HMAC con expiración, revocación inmediata, errores genéricos | `autenticacion.py` |
| Configuración insegura en producción | La app no arranca con `APP_ENV=production` si `SANITIZER_ENABLED=false`, falta `ENTITY_MAP_KEY` o `AUTH_SECRET` < 32 caracteres | `config.py` |
| Exposición de servicios | Puertos publicados solo en `127.0.0.1`; contenedor con usuario sin privilegios | `docker-compose.yml`, `Dockerfile` |

> `infrastructure/security/seguridad.py` nació en el proyecto **ComplianceAI-Prompt-Injection** (ver `Extras/Guia_ComplianceAI_PromptInjection.docx.pdf`), que no está publicado: hoy la única copia vigente es la de este repositorio (HU-33). Si ese proyecto se publica, copiar este archivo allá y verificar que son idénticos con `RUTA_REPO_PROMPT_INJECTION=<carpeta del repo> pytest tests/test_hu33_detector_contexto.py -k copia`.

---

## 10. Frontend

### 10.1 Panel web (HU-13, HU-11, HU-12)

**Estado:** hecho y conectado a la API real. Carpeta `frontend-next/` (Next.js 15 + React 19 + TypeScript), servicio `web` en `http://localhost:3000/panel`.

| Ruta | Contenido |
|---|---|
| `/panel?evaluacion=ID` | Diagnóstico: madurez general, nivel, brechas abiertas y controles evaluados; radar de madurez por dominio (empresa vs. **meta** y promedio del rubro); barras por severidad; comparativa meta y rubro; las 4 brechas más urgentes; **Descargar PDF** y **Enviar por correo** |
| `/panel/dominios` | Una tarjeta por dominio: puntaje, nivel, distancia a la meta, marca del promedio del rubro y acceso a sus brechas |
| `/panel/brechas?severidad=&dominio=&estado=&q=` | HU-11: listado priorizado por severidad (Crítica/Alta/Media/Baja), filtros en la URL, CSV, vistas fijadas, **PDF directo del listado filtrado** y envío por correo |
| `/panel/capacitacion` | HU-12: plan de estudio por dimensión normativa (nivel del plan, objetivo, módulos con objetivos y contenidos, brechas que cierran), filtros por nivel, "Empieza por" y exportación CSV para el LMS |

- **Datos:** consume `GET /api/evaluaciones`, `/{id}/resumen`, `/{id}/comparativa` (opcional), `/{id}/respuestas`, `/{id}/plan-formativo`, `/{id}/informe/pdf`, `POST /{id}/informe/enviar`, `GET /api/brechas` y `/api/controles`. El encuestado de la landing pasa por el BFF (`/bff/api/*`), que solo deja su propia evaluación. Una evaluación sin resumen (sin `POST /cerrar` o `/completar`) muestra un aviso en vez de los gráficos.
- **Reglas:** brecha = respuesta con estado vigente `no_cumplido` (misma regla que `Respuesta.sincronizar_brecha`, HU-02); las parciales se cuentan aparte. Niveles con los mismos cortes del backend (25/50/75).
- **Criterios de aceptación:** responsivo ≥ 1024 px (barra lateral compacta entre 1024 y 1279 px); gráficos de radar y barras interactivos con mouse y teclado (tooltip, Enter filtra o abre el detalle, vista de tabla); WCAG 2.1 AA (contraste ≥ 5,7:1 en texto, foco visible, zoom 200 %, alternativas en texto). Paleta y tipografía del sitio TherionLabs.
- **Documentación:** `frontend-next/README.md`, `Extras/Cambios/frontend/HU-13_HANDOFF.md` (tokens, layout, componentes, casos borde) y `docs/ACCESIBILIDAD.md` (auditoría).
- **Modo demo** sin backend: `cd frontend-next && npm install && NEXT_PUBLIC_DEMO=1 npm run dev`.

**Acceso con email y contraseña (HU-28).** Todo pasa por el BFF de Next.js y el token vive solo en una cookie httpOnly:

| Ruta | Para quién | Contenido |
|---|---|---|
| `/ingresar` | Usuario definitivo de una empresa cliente | Inicio de sesión; con sesión vigente lleva directo a `/empresa` |
| `/empresa` | Usuario definitivo | Espacio de su empresa: contrato, **Mis evaluaciones** (HU-29: historial con gráfico de evolución global y por dimensión, **Nueva evaluación** y **Guardar informe**; cada una con **Ver resultados** en `/panel` modo cliente) y **Mis documentos** (informes, borradores, evidencias y constancias con descarga y eliminación) |
| `/empresa/evaluacion/[id]` | Usuario definitivo | HU-29: responde la reevaluación con el cuestionario de siempre, por `/bff/cliente/api/*` |
| `/empresa/borradores` | Usuario definitivo | HU-16: genera la política de uso de LLM, el aviso de privacidad o la PIA adaptados a sus brechas; editor Markdown con vista previa y campos por completar, descarga en Markdown/PDF y consolidación |
| `/panel/capacitacion` (modo cliente) | Usuario definitivo | HU-26: avance de la empresa (por dimensión y nivel) y, en cada módulo, su estado y la acción Empezar / Continuar / Constancia |
| `/panel/capacitacion/[ruta]` | Usuario definitivo | HU-26: recorrido del módulo (lecciones, material, actividad de verificación y constancia) |
| `/panel/remediacion` | Usuario definitivo | HU-17: cerrar brechas subiendo evidencia; el puntaje y el radar se actualizan si el control mejora |
| `/admin/login` → `/admin/clientes` | Administrador de Therion Labs | Panel interno con pestañas **Solicitudes de contratación**, **Empresas**, **Evaluaciones** y **Bitácora**, y **Cerrar sesión** |
| `/admin/matriz` | Administrador de Therion Labs | HU-24: mantenedor de la matriz normativa: versión vigente frente al borrador, controles, brechas, rutas, filtro inicial, árbol de aplicabilidad con simulador, historial de versiones y publicación |
| `/mis-derechos` | Cualquiera | HU-32: puerta pública a los derechos ARCOP: ingreso con N.º de evaluación + clave, acceso de clientes y consulta del estado con el código `ARC-XXXX-XXXX` |
| `/panel/mis-derechos` | Usuario temporal | HU-32: enviar solicitudes de los 6 derechos, seguir su avance, responder pedidos de información, cancelar y descargar sus datos |
| `/empresa/mis-derechos` | Usuario definitivo | HU-32: lo mismo desde la interfaz contratada, con o sin contrato vigente |
| `/admin/arcop` | Administrador de Therion Labs | HU-32: bandeja de solicitudes ARCOP con cifras por atender, filtros, detalle con historial y acciones (revisión, pedir información, proceso, prórroga, resolver o rechazar; la supresión pide confirmación) |
| `/recuperar` (`?tipo=admin`) | Ambos | "¿Olvidaste tu contraseña?": pide el enlace por correo (misma respuesta exista o no la cuenta) |
| `/restablecer#token=…` | Ambos | Define la contraseña nueva; cierra todas las sesiones abiertas de la cuenta |

Cerrar sesión revoca el token en el servidor (`POST /api/auth/logout`) antes de borrar la cookie. Detalle en `Extras/Cambios/frontend/CAMBIOS_HU28.md`.

### 10.2 Prototipo estático (archivado)

El prototipo HTML/JS original (14 páginas con una API simulada en `localStorage`, servidas por nginx en `:8088`) ya no forma parte del sistema: se movió a `Extras/frontend-prototipo/` como evidencia del diseño inicial. Todo el frontend vigente está en `frontend-next/`. Lo que solo existía allí y falta migrar es el **backoffice de matriz y árbol de aplicabilidad** (deuda #11). Para verlo de nuevo, ver `Extras/frontend-prototipo/README.md`.

---

## 11. Datos maestros

**Dominios:** 1 Protección de Datos · 2 Gobernanza de IA · 3 Gestión de Riesgos · 4 Uso Responsable.

**Rubros:** 1 Banca y Finanzas · 2 Salud · 3 Retail y E-commerce · 4 Telecomunicaciones · 5 Educación · 6 Tecnología/SaaS · 7 Manufactura · 8 Servicios/Otros.

**Rutas formativas (12):** cada dominio × {Inicial, Intermedio, Avanzado}. Cada brecha apunta a una ruta (no necesariamente de su mismo dominio; p. ej. `ERR-DAT-002` → *Gestión de Riesgos – Intermedio*).

**Controles (40):**

| Prefijo | Dominio | Marco principal | Alta | Media | Baja |
|---|---|---|---:|---:|---:|
| DAT-001…010 | Protección de Datos | Ley N.º 21.719 | 7 | 3 | 0 |
| GOB-001…010 | Gobernanza de IA | ISO/IEC 42001 | 3 | 5 | 2 |
| RIE-001…010 | Gestión de Riesgos | NIST AI RMF 100-1 (RIE-004: ISO/IEC 42001) | 5 | 5 | 0 |
| SEG-001…010 | Uso Responsable | OWASP LLM, NIST 600-1 (SEG-006/007), Ley 21.719 (SEG-008/010) | 8 | 1 | 1 |
| **Total** | | | **23** | **14** | **3** |

Cada control tiene su brecha `ERR-<prefijo>-<n>` (40 en total). La fuente de verdad es la migración `2e398c9a9b2e_seed_catalogs_and_controls.py`.

---

## 12. Puesta en marcha

### 12.1 Con Docker (recomendado)

Solo se necesita **Docker Desktop** (en Windows, con WSL 2). No hace falta Python ni spaCy en la máquina.

**1. Crear `Proyecto/.env`** (el **único** archivo de configuración: lo usan docker compose, el backend y el frontend) desde la plantilla y completar las claves:

```powershell
cd Proyecto
copy .env.example .env
```

| Variable | Cómo obtenerla |
|---|---|
| `GROQ_API_KEY` | [console.groq.com/keys](https://console.groq.com/keys) |
| `ENTITY_MAP_KEY` | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `AUTH_SECRET` | `python -c "import secrets; print(secrets.token_urlsafe(48))"` (necesaria para `/api/auth` y `/api/arcop`) |

Sin Python local: `docker run --rm python:3.13-slim sh -c "pip install -q cryptography && python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"`.

**2. Levantar todo:**

```powershell
docker compose up -d --build
```

La primera vez tarda varios minutos (descarga imágenes, instala spaCy con su modelo y compila el panel Next.js).

**Puertos en Windows:** Hyper-V/WSL reserva rangos de puertos y Docker puede fallar con `bind: An attempt was made to access a socket in a way forbidden by its access permissions` (pasó con el 8080). Cualquier puerto del host se cambia sin editar el compose, en el mismo `Proyecto/.env`:

```
WEB_PORT=3001
API_PORT=8001
```

Para ver los rangos reservados: `netsh interface ipv4 show excludedportrange protocol=tcp`.

| URL | Qué es |
|---|---|
| http://localhost:3000 | Frontend: landing, encuesta (`/comenzar`, `/retomar`) y panel (`/panel`) |
| http://localhost:8000/docs | Swagger de la API |
| `localhost:5433` | PostgreSQL (`postgres` / `1234`, BD `complaince_db`) — solo desarrollo |
| `localhost:6379` | Redis |

**3. Crear un administrador** (opcional, para ARCOP):

```powershell
docker compose exec api python -m app.core.crear_admin --email admin@therionlabs.cl
```

**4. Envío del informe por correo** (opcional). Sin configurar, el backend queda en `CORREO_MODO=archivo`: el botón funciona pero el correo se guarda en `/data/storage/correos` y el panel avisa «Entorno de desarrollo…». Para que llegue de verdad (guía paso a paso en `frontend-next/docs/Guia_envio_informe_por_correo.pdf`):

1. En la cuenta Gmail remitente activa la verificación en 2 pasos y crea una **contraseña de aplicación** en `myaccount.google.com/apppasswords` (16 caracteres; no es la contraseña normal y no vence: todo el equipo puede usar la misma).
2. Descomenta y completa en `Proyecto/.env` la sección «Informe por correo»:

   ```
   CORREO_MODO=smtp
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_STARTTLS=true
   SMTP_USUARIO=tucuenta@gmail.com
   SMTP_PASSWORD=abcdefghijklmnop
   CORREO_REMITENTE=ComplianceIA <tucuenta@gmail.com>
   ```

3. `docker compose up -d --force-recreate api`.
4. **Avast/AVG** (y otros antivirus con escaneo de correo) interceptan el puerto 587 y el envío falla con `SSLCertVerificationError`: en Avast → Configuración → Protección → Escudos principales → Escudo de correo, desmarca «Analizar correo saliente (SMTP)».

El `.env` no se sube al repositorio (lleva la clave).

En Docker se ignoran `DATABASE_URL`, `DATABASE_URL_SYNC`, `REDIS_URL` y `STORAGE_DIR` del `.env` (el compose los reemplaza por los servicios internos). Si cambias el `.env`, aplica con `docker compose up -d`.

### 12.2 Manual (para depurar la API o el worker)

Requisitos: Python 3.12+ (probado en 3.13), Docker para PostgreSQL y Redis.

```powershell
cd Proyecto
docker compose up -d db redis

cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1          # si PowerShell lo bloquea: Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
pip install --upgrade pip
pip install -r requirements.txt      # incluye spaCy y el wheel de es_core_news_md 3.8.0
# la configuración sale de Proyecto/.env (sus DATABASE_URL apuntan a 127.0.0.1:5433)
alembic upgrade head

# Terminal 1
uvicorn app.main:app --reload --port 8000
# Terminal 2
arq app.worker.tasks.WorkerSettings
```

Notas: usa `127.0.0.1` y no `localhost` (en Windows `localhost` resuelve primero a IPv6). Si `python -m spacy download es_core_news_md` falla por incompatibilidad con pydantic, el wheel ya viene fijado en `requirements.txt`.

### 12.3 Preparar datos de prueba

Mientras no existan endpoints de alta (deuda #1), se insertan por SQL:

```powershell
docker compose exec db psql -U postgres -d complaince_db -c "INSERT INTO usuario_temporal (fecha_expiracion, email, validacion_invitacion, `"Rubro_id`") VALUES ('2027-12-31', 'test@example.com', 'S', 6);"
docker compose exec db psql -U postgres -d complaince_db -c "INSERT INTO evaluacion (fecha_inicio, estado_progreso, `"Usuario_temporal_id`", filtro_completado) VALUES (CURRENT_DATE, 'en_progreso', 1, false);"
```

`filtro_completado` es `NOT NULL` sin valor por defecto en la BD, por eso se indica explícitamente. En PowerShell las comillas dobles internas se escapan con acento grave (`` ` ``).

### 12.4 Recorrido de prueba (PowerShell)

```powershell
$api = "http://localhost:8000/api"

# 1. Filtro: usa IA y LLM (F1 y F4 = SI)
Invoke-RestMethod -Method Post "$api/evaluaciones/1/filtro" -ContentType "application/json" -Body '{"respuestas":[{"codigo":"F1","respuesta":true},{"codigo":"F2","respuesta":false},{"codigo":"F3","respuesta":false},{"codigo":"F4","respuesta":true},{"codigo":"F5","respuesta":false},{"codigo":"F6","respuesta":false},{"codigo":"F7","respuesta":false}]}'

# 2. No cumplido -> brecha automática
Invoke-RestMethod -Method Post "$api/respuestas/" -ContentType "application/json" -Body '{"evaluacion_id":1,"matriz_control_id":3,"estado_clasificacion":"no_cumplido","justificacion":"No tenemos politica formal."}'

# 3. Cumplido + evidencia (procesada por el worker)
$r = Invoke-RestMethod -Method Post "$api/respuestas/" -ContentType "application/json" -Body '{"evaluacion_id":1,"matriz_control_id":1,"estado_clasificacion":"cumplido","justificacion":"Politica aprobada."}'
curl.exe -X POST "$api/respuestas/$($r.id_respuesta)/evidencias" -F "file=@backend/tests/data/evidencias_ejemplo/evidencia.txt"
Start-Sleep 10
Invoke-RestMethod "$api/respuestas/$($r.id_respuesta)" | ConvertTo-Json -Depth 5

# 4. Evidencia maliciosa -> bloqueo preventivo y evento de seguridad
curl.exe -X POST "$api/respuestas/$($r.id_respuesta)/evidencias" -F "file=@backend/tests/data/evidencias_ejemplo/evidencia_maliciosa.txt"
Invoke-RestMethod "$api/seguridad/eventos"

# 5. Cerrar y ver reporte
Invoke-RestMethod -Method Post "$api/evaluaciones/1/cerrar"
Invoke-RestMethod "$api/evaluaciones/1/comparativa"
Invoke-RestMethod "$api/ia/metricas"
```

El recorrido ARCOP (login, titular, solicitudes) está en [`Extras/Cambios/backend/CAMBIOS_ARCOP.md`](../Extras/Cambios/backend/CAMBIOS_ARCOP.md#probar-a-mano-docker-powershell-desde-proyecto).

---

## 13. Variables de entorno

| Variable | Defecto | Descripción |
|---|---|---|
| `DATABASE_URL` | — (obligatoria) | URL async (`postgresql+asyncpg://…`) |
| `DATABASE_URL_SYNC` | — (obligatoria) | URL síncrona para Alembic (`postgresql+psycopg2://…`) |
| `REDIS_URL` | — (obligatoria) | Redis para ARQ |
| `GROQ_API_KEY` | — (obligatoria con `LLM_PROVIDER=groq`) | Clave de Groq |
| `LLM_PROVIDER` | `groq` | Proveedor del LLM: `groq` u `ollama` (HU-07: modelo local; con `ollama` no se exige `GROQ_API_KEY`) |
| `OLLAMA_URL` | `http://ollama:11434` | HU-07: servidor del modelo local (servicio `ollama`, perfil `modelo-local` del compose) |
| `LLM_MODEL` | `openai/gpt-oss-safeguard-20b` | Modelo (con *structured outputs*) |
| `LLM_TIMEOUT_S` / `LLM_MAX_REINTENTOS` | `60` / `2` | Timeout por intento y reintentos (429/5xx) |
| `LLM_MAX_TOKENS_SALIDA` | `1500` | Tope de tokens de respuesta |
| `LLM_PRECIO_ENTRADA_USD_1M` / `LLM_PRECIO_SALIDA_USD_1M` | `0` / `0` | Precio del modelo para estimar costo en métricas |
| `UMBRAL_CONFIANZA` | `0.8` | Confianza mínima para aceptar la clasificación del LLM |
| `JUSTIFICACION_MIN_CARACTERES` | `20` | HU-02: largo mínimo de la justificación en `parcialmente_cumplido` y `requiere_revision` |
| `MAX_CHARS_EVIDENCIA_LLM` / `MAX_CHARS_JUSTIFICACION_LLM` | `8000` / `4000` | Caracteres enviados al LLM (tras sanitizar) |
| `MODO_SEGURIDAD_EVIDENCIA` | `bloquear` | `bloquear` o `marcar` ante posible inyección en evidencias |
| `MODO_VERIFICACION_SALIDA` | `bloquear` | HU-07: `bloquear` (la propuesta del modelo con un hallazgo grave no se aplica y la pregunta queda para revisión) o `marcar` (solo se registra la alerta) |
| `SANITIZER_ENABLED` | `true` | Anonimización NER antes del LLM (`false` solo debug) |
| `ENTITY_MAP_KEY` | — | Clave maestra Fernet: huellas del mapa, cifrado de evidencias y de textos ARCOP (obligatoria) |
| `GUARDAR_MAPA_ENTIDADES_CIFRADO` | `false` | HU-06: `true` reactiva el mapa reversible (debe documentarse como excepción) |
| `REQUIERE_NER` | `false` | **Obsoleta** (reemplazada por `SANITIZER_ENABLED`) |
| `APP_ENV` | `development` | `development` · `test` · `production` (activa validaciones estrictas) |
| `STORAGE_DIR` | `./storage` | Carpeta de evidencias (`/data/storage` en Docker) |
| `AUTH_SECRET` | — | Secreto HMAC de tokens (≥ 32 caracteres en producción) |
| `AUTH_TOKEN_TTL_MIN` | `480` | Vigencia del token |
| `ARCOP_PLAZO_RESPUESTA_DIAS` | vacío | Plazo de respuesta ARCOP (días corridos). **Dejar comentada** hasta definirla: con `=` vacío la app no arranca |
| `ARCOP_PLAZO_INFORMACION_DIAS` | vacío | Plazo para aportar información (mismo cuidado) |
| `META_CUMPLIMIENTO_PUNTAJE` | `75` | Meta por dimensión que muestra la comparativa ("lo que debería cumplir") |
| `K_ANONIMATO_MINIMO` | `5` | HU-10: empresas distintas del rubro necesarias para publicar su promedio (en production no puede ser < 5; `1` solo en demos locales) |
| `K_ANONIMATO_DISTRIBUCION` | `10` | HU-10: empresas necesarias para publicar mediana y percentiles 25/75 del rubro |
| `BENCHMARK_AL_COMPLETAR` | `true` | Recalcular el benchmark al completar cada evaluación |
| `CORREO_MODO` | `archivo` | `archivo` (guarda el `.eml`, desarrollo) · `smtp` (envío real) · `desactivado`. En `production` no se permite `archivo` |
| `SMTP_HOST` / `SMTP_PORT` | — / `587` | Servidor de correo (Gmail: `smtp.gmail.com`). Obligatorio con `CORREO_MODO=smtp` |
| `SMTP_USUARIO` / `SMTP_PASSWORD` | — | Cuenta y **contraseña de aplicación** (16 caracteres, sin espacios) |
| `SMTP_STARTTLS` / `SMTP_SSL` | `true` / `false` | 587 con STARTTLS, o 465 con `SMTP_SSL=true` y `SMTP_STARTTLS=false` |
| `SMTP_TIMEOUT_S` | `20` | Tiempo máximo de conexión SMTP |
| `CORREO_REMITENTE` | `ComplianceIA <no-responder@complianceia.cl>` | Remitente; con Gmail debe ser la misma cuenta de `SMTP_USUARIO` |
| `INFORME_CORREOS_DIA_EVALUACION` / `INFORME_CORREOS_DIA_IP` | `3` / `10` | Envíos del informe permitidos por día |
| `DB_APP_USER` / `DB_APP_PASSWORD` | `complianceia_app` / `complianceia_app_dev` | HU-09: rol de PostgreSQL de la API y el worker (sin UPDATE/DELETE en el audit_log). Lo crea la migración; en `production` la clave debe ser propia (≥ 16) |
| `AUDIT_LOTE_TAMANO` / `AUDIT_SELLO_CADA_MIN` | `500` / `15` | HU-09: filas por lote sellado y cada cuántos minutos sella el worker |
| `AUDIT_EXPORT_MAX_FILAS` | `200000` | HU-09: tope de registros por exportación (413 si se supera) |
| `AUDITOR_VIGENCIA_MAX_DIAS` / `AUDITOR_PASSWORD_MIN` | `90` / `12` | HU-09: vigencia máxima y largo mínimo de la clave del Auditor Externo |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | `postgres` / `1234` / `complaince_db` | `Proyecto/.env` (solo los usa `docker-compose.yml`) |

---

## 14. Pruebas y calidad

Las pruebas unitarias e integración **no necesitan PostgreSQL, Redis ni Groq**: usan repositorios falsos o SQLite en memoria (`aiosqlite`).

| Archivo | Pruebas | Qué cubre |
|---|---:|---|
| `test_bordes_na_y_evidencia.py` | 42 | Escenarios borde: N/A masivo, falta de evidencia, cálculo de puntaje, una respuesta por control, evidencias en evaluación cerrada |
| `test_hu01_cuestionario.py` | 14 | HU-01: upsert y PUT de respuestas, rechazo de controles no aplicables y evaluaciones cerradas, `controles-aplicables` optimizado, progreso (la de carrera de 10 POST corre solo live) |
| `test_completar_evaluacion.py` | 9 | `POST /completar`: condiciones, cierre atómico y bloqueo de respuestas, filtro y evidencias |
| `test_hu02_matriz_estados.py` | 24 | HU-02: 5 estados, justificación obligatoria (unitarias y API), `requiere_revision` resuelta por el LLM, revisión humana, requisito de evidencia al completar y brecha coherente con el estado vigente |
| `test_solicitudes_arcop.py` | 24 | ARCOP: ciclo de vida, roles, login, anonimización, plazos |
| `test_ner_sanitizer.py` | 18 | Motor NER, cifrado del mapa y precisión contra `tests/data/ner_gold.jsonl` (17 casos) |
| `test_rendimiento_ner.py` | 14 | T-04: < 2,0 s por página, pipeline mínimo, segunda pasada acotada, NER fuera del event loop y precisión ≥ 0,95 / cobertura 100 % sobre 40 páginas etiquetadas |
| `test_capa_ia.py` | 17 | AIGateway contra las reglas R1–R6 |
| `test_seguridad_integracion.py` | 11 | Capa anti prompt-injection en el backend |
| `test_hu07_verificacion_salida.py` | 20 (144 casos) | HU-07: test-set de 124 salidas (alucinación residual < 2 %, 100 % de fugas, inyecciones y salidas inseguras, ≤ 5 % de falsos positivos), saneamiento de la salida y métricas |
| `test_hu07_owasp_entrada.py` | 13 (54 casos) | HU-07: 96 ataques OWASP LLM01 (directos, indirectos, multilenguaje, codificados, ofuscados, delimitadores, fuga y exfiltración) al 100 %, legítimos multilenguaje y frases frontera sin bloqueo, saneamiento antes del prompt |
| `test_hu07_integracion.py` | 19 (22 casos) | HU-07: revisión humana y alerta al retener una salida, confianza baja, remediación, modo `marcar`, hallazgos en `llamadas_llm`, proveedor local (Ollama) y configuración |
| `test_metricas_ia.py` | 6 | Cálculo de métricas (funciones puras) |
| `test_e2e_capa_ia.py` | 2 | Caso end-to-end del sistema con la capa de IA |
| `test_latencia_api.py` | 1 | Latencia de la API REST: p95 < 500 ms por endpoint (en proceso o live) |
| `test_hu06_anonimizacion.py` | 20 | HU-06: etiquetas fijas, fail-closed, archivo cifrado y reemplazado por el texto anonimizado, mapa irreversible, textos ARCOP cifrados |
| `test_hu06_regresion_pii.py` | 1 | HU-06 C3: siembra PII por todas las entradas y verifica que no aparece en ninguna tabla (lectura en crudo), en disco, en los logs ni en lo enviado al LLM |
| `test_hu12_plan_formativo.py` | 32 | HU-12: severidad igual al panel, mapeo brecha → ruta, niveles y objetivos, agrupación por dimensión, PDF válido; API: plan, comparativa con meta y benchmark al completar, descarga del PDF, envío por correo (modo archivo y límite diario), correo desactivado y `ruta_formativa` en `/api/brechas` |
| `test_hu19_encuesta_publica.py` | 19 | HU-19: encuesta pública sin invitación, aislamiento entre encuestados, retomar con clave, límites por IP, CAPTCHA, cuota de IA y benchmark |
| `test_t06_minimizacion.py` | 15 | T-06: inventario de datos personales, plazos de conservación y validaciones de producción |
| `test_hu20_autorizacion.py` | 15 (75 casos) | HU-20: matriz de autorización **por endpoint** (6 actores), solo-admin, rutas públicas y una prueba que falla si aparece una ruta sin clasificar |
| `test_hu23_semilla_staging.py` | 5 | HU-23: datos semilla de staging (administrador sin teclado, evaluaciones sintéticas con k ≥ 5 en el benchmark, idempotencia y `--eliminar`) |
| `test_hu38_integracion_rat.py` | 14 | HU-38: factores de IA y volumen, reglas de la evaluación de impacto y matriz de mayor riesgo, volumen sin cambiar versiones, PDF y Excel; aportes del registro y que nunca baja un control; brechas con su paso; PIA y aviso pre-llenados; API: evidencia al dejar vigente (estado, brecha, puntaje, evolución y audit log), brechas con su ruta, borradores desde el registro, contrato y roles |
| `test_hu40_revision_interna.py` | 17 | HU-40: lista por actividad y por elemento del mapa, bloqueos, verificar/aceptar/desactualizar, requisitos (observaciones abiertas bloquean), periodicidad y recordatorio por etapa, diferencias, marca en el PDF y el Excel del registro, informe de la revisión, paquete determinista verificable (script independiente) y API completa |
| `test_hu41_registro_plataforma.py` | 28 | HU-41: actividades desde el inventario, cobertura (tabla nueva sin actividad = falla), plazos iguales a los ajustes configurados, proveedores como encargados con país y garantía, revisión interna, RAT y RoPA con los generadores del cliente y API solo admin |
| `test_live_capa_ia.py` | 1 | Sistema real: uvicorn + ARQ + PostgreSQL + Redis + Groq + spaCy (se activa con `LIVE_BASE_URL`) |

Soporte: `conftest.py` (variables mínimas y storage temporal), `_api_harness.py` (siembra datos de prueba), `_capa_ia_fakes.py` (dobles de prueba), `_corpus_ner.py` (corpus sintético etiquetado para medir el NER).

```powershell
# Suite completa en Docker (no toca la BD real)
docker compose run --rm --no-deps api pytest tests -q

# Suite local (Windows, venv en backend/)
pytest tests -v -rxX

# Precisión del NER con detalle
pytest tests/test_ner_sanitizer.py -s

# Rendimiento del NER (T-04): pruebas y benchmark
docker compose exec worker pytest tests/test_rendimiento_ner.py -v -s
docker compose exec worker python scripts/benchmark_ner.py --paginas 100 --evidencia 8000
docker compose exec worker python scripts/benchmark_ner.py --paginas 20 --perfil   # + profiling

# Prueba en vivo contra el sistema levantado (usa la BD real, evaluación 9101)
docker compose exec api sh -c 'LIVE_BASE_URL=http://localhost:8000 LIVE_DATABASE_URL=$DATABASE_URL LIVE_ENTITY_MAP_KEY=$ENTITY_MAP_KEY pytest tests/test_live_capa_ia.py -v -s'
```

**Frontend (`frontend-next`):** `npm test` corre 5 suites vitest (66 pruebas, 13 de HU-12: meta, BFF, CSV del plan, plan demo).

**Últimos resultados reportados**

- **HU-12 · plan formativo, comparativa y correo (22-oct-2026):** 25 pruebas de lógica y PDF aprobadas (las 7 de API se corren en Docker); 66/66 del frontend. Recorrido en Chromium a 1440, 1024 y 720 px sin errores; PDF descargado directo; correo real recibido vía Gmail SMTP tras desactivar el Escudo de correo de Avast.

- **T-04 · Motor NER (15-oct-2026, Docker, 8 núcleos):** página de 3.000 caracteres en 25,1 ms (p95; límite 2.000 ms), evidencia de 8.000 caracteres en 66,6 ms (p95). Precisión 0,988 y cobertura de PII 100 % sobre 40 páginas etiquetadas. Suite completa: 212 aprobadas, 1 omitida (prueba en vivo).
- **Prueba en vivo (13-oct-2026):** PASSED con `openai/gpt-oss-safeguard-20b` y spaCy `es_core_news_md` 3.8.0. Sin fugas de PII, mapa cifrado correcto e inyección bloqueada sin llamar al LLM. Falsos positivos del NER observados: "la Ley 21" como dirección y "Presidenta del Directorio" como nombre (**corregidos en T-04**, motor v1.1.0).
- **Latencia live (11-oct-2026, concurrencia 10):** 12 de 13 endpoints cumplen p95 < 500 ms. No cumplía `GET controles-aplicables` (p95 542,7 ms). Detalle en [`reporte_latencia_live_c10.md`](../Extras/Evidencias/reporte_latencia_live_c10.md).
- **HU-01 (15-oct-2026):** `controles-aplicables` optimizado (1 consulta + catálogo cacheado). **Latencia live oficial (16-oct-2026, Docker, concurrencia 10): 12/12 endpoints cumplen**; `GET controles-aplicables` p95 24,1 ms (antes 542,7 ms). Detalle en [`Extras/Evidencias/reporte_latencia_live_hu01.md`](../Extras/Evidencias/reporte_latencia_live_hu01.md) y [`Extras/Cambios/backend/CAMBIOS_HU01.md`](../Extras/Cambios/backend/CAMBIOS_HU01.md).

### 14.1 Integración y despliegue continuo (HU-23)

| Workflow | Cuándo | Qué hace |
|---|---|---|
| [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) | Cada pull request a `main`, cada push a `main` y a mano | pytest con cobertura ≥ 70 % (y SonarQube si hay `SONAR_TOKEN`); TypeScript + vitest del frontend; construye las imágenes `api` y `web` sin publicarlas y comprueba que no lleven secretos. Resume todo en el check **CI aprobado**, que se marca como obligatorio en `main` |
| [`.github/workflows/deploy-staging.yml`](../.github/workflows/deploy-staging.yml) | Solo, cuando CI termina en verde en `main`; y a mano | Publica `api:<commit>` y `web:<commit>` en `acrcomplainceia`, ejecuta el job `migrate`, actualiza `api`, `worker` y `web`, hace la prueba de humo por HTTPS y vuelve a la versión anterior si algo falla |

El flujo del equipo pasa a ser **rama → pull request → CI en verde + revisión → merge**. Las pruebas corren en GitHub; nadie tiene que ejecutar nada en su computador. Los datos semilla del piloto (administrador y 20 evaluaciones sintéticas para la comparativa) los carga `backend/scripts/sembrar_staging.py`. La guía completa (preparación, secretos, vuelta atrás, verificación QA y costos) está en [`docs/DESPLIEGUE_STAGING.md`](docs/DESPLIEGUE_STAGING.md).

---

## 15. Comandos útiles y solución de problemas

```powershell
docker compose ps                        # estado de cada servicio
docker compose logs -f worker            # procesamiento de evidencias
docker compose logs migrate              # si la API no arranca, mirar aquí primero
docker compose up -d --build api worker  # tras cambiar código del backend
docker compose up -d --build web         # tras cambiar código del panel (frontend-next)
docker compose down                      # detener (conserva datos)
docker compose down -v                   # detener y BORRAR BD y evidencias

docker compose exec db psql -U postgres -d complaince_db           # consola SQL
docker compose exec db psql -U postgres -d complaince_db -c "\dt"  # listar tablas
docker compose exec redis redis-cli ping                           # PONG

docker compose exec api alembic current                            # revisión aplicada
docker compose exec api alembic history --verbose
alembic revision --autogenerate -m "descripcion"                   # nueva migración (modo manual)
```

| Problema | Causa probable | Solución |
|---|---|---|
| Puerto 3000, 5433, 6379 u 8000 en uso | Servicios locales fuera de Docker | Detener el uvicorn/worker/Redis/PostgreSQL/Next local, o cambiar el puerto en `Proyecto/.env` |
| `bind: An attempt was made to access a socket in a way forbidden…` | Puerto reservado por Hyper-V/WSL (Windows) | Cambiar el puerto en `Proyecto/.env` (`WEB_PORT`, `API_PORT`, …); ver 12.1 |
| El panel muestra "Esta evaluación todavía no tiene resultados" | La evaluación no tiene resumen | Completar el cuestionario o llamar `POST /api/evaluaciones/{id}/cerrar` |
| `worker` se reinicia en bucle | Falta `ENTITY_MAP_KEY` o `GROQ_API_KEY`, o el modelo de spaCy | `docker compose logs worker` |
| `migrate` falla | Error de migración o BD no disponible | `docker compose logs migrate` |
| 503 `AUTH_NO_CONFIGURADA` | Falta `AUTH_SECRET` | Agregarla al `.env` y `docker compose up -d` |
| La app no arranca tras definir plazos ARCOP | Variable con `=` vacío | Comentarla o poner un número |
| `ConnectionDoesNotExistError` (asyncpg) | `localhost` resuelve a IPv6 | Usar `127.0.0.1` |
| `404 model does not exist` (Groq) | Modelo deprecado | `LLM_MODEL=openai/gpt-oss-safeguard-20b` |
| `ModuleNotFoundError: No module named 'app'` | Carpeta equivocada | Ejecutar desde `backend/` |
| `column "Matriz_controles_id_control" does not exist` | PostgreSQL pasa a minúsculas | Envolver en comillas dobles |
| `-Form` no se reconoce | PowerShell 5.1 | Usar `curl.exe -F "file=@archivo"` |
| «Entorno de desarrollo: el correo… quedó guardado en el servidor» | `CORREO_MODO=archivo` (por defecto) | Configurar SMTP (12.1, paso 4) y `docker compose up -d --force-recreate api` |
| «No pudimos enviar el correo» + `SSLCertVerificationError` en `docker compose logs api` | Avast/AVG u otro antivirus intercepta el correo cifrado | Desactivar «Analizar correo saliente (SMTP)» en el Escudo de correo |
| `SMTPAuthenticationError` / `535` | Clave que no es de aplicación, con espacios o de otra cuenta | Crear una contraseña de aplicación con la misma cuenta de `SMTP_USUARIO` |
| `TimeoutError` al enviar | La red bloquea el puerto 587 | Otra red, o `SMTP_PORT=465`, `SMTP_SSL=true`, `SMTP_STARTTLS=false` |
| La comparativa no muestra el promedio del rubro | Menos de `K_ANONIMATO_MINIMO` (5) empresas distintas del rubro, o el benchmark no se recalculó tras la migración HU-10 | Es lo esperado (HU-10: se muestra la advertencia y la meta). Tras migrar: `docker compose exec worker python scripts/recalcular_benchmark.py`; en demos locales `K_ANONIMATO_MINIMO=1` |
| Caracteres raros (`polÃtica`) | Codificación de la consola | Verificar en `psql`; suele ser solo visual |

---

## 16. Backlog, deuda técnica y riesgos

Priorizado para la planificación del próximo sprint. Los números se usan como referencia en el resto del documento.

### Prioridad alta

| # | Ítem | Impacto | Propuesta |
|---|---|---|---|
| 1 | **No hay endpoints para crear invitaciones (`usuario_temporal`) ni evaluaciones** | El flujo completo depende de SQL manual | `POST /api/invitaciones` (admin) con código aleatorio y `POST /api/evaluaciones` (referente) |
| 2 | ~~Solo `/api/arcop` y `/api/auth/me` exigen token~~ **Resuelto en HU-20:** todas las rutas de datos exigen el token del dueño o de un admin, con prueba de autorización por endpoint | — | El panel interno del frontend necesita el login del admin |
| 3 | **Frontend parcialmente integrado:** el panel (HU-13) ya consume la API real en `frontend-next/`, pero cuestionario, informe, formación y backoffice existían solo en el prototipo archivado (`Extras/frontend-prototipo/`, con `store.js` simulado y reglas distintas: `revision` 50 vs 0; escalas de nivel distintas) | Las demás pantallas no reflejan los resultados reales | Migrar esas páginas a `frontend-next/` reutilizando `lib/api.ts` y `lib/madurez.ts` (niveles del backend) |
| 4 | ~~Benchmark siempre vacío~~ **Resuelto:** `POST /completar` marca la evaluación como `completada` y recalcula el benchmark (HU-12) | — | Pendiente decidir si se permite reabrir una evaluación completada |
| 5 | ~~Falta `backend/.dockerignore`~~ **Resuelto (15-oct):** `backend/download` renombrado a `backend/.dockerignore`; el `.env` y el `venv` ya no entran en la imagen | — | — |

### Prioridad media

| # | Ítem | Propuesta |
|---|---|---|
| 6 | Las evidencias se leen como texto UTF-8: PDF, DOCX e imágenes llegan al LLM como texto ilegible. La API no limita tamaño (solo el BFF de Next, 12 MB) ni tipo MIME | Extracción de texto por tipo (pypdf, python-docx, OCR opcional), lista blanca de MIME y tope de tamaño en la API |
| 7 | ~~`GET /evaluaciones/{id}/controles-aplicables` p95 542 ms~~ **Resuelto en HU-01** (consulta única + caché del catálogo): p95 24,1 ms en la medición live del 16-oct | — |
| 8 | NER: los falsos positivos "la Ley 21" y "Presidenta del Directorio" se corrigieron en T-04. Queda abierto: textos **completamente en mayúsculas** con frases largas, donde spaCy puede no aislar el nombre | Regla adicional para texto 100 % en mayúsculas; ampliar `ner_gold.jsonl` con casos reales anonimizados |
| 9 | `LLM_PRECIO_*` en 0: el costo estimado sale siempre 0 | Cargar precios del modelo en el `.env` |
| 10 | Decisiones ARCOP abiertas: plazos y qué pasa al vencer, código de invitación, límite de intentos de login, verificación de identidad, duplicados | Definir con el PO; detalle en `Extras/Cambios/backend/CAMBIOS_ARCOP.md` |
| 18 | Decisiones HU-12 a validar con el PO: meta de cumplimiento (75), mínimo de 3 evaluaciones para mostrar el promedio del rubro, cortes de nivel del plan (50/75) y contenido de las 12 rutas (objetivos, horas, modalidad) | Revisarlos con el equipo; se ajustan por `.env` o en la tabla `ruta_formativa` |
| 11 | Sin CRUD de administración de matriz y árbol en el backend (solo en la demo) ni versionado de controles | Endpoints admin + migración de versionado |

### Prioridad baja

| # | Ítem |
|---|---|
| 12 | ~~Limpieza de archivos sobrantes~~ **Resuelto (22-oct):** un solo `.env`, sin `test_defectos_api.py` ni `document_validator_port.py`, sin `langchain-*` en `requirements.txt`. Se conserva la migración vacía `b25cc4eed4b0` porque está en medio de la cadena de Alembic (borrarla rompe las BD ya migradas) |
| 13 | `seguridad.py` se sincroniza a mano con el repo ComplianceAI-Prompt-Injection: riesgo de divergencia (evaluar paquete compartido o submódulo). Además, su regex de correo no acepta tildes (`matías.díaz@…` queda en parte visible en los extractos de eventos de seguridad): corregirla allá, como se hizo en `ner_sanitizer.py` |
| 14 | Fechas de respuestas/evidencias en `Date` (sin hora): limita la trazabilidad fina |
| 15 | Credenciales por defecto de PostgreSQL (`postgres`/`1234`) en el compose: aceptables solo en desarrollo |
| 16 | ~~Pipeline CI/CD y entorno de staging~~ **Resuelto en HU-23** (ver [14.1](#141-integración-y-despliegue-continuo-hu-23)). Queda activar la protección de `main` con el check **CI aprobado** |
| 17 | Correo del informe con una cuenta Gmail: para el piloto conviene un remitente del dominio (SMTP del proveedor o servicio transaccional) con SPF/DKIM, para que no caiga en spam |

---

## 17. Documentación complementaria

| Documento | Contenido |
|---|---|
| [`Extras/Cambios/backend/CAMBIOS_ARCOP.md`](../Extras/Cambios/backend/CAMBIOS_ARCOP.md) | Historia de usuario ARCOP: archivos, acceso, anonimización, plazos, endpoints y decisiones pendientes |
| [`reporte_latencia_live_c10.md`](../Extras/Evidencias/reporte_latencia_live_c10.md) | Último reporte de latencia de la API |
| [`Extras/Cambios/backend/CAMBIOS_HU06.md`](../Extras/Cambios/backend/CAMBIOS_HU06.md) | HU-06: anonimización antes de persistir, decisiones del PO, excepción ARCOP y migración de datos existentes |
| [`Extras/Cambios/backend/CAMBIOS_T04.md`](../Extras/Cambios/backend/CAMBIOS_T04.md) | T-04: optimización del motor NER (cambios, mediciones antes/después, decisión sobre ONNX) |
| [`Extras/Cambios/CAMBIOS_HU12.md`](../Extras/Cambios/CAMBIOS_HU12.md) | HU-12, arreglo de la comparativa y PDF/correo: archivos, cómo aplicarlo, verificación y decisiones para el PO |
| `frontend-next/docs/Guia_envio_informe_por_correo.pdf` | Guía para el equipo: configurar Gmail SMTP, el `.env`, el antivirus y solucionar errores del envío por correo |
| [`CAMBIOS_HU13.md`](../Extras/Cambios/frontend/CAMBIOS_HU13.md) | HU-13: qué se agregó, cómo aplicarlo y qué se verificó |
| [`HU-13_HANDOFF.md`](../Extras/Cambios/frontend/HU-13_HANDOFF.md) | Especificación de diseño del panel: criterios de aceptación, tokens, layout, componentes y casos borde |
| [`frontend-next/docs/ACCESIBILIDAD.md`](frontend-next/docs/ACCESIBILIDAD.md) | Auditoría WCAG 2.1 AA del panel |
| `../Documentos/Fase 1/Presentación Proyecto.pdf` | Presentación: cliente, problema, solución, equipo, sprints, TRL |
| `../Documentos/Fase 1/Bitácora CPCITT 2025-2.pdf` | Bitácora del proyecto |
| `../Documentos/Fase 1/`, `../Documentos/Fase 2/` | Guía del estudiante, evaluaciones formativas, autoevaluaciones y diarios de reflexión por integrante |
| `../Extras/Guia_ComplianceAI_PromptInjection.docx.pdf` | Guía del módulo anti prompt-injection |
| [`../Extras/README.md`](../Extras/README.md) | Qué hay en `Extras/` (documentos de cambios por HU, evidencias y prototipo archivado) y la regla para los documentos nuevos |
| [`CAMBIOS_HU20.md`](../Extras/Cambios/backend/CAMBIOS_HU20.md) | HU-20: matriz de autorización, interruptor de desarrollo y ajustes a las pruebas |
| [`docs/DESPLIEGUE_STAGING.md`](docs/DESPLIEGUE_STAGING.md) | HU-23: CI/CD, ambiente de staging en Azure, datos semilla, secretos, vuelta atrás, verificación QA y costos |
| [`CAMBIOS_HU23.md`](../Extras/Cambios/backend/CAMBIOS_HU23.md) | HU-23: estado anterior, archivos, decisiones y pendientes del pipeline |

---

**Licencia:** proyecto académico (Capstone APT122, Duoc UC) desarrollado para Therion Labs.
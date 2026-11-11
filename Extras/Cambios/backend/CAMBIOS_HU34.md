# HU-34 · Mapa de datos personales (backend)

*Como Usuario Definitivo (cliente), quiero mapear los sistemas, bases de datos y flujos donde mi empresa trata datos personales, para saber qué datos tengo, de quién, dónde están y con quién los comparto, y usarlo como base del RAT y del RoPA.*

La plataforma ya le decía a la empresa qué brechas tiene en gobernanza de IA y protección de datos, pero no tenía dónde registrar **qué datos personales trata y por dónde viajan**. Ese inventario es el punto de partida de casi todo lo que viene (registro de actividades de tratamiento, RoPA, evaluaciones de impacto, respuesta a incidentes), por eso esta historia se diseñó como base: un catálogo común, un modelo relacional que el RAT podrá referenciar por id, reglas de dominio puras y versiones inalterables.

## Decisiones principales

**1. Un catálogo común, en código y versionado.** `app/domain/catalogo_tratamiento.py` es la única fuente de las categorías de datos (19, con 8 sensibles según la definición de la Ley 21.719: origen étnico o racial, afiliación política/sindical/gremial, situación socioeconómica, convicciones, salud, perfil biológico, biometría, vida sexual/orientación/identidad de género), las categorías de titulares (13, con `nna` y `posible_nna`), los tipos y subtipos de elementos, los roles de terceros, las garantías de transferencia, frecuencias, medios y países (ISO 3166-1). El RAT guardará **los mismos códigos**: un elemento del mapa y una actividad del RAT se podrán cruzar sin traducciones. Los códigos no se renombran ni se borran (se retiran con `vigente=False`); una prueba vigila que los principales existan.

**2. Las transferencias internacionales se calculan, no se declaran.** Un flujo es transferencia internacional cuando el país del destino está fuera de Chile y es distinto del país del origen (`analisis.es_internacional`). Los sistemas y bases internos sin país se asumen en Chile; los terceros y los servicios en la nube (SaaS, colaboración, almacenamiento en la nube, bases vectoriales) sin país quedan «sin informar» y generan un hallazgo. Así nadie puede olvidar marcar una transferencia: basta con registrar dónde está cada cosa.

**3. Minimización.** El mapa describe sistemas de la **organización**, no personas: guarda categorías, no datos de titulares. El responsable interno es un cargo o área; los textos libres se rechazan (422 con el campo) si traen un correo, un RUT o un teléfono (`modelo.contiene_contacto`). Las tablas quedaron clasificadas en el inventario de T-06 con control de contenido `pii`. El audit log nunca lleva nombres ni textos del mapa: solo ids, tipos, campos cambiados y conteos.

**4. Cada cambio es una versión inalterable.** `mapa_datos_version` guarda la instantánea **completa** (elementos y flujos), su huella SHA-256 (independiente del orden) y las diferencias con la anterior, con un resumen legible («Se agregó el tercero «Courier»»). En PostgreSQL un trigger rechaza `UPDATE`. La versión y el registro `mapa_datos.*` del audit log se escriben en la **misma transacción** que el cambio: no hay cambio sin versión ni versión sin cambio (si un PATCH no cambia nada, no se crea versión). Restaurar una versión crea una nueva (nada se sobrescribe) y recrea los elementos eliminados **con su mismo id**, para no romper las referencias que tendrá el RAT.

**5. Concurrencia optimista.** Toda edición manda la versión del mapa que vio el usuario; la fila de `mapa_datos` se bloquea (`SELECT … FOR UPDATE`) mientras se aplica el cambio. Si otra pestaña guardó antes: 409 `MAPA_DESACTUALIZADO` con `version_actual`, y el intento queda en el audit log como `mapa_datos.cambio_rechazado`.

## Estructura

| Capa | Archivo | Qué hace |
|---|---|---|
| Dominio | `app/domain/catalogo_tratamiento.py` | Catálogo común con el RAT/RoPA y `catalogo_dict()` para la interfaz |
| Dominio | `app/domain/mapa_datos/modelo.py` | `Elemento`, `Flujo`, validación y normalización (`normalizar_elemento`, `normalizar_flujo`, ediciones parciales) |
| Dominio | `app/domain/mapa_datos/analisis.py` | Transferencias, resumen, completitud, **hallazgos de riesgo**, filtros del mapa y base para el RAT |
| Dominio | `app/domain/mapa_datos/versiones.py` | Instantánea, huella, diferencias y resumen legible |
| Dominio | `app/domain/mapa_datos/disposicion.py` | Disposición por capas del diagrama (la misma que el panel) |
| Aplicación | `app/application/mapa_datos/plantillas.py` | 8 plantillas por rubro + base común |
| Aplicación | `app/application/mapa_datos/sugerencias.py` | Sugerencias desde las respuestas F1–F7 de la evaluación |
| Aplicación | `app/application/mapa_datos/pdf_mapa.py` | Informe PDF (reportlab) y cuerpo del correo |
| Aplicación | `app/application/use_cases/mapa_datos.py` | Casos de uso: CRUD, plantillas, sugerencias, versiones, restauración e informe |
| API | `app/api/routes/mapa_datos.py` | 20 rutas bajo `/api/mapa-datos`, todas con `empresa_con_servicio` |
| Modelos | `app/domain/models/mapa_datos.py` | `mapa_datos`, `mapa_elemento`, `mapa_flujo`, `mapa_datos_version` |

## Hallazgos de riesgo

Se calculan con cada lectura del mapa (no se guardan) y se ordenan por severidad. Cada uno trae detalle, qué hacer, referencia y los elementos o flujos afectados (el panel los lleva al mapa):

| Hallazgo | Severidad | Referencia |
|---|---|---|
| Transferencia internacional sin garantía con datos sensibles o de NNA | Crítica | Ley 21.719, arts. 27 y 28 |
| Proveedor de IA externo que recibe datos sensibles o de NNA | Crítica | Ley 21.719, arts. 16 y 16 quater · OWASP LLM |
| Terceros que reciben datos sin contrato confirmado (crítica si reciben sensibles) | Alta / Crítica | Ley 21.719, art. 15 bis |
| Transferencia internacional sin garantía | Alta | Ley 21.719, arts. 27 y 28 |
| Datos sensibles que viajan sin cifrar | Alta | Ley 21.719, art. 14 quinquies |
| Tratamiento de datos de niños, niñas y adolescentes | Media | Ley 21.719, art. 16 quater |
| Datos sensibles sin responsable interno | Media | Principio de responsabilidad |
| Elementos sin país de alojamiento | Media | Arts. 27 y 28 |
| Cifrado desconocido en flujos con datos sensibles | Media | Art. 14 quinquies |
| Elementos o flujos sin categorías · elementos aislados | Baja | Inventario |

Los terceros con rol «destinatario por obligación legal» (SII, previsión, reguladores) no exigen contrato. Las referencias son orientativas y el informe lo aclara.

## Plantillas y sugerencias (criterio 4)

Las **plantillas** (`banca`, `salud`, `retail`, `telecomunicaciones`, `educacion`, `tecnologia`, `manufactura`, `general`) suman la base común (correo y colaboración, remuneraciones, base del personal, previsión y salud, banco de remuneraciones, respaldos) más lo típico del rubro. La recomendada se elige por palabras clave del nombre del rubro de la empresa (los rubros los mantiene el equipo interno y pueden crecer). Aplicar una plantilla **nunca reemplaza**: omite lo que ya existe por clave o por nombre y tipo, y todo lo nuevo queda `pendiente_revision` con origen `plantilla`. Una prueba verifica que cada elemento y flujo de cada plantilla pase la misma validación que el usuario.

Las **sugerencias** leen las respuestas F1–F7 de la evaluación más reciente de la empresa:

| Respuesta | Sugerencia |
|---|---|
| F4 (LLM / IA generativa / RAG) | Flujo hacia el **proveedor de modelos de lenguaje** (tercero `proveedor_ia`, Estados Unidos, encargado) y base vectorial para RAG |
| F3 sin F4 (IA de terceros en la nube) | Flujo hacia el servicio de IA en la nube |
| F2 (datos sensibles) | Repositorio de datos sensibles |
| F5 (agentes conectados a sistemas) | Agente de IA con flujos desde el ERP/CRM existentes |
| F6 (decisiones que afectan a personas) | Motor de decisiones automatizadas |
| F7 (modelos propios) | Datos de entrenamiento y plataforma de entrenamiento |

F1 = No (no usa IA) no sugiere nada. Si el mapa ya tiene un «Sistema con IA», el flujo sale de él; al aceptar, la empresa puede elegir otro elemento de origen (`origen_id`). Una sugerencia desaparece al aplicarse (por la clave de su elemento principal) o al descartarse (`mapa_datos.sugerencias_descartadas`, se pueden restablecer). Descartar no cambia el contenido del mapa: no crea versión, pero queda en el audit log.

## Informe PDF y correo (criterio 3)

`GET /api/mapa-datos/informe/pdf` acepta los mismos filtros del mapa navegable (`sensibles`, `nna`, `internacional`, `tercero`, `pais`, `tipo`). A4 horizontal: portada (empresa, rubro, versión, huella, vista), 7 indicadores, completitud, hallazgos por severidad y aviso legal; **diagrama** (misma disposición del panel, con puntos de paso para que las flechas no pasen detrás de los nodos) y leyenda; hallazgos con qué hacer y referencia; inventario de sistemas y bases; terceros (rol, país, contrato, datos que reciben); flujos; **transferencias internacionales** con su garantía; **base para el RAT** (por categoría: dónde está, titulares, con quién se comparte y países); historial reciente y verificación. Con filtros, el diagrama y las tablas muestran lo filtrado y los indicadores y hallazgos siguen siendo los del mapa completo (se aclara).

`POST /api/mapa-datos/informe/enviar` envía el mismo PDF (por defecto al correo del usuario de la empresa) con `app/application/informes/correo.py`, límite de `MAPA_CORREOS_DIA_EMPRESA` por día (el cupo se devuelve si el envío falla) y respuesta con el destino enmascarado. El audit log registra la descarga y el envío sin el correo.

## Criterios de aceptación

| Criterio | Dónde se cumple | Pruebas (`tests/test_hu34_mapa_datos.py`) |
|---|---|---|
| 1. Sistemas y BD (nombre, tipo, proveedor, país, responsable), flujos, terceros y transferencias internacionales | `modelo.py`, `analisis.derivados_flujo`, rutas `/elementos` y `/flujos` | `test_elemento_valido…`, `test_elemento_invalido…`, `test_transferencia_internacional…`, `test_api_crear_editar_eliminar…` |
| 2. Categorías de datos (sensibles) y de titulares (NNA) con catálogo común con el RAT | `catalogo_tratamiento.py`, `GET /catalogo` | `test_catalogo_comun…`, `test_catalogo_estable_para_el_rat` |
| 3. Mapa navegable con filtros, exportable a PDF y PNG | `analisis.aplicar_filtros`, `disposicion.py`, `pdf_mapa.py`, `/informe/*` (el PNG lo genera el panel) | `test_filtros…`, `test_disposicion…`, `test_informe_pdf_completo_y_filtrado`, `test_api_plantilla_sugerencias_e_informe` |
| 4. Inicio desde plantilla por rubro y desde la evaluación | `plantillas.py`, `sugerencias.py`, `/plantillas/aplicar`, `/sugerencias/*` | `test_plantillas_coherentes…`, `test_plantilla_recomendada_por_rubro`, `test_llm_externo_sugiere…`, `test_sugerencia_usa_el_sistema_existente…`, `test_api_plantilla_sugerencias_e_informe` |
| 5. Cada cambio versionado y en el audit log; solo con contrato vigente | `versiones.py`, `mapa_datos_version` (trigger), `Accion.MAPA_*`, `empresa_con_servicio` | `test_versiones…`, `test_api_crear_editar_eliminar_con_versiones_y_audit_log`, `test_api_solo_usuario_definitivo_con_contrato_vigente` |

La matriz de autorización de HU-20 y la prueba de rutas pagadas de HU-30 incluyen las 20 rutas nuevas. La parte pura (40 pruebas) corre sin base de datos; las de API usan el arnés SQLite en proceso de HU-27.

## Configuración (`Proyecto/.env`, opcionales)

| Variable | Por defecto | Para qué |
|---|---|---|
| `MAPA_MAX_ELEMENTOS` | 300 | Elementos por mapa (el mapa completo viaja en cada respuesta y se dibuja en el navegador) |
| `MAPA_MAX_FLUJOS` | 800 | Flujos por mapa |
| `MAPA_CORREOS_DIA_EMPRESA` | 5 | Envíos del informe por correo por empresa y día |

## Base de datos

Migración `b9e3d7a2c5f1_hu34_mapa_datos.py` (revisa `e7c3a9f2b6d4`, la de HU-25): crea `mapa_datos` (única por empresa), `mapa_elemento` (CHECK de tipo, origen, país ISO y rol solo para terceros; clave única por mapa), `mapa_flujo` (CHECK de extremos distintos, `ON DELETE CASCADE`) y `mapa_datos_version` (número único por mapa, CHECK de acción, trigger de inalterabilidad en PostgreSQL). El rol `complianceia_app` recibe los permisos por los `DEFAULT PRIVILEGES` de HU-09.

## Siguiente paso natural

El RAT puede crear sus actividades referenciando `mapa_elemento.id` y reutilizando `base_rat()` como punto de partida (categorías por sistema, titulares, destinatarios y países ya calculados).

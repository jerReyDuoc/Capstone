# HU-37 · Informe RoPA desde el registro de actividades — cambios de backend

> Como Usuario Definitivo (cliente), quiero generar el informe RoPA desde el mismo registro, para responder a
> clientes, matrices o socios que piden ese formato sin rehacer el trabajo.

## Decisiones del PO aplicadas

- El formato del art. 30 se usa como **estándar de estructura**, no como ley: ni la interfaz ni el PDF/Excel
  mencionan RGPD, Unión Europea ni representante en la UE. Sin marca de adecuación en las transferencias.
- Solo entran actividades con **versión vigente**; las demás se cuentan (`excluidas`) y no se muestran.
- Un archivo con dos partes (como responsable / como encargado); se puede generar solo una.
- Los datos que el registro no tiene se **guardan y reutilizan**.

## Criterios de aceptación

| Criterio | Dónde |
|---|---|
| C1 · Desde el RAT vigente, sin reingresar datos; cada campo traducido | `app/application/ropa/informe.py` (`armar`, `campos_responsable`, `campos_encargado`). Parte de `InformeRatCasos._fuentes` + `rat/informe.armar` y usa solo `origen == "vigente"` |
| C2 · Dos vistas según el rol de cada actividad | `contenido.rol` de la versión vigente; encargado agrupado por `responsable_mandante` (clave normalizada) |
| C3 · En español; lo que falta se pide antes de generar | `app/domain/ropa/datos.py` (`normalizar`, `faltantes`); 422 `ROPA_DATOS_INCOMPLETOS` |
| C4 · PDF y XLSX con fecha, versión y aviso legal; Mis documentos y audit log | `pdf_ropa.py`, `xlsx_ropa.py`, `AVISO_ROPA`; `documento_empresa` tipos `ropa_pdf`/`ropa_xlsx`; acciones `ropa.*` |

## Archivos

**Nuevos**
- `app/domain/ropa/datos.py` — validación de contacto (correo, teléfono, cargo del delegado sin correos), merge de
  organizaciones por clave, `faltantes()` por parte y `texto_faltantes()`.
- `app/application/ropa/informe.py` — traducción RAT → RoPA, huella (versiones vigentes + partes + datos de
  contacto, no la fecha), código `CIA-ROPA-AAAA-NNNNNN-D`, nombre de archivo, vista previa para el panel.
- `app/application/ropa/pdf_ropa.py` — portada (empresa, RUT, código, versión, fecha, idioma, partes, aviso legal),
  Organización, Como responsable, Como encargado (por organización) y Transferencias.
- `app/application/ropa/xlsx_ropa.py` — hojas Portada, Organización, Como responsable, Como encargado,
  Transferencias y Aviso legal. Sin fórmulas (inyección en planillas).
- `app/application/use_cases/informe_ropa.py` — `listar`, `guardar_datos`, `emitir` (reutiliza si nada cambió,
  límite diario `RAT_INFORMES_DIA_EMPRESA`), `descargar` (verifica el hash).
- `app/api/routes/informe_ropa.py` — `GET/POST /api/registro-actividades/ropa`, `PATCH …/ropa/datos`,
  `GET …/ropa/{id}/descarga`. Contrato vigente obligatorio.
- `app/domain/models/ropa.py` — `RopaDatos` (contenido JSON **cifrado**) y `RopaInforme`.
- `migrations/versions/c5e8a2d7f3b1_hu37_informe_ropa.py` — tablas, índice, tipos de documento y trigger de
  inmutabilidad en PostgreSQL. **down_revision = a3f9c1e7b5d2** (HU-39): si tu head es otro, ajústalo.
- `tests/test_hu37_informe_ropa.py` — 14 pruebas de lógica + 2 de API en proceso.

**Modificados**
- `app/core/cifrado_columnas.py` — `TextoCifradoRopa` (subclave `ropa`, misma excepción documentada que los
  borradores de HU-16: el RoPA exige datos de contacto).
- `app/core/catalogo_datos_personales.py` — clasificación de `ropa_datos` (contacto, cifrado) y `ropa_informe`
  (T-06 falla si una columna nueva no está clasificada).
- `app/domain/models/documento_empresa.py`, `app/domain/models/__init__.py` — tipos y modelos nuevos.
- `app/application/use_cases/documentos_empresa.py` — Mis documentos lista los RoPA en `registro_actividades`
  con `{ropa: {codigo, version, partes, …}}`.
- `app/infrastructure/repositories/bitacora_repository.py` — `ROPA_DATOS_ACTUALIZADOS` (modificación),
  `ROPA_INFORME_GENERADO` (creación), `ROPA_INFORME_DESCARGADO` (acceso).
- `app/main.py` — registra el router.
- `tests/test_hu20_autorizacion.py` — las 4 rutas nuevas quedan clasificadas en `RUTAS_CON_TOKEN_PROPIO` (sin token: 401), junto a las del informe del registro. Corrige `test_todas_las_rutas_estan_clasificadas`.

## Diferencia con el plan aprobado

El plan proponía dos tablas (`ropa_datos` y `ropa_mandante`). Quedó **una sola** (`ropa_datos`) con todo el
contacto en un JSON **cifrado en reposo**: la prueba de minimización (T-06) exige control de contenido en las
columnas JSON y estos datos llevan correos a propósito; cifrarlos sigue el precedente de los borradores (HU-16).

## Privacidad

- La bitácora nunca recibe direcciones, correos ni teléfonos: solo nombres de campos, ids, versión, partes y
  conteos (la prueba de API lo verifica).
- En la BD el contenido queda con prefijo `enc:v1:` (la prueba de API lo verifica con SQL directo).

## Cómo probar

```bash
docker compose exec backend alembic upgrade head
docker compose exec backend pytest tests/test_hu37_informe_ropa.py tests/test_hu36_informe_rat.py tests/test_t06_minimizacion.py tests/test_hu20_autorizacion.py tests/test_hu30_contrato.py -q
```

En el entorno de desarrollo de esta entrega (sin acceso a PyPI) se ejecutaron las pruebas de lógica pura
(`pytest --noconftest`: 63 pasan en HU-35/36/37). Las de API en proceso y T-06 requieren SQLAlchemy/aiosqlite:
**correrlas en Docker antes de integrar**.

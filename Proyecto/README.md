# Sistema de Validación de Evidencias con LLM

Backend con FastAPI que recibe evidencias de archivos, las valida con un LLM y actualiza automáticamente la clasificación de respuestas en un sistema de evaluación de madurez organizacional en IA.

## Descripción

El sistema implementa un flujo **sin validación humana** donde el LLM actúa como autoridad final sobre la clasificación de cada respuesta. El sistema evalúa 40 controles basados en marcos normativos (Ley chilena N.º 21.719, ISO/IEC 42001, NIST AI RMF 100-1, OWASP LLM, NIST 600-1) distribuidos en 4 dominios temáticos.

**Flujo general:**

```
Usuario responde → (elige 1 de 4 opciones)
                    ├─ Cumplido / Parcialmente → requiere evidencia → LLM valida
                    └─ No cumplido / No aplica → sin evidencia, brecha automática

Usuario sube evidencia → Worker ARQ → LLM evalúa → Backend decide → BD actualizada
```

**Principio arquitectónico clave:** el LLM **nunca** accede a la base de datos. Solo recibe texto (prompt) y devuelve JSON estructurado. El backend es el único que lee y escribe en la BD.

**Stack:** FastAPI, SQLAlchemy 2.0 async, PostgreSQL 16, Redis 7, ARQ, LangChain, Groq.

---

## Requisitos previos

| Herramienta | Versión mínima | Notas |
|---|---|---|
| Python | 3.12+ | Probado en 3.13 |
| Docker Desktop | Última | Con backend WSL 2 activado |
| PowerShell | 5.1+ | Viene por defecto en Windows 10/11 |
| Git | Opcional | Para control de versiones |

**En Windows:** durante la instalación de Python, marca **"Add Python to PATH"**.

---

## Estructura del proyecto

```
Proyecto/
├── backend/
│   ├── app/
│   │   ├── core/
│   │   │   ├── config.py              # Settings con pydantic-settings
│   │   │   └── database.py            # Engine async + Base
│   │   ├── domain/
│   │   │   ├── models/                # 12 entidades SQLAlchemy
│   │   │   │   ├── dominio.py
│   │   │   │   ├── rubro.py
│   │   │   │   ├── ruta_formativa.py
│   │   │   │   ├── usuario_temporal.py
│   │   │   │   ├── catalogo_brechas.py
│   │   │   │   ├── evaluacion.py
│   │   │   │   ├── matriz_control.py
│   │   │   │   ├── respuesta.py
│   │   │   │   ├── evidencia.py
│   │   │   │   ├── benchmark.py
│   │   │   │   └── resumen.py
│   │   │   └── ports/                 # Interfaces ABC
│   │   │       ├── file_storage_port.py
│   │   │       └── evidence_validator_port.py
│   │   ├── application/
│   │   │   ├── schemas/
│   │   │   │   ├── evidence_validation.py  # Schema del LLM
│   │   │   │   └── api_schemas.py          # Schemas de request/response
│   │   │   └── use_cases/
│   │   │       ├── create_respuesta.py
│   │   │       ├── upload_evidence.py
│   │   │       └── process_evidence.py     # Caso de uso principal
│   │   ├── infrastructure/
│   │   │   ├── llm/groq_validator.py       # Adaptador LLM
│   │   │   ├── storage/local_storage.py
│   │   │   └── repositories/
│   │   │       ├── evidencia_repository.py
│   │   │       ├── respuesta_repository.py
│   │   │       ├── evaluacion_repository.py
│   │   │       └── catalogo_repository.py
│   │   ├── api/
│   │   │   ├── routes/
│   │   │   │   ├── respuestas.py
│   │   │   │   ├── evidencias.py
│   │   │   │   ├── catalogos.py
│   │   │   │   ├── controles.py
│   │   │   │   └── evaluaciones.py
│   │   │   └── dependencies.py
│   │   ├── worker/tasks.py            # Tareas ARQ
│   │   └── main.py
│   ├── migrations/                    # Alembic
│   ├── storage/                       # Archivos subidos
│   ├── requirements.txt
│   └── .env
├── docker-compose.yml
└── README.md
```

---

## Esquema de base de datos

**12 tablas** organizadas en 4 capas:

### Catálogos (datos maestros, se llenan una vez)

| Tabla | Registros | Descripción |
|---|---|---|
| `dominio` | 4 | Dominios temáticos (Protección de Datos, Gobernanza IA, Gestión de Riesgos, Uso Responsable) |
| `rubro` | 8 | Sectores económicos (Banca, Salud, Retail, etc.) |
| `ruta_formativa` | 12 | Rutas de capacitación (3 niveles × 4 dominios) |
| `catalogo_brechas` | 40 | Brechas detectables (ERR-XXX-001 a ERR-XXX-010) |
| `matriz_controles` | 40 | Controles de evaluación (DAT-001 a SEG-010) |

### Operacionales (se crean dinámicamente)

| Tabla | Descripción |
|---|---|
| `usuario_temporal` | Usuarios invitados con expiración |
| `evaluacion` | Sesión de evaluación de un usuario |
| `respuestas` | Respuesta del usuario a un control |
| `evidencias` | Archivos subidos que respaldan respuestas |

### Analíticas (agregados, se recalculan)

| Tabla | Descripción |
|---|---|
| `benchmark` | Estadísticas por rubro y dominio |
| `resumen` | Resumen agregado por evaluación y dominio |

### Control interno

| Tabla | Descripción |
|---|---|
| `alembic_version` | Control de migraciones |

### Relaciones (12 foreign keys)

```
rubro ─┬─ usuario_temporal ── evaluacion ── respuestas ── evidencias
       └─ benchmark

dominio ─┬─ matriz_controles ── respuestas
         ├─ benchmark
         └─ resumen

ruta_formativa ── catalogo_brechas ─┬─ respuestas
                                    └─ matriz_controles

evaluacion ── resumen
```

### Modelo ER

```mermaid
erDiagram
    rubro ||--o{ usuario_temporal : "Rubro_id"
    rubro ||--o{ benchmark : "Rubro_id"
    dominio ||--o{ matriz_controles : "dominio_id"
    dominio ||--o{ benchmark : "dominio_id"
    dominio ||--o{ resumen : "dominio_id"
    ruta_formativa ||--o{ catalogo_brechas : "ruta_formativa_id"
    usuario_temporal ||--o{ evaluacion : "Usuario_temporal_id"
    evaluacion ||--o{ respuestas : "Evaluacion_id"
    evaluacion ||--o{ resumen : "Evaluacion_id"
    matriz_controles ||--o{ respuestas : "Matriz_controles_id_control"
    catalogo_brechas ||--o{ respuestas : "Catalogo_brechas_id_brecha"
    respuestas ||--o{ evidencias : "Respuestas_id_respuesta"
```

---

## Levantamiento paso a paso

### Paso 1: Clonar/ubicar el proyecto

```powershell
cd C:\Users\<usuario>\Documents\Repositorios\Capstone\Proyecto
```

### Paso 2: Crear y activar el entorno virtual

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**Si PowerShell bloquea la ejecución de scripts:**

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Paso 3: Instalar dependencias

```powershell
pip install --upgrade pip
pip install -r requirements.txt
```

**Contenido de `requirements.txt`:**

```txt
fastapi==0.115.0
uvicorn[standard]==0.32.0
sqlalchemy[asyncio]==2.0.36
asyncpg==0.30.0
psycopg2-binary==2.9.10
alembic==1.14.0
pydantic==2.10.0
pydantic-settings==2.6.0
python-multipart==0.0.12
langchain-groq==0.2.0
langchain-core==0.3.20
arq==0.26.1
redis==5.2.0
aiofiles==24.1.0
```

### Paso 4: Crear el archivo `.env`

Crea `backend\.env` con este contenido:

```env
DATABASE_URL=postgresql+asyncpg://user:password@127.0.0.1:5433/mydb
DATABASE_URL_SYNC=postgresql://user:password@127.0.0.1:5433/mydb
REDIS_URL=redis://127.0.0.1:6379
GROQ_API_KEY=gsk_tu_clave_aqui
LLM_MODEL=openai/gpt-oss-safeguard-20b
UMBRAL_CONFIANZA=0.8
STORAGE_DIR=./storage
```

**Notas importantes:**

- Usa `127.0.0.1`, **no `localhost`**. En Windows, `localhost` se resuelve primero a IPv6 y Docker solo publica IPv4.
- El puerto `5433` evita conflicto con PostgreSQL nativo de Windows.
- `GROQ_API_KEY` se obtiene en [console.groq.com/keys](https://console.groq.com/keys).
- `LLM_MODEL` debe ser un modelo con soporte de `structured_outputs`. `openai/gpt-oss-safeguard-20b` funciona.

### Paso 5: Configurar `docker-compose.yml`

```yaml
version: '3.8'

services:
  db:
    image: postgres:16
    environment:
      POSTGRES_USER: user
      POSTGRES_PASSWORD: password
      POSTGRES_DB: mydb
    ports:
      - "5433:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U user -d mydb"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5

volumes:
  postgres_data:
```

### Paso 6: Levantar Docker

```powershell
cd ..
docker-compose up -d
docker-compose ps
```

Ambos servicios deben estar `Up (healthy)`.

### Paso 7: Aplicar migraciones

```powershell
cd backend
.\venv\Scripts\Activate.ps1
alembic upgrade head
```

Verifica las 12 tablas:

```powershell
docker exec -it proyecto-db-1 psql -U user -d mydb -c "\dt"
```

### Paso 8: Levantar los servicios (3 terminales)

**Terminal 1 — Docker** (ya corriendo).

**Terminal 2 — FastAPI:**

```powershell
cd C:\Users\<usuario>\Documents\Repositorios\Capstone\Proyecto\backend
.\venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8000
```

**Terminal 3 — Worker ARQ:**

```powershell
cd C:\Users\<usuario>\Documents\Repositorios\Capstone\Proyecto\backend
.\venv\Scripts\Activate.ps1
arq app.worker.tasks.WorkerSettings
```

---

## Reglas de negocio

### Clasificaciones posibles

El usuario elige **1 de 4 opciones** al responder un control:

| Clasificación | Valor en BD | ¿Requiere evidencia? | ¿Activa LLM? | ¿Asigna brecha? |
|---|---|---|---|---|
| Cumplido | `cumplido` | Sí | Sí | Solo si LLM lo degrada |
| Parcialmente cumplido | `parcialmente_cumplido` | Sí | Sí | Solo si LLM lo degrada |
| No cumplido | `no_cumplido` | No | No | **Sí, directo** |
| No aplica | `no_aplica` | No | No | No |

### Reglas de decisión del LLM

1. **Umbral de confianza:** si `confianza < 0.8` → fallback a la clasificación del usuario.
2. **Degradación:** si el LLM detecta que la evidencia no alcanza el nivel declarado, degrada la clasificación.
3. **Asignación de brecha:** cuando la clasificación final sea `no_cumplido`, el backend asigna automáticamente la brecha del control (regla de negocio, no del LLM).

### Principio de separación LLM/Backend

```
┌──────────────────────────────────────────────────────────┐
│  BACKEND (única capa con acceso a BD)                    │
│  - Lee control, respuesta, brecha, contenido del archivo │
│  - Construye el prompt                                   │
│  - Envía al LLM vía HTTPS                                │
│  - Recibe JSON estructurado                              │
│  - Aplica reglas de negocio                              │
│  - Escribe en la BD                                      │
└──────────────────────────┬───────────────────────────────┘
                           │
                  ┌────────▼────────┐
                  │      LLM        │
                  │  (solo texto)   │
                  │  Sin BD, sin    │
                  │  estado, sin    │
                  │  credenciales   │
                  └─────────────────┘
```

**El LLM:**
- Solo recibe texto y devuelve JSON validado con Pydantic.
- No tiene acceso a la BD ni credenciales.
- No asigna brechas (regla de negocio del backend).
- No tiene memoria entre llamadas.

---

## Endpoints disponibles

### Sistema

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/health` | Health check |
| GET | `/docs` | Documentación interactiva (Swagger UI) |

### Catálogos (sin paginación)

| Método | Ruta | Devuelve |
|---|---|---|
| GET | `/api/dominios` | Los 4 dominios |
| GET | `/api/rubros` | Los 8 rubros |
| GET | `/api/rutas-formativas` | Las 12 rutas |
| GET | `/api/brechas` | Las 40 brechas con ruta anidada |

### Controles (sin paginación)

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/api/controles` | Los 40 controles con dominio y brecha anidados |
| GET | `/api/controles?dominio_id={id}` | Filtrar por dominio |
| GET | `/api/controles?criticidad={Alta\|Media\|Baja}` | Filtrar por criticidad |
| GET | `/api/controles/{id}` | Detalle de un control |

### Respuestas

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/api/respuestas/` | Crear respuesta |
| GET | `/api/respuestas/{id}` | Consultar respuesta + evidencias |

### Evidencias

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/api/respuestas/{id}/evidencias` | Subir evidencia (202 Accepted) |
| GET | `/api/evidencias/{id}` | Consultar evidencia |

### Evaluaciones (con paginación)

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/api/evaluaciones?page=1&size=20` | Lista paginada |
| GET | `/api/evaluaciones/{id}` | Detalle |
| GET | `/api/evaluaciones/{id}/respuestas?page=1&size=20` | Respuestas paginadas |

**Parámetros de paginación:**

- `page` (int, ≥1): número de página, empieza en 1.
- `size` (int, 1-100): registros por página.
- Respuesta incluye: `{items, total, page, size, pages}`.

---

## Probar el flujo completo

### Preparar datos base

```powershell
# Usuario temporal
docker exec -it proyecto-db-1 psql -U user -d mydb -c "INSERT INTO usuario_temporal (fecha_expiracion, email, validacion_invitacion, `"Rubro_id`") VALUES ('2027-12-31', 'test@example.com', 'S', 6);"

# Evaluación
docker exec -it proyecto-db-1 psql -U user -d mydb -c "INSERT INTO evaluacion (fecha_inicio, estado_progreso, `"Usuario_temporal_id`") VALUES (CURRENT_DATE, 'en_progreso', 1);"
```

### Caso 1: No cumplido (sin evidencia, brecha automática)

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/respuestas/" `
  -Method Post -ContentType "application/json" `
  -Body '{"evaluacion_id": 1, "matriz_control_id": 1, "estado_clasificacion": "no_cumplido", "justificacion": "No tenemos politica formal."}'
```

Verifica:

```powershell
docker exec -it proyecto-db-1 psql -U user -d mydb -c "SELECT id_respuesta, estado_clasificacion_final, `"Catalogo_brechas_id_brecha`" FROM respuestas ORDER BY id_respuesta DESC LIMIT 1;"
```

Debe mostrar la brecha asignada (por ejemplo `1` para ERR-DAT-001).

### Caso 2: No aplica (sin brecha)

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/respuestas/" `
  -Method Post -ContentType "application/json" `
  -Body '{"evaluacion_id": 1, "matriz_control_id": 1, "estado_clasificacion": "no_aplica", "justificacion": "No aplica."}'
```

### Caso 3: Cumplido + evidencia

```powershell
# Crear respuesta
Invoke-RestMethod -Uri "http://localhost:8000/api/respuestas/" `
  -Method Post -ContentType "application/json" `
  -Body '{"evaluacion_id": 1, "matriz_control_id": 1, "estado_clasificacion": "cumplido", "justificacion": "Politica aprobada."}'
```

Anota el `id_respuesta`. Sube evidencia:

```powershell
@"
Politica de Seguridad de la Informacion
Aprobada por la Direccion General el 15 de enero de 2026
Version: 2.1. Alcance: Todas las areas.
Firma: Gerente General
"@ | Out-File -Encoding utf8 evidencia.txt

curl.exe -X POST "http://localhost:8000/api/respuestas/{ID}/evidencias" -F "file=@evidencia.txt"
```

Espera 5-10 segundos (worker procesa) y consulta:

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/respuestas/{ID}" | ConvertTo-Json -Depth 5
```

### Caso 4: Intento de evidencia sobre `no_aplica` (debe fallar 400)

```powershell
curl.exe -X POST "http://localhost:8000/api/respuestas/{ID_NO_APLICA}/evidencias" -F "file=@evidencia.txt"
```

Debe responder `HTTP 400`.

---

## Variables de entorno

| Variable | Descripción | Ejemplo |
|---|---|---|
| `DATABASE_URL` | URL asíncrona para la app | `postgresql+asyncpg://user:password@127.0.0.1:5433/mydb` |
| `DATABASE_URL_SYNC` | URL síncrona para Alembic | `postgresql://user:password@127.0.0.1:5433/mydb` |
| `REDIS_URL` | URL de Redis para ARQ | `redis://127.0.0.1:6379` |
| `GROQ_API_KEY` | API key de Groq | `gsk_...` |
| `LLM_MODEL` | Modelo a usar | `openai/gpt-oss-safeguard-20b` |
| `UMBRAL_CONFIANZA` | Umbral para aceptar LLM | `0.8` |
| `STORAGE_DIR` | Carpeta de archivos | `./storage` |

---

## Comandos útiles

### Docker

```powershell
docker-compose up -d          # Levantar servicios
docker-compose down           # Detener (mantiene datos)
docker-compose down -v        # Detener y borrar BD
docker-compose logs -f db     # Logs de PostgreSQL
docker-compose ps             # Estado de servicios
```

### PostgreSQL

```powershell
docker exec -it proyecto-db-1 psql -U user -d mydb                    # Entrar a psql
docker exec -it proyecto-db-1 psql -U user -d mydb -c "\dt"           # Listar tablas
docker exec -it proyecto-db-1 psql -U user -d mydb -c "\d respuestas" # Describir tabla

# Ver todas las FKs
docker exec -it proyecto-db-1 psql -U user -d mydb -c "
SELECT tc.table_name, kcu.column_name, ccu.table_name AS foreign_table
FROM information_schema.table_constraints AS tc
JOIN information_schema.key_column_usage AS kcu ON tc.constraint_name = kcu.constraint_name
JOIN information_schema.constraint_column_usage AS ccu ON ccu.constraint_name = tc.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY' ORDER BY tc.table_name;
"
```

### Redis

```powershell
docker exec -it proyecto-redis-1 redis-cli ping       # Debe responder PONG
docker exec -it proyecto-redis-1 redis-cli KEYS "*"   # Ver claves
```

### Alembic

```powershell
alembic current                                        # Revisión actual
alembic history --verbose                              # Historial detallado
alembic revision --autogenerate -m "descripcion"       # Nueva migración
alembic upgrade head                                   # Aplicar
alembic downgrade -1                                   # Revertir última
```

---

## Solución de problemas comunes

| Error | Causa | Solución |
|---|---|---|
| `ModuleNotFoundError: No module named 'app'` | Ejecutando desde carpeta equivocada | `cd backend` antes de ejecutar |
| `Activate.ps1 no se puede cargar` | Política de ejecución | `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser` |
| `ConnectionDoesNotExistError` con asyncpg | `localhost` resuelve a IPv6 | Usa `127.0.0.1` en `.env` |
| `port is already allocated` | Puerto 5432 en uso | Cambia a `5433:5432` en Docker |
| `404 model does not exist` (Groq) | Modelo deprecado | Cambia `LLM_MODEL` a `openai/gpt-oss-safeguard-20b` |
| `Invalid API Key` (Groq) | Key mal pasada | Verifica `$env:GROQ_API_KEY` o pásala directa |
| `-Form no se reconoce` | PowerShell 5.1 | Usa `curl.exe -F "file=@archivo"` |
| `psycopg2` no instala en Python 3.13 | Sin wheels para 3.13 | Usa `psycopg[binary]` y ajusta `DATABASE_URL_SYNC` a `postgresql+psycopg://` |
| `ForeignKeyViolation` al crear respuesta | Faltan datos padre | Inserta `usuario_temporal` y `evaluacion` primero |
| `column "Matriz_controles_id_control" does not exist` | PostgreSQL convierte a minúsculas | Envuelve en comillas dobles: `"Matriz_controles_id_control"` |
| `Revision <el anterior> referenced ... is not present` | Placeholders sin reemplazar en migración | Copia los hashes reales de `alembic history` |
| Caracteres raros (`polÃtica`) | Mojibake en consola | Verifica con `psql`; suele ser solo visual |

---

## Arquitectura de Clean Architecture

```
┌──────────────────────────────────────────────────────────┐
│  api/ (FastAPI)                                          │
│  └─ Rutas, dependencias, schemas de entrada/salida       │
├──────────────────────────────────────────────────────────┤
│  application/ (Casos de uso)                             │
│  └─ Orquesta el flujo, sin saber de FastAPI ni del LLM   │
├──────────────────────────────────────────────────────────┤
│  domain/ (Núcleo)                                        │
│  └─ Modelos y puertos (interfaces ABC)                   │
├──────────────────────────────────────────────────────────┤
│  infrastructure/ (Adaptadores)                           │
│  └─ SQLAlchemy, Groq, ARQ, storage                       │
└──────────────────────────────────────────────────────────┘
```

**Regla de dependencia:** las capas externas dependen de las internas, nunca al revés. Cambiar el LLM (Groq → OpenAI) o el storage (local → S3) es reemplazar un adaptador sin tocar la lógica de negocio.

**Ejemplo:** `ProcessEvidenceUseCase` depende de `EvidenceValidatorPort` (interfaz), no de `GroqEvidenceValidator` (implementación).

---

## Datos maestros

### 4 dominios

| ID | Nombre |
|---|---|
| 1 | Protección de Datos |
| 2 | Gobernanza de IA |
| 3 | Gestión de Riesgos |
| 4 | Uso Responsable |

### 8 rubros

| ID | Nombre |
|---|---|
| 1 | Banca y Finanzas |
| 2 | Salud |
| 3 | Retail y E-commerce |
| 4 | Telecomunicaciones |
| 5 | Educación |
| 6 | Tecnología/SaaS |
| 7 | Manufactura |
| 8 | Servicios/Otros |

### 40 controles (por dominio)

| Prefijo | Dominio | Controles |
|---|---|---|
| DAT | Protección de Datos | 10 |
| GOB | Gobernanza de IA | 10 |
| RIE | Gestión de Riesgos | 10 |
| SEG | Uso Responsable | 10 |

Marcos normativos: Ley N.º 21.719, ISO/IEC 42001, NIST AI RMF 100-1, OWASP LLM, NIST 600-1.

---

## Roadmap

- [x] Backend FastAPI con Clean Architecture
- [x] PostgreSQL con 12 tablas y 12 FKs
- [x] Worker ARQ con procesamiento asíncrono
- [x] Validador LLM con Groq
- [x] Seeds de catálogos y controles (104 registros)
- [x] Reglas de negocio (4 clasificaciones, brecha automática)
- [x] Endpoints de catálogos, controles y evaluaciones
- [x] Paginación en evaluaciones y respuestas
- [ ] Endpoints CRUD para administración de catálogos
- [ ] Panel de auditoría de divergencias
- [ ] Reportes agregados (`benchmark`, `resumen`)
- [ ] Frontend (React + TypeScript + Vite)
- [ ] Dockerización completa de backend y worker
- [ ] Tests automatizados (pytest)
- [ ] Capa de políticas de IA entre backend y LLM

---

## Licencia

Proyecto académico (Capstone).
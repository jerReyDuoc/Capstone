# Sistema de Validación de Evidencias con LLM

Backend con FastAPI que recibe evidencias de archivos, las valida con un LLM y actualiza automáticamente la clasificación de respuestas en un sistema de evaluación de madurez organizacional.

## Descripción

El sistema implementa un flujo **sin validación humana** donde el LLM actúa como autoridad final sobre la clasificación de cada respuesta:

```
Usuario → POST respuesta → POST evidencia → Worker ARQ → LLM valida → BD actualizada
```

- Si la confianza del LLM ≥ umbral (0.8) → aplica la clasificación del LLM.
- Si la confianza es menor → fallback a la clasificación del usuario.

**Arquitectura:** Clean Architecture con capas `domain`, `application`, `infrastructure` y `api`.
**Stack:** FastAPI, SQLAlchemy 2.0 async, PostgreSQL 16, Redis 7, ARQ, LangChain, Groq.

---

## Requisitos previos

| Herramienta | Versión mínima | Notas |
|---|---|---|
| Python | 3.12+ | Probado en 3.13 |
| Docker Desktop | Última | Con backend WSL 2 activado |
| PowerShell | 5.1+ | Viene por defecto en Windows 10/11 |
| Git | Opcional | Para control de versiones |

**En Windows:** durante la instalación de Python, marca **"Add Python to PATH"**. Es la causa #1 de problemas posteriores.

---

## Estructura del proyecto

```
Proyecto/
├── backend/
│   ├── app/
│   │   ├── core/
│   │   │   ├── config.py              # Settings con pydantic-settings
│   │   │   └── database.py            # engine async + Base
│   │   ├── domain/
│   │   │   ├── models/                # Entidades SQLAlchemy
│   │   │   │   ├── evaluacion.py
│   │   │   │   ├── respuesta.py
│   │   │   │   ├── matriz_control.py
│   │   │   │   └── evidencia.py
│   │   │   └── ports/                 # Interfaces (ABC)
│   │   │       ├── file_storage_port.py
│   │   │       └── evidence_validator_port.py
│   │   ├── application/
│   │   │   ├── schemas/               # Pydantic
│   │   │   └── use_cases/             # Lógica de negocio
│   │   ├── infrastructure/
│   │   │   ├── llm/groq_validator.py  # Adaptador LLM
│   │   │   ├── storage/local_storage.py
│   │   │   └── repositories/          # Acceso a BD
│   │   ├── api/routes/                # Endpoints FastAPI
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

**Si no quieres modificar la política de ejecución**, usa la ruta directa:

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
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

> **Nota:** `psycopg2-binary` es necesario para Alembic (usa conexiones síncronas), aunque la app use `asyncpg`. En Python 3.13, si `pip install psycopg2-binary` falla, usa `pip install "psycopg[binary]"` y cambia `DATABASE_URL_SYNC` a `postgresql+psycopg://...`.

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

- Usa `127.0.0.1`, **no `localhost`**. En Windows, `localhost` se resuelve primero a IPv6 y Docker solo publica IPv4, causando errores de conexión.
- El puerto `5433` (no 5432) evita conflicto con PostgreSQL nativo de Windows.
- La `GROQ_API_KEY` se obtiene en [console.groq.com/keys](https://console.groq.com/keys).

Crea también `backend\.env.example` con los mismos nombres pero valores ficticios (este sí se commitea).

### Paso 5: Configurar `docker-compose.yml`

En la raíz del proyecto:

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

Asegúrate de que **Docker Desktop esté corriendo** (ícono de ballena verde en la bandeja del sistema).

```powershell
cd ..
docker-compose up -d
docker-compose ps
```

Debes ver ambos servicios con estado `Up (healthy)`.

**Si el puerto 5432 o 5433 ya está en uso**, revisa:

```powershell
Get-Service | Where-Object { $_.Name -like "*postgres*" }
```

Si hay un PostgreSQL nativo corriendo, deténlo o cambia el puerto en `docker-compose.yml`.

### Paso 7: Aplicar migraciones de Alembic

```powershell
cd backend
.\venv\Scripts\Activate.ps1
alembic upgrade head
```

Verifica las tablas creadas:

```powershell
docker exec -it proyecto-db-1 psql -U user -d mydb -c "\dt"
```

Debes ver: `alembic_version`, `evaluacion`, `evidencias`, `matriz_controles`, `respuestas`.

### Paso 8: Levantar los servicios (3 terminales)

**Terminal 1 — Docker (ya corriendo del Paso 6):**

Verifica con `docker-compose ps` desde la raíz del proyecto.

**Terminal 2 — FastAPI:**

```powershell
cd C:\Users\<usuario>\Documents\Repositorios\Capstone\Proyecto\backend
.\venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8000
```

Verifica en [http://localhost:8000/health](http://localhost:8000/health) → debe devolver `{"status":"ok"}`.

Documentación interactiva: [http://localhost:8000/docs](http://localhost:8000/docs).

**Terminal 3 — Worker ARQ:**

```powershell
cd C:\Users\<usuario>\Documents\Repositorios\Capstone\Proyecto\backend
.\venv\Scripts\Activate.ps1
arq app.worker.tasks.WorkerSettings
```

Salida esperada:

```
Starting worker for 1 functions: process_evidence_task
redis_version=7.4.x mem_usage=1.x M clients_connected=2 db_keys=0
```

**No cierres ninguna de las 3 terminales.** Deben quedarse corriendo en background.

---

## Probar el flujo completo

### Preparar datos base

```powershell
docker exec -it proyecto-db-1 psql -U user -d mydb -c "INSERT INTO evaluacion (id, estado_progreso) VALUES (1, 'en_progreso') ON CONFLICT DO NOTHING;"

docker exec -it proyecto-db-1 psql -U user -d mydb -c "INSERT INTO matriz_controles (id_control, pregunta_evaluacion, obligacion) VALUES (1, 'Cuenta con politica de seguridad aprobada?', 'Documentar y aprobar formalmente') ON CONFLICT DO NOTHING;"
```

### 1. Crear una respuesta

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/respuestas/" `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"evaluacion_id": 1, "matriz_control_id": 1, "estado_clasificacion": "verde", "justificacion": "Politica de seguridad aprobada."}'
```

Anota el `id_respuesta` que devuelve.

### 2. Crear y subir una evidencia

```powershell
@"
Politica de Seguridad de la Informacion
Aprobada por la Direccion General el 15 de enero de 2026
Version: 2.1
Alcance: Todas las areas de la organizacion
Firma: Gerente General
"@ | Out-File -Encoding utf8 evidencia.txt

curl.exe -X POST "http://localhost:8000/api/respuestas/{ID}/evidencias" -F "file=@evidencia.txt"
```

Reemplaza `{ID}` por el id de la respuesta.

> **Importante en PowerShell:** usa `curl.exe` (con extensión). El `-Form` de `Invoke-RestMethod` solo existe en PowerShell 7+.

### 3. Observar el worker

En la **Terminal 3** (worker ARQ), deberías ver:

```
process_evidence_task(1) started
process_evidence_task(1) completed in X.Xs
```

### 4. Consultar el resultado

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/respuestas/{ID}" | ConvertTo-Json -Depth 5
```

Respuesta esperada:

```json
{
  "id_respuesta": 5,
  "estado_clasificacion": "verde",
  "estado_clasificacion_final": "verde",
  "fuente_clasificacion": "llm",
  "confianza_clasificacion": 0.95,
  "evidencias": [
    {
      "estado_validacion": "validated",
      "clasificacion_llm": "verde",
      "confianza": 0.95,
      "justificacion_llm": "La evidencia respalda..."
    }
  ]
}
```

**Criterio de éxito:** `fuente_clasificacion: "llm"` y `estado_validacion: "validated"`.

---

## Endpoints disponibles

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/health` | Health check |
| POST | `/api/respuestas/` | Crear respuesta |
| GET | `/api/respuestas/{id}` | Consultar respuesta + evidencias |
| POST | `/api/respuestas/{id}/evidencias` | Subir evidencia |
| GET | `/api/evidencias/{id}` | Consultar evidencia |

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
# Entrar a psql
docker exec -it proyecto-db-1 psql -U user -d mydb

# Listar tablas
docker exec -it proyecto-db-1 psql -U user -d mydb -c "\dt"

# Describir tabla
docker exec -it proyecto-db-1 psql -U user -d mydb -c "\d respuestas"
```

### Redis

```powershell
docker exec -it proyecto-redis-1 redis-cli ping       # Debe responder PONG
docker exec -it proyecto-redis-1 redis-cli KEYS "*"   # Ver claves
```

### Alembic

```powershell
alembic current                                        # Revisión actual
alembic history                                        # Historial
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
| `Invalid API Key` (Groq) | Key mal pasada en `curl.exe` | Verifica `$env:GROQ_API_KEY` |
| `-Form no se reconoce` | PowerShell 5.1 | Usa `curl.exe -F "file=@archivo"` |
| `psycopg2` no instala en Python 3.13 | Sin wheels para 3.13 | Instala `psycopg[binary]` y ajusta `DATABASE_URL_SYNC` |
| `ForeignKeyViolation` al crear respuesta | Faltan datos padre | Inserta `evaluacion` y `matriz_controles` primero |
| Caracteres raros (`polÃtica`) | Mojibake en consola | Problema visual de PowerShell; verifica con `psql` |

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

**Regla de dependencia:** las capas externas dependen de las internas, nunca al revés. Esto permite cambiar el LLM (Groq → OpenAI) o el storage (local → S3) sin tocar la lógica de negocio.

**Ejemplo:** el caso de uso `ProcessEvidenceUseCase` depende de `EvidenceValidatorPort` (interfaz), no de `GroqEvidenceValidator` (implementación). Cambiar de proveedor LLM es reemplazar un archivo en `infrastructure/llm/`.

---

## Modelo de datos

### Tablas implementadas

- **evaluacion:** sesión de evaluación de un usuario.
- **matriz_controles:** catálogo de controles a evaluar.
- **respuestas:** respuesta de un usuario a un control, con clasificación original y final.
- **evidencias:** archivos subidos que respaldan respuestas.

### Tablas pendientes (del diagrama original)

- **benchmark:** estadísticas agregadas por rubro/dominio.
- **rubro:** categoría sectorial.
- **usuario_temporal:** usuarios invitados sin registro completo.
- **resumen:** resúmenes agregados por evaluación.
- **catalogo_brechas:** catálogo de brechas detectables.
- **ruta_formativa:** rutas de capacitación sugeridas.

---

## Licencia

Proyecto académico (Capstone).

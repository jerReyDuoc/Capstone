1. Configurar el entorno virtual y las depencias:

cd backend
python -m venv venv
source venv/bin/activate        # En Windows: venv\Scripts\activate

pip install -r requirements.txt

2. Levantar docker

docker-compose up -d

3. Ejecutar el proyecto

Terminal 1 — Servidor FastAPI:

cd backend
source venv/bin/activate
uvicorn app.main:app --reload --port 8000

Terminal 2 — Worker de ARQ:

cd backend
source venv/bin/activate
arq app.worker.tasks.WorkerSettings

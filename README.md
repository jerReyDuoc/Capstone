# ComplianceIA — Plataforma de Evaluación de Gobernanza de IA

Proyecto Capstone para **Therion Labs**. Autodiagnóstico de madurez en gobernanza de Inteligencia Artificial para empresas, con validación de evidencias asistida por IA, reportes de madurez y brechas, rutas formativas y gestión de derechos de protección de datos (Ley N.º 21.719).

> 📘 **La documentación técnica completa está en [`Proyecto/README.md`](Proyecto/README.md)**: funcionalidades, arquitectura, variables de entorno, endpoints, pruebas y backlog.

## Inicio rápido

Requiere Docker Desktop. Desde la carpeta `Proyecto/`:

```powershell
cd Proyecto
copy .env.example .env      # completar las claves obligatorias
docker compose up -d --build
```

- Frontend: http://localhost:3000
- API (Swagger): http://localhost:8000/docs

## Estructura del repositorio

| Carpeta | Contenido |
|---|---|
| [`Proyecto/`](Proyecto/) | Código: `backend/` (FastAPI), `frontend-next/` (Next.js), `infra/` y `docker-compose.yml` |
| [`Extras/`](Extras/) | Registro de cambios por historia de usuario y guía de despliegue a staging |
| `Documentos/` | Entregables académicos por fase e integrante |

## Equipo

| Integrante | Rol |
|---|---|
| Jerson Reyes | Product Owner |
| Jason Sánchez | Scrum Master |
| Ángel Muñoz | Developer Lead |
| Rodrigo Álvarez | Docente guía |

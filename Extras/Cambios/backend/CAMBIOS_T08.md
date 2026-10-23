# T-08 · Suite de pruebas automatizadas en CI/CD con cobertura ≥ 70 %

## Qué se agregó

| Archivo | Tipo | Para qué sirve |
|---|---|---|
| `.github/workflows/ci-backend.yml` (raíz del repo) | nuevo | Workflow de GitHub Actions: instala Python 3.13 y las dependencias, corre `pytest` con cobertura, publica los reportes y (opcional) envía el análisis a SonarQube Cloud. |
| `Proyecto/backend/.coveragerc` | nuevo | Configura coverage.py: mide la carpeta `app/` y fija `fail_under = 70`. |
| `Proyecto/backend/sonar-project.properties` | nuevo | Configuración de SonarQube Cloud (fuentes, pruebas y reporte `coverage.xml`). |
| `Proyecto/backend/requirements.txt` | modificado | Agrega `pytest-cov`. |
| `Proyecto/.gitignore` | modificado | Ignora `.coverage`, `coverage.xml`, `htmlcov/` y `reports/`. |

## Cómo funciona

El workflow se dispara en cada push o pull request a `main` que toque `Proyecto/backend/`, y también a mano desde la pestaña *Actions*. La suite no necesita PostgreSQL, Redis ni Groq porque usa SQLite en memoria y repositorios falsos (ver `tests/conftest.py`); la prueba en vivo `test_live_capa_ia.py` se omite sola al no existir `LIVE_BASE_URL`.

Si la cobertura total de `app/` queda bajo 70 %, `pytest` termina con error y el commit aparece en rojo. Los reportes (HTML navegable, `coverage.xml` y `junit.xml`) quedan como artefacto descargable del run durante 30 días, y el resumen de cobertura aparece en la página del workflow.

## Ejecutar lo mismo en local (Docker)

```bash
docker compose build worker            # para que la imagen incluya pytest-cov
docker compose up -d
docker compose exec worker pytest tests --cov=app --cov-report=term-missing
```

## Evidencia sugerida para el informe

1. Captura del run en verde en la pestaña *Actions*.
2. Captura del resumen de cobertura (porcentaje total ≥ 70 %).
3. Captura del reporte HTML (`htmlcov/index.html`) descargado del artefacto.
4. Si se activa SonarQube: captura del Quality Gate aprobado.

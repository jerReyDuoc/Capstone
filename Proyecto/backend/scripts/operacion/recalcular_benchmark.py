"""
HU-10 · Recalcula la tabla benchmark ahora (lo mismo que hace el cron de las 02:00 UTC).

Úsalo después de aplicar la migración a7c4e2f9d1b3: las filas antiguas no tienen
total_empresas y quedan suprimidas hasta el siguiente recálculo.

    docker compose exec worker python scripts/operacion/recalcular_benchmark.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.application.use_cases.actualizar_benchmark import UpdateBenchmarkUseCase  # noqa: E402
from app.bootstrap import configurar  # noqa: E402
from app.core.database import AsyncSessionLocal  # noqa: E402

configurar()  # raíz de composición (A-40)


async def main() -> None:
    async with AsyncSessionLocal() as session:
        print(f"[benchmark] {await UpdateBenchmarkUseCase(session).execute()}")


if __name__ == "__main__":
    asyncio.run(main())

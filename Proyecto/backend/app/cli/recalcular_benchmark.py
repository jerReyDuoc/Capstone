"""
HU-10 · Recalcula la tabla benchmark ahora (lo mismo que hace el cron de las 02:00 UTC).

Úsalo después de aplicar la migración a7c4e2f9d1b3: las filas antiguas no tienen
total_empresas y quedan suprimidas hasta el siguiente recálculo.

    docker compose exec worker python -m app.cli.recalcular_benchmark
"""
import argparse
import asyncio

from app.application.benchmark.casos_uso.actualizar_benchmark import ActualizarBenchmarkUseCase
from app.bootstrap import configurar
from app.core.contexto_auditoria import ORIGEN_CLI, fijar_origen_por_defecto
from app.core.database import AsyncSessionLocal, engine


async def _ejecutar() -> None:
    fijar_origen_por_defecto(ORIGEN_CLI)
    async with AsyncSessionLocal() as session:
        print(f"[benchmark] {await ActualizarBenchmarkUseCase(session).execute()}")


async def _main() -> None:
    try:
        await _ejecutar()
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> None:
    argparse.ArgumentParser(description="Recalcula la tabla benchmark (HU-10).").parse_args(argv)
    configurar()  # raíz de composición (A-40)
    asyncio.run(_main())


if __name__ == "__main__":
    main()

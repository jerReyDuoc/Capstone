"""Lectura de la tabla benchmark (sin supresión k-anónima: eso lo aplica application)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.benchmark import Benchmark


class BenchmarkRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def filas_del_rubro(self, rubro_id: int) -> list[Benchmark]:
        return list((await self.session.execute(
            select(Benchmark).where(Benchmark.rubro_id == rubro_id))).scalars().all())

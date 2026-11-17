"""Puertos de consulta (solo lectura) de evaluaciones y reportes. A-41."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.domain.models.benchmark import Benchmark
from app.domain.models.dominio import Dominio
from app.domain.models.evaluacion import Evaluacion
from app.domain.models.resumen import Resumen
from app.domain.models.respuesta import Respuesta
from app.domain.models.rubro import Rubro

# Tipos de alcance del listado de evaluaciones
ALCANCE_SIN_PUBLICAS = "sin_publicas"  # sin token: excluye origen pública y empresa
ALCANCE_EVALUACION = "evaluacion"      # encuestado: solo su evaluación (valor = id)
ALCANCE_REFERENTE = "referente"        # referente: las de su invitación, sin las públicas
ALCANCE_EMPRESA = "empresa"            # cliente: las de su empresa (valor = empresa_id)
ALCANCE_TODO = "todo"                  # admin
ALCANCE_NADA = "nada"                  # rol desconocido


@dataclass(frozen=True)
class AlcanceEvaluaciones:
    """Restricción de visibilidad del listado de evaluaciones."""
    tipo: str
    valor: int | None = None


class ConsultaEvaluacionesPort(Protocol):
    """Consultas de lectura sobre evaluaciones y sus respuestas."""

    async def empresa_del_usuario_definitivo(self, usuario_id: int) -> int | None: ...

    async def listar_evaluaciones(self, *, alcance: AlcanceEvaluaciones, estado_progreso: str | None,
                                  offset: int, limit: int) -> tuple[list[Evaluacion], int]: ...

    async def obtener_evaluacion(self, evaluacion_id: int) -> Evaluacion | None: ...

    async def existe_evaluacion(self, evaluacion_id: int) -> bool: ...

    async def listar_respuestas(self, evaluacion_id: int, *, estado_final: str | None, fuente: str | None,
                                offset: int, limit: int) -> tuple[list[Respuesta], int]: ...


class ReportesPort(Protocol):
    """Consultas de lectura para resumen, benchmark y comparativa."""

    async def resumenes_con_dominio(self, evaluacion_id: int) -> list[tuple[Resumen, Dominio]]: ...

    async def benchmark_con_rubro_y_dominio(self, rubro_id: int | None
                                            ) -> list[tuple[Benchmark, Rubro, Dominio | None]]: ...

    async def obtener_evaluacion(self, evaluacion_id: int) -> Evaluacion | None: ...

    async def evaluacion_tiene_empresa(self, evaluacion_id: int) -> bool: ...

    async def rubro_id_de_evaluacion(self, evaluacion: Evaluacion) -> int | None: ...

    async def obtener_rubro(self, rubro_id: int) -> Rubro | None: ...

    async def benchmark_del_rubro(self, rubro_id: int | None) -> dict[int | None, Benchmark]: ...

"""Puertos de repositorio de los casos de uso del espacio de la empresa cliente (HU-26/29)."""
from __future__ import annotations

from typing import Protocol

from app.domain.models.documento_empresa import DocumentoEmpresa
from app.domain.models.dominio import Dominio
from app.domain.models.evaluacion import Evaluacion
from app.domain.models.evidencia import Evidencia
from app.domain.models.formacion_recorrido import AvanceFormativo, LeccionFormativa, PreguntaVerificacion
from app.domain.models.rat_informe import RatInforme
from app.domain.models.resumen import Resumen
from app.domain.models.ropa_modelo import RopaInforme
from app.domain.models.ruta_formativa import RutaFormativa


class DocumentosEmpresaRepositoryPort(Protocol):
    """Documentos, evidencias y constancias de la empresa ("Mis documentos", HU-29)."""

    async def obtener_evaluacion(self, evaluacion_id: int) -> Evaluacion | None: ...

    async def contar_informes_de_evaluacion(self, evaluacion_id: int, tipo: str) -> int: ...

    async def agregar_documento(self, documento: DocumentoEmpresa) -> None:
        """Agrega el documento y lo vuelca a la base (flush), sin commit."""
        ...

    async def obtener_documento(self, documento_id: int) -> DocumentoEmpresa | None: ...

    async def eliminar_documento(self, documento: DocumentoEmpresa) -> None: ...

    async def documentos_de_empresa(self, empresa_id: int) -> list[DocumentoEmpresa]:
        """Más recientes primero."""
        ...

    async def evidencias_de_empresa(self, empresa_id: int) -> list[tuple[Evidencia, int, str | None]]:
        """(evidencia, evaluación, código del control) vigentes y que no son del registro, más recientes primero."""
        ...

    async def obtener_evidencia_de_empresa(self, evidencia_id: int, empresa_id: int) -> tuple[Evidencia, int] | None:
        """(evidencia, evaluación) si pertenece a la empresa."""
        ...

    async def informes_rat(self, empresa_id: int) -> list[RatInforme]: ...

    async def informes_ropa(self, empresa_id: int) -> list[RopaInforme]: ...

    async def avances_con_constancia(self, empresa_id: int) -> list[tuple[AvanceFormativo, str | None]]:
        """(avance, nombre de la ruta) con código de constancia, el más reciente primero."""
        ...

    async def obtener_avance(self, empresa_id: int, ruta_id: int) -> AvanceFormativo | None: ...


class FormacionEmpresaRepositoryPort(Protocol):
    """Avance formativo de la empresa y catálogo de lecciones (HU-26)."""

    async def obtener_evaluacion(self, evaluacion_id: int) -> Evaluacion | None: ...

    async def avances_de_empresa(self, empresa_id: int) -> list[AvanceFormativo]: ...

    async def lecciones_de_ruta(self, ruta_id: int) -> list[LeccionFormativa]: ...

    async def orden_de_todas_las_lecciones(self) -> list[tuple[int, int]]:
        """(ruta, orden) de todas las lecciones guardadas."""
        ...

    async def preguntas_de_ruta(self, ruta_id: int) -> list[PreguntaVerificacion]: ...

    async def avance_para_actualizar(self, empresa_id: int, ruta_id: int) -> AvanceFormativo | None:
        """El avance bloqueado (FOR UPDATE), o None."""
        ...

    async def obtener_avance(self, empresa_id: int, ruta_id: int) -> AvanceFormativo | None: ...

    def agregar_avance(self, avance: AvanceFormativo) -> None: ...

    async def obtener_ruta(self, ruta_id: int) -> RutaFormativa | None: ...

    async def obtener_dominio(self, dominio_id: int) -> Dominio | None: ...


class HistorialEmpresaRepositoryPort(Protocol):
    """Evaluaciones de la empresa: historial, reevaluación y "la más reciente" (HU-29)."""

    async def evaluacion_mas_reciente(self, empresa_id: int, solo_completadas: bool) -> int | None:
        """Id de la evaluación con resumen de mayor id (solo las cerradas si `solo_completadas`)."""
        ...

    async def evaluacion_en_curso(self, empresa_id: int) -> Evaluacion | None: ...

    async def rubro_de_empresa(self, empresa_id: int) -> int | None: ...

    async def rubro_de_usuario_temporal(self, usuario_temporal_id: int) -> int | None: ...

    async def evaluaciones_de_empresa(self, empresa_id: int) -> list[Evaluacion]:
        """Por id ascendente."""
        ...

    async def resumenes_con_dominio(self, evaluaciones_ids: list[int]) -> list[tuple[Resumen, Dominio]]: ...

    async def bloquear_empresa(self, empresa_id: int) -> None:
        """SELECT ... FOR UPDATE de la fila de la empresa, hasta el fin de la transacción."""
        ...

    def agregar_evaluacion(self, evaluacion: Evaluacion) -> None: ...

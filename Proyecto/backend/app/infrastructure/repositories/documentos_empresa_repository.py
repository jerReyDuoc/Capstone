"""Repositorio de "Mis documentos" de la empresa cliente (HU-29)."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.documento_empresa import DocumentoEmpresa
from app.domain.models.evaluacion import Evaluacion
from app.domain.models.evidencia import ORIGEN_RAT, Evidencia
from app.domain.models.formacion_recorrido import AvanceFormativo
from app.domain.models.matriz_control import MatrizControl
from app.domain.models.rat_informe import RatInforme
from app.domain.models.respuesta import Respuesta
from app.domain.models.ropa_modelo import RopaInforme
from app.domain.models.ruta_formativa import RutaFormativa


class DocumentosEmpresaRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def obtener_evaluacion(self, evaluacion_id: int) -> Evaluacion | None:
        return await self.session.get(Evaluacion, evaluacion_id)

    async def contar_informes_de_evaluacion(self, evaluacion_id: int, tipo: str) -> int:
        return await self.session.scalar(
            select(func.count()).select_from(DocumentoEmpresa).where(
                DocumentoEmpresa.evaluacion_id == evaluacion_id, DocumentoEmpresa.tipo == tipo)
        ) or 0

    async def agregar_documento(self, documento: DocumentoEmpresa) -> None:
        self.session.add(documento)
        await self.session.flush()

    async def obtener_documento(self, documento_id: int) -> DocumentoEmpresa | None:
        return await self.session.get(DocumentoEmpresa, documento_id)

    async def eliminar_documento(self, documento: DocumentoEmpresa) -> None:
        await self.session.delete(documento)

    async def documentos_de_empresa(self, empresa_id: int) -> list[DocumentoEmpresa]:
        filas = (await self.session.execute(
            select(DocumentoEmpresa).where(DocumentoEmpresa.empresa_id == empresa_id)
            .order_by(DocumentoEmpresa.fecha_creacion.desc(), DocumentoEmpresa.id.desc())
        )).scalars().all()
        return list(filas)

    async def evidencias_de_empresa(self, empresa_id: int) -> list[tuple[Evidencia, int, str | None]]:
        filas = (await self.session.execute(
            select(Evidencia, Respuesta.evaluacion_id, MatrizControl.codigo_control)
            .join(Respuesta, Evidencia.respuesta_id == Respuesta.id)
            .join(Evaluacion, Respuesta.evaluacion_id == Evaluacion.id)
            .outerjoin(MatrizControl, Respuesta.matriz_controles_id_control == MatrizControl.id_control)
            .where(Evaluacion.empresa_id == empresa_id, Evidencia.fecha_eliminacion.is_(None),
                   Evidencia.origen != ORIGEN_RAT)      # HU-38: la del registro no es un archivo
            .order_by(Evidencia.id_evidencia.desc())
        )).all()
        return [(e, ev_id, codigo) for e, ev_id, codigo in filas]

    async def obtener_evidencia_de_empresa(self, evidencia_id: int, empresa_id: int) -> tuple[Evidencia, int] | None:
        fila = (await self.session.execute(
            select(Evidencia, Evaluacion.id)
            .join(Respuesta, Evidencia.respuesta_id == Respuesta.id)
            .join(Evaluacion, Respuesta.evaluacion_id == Evaluacion.id)
            .where(Evidencia.id_evidencia == evidencia_id, Evaluacion.empresa_id == empresa_id)
        )).first()
        return None if fila is None else (fila[0], fila[1])

    async def informes_rat(self, empresa_id: int) -> list[RatInforme]:
        filas = (await self.session.execute(select(RatInforme).where(RatInforme.empresa_id == empresa_id))).scalars().all()
        return list(filas)

    async def informes_ropa(self, empresa_id: int) -> list[RopaInforme]:
        filas = (await self.session.execute(select(RopaInforme).where(RopaInforme.empresa_id == empresa_id))).scalars().all()
        return list(filas)

    async def avances_con_constancia(self, empresa_id: int) -> list[tuple[AvanceFormativo, str | None]]:
        filas = (await self.session.execute(
            select(AvanceFormativo, RutaFormativa.nombre)
            .join(RutaFormativa, RutaFormativa.id == AvanceFormativo.ruta_formativa_id)
            .where(AvanceFormativo.empresa_id == empresa_id, AvanceFormativo.codigo_constancia.is_not(None))
            .order_by(AvanceFormativo.fecha_completado.desc())
        )).all()
        return [(a, nombre) for a, nombre in filas]

    async def obtener_avance(self, empresa_id: int, ruta_id: int) -> AvanceFormativo | None:
        return await self.session.scalar(
            select(AvanceFormativo).where(
                AvanceFormativo.empresa_id == empresa_id, AvanceFormativo.ruta_formativa_id == ruta_id)
        )

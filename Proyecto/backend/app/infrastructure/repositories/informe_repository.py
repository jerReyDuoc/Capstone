"""Consultas que necesitan los informes (carga de los datos de una evaluación)."""
from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.models.catalogo_brechas import CatalogoBrechas
from app.domain.models.dominio import Dominio
from app.domain.models.evaluacion import Evaluacion
from app.domain.models.matriz_control import MatrizControl
from app.domain.models.matriz_version import ESTADO_PUBLICADA, MatrizVersion
from app.domain.models.respuesta import Respuesta
from app.domain.models.resumen import Resumen
from app.domain.models.rubro import Rubro
from app.domain.models.ruta_formativa import RutaFormativa
from app.domain.models.usuario_temporal import UsuarioTemporal


class InformeRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def version_publicada_texto(self) -> str | None:
        return (await self.session.execute(
            select(MatrizVersion.version_texto).where(MatrizVersion.estado == ESTADO_PUBLICADA)
        )).scalar_one_or_none()

    async def filas_matriz_para_huella(self) -> list:
        return list((await self.session.execute(select(
            MatrizControl.id_control, MatrizControl.codigo_control, MatrizControl.dominio_id,
            MatrizControl.pregunta_evaluacion, MatrizControl.aplicabilidad, MatrizControl.criticidad,
            MatrizControl.obligacion, MatrizControl.catalogo_brechas_id_brecha,
        ))).all())

    async def evaluacion(self, evaluacion_id: int) -> Evaluacion | None:
        return await self.session.get(Evaluacion, evaluacion_id)

    async def congelar_version_aviso(self, evaluacion_id: int, version: str) -> str | None:
        """T-16: fija `version` solo si la evaluación aún no tiene (UPDATE condicional, sin carrera).
        Devuelve la versión que quedó. No hace commit."""
        await self.session.execute(
            update(Evaluacion)
            .where(Evaluacion.id == evaluacion_id, Evaluacion.aviso_informe_version.is_(None))
            .values(aviso_informe_version=version)
            .execution_options(synchronize_session=False)
        )
        # Se recarga la entidad (populate_existing) para que la del identity map no quede desfasada.
        fila = (await self.session.execute(
            select(Evaluacion).where(Evaluacion.id == evaluacion_id).execution_options(populate_existing=True)
        )).scalar_one_or_none()
        return fila.aviso_informe_version if fila else None

    async def resumenes_con_dominio(self, evaluacion_id: int) -> list:
        return list((await self.session.execute(
            select(Resumen, Dominio).join(Dominio, Resumen.dominio_id == Dominio.id)
            .where(Resumen.evaluacion_id == evaluacion_id)
        )).all())

    async def dominios(self) -> list[Dominio]:
        return list((await self.session.execute(select(Dominio))).scalars().all())

    async def rutas(self) -> list[RutaFormativa]:
        return list((await self.session.execute(
            select(RutaFormativa).order_by(RutaFormativa.id))).scalars().all())

    async def brechas(self) -> list[CatalogoBrechas]:
        return list((await self.session.execute(select(CatalogoBrechas))).scalars().all())

    async def controles_con_dominio(self) -> list[MatrizControl]:
        return list((await self.session.execute(
            select(MatrizControl).options(selectinload(MatrizControl.dominio))
        )).scalars().all())

    async def respuestas(self, evaluacion_id: int) -> list[Respuesta]:
        return list((await self.session.execute(
            select(Respuesta).where(Respuesta.evaluacion_id == evaluacion_id).order_by(Respuesta.id)
        )).scalars().all())

    async def usuario_temporal(self, usuario_temporal_id: int) -> UsuarioTemporal | None:
        return await self.session.get(UsuarioTemporal, usuario_temporal_id)

    async def actualizar_email_usuario_temporal(self, usuario: UsuarioTemporal, email: str | None) -> None:
        """Asigna el correo; la confirmación (commit) es de quien orquesta la transacción."""
        usuario.email = email

    async def rubro(self, rubro_id: int) -> Rubro | None:
        return await self.session.get(Rubro, rubro_id)

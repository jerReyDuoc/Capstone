"""Panel interno (HU-28): evaluaciones, formación de una empresa y bitácora para el admin."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.fabricas import fabricas
from app.domain.auditoria.acciones import Accion
from app.domain.auth.actor import Actor
from app.domain.models.bitacora_auditoria import BitacoraAuditoria
from app.domain.ports.repositorios_admin import (
    DatosEvaluacionPanel,
    PaginaEvaluacionesPanel,
    PanelClientesRepositoryPort,
)


class PanelClientesError(Exception):
    def __init__(self, status_code: int, codigo: str, mensaje: str):
        super().__init__(mensaje)
        self.status_code = status_code
        self.codigo = codigo
        self.mensaje = mensaje


class PanelClientesUseCase:
    def __init__(self, session: AsyncSession, repo: PanelClientesRepositoryPort):
        self.session = session
        self.repo = repo

    async def datos_evaluacion(self, evaluacion_id: int) -> DatosEvaluacionPanel | None:
        return await self.repo.datos_evaluacion(evaluacion_id)

    async def listar_evaluaciones(self, *, estado: str | None, origen: str | None, empresa_id: int | None,
                                  incluir_prueba: bool, page: int, size: int) -> PaginaEvaluacionesPanel:
        return await self.repo.listar_evaluaciones(estado=estado, origen=origen, empresa_id=empresa_id,
                                                   incluir_prueba=incluir_prueba, page=page, size=size)

    async def formacion_empresa(self, empresa_id: int, evaluacion_id: int | None) -> dict:
        """HU-26: avance formativo de la empresa. Puede lanzar `FormacionError`."""
        from app.application.use_cases.formacion_empresa import avance_de_empresa_para_admin

        empresa = await self.repo.obtener_empresa(empresa_id)
        if empresa is None:
            raise PanelClientesError(404, "NO_ENCONTRADO", "Empresa no encontrada.")
        return await avance_de_empresa_para_admin(self.session, empresa, evaluacion_id)

    async def listar_bitacora(self, *, entidad: str | None, entidad_id: int | None, accion: str | None,
                              page: int, size: int) -> tuple[list[BitacoraAuditoria], int]:
        return await fabricas().bitacora(self.session).listar(
            entidad=entidad, entidad_id=entidad_id, accion=accion, page=page, size=size)

    async def verificar_bitacora(self, actor: Actor) -> dict:
        """HU-18 + HU-09: verifica cadena y lotes, y deja constancia de la verificación."""
        r = await fabricas().integridad_bitacora.verificar_lotes(self.session)
        fabricas().bitacora(self.session).registrar(
            accion=Accion.AUDITORIA_VERIFICACION, entidad="audit_log", actor=actor,
            resultado="ok" if r["integra"] else "rechazado",
            detalle={"integra": r["integra"], "lotes": r["lotes"]["total"], "lotes_con_falla": r["lotes"]["con_falla"],
                     "filas": r["filas"]["total"]})
        await self.session.commit()
        return r

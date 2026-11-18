"""Consultas de solicitudes: por id, seguimiento público por código y listado."""
from app.domain.auth.actor import Actor
from app.domain.models.solicitud_arcop import (
    EstadoSolicitudARCOP as Estado,
    SolicitudARCOP,
    TipoSolicitudARCOP,
)
from app.application.arcop.casos_uso.gestionar_solicitud_arcop.comun import (
    SolicitudNoEncontradaError, _ahora, normalizar_codigo, ventana_por_vencer,
)


class LecturaMixin:
    # ------------------------------------------------------------ consulta
    async def obtener(self, actor: Actor, solicitud_id: int) -> SolicitudARCOP:
        return await self._obtener_visible(actor, solicitud_id)

    async def seguimiento(self, codigo: str) -> SolicitudARCOP:
        """Consulta pública por código: el router solo expone datos sin PII."""
        normalizado = normalizar_codigo(codigo)
        solicitud = await self.repo.get_por_codigo(normalizado) if normalizado else None
        if not solicitud:
            raise SolicitudNoEncontradaError("Solicitud no encontrada")
        return solicitud

    async def listar(self, actor: Actor, estado: str | None, tipo: str | None,
                     usuario_temporal_id: int | None, page: int, size: int,
                     solo_vencidas: bool = False, evaluacion_id: int | None = None,
                     por_vencer_dias: int | None = None):
        if estado and estado not in Estado.valores():
            raise ValueError(f"Estado inválido. Debe ser uno de: {', '.join(Estado.valores())}")
        if tipo and tipo not in TipoSolicitudARCOP.valores():
            raise ValueError(f"Tipo inválido. Debe ser uno de: {', '.join(TipoSolicitudARCOP.valores())}")
        # T-19: abiertas, sin plazo vencido y con alguno de sus plazos dentro de N días
        por_vencer = ventana_por_vencer(por_vencer_dias) if por_vencer_dias is not None else None
        # El titular SIEMPRE queda filtrado a sus propias solicitudes
        if actor.es_admin:
            filtro = {"usuario_temporal_id": usuario_temporal_id, "evaluacion_id": evaluacion_id}
        elif actor.es_encuestado:
            filtro = {"usuario_temporal_id": None, "evaluacion_id": actor.id}
        elif actor.es_cliente:
            filtro = {"usuario_temporal_id": None, "evaluacion_id": None, "usuario_definitivo_id": actor.id}
        else:
            filtro = {"usuario_temporal_id": actor.id, "evaluacion_id": None}
        return await self.repo.list(
            **filtro, estado=estado, tipo=tipo,
            solo_vencidas_al=_ahora() if solo_vencidas else None,
            por_vencer_entre=por_vencer,
            offset=(page - 1) * size, limit=size,
        )

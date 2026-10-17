from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.llamada_llm import LlamadaLLM
from app.domain.models.sanitizacion import Sanitizacion
from app.domain.ports.registro_ia_port import RegistroIAPort, RegistroLlamada, RegistroSanitizacion
from app.infrastructure.security.cifrado import CifradorEntidades


class RegistroIARepository(RegistroIAPort):
    """
    Persiste métricas y mapas de entidades. Usa una sesión propia (no la del caso
    de uso) para que un rollback del negocio no borre la auditoría ni las métricas.
    """

    def __init__(self, session: AsyncSession, cifrador: CifradorEntidades | None,
                 guardar_mapa: bool = False):
        self.session = session
        self.cifrador = cifrador
        # HU-06: por defecto no se guardan los valores originales (irreversible); solo
        # tipos, posiciones, huellas HMAC y conteos.
        self.guardar_mapa = guardar_mapa

    async def guardar_llamada(self, r: RegistroLlamada) -> int:
        fila = LlamadaLLM(
            traza_id=r.traza_id,
            fecha=r.fecha,
            tarea=r.tarea,
            proveedor=r.proveedor,
            modelo=r.modelo,
            prompt_version=r.prompt_version,
            exito=r.exito,
            tipo_error=r.tipo_error,
            detalle_error=r.detalle_error,
            tokens_entrada=r.tokens_entrada,
            tokens_salida=r.tokens_salida,
            costo_estimado_usd=r.costo_estimado_usd,
            latencia_ms=r.latencia_ms,
            sanitizado=r.sanitizado,
            entidades_anonimizadas=r.entidades_anonimizadas,
            clasificacion=r.clasificacion,
            confianza=r.confianza,
            advertencias=r.advertencias or None,
            evaluacion_id=r.contexto.evaluacion_id,
            respuesta_id=r.contexto.respuesta_id,
            evidencia_id=r.contexto.evidencia_id,
        )
        self.session.add(fila)
        await self._commit()
        return fila.id_llamada

    async def guardar_sanitizaciones(self, registros: list[RegistroSanitizacion]) -> None:
        if not registros:
            return
        if self.cifrador is None:
            # Sin clave no hay forma de cumplir R2 de forma segura: se aborta la llamada.
            raise RuntimeError("ENTITY_MAP_KEY no configurada: no se puede guardar el mapa de entidades")

        ahora = datetime.now(timezone.utc).replace(tzinfo=None)
        for r in registros:
            metadatos = [
                {"tipo": e.tipo.value, "inicio": e.inicio, "fin": e.fin,
                 "fuente": e.fuente, "huella": self.cifrador.huella(e.valor)}
                for e in r.entidades
            ]
            valores = [
                {"tipo": e.tipo.value, "inicio": e.inicio, "fin": e.fin, "valor": e.valor}
                for e in r.entidades
            ]
            conteo: dict[str, int] = {}
            for e in r.entidades:
                conteo[e.tipo.value] = conteo.get(e.tipo.value, 0) + 1

            self.session.add(Sanitizacion(
                traza_id=r.traza_id,
                fecha=ahora,
                campo=r.campo,
                motor=r.motor[:120],
                duracion_ms=r.duracion_ms,
                truncado=r.truncado,
                total_entidades=len(r.entidades),
                conteo_por_tipo=conteo,
                entidades=metadatos,
                mapa_cifrado=(self.cifrador.cifrar_json(valores)
                              if valores and self.guardar_mapa else None),
                evaluacion_id=r.contexto.evaluacion_id,
                respuesta_id=r.contexto.respuesta_id,
                evidencia_id=r.contexto.evidencia_id,
            ))
        await self._commit()

    async def _commit(self) -> None:
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()  # deja la sesión usable para la siguiente métrica
            raise

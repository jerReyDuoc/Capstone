from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ai.metricas import FilaLlamada, precision_clasificacion, resumen_operacion
from app.domain.models.llamada_llm import LlamadaLLM
from app.domain.models.respuesta import Respuesta
from app.domain.models.sanitizacion import Sanitizacion


class ObtenerMetricasIAUseCase:
    def __init__(self, session: AsyncSession, umbral_confianza: float):
        self.session = session
        self.umbral = umbral_confianza

    async def execute(
        self,
        desde: datetime | None = None,
        hasta: datetime | None = None,
        tarea: str | None = None,
        modelo: str | None = None,
    ) -> dict:
        q = select(LlamadaLLM)
        if desde:
            q = q.where(LlamadaLLM.fecha >= desde)
        if hasta:
            q = q.where(LlamadaLLM.fecha <= hasta)
        if tarea:
            q = q.where(LlamadaLLM.tarea == tarea)
        if modelo:
            q = q.where(LlamadaLLM.modelo == modelo)
        llamadas = list((await self.session.execute(q.order_by(LlamadaLLM.fecha))).scalars().all())

        operacion = resumen_operacion(
            [FilaLlamada(
                exito=l.exito, tipo_error=l.tipo_error, latencia_ms=l.latencia_ms,
                tokens_entrada=l.tokens_entrada, tokens_salida=l.tokens_salida,
                costo_estimado_usd=l.costo_estimado_usd, confianza=l.confianza,
                advertencias=l.advertencias, sanitizado=l.sanitizado,
            ) for l in llamadas],
            self.umbral,
        )

        # Precisión: última clasificación exitosa del LLM por respuesta vs. revisión humana
        ids = {l.respuesta_id for l in llamadas if l.exito and l.respuesta_id and l.clasificacion}
        pares = []
        if ids:
            revisadas = {
                r.id: r.clasificacion_revisada
                for r in (await self.session.execute(
                    select(Respuesta).where(
                        Respuesta.id.in_(ids), Respuesta.clasificacion_revisada.is_not(None)
                    )
                )).scalars().all()
            }
            ultima: dict[int, str] = {}
            for l in llamadas:  # ordenadas por fecha: la última gana
                if l.exito and l.respuesta_id in revisadas and l.clasificacion:
                    ultima[l.respuesta_id] = l.clasificacion
            pares = [(pred, revisadas[rid]) for rid, pred in ultima.items()]

        # Sanitización
        qs = select(Sanitizacion)
        if desde:
            qs = qs.where(Sanitizacion.fecha >= desde)
        if hasta:
            qs = qs.where(Sanitizacion.fecha <= hasta)
        sans = list((await self.session.execute(qs)).scalars().all())
        por_tipo: dict[str, int] = {}
        for s in sans:
            for t, n in (s.conteo_por_tipo or {}).items():
                por_tipo[t] = por_tipo.get(t, 0) + n
        fallos = operacion["errores_por_tipo"].get("sanitizacion", {}).get("cantidad", 0)

        return {
            "periodo": {"desde": desde, "hasta": hasta},
            "operacion_modelo": operacion,
            "precision_modelo": precision_clasificacion(pares),
            "sanitizacion": {
                "textos_sanitizados": len(sans),
                "fallos_sanitizacion": fallos,
                "entidades_por_tipo": por_tipo,
                "textos_truncados": sum(1 for s in sans if s.truncado),
                "duracion_ms_promedio": (
                    round(sum(s.duracion_ms for s in sans) / len(sans), 2) if sans else None
                ),
            },
        }

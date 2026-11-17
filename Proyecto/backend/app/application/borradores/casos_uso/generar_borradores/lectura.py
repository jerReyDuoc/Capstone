"""Catálogo, cuota y lectura de borradores."""
from __future__ import annotations

from app.application.borradores.plantillas_borrador import catalogo
from app.application.encuesta_publica.casos_uso.limites_encuesta import ventana_diaria
from app.core.config import settings
from app.domain.models.borrador_modelo import BorradorDocumento
from app.domain.ports.limitador_port import LimitadorNoDisponibleError
from app.application.borradores.casos_uso.generar_borradores.comun import logger, BorradorError, borrador_a_dict


class LecturaMixin:
    """Catálogo, cuota y lectura de borradores."""

    # ------------------------------------------------------------------ catálogo y cuota
    def _clave_dia(self, fecha: str) -> str:
        return f"borrador:dia:{self.empresa.id}:{fecha}"

    async def cuota(self) -> dict:
        fecha, _, reinicio = ventana_diaria()
        limite = settings.BORRADORES_IA_DIA_EMPRESA
        try:
            usados = await self.limitador.usados(self._clave_dia(fecha)) if self.limitador else 0
        except LimitadorNoDisponibleError:
            usados = 0
        return {"usados": usados, "limite": limite or None,
                "restantes": max(0, limite - usados) if limite > 0 else None,
                "reinicia_en": reinicio.isoformat().replace("+00:00", "Z")}

    # ------------------------------------------------------------------ HU-38: el registro de actividades
    async def _registro(self):
        from app.application.borradores import registro_borrador as reg_borrador
        from app.application.rat.casos_uso.generar_informe import InformeRatCasos

        return reg_borrador.desde_informe(await InformeRatCasos(self.db, self.cliente).armar())

    async def _registro_para_catalogo(self) -> dict:
        try:
            reg = await self._registro()
        except Exception as e:  # noqa: BLE001 - el catálogo de plantillas no depende del registro
            logger.error("HU-38: no se pudo leer el registro para los borradores (%s)", type(e).__name__)
            await self.db.rollback()
            return {"actividades": [], "pia": [], "finalidades": 0}

        def act(a) -> dict:
            return {"actividad_id": a.id, "nombre": a.nombre, "nivel": a.riesgo.nivel, "puntaje": a.riesgo.puntaje,
                    "requiere_pia": a.riesgo.requiere_pia, "motivos_pia": list(a.riesgo.motivos_pia),
                    "vigente": a.vigente}
        return {"actividades": [act(a) for a in reg.actividades], "pia": [act(a) for a in reg.recomendadas_pia()],
                "finalidades": sum(len(a.finalidades) for a in reg.actividades)}

    async def catalogo(self) -> dict:
        return {
            "registro": await self._registro_para_catalogo(),
            "plantillas": catalogo(),
            "ia_habilitada": bool(settings.BORRADORES_IA_HABILITADA),
            "cuota": await self.cuota(),
            "max_caracteres_contenido": settings.BORRADORES_MAX_CHARS_CONTENIDO,
            "max_caracteres_instrucciones": settings.BORRADORES_MAX_CHARS_INSTRUCCIONES,
            "max_en_revision": settings.BORRADORES_MAX_EN_REVISION,
        }

    # ------------------------------------------------------------------ lectura
    async def _borrador(self, borrador_id: int) -> BorradorDocumento:
        b = await self.repo.borrador(borrador_id)
        if b is None or b.empresa_id != self.empresa.id:   # lo ajeno no existe (404, no 403)
            raise BorradorError(404, "BORRADOR_NO_ENCONTRADO", "Borrador no encontrado.")
        return b

    async def listar(self) -> dict:
        filas = await self.repo.listar(self.empresa.id)
        return {"items": [borrador_a_dict(b) for b in filas]}

    async def obtener(self, borrador_id: int) -> dict:
        return {"borrador": borrador_a_dict(await self._borrador(borrador_id), con_contenido=True)}

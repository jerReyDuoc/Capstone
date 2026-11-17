"""Verificación del código de una emisión del informe RAT."""
from __future__ import annotations

from app.application.rat import armado_informe_rat as I
from app.domain.models.bitacora_auditoria import RESULTADO_RECHAZADO
from app.domain.auditoria.acciones import Accion
from app.application.rat.casos_uso.generar_informe.comun import InformeRatError


class VerificacionInformeMixin:
    async def verificar(self, codigo_txt: str) -> dict:
        leido = I.leer_codigo(codigo_txt)
        if leido is None:
            self.bitacora.registrar(accion=Accion.RAT_INFORME_VERIFICADO, entidad="rat_informe", entidad_id=None,
                                    actor=self.actor, resultado=RESULTADO_RECHAZADO, detalle={"motivo": "codigo_invalido"})
            await self.db.commit()
            raise InformeRatError(422, "CODIGO_INVALIDO", "El código no es válido. Revisa que esté completo y bien "
                                                          "escrito: el último carácter es de control.")
        anio, emision_id = leido
        fila = await self.repo.emision(emision_id)
        if fila is None or fila.empresa_id != self.empresa_id or fila.codigo != I.codigo(emision_id, anio):
            self.bitacora.registrar(accion=Accion.RAT_INFORME_VERIFICADO, entidad="rat_informe", entidad_id=None,
                                    actor=self.actor, resultado=RESULTADO_RECHAZADO, detalle={"motivo": "no_encontrado"})
            await self.db.commit()
            raise InformeRatError(404, "INFORME_NO_ENCONTRADO", "No encontramos un informe de tu empresa con ese código.")
        actual = await self.armar()
        vigente = actual.huella == fila.huella
        self.bitacora.registrar(accion=Accion.RAT_INFORME_VERIFICADO, entidad="rat_informe", entidad_id=fila.id,
                                actor=self.actor, detalle={"sigue_al_dia": vigente})
        await self.db.commit()
        return {
            "valido": True, "informe": await self._vista_emision(fila), "sigue_al_dia": vigente,
            "mensaje": ("El código es auténtico y el registro no ha cambiado desde esa emisión." if vigente else
                        "El código es auténtico, pero el registro cambió después de esa emisión: genera un informe "
                        "nuevo para presentar la versión actual."),
        }

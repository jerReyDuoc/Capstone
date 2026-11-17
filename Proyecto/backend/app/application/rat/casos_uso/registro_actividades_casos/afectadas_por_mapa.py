"""Vínculo con el mapa de datos (C2): actividades que vuelven a revisión al cambiar el mapa."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.mapa_datos import versiones_mapa
from app.domain.rat import estados, vinculo_mapa
from app.domain.auditoria.acciones import Accion
from app.application.fabricas import fabricas
from app.domain.ports.bitacora_port import BitacoraPort
from app.application.rat.casos_uso.registro_actividades_casos.comun import MAX_MOTIVOS, _ahora, _evaluar


# ====================================================================== vínculo con el mapa (C2)
async def marcar_afectadas_por_mapa(db: AsyncSession, empresa_id: int, cambios: list[dict], antes: dict | None,
                                    despues: dict, version_mapa: int, actor, bitacora: BitacoraPort) -> list[int]:
    """
    Lo llama el mapa de datos (MapaDatosCasos._guardar) ANTES de confirmar un cambio: las actividades
    que usan lo que cambió vuelven a revisión (las vigentes) o anotan el motivo (borradores y en
    revisión). No confirma la transacción: lo hace el mapa, así ambos cambios quedan juntos o ninguno.
    """
    if not vinculo_mapa.cambios_relevantes(cambios):
        return []
    filas = await fabricas().registro_actividades(db).actividades_no_archivadas_bloqueadas(empresa_id)
    if not filas:
        return []
    afectadas = vinculo_mapa.afectadas([{"id": f.id, "contenido": f.contenido} for f in filas], cambios, antes, despues)
    if not afectadas:
        return []
    elementos, flujos = versiones_mapa.desde_instantanea(despues)
    ahora = _ahora()
    vuelven = 0
    for f in filas:
        motivos = afectadas.get(f.id)
        if not motivos:
            continue
        nuevo_estado = estados.tras_cambio_en_mapa(f.estado)
        vuelven += int(nuevo_estado != f.estado)
        registro = [{"fecha": ahora.isoformat(), "texto": m, "version_mapa": version_mapa} for m in motivos]
        f.motivos_revision = (list(f.motivos_revision or []) + registro)[-MAX_MOTIVOS:]
        f.estado = nuevo_estado
        f.revision += 1
        f.fecha_actualizacion = ahora
        f.completitud = _evaluar(f.contenido, elementos, flujos)[1]["porcentaje"]
    bitacora.registrar(
        accion=Accion.RAT_MARCADA_REVISION, entidad="rat_actividad", entidad_id=None, actor=actor,
        detalle={"actividades": sorted(afectadas), "vuelven_a_revision": vuelven, "version_mapa": version_mapa})
    return sorted(afectadas)

"""Constantes, errores y conversiones comunes del mapa de datos (HU-34)."""
from __future__ import annotations

from datetime import datetime, timezone

from app.domain.mapa_datos.modelo_mapa import Elemento, Flujo
from app.domain.models.mapa_datos_tablas import MapaElemento, MapaFlujo


MAX_CAMBIOS_GUARDADOS = 500        # diferencias que se guardan por versión (el resto se cuenta)
TAMANO_PAGINA_VERSIONES = 30


class MapaDatosError(Exception):
    def __init__(self, status: int, codigo: str, mensaje: str, **extra):
        super().__init__(mensaje)
        self.status, self.codigo, self.mensaje, self.extra = status, codigo, mensaje, extra


def _ahora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso(d: datetime | None) -> str | None:
    return d.isoformat() if d else None


def elemento_de_fila(r: MapaElemento) -> Elemento:
    return Elemento(
        id=r.id, tipo=r.tipo, nombre=r.nombre, subtipo=r.subtipo, descripcion=r.descripcion, proveedor=r.proveedor,
        pais=r.pais, responsable=r.responsable, categorias_datos=list(r.categorias_datos or []),
        categorias_titulares=list(r.categorias_titulares or []), nna_declarado=bool(r.nna_declarado),
        rol_tercero=r.rol_tercero, contrato_firmado=r.contrato_firmado, origen=r.origen, clave=r.clave,
        pendiente_revision=bool(r.pendiente_revision),
    )


def flujo_de_fila(r: MapaFlujo) -> Flujo:
    return Flujo(
        id=r.id, origen_id=r.origen_id, destino_id=r.destino_id, finalidad=r.finalidad,
        categorias_datos=list(r.categorias_datos or []), categorias_titulares=list(r.categorias_titulares or []),
        nna_declarado=bool(r.nna_declarado), frecuencia=r.frecuencia, medio=r.medio, cifrado=r.cifrado,
        garantia=r.garantia, origen=r.origen, clave=r.clave, pendiente_revision=bool(r.pendiente_revision),
    )

"""Constantes, errores y utilidades comunes de la revisión interna (HU-40)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timezone

from app.application.informes.formato import ZONA, fecha_local
from app.application.rat import armado_informe_rat as I
from app.domain.models.rat_revision import ABIERTA, RatObservacion
from app.domain.rat import lista_verificacion as R


CLAVE_REGISTRO = "registro:0"
LARGO_OBSERVACION = (5, 1000)
LARGO_CIERRE = (5, 1000)
LARGO_CONCLUSION = 1500
MAX_HISTORIAL_AUDITORIA = 5000
_SOLO_TEXTO = re.compile(r"^[A-Za-zÁÉÍÓÚÜÑáéíóúüñ' .,\-()/]+$")
_PREFIJOS_HISTORIAL = ("rat.", "mapa_datos.", "revision_rat.", "ropa.")


class RevisionError(Exception):
    def __init__(self, status: int, codigo: str, mensaje: str, **extra):
        super().__init__(mensaje)
        self.status, self.codigo, self.mensaje, self.extra = status, codigo, mensaje, extra


def _ahora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso(d: datetime | None) -> str | None:
    return d.isoformat() if d else None


def _texto(valor: str | None) -> str | None:
    return " ".join((valor or "").split()) or None


def _hoy_chile(v: datetime | None = None) -> date:
    """Fecha en Chile de un instante (las fechas de la BD son UTC sin zona); sin argumento, hoy."""
    v = v or datetime.now(timezone.utc)
    if v.tzinfo is None:
        v = v.replace(tzinfo=timezone.utc)
    return v.astimezone(ZONA).date()


def _fecha_txt(d: date | datetime | None) -> str | None:
    if d is None:
        return None
    if isinstance(d, datetime):
        return fecha_local(d, con_hora=False)
    return f"{d:%d-%m-%Y}"


@dataclass
class Contexto:
    inf: I.InformeRat
    version_mapa: int
    objetos: list[R.Objeto]
    por_clave: dict[str, R.Objeto]


def observacion_vista(o: RatObservacion, por_clave: dict[str, R.Objeto] | None = None) -> dict:
    criterios = R.CRITERIOS.get(o.objeto_tipo, {})
    actual = (por_clave or {}).get(o.objeto_clave)
    return {
        "id": o.id, "numero": o.numero, "revision_id": o.revision_id, "objeto_tipo": o.objeto_tipo,
        "objeto_id": o.objeto_id, "objeto_clave": o.objeto_clave, "objeto_nombre": o.objeto_nombre,
        "objeto_existe": o.objeto_tipo == "registro" or actual is not None,
        "criterio": o.criterio, "criterio_titulo": criterios[o.criterio].titulo if o.criterio in criterios else None,
        "prioridad": o.prioridad, "texto": o.texto, "estado": o.estado,
        "fecha_apertura": _iso(o.fecha_apertura), "fecha_cierre": _iso(o.fecha_cierre), "nota_cierre": o.nota_cierre,
        "objeto_cambio": o.objeto_cambio, "reaperturas": o.reaperturas,
        # Mientras está abierta: ¿ya cambió el elemento desde que se observó? (pista de que se corrigió)
        "cambio_desde_apertura": (actual.huella != o.huella_apertura) if (actual and o.huella_apertura
                                                                          and o.estado == ABIERTA) else None,
    }


def _sin_preguntas(objs: list[dict]) -> list[dict]:
    """La pregunta de cada criterio va una sola vez en el catálogo (no repetida en cada punto)."""
    return [{**o, "items": [{k: v for k, v in i.items() if k != "pregunta"} for i in o["items"]]} for o in objs]


def catalogo_criterios() -> dict:
    return {tipo: [{"codigo": c.codigo, "titulo": c.titulo, "pregunta": c.pregunta, "bloqueante": c.bloqueante}
                   for c in lista]
            for tipo, lista in (("actividad", R.CRITERIOS_ACTIVIDAD), ("elemento", R.CRITERIOS_ELEMENTO),
                                ("flujo", R.CRITERIOS_FLUJO))}

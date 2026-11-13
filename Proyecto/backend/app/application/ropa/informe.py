"""
HU-37 · Informe RoPA desde el registro de actividades (lógica PURA: sin BD, sin red, sin reportlab).

Criterio 1 · Se genera desde el RAT vigente sin ingresar los datos de nuevo: parte del informe del registro
(app/application/rat/informe.py: armar), que ya resuelve qué versión de cada actividad entra, y usa SOLO las
actividades con versión vigente (su instantánea inmutable). Las que nunca han estado vigentes no entran
(se cuentan en `excluidas`).

Cada campo del registro se traduce a los del RoPA (la estructura del art. 30 se usa como estándar de
formato; los documentos no la citan):

  Como responsable                      Como encargado (agrupado por organización mandante)
  ─────────────────────────────────     ─────────────────────────────────────────────────────
  Responsable y delegado     ← datos    Encargado y delegado              ← datos
  Finalidades                ← RAT      Responsable por cuenta del cual   ← RAT (nombre) + datos (contacto)
  Categorías de titulares    ← mapa     Categorías de tratamientos        ← RAT (descripción y finalidades)
  Categorías de datos        ← mapa     Transferencias internacionales    ← mapa
  Destinatarios              ← mapa     Medidas de seguridad              ← RAT
  Transferencias internac.   ← mapa
  Plazos de supresión        ← RAT
  Medidas de seguridad       ← RAT

  "datos" = app/domain/ropa/datos.py (lo que el RoPA pide y el registro no tiene).

Criterio 2 · Dos vistas según el rol marcado en cada actividad (contenido.rol de la versión vigente).
Huella: SHA-256 de las versiones incluidas, las partes y los datos de contacto (no de la fecha): si no
cambia, el caso de uso reutiliza la última emisión. Código: CIA-ROPA-2026-000031-7 (módulo 11).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from datetime import datetime

from app.application.informes.ficha import AvisoInforme, digito_verificador
from app.application.informes.motor_pdf import fecha_local
from app.application.rat import informe as I
from app.domain import catalogo_tratamiento as cat_mapa
from app.domain.ropa import datos as D

PREFIJO_CODIGO = "CIA-ROPA"
FORMATO = 1

TITULO = "Registro de actividades de tratamiento (RoPA)"
TITULO_PARTE = {"responsable": "Como responsable del tratamiento", "encargado": "Como encargado del tratamiento"}
NOMBRE_PARTE = {"responsable": "Como responsable", "encargado": "Como encargado"}

# Etiquetas de cada campo, en el orden del documento
CAMPOS_RESPONSABLE = (
    ("responsable", "Responsable y delegado de protección de datos"),
    ("finalidades", "Finalidades del tratamiento"),
    ("titulares", "Categorías de titulares"),
    ("datos", "Categorías de datos personales"),
    ("destinatarios", "Destinatarios"),
    ("transferencias", "Transferencias internacionales"),
    ("plazos", "Plazos previstos de supresión"),
    ("medidas", "Medidas de seguridad técnicas y organizativas"),
)
CAMPOS_ENCARGADO = (
    ("encargado", "Encargado y delegado de protección de datos"),
    ("mandante", "Responsable por cuenta del cual se actúa"),
    ("tratamientos", "Categorías de tratamientos"),
    ("transferencias", "Transferencias internacionales"),
    ("medidas", "Medidas de seguridad técnicas y organizativas"),
)

# Borrador técnico para validar con asesoría legal (como AVISO_RAT). Si cambia, sube la versión.
AVISO_ROPA = AvisoInforme(
    version="2026-11-ropa-v1",
    titulo="Aviso legal",
    texto=(
        "Este documento presenta, en formato RoPA, el registro de actividades de tratamiento que la propia "
        "organización elaboró y mantiene en la plataforma ComplianceIA de Therion Labs. Se arma con la versión "
        "vigente de cada actividad y con los datos de contacto que la organización informó; la plataforma no "
        "revisa la veracidad de lo declarado.",
        "La organización responde por la exactitud, la completitud y la actualización de este registro. Este "
        "documento no es una auditoría, no certifica el cumplimiento de ninguna norma y no constituye asesoría "
        "legal.",
        "Antes de entregarlo a un cliente, una casa matriz o un socio, se recomienda validarlo con el encargado "
        "o delegado de protección de datos y con un abogado.",
    ),
    pie="La plataforma apoya la gestión del registro y no reemplaza la asesoría legal.",
)


# ============================================================ resultado
@dataclass(frozen=True)
class ActividadRopa:
    numero: int
    id: int
    nombre: str
    rol: str                                   # "responsable" | "encargado"
    version: int | None
    fecha_version: datetime | None
    huella_version: str | None
    area: str | None
    descripcion: str | None
    finalidades: tuple[str, ...]
    titulares: tuple[str, ...]
    datos: tuple[str, ...]
    sensibles: bool
    destinatarios: tuple[str, ...]
    transferencias: tuple[dict, ...]           # {destino, pais, garantia, con_garantia}
    plazos: tuple[str, ...]
    medidas: dict                              # {grupo: [medidas]}
    mandante_clave: str | None = None
    mandante_nombre: str | None = None


@dataclass(frozen=True)
class GrupoEncargado:
    clave: str
    nombre: str
    contacto: dict                             # {direccion, correo, dpo}
    actividades: tuple[ActividadRopa, ...]


@dataclass(frozen=True)
class InformeRopa:
    empresa: str
    rut: str | None
    generado: datetime
    datos: dict                                # app/domain/ropa/datos.py: completar()
    partes: tuple[str, ...]                    # las que trae el informe, en orden
    responsable: tuple[ActividadRopa, ...]
    encargado: tuple[GrupoEncargado, ...]
    excluidas: int                             # actividades sin versión vigente (no entran)
    huella: str
    aviso: AvisoInforme = AVISO_ROPA
    codigo: str | None = None
    version: int | None = None
    disponibles: tuple[str, ...] = field(default=())   # partes con actividades vigentes

    def con_emision(self, codigo: str, version: int) -> "InformeRopa":
        return replace(self, codigo=codigo, version=version)

    @property
    def actividades(self) -> list[ActividadRopa]:
        return list(self.responsable) + [a for g in self.encargado for a in g.actividades]

    @property
    def transferencias(self) -> list[dict]:
        """Todas las transferencias de las actividades incluidas, con su actividad y su parte."""
        return [{**t, "actividad": a.nombre, "rol": a.rol} for a in self.actividades for t in a.transferencias]

    @property
    def resumen(self) -> dict:
        return {
            "responsable": len(self.responsable),
            "encargado": sum(len(g.actividades) for g in self.encargado),
            "organizaciones": len(self.encargado),
            "transferencias": len(self.transferencias),
            "transferencias_sin_garantia": sum(1 for t in self.transferencias if not t["con_garantia"]),
            "excluidas": self.excluidas,
        }


# ============================================================ código verificable
def codigo(emision_id: int, anio: int) -> str:
    return f"{PREFIJO_CODIGO}-{anio:04d}-{emision_id:06d}-{digito_verificador(emision_id)}"


def nombre_archivo(inf: InformeRopa, extension: str) -> str:
    """ropa_v3_2026-11-13.pdf. Solo [A-Za-z0-9_.-] (lo exige Mis documentos)."""
    dd, mm, aaaa = fecha_local(inf.generado, con_hora=False).split("-")
    v = f"v{inf.version}" if inf.version else "vista-previa"
    return f"ropa_{v}_{aaaa}-{mm}-{dd}.{extension}"


# ============================================================ traducción de una actividad
def _destinatarios(a: I.ActividadInforme) -> tuple[str, ...]:
    terceros = a.mapa.get("terceros") or []
    if not terceros:
        return ("No se comunican a terceros.",) if a.contenido.get("sin_destinatarios") else ()
    salida = []
    for t in terceros:
        extras = [x for x in (cat_mapa.etiqueta("rol", t.get("rol_tercero")) if t.get("rol_tercero") else "",
                              cat_mapa.nombre_pais(t.get("pais")) if t.get("pais") else "") if x]
        salida.append(f"{t.get('nombre', '?')}" + (f" ({', '.join(extras)})" if extras else ""))
    return tuple(salida)


def _transferencias(a: I.ActividadInforme) -> tuple[dict, ...]:
    return tuple({
        "destino": t.get("nombre") or "?",
        "pais": t.get("pais_nombre") or cat_mapa.nombre_pais(t.get("pais_destino")) or "—",
        "garantia": t.get("garantia_nombre") or "Sin garantía registrada",
        "con_garantia": bool(t.get("garantia_valida")),
    } for t in a.transferencias)


def _actividad(numero: int, a: I.ActividadInforme, mandantes: dict[str, str]) -> ActividadRopa:
    c = a.contenido
    rol = "encargado" if c.get("rol") == "encargado" else "responsable"
    clave = D.clave_mandante(c.get("responsable_mandante")) if rol == "encargado" else None
    tipos = a.mapa.get("tipos_datos") or []
    return ActividadRopa(
        numero=numero, id=a.id, nombre=a.nombre, rol=rol, version=a.version, fecha_version=a.fecha_version,
        huella_version=a.huella_version, area=c.get("area"), descripcion=c.get("descripcion"),
        finalidades=tuple(c.get("finalidades") or []),
        titulares=tuple(f"{t.get('nombre') or cat_mapa.nombre_titular(t['codigo'])}{' (NNA)' if t.get('nna') else ''}"
                        for t in a.mapa.get("titulares") or []),
        datos=tuple(f"{t.get('nombre') or cat_mapa.nombre_dato(t['codigo'])}{' (sensible)' if t.get('sensible') else ''}"
                    for t in tipos),
        sensibles=any(t.get("sensible") for t in tipos),
        destinatarios=_destinatarios(a),
        transferencias=_transferencias(a),
        plazos=tuple(f"{cat_mapa.nombre_dato(p['categoria'])}: {I.texto_plazo(p)}"
                     + (f" ({p['fundamento']})" if p.get("fundamento") else "") for p in c.get("plazos") or []),
        medidas=I.medidas_por_grupo(c),
        mandante_clave=clave,
        mandante_nombre=(mandantes.get(clave) or c.get("responsable_mandante")) if clave else None,
    )


def vigentes(inf_rat: I.InformeRat) -> list[I.ActividadInforme]:
    return [a for a in inf_rat.actividades if a.origen == "vigente"]


def mandantes(inf_rat: I.InformeRat) -> dict[str, str]:
    """{clave: nombre} de las organizaciones por cuenta de las cuales la empresa actúa (actividades vigentes)."""
    salida: dict[str, str] = {}
    for a in vigentes(inf_rat):
        if a.contenido.get("rol") == "encargado" and a.contenido.get("responsable_mandante"):
            clave = D.clave_mandante(a.contenido["responsable_mandante"])
            salida.setdefault(clave, a.contenido["responsable_mandante"])
    return dict(sorted(salida.items(), key=lambda x: x[1].lower()))


def partes_disponibles(inf_rat: I.InformeRat) -> tuple[str, ...]:
    roles = {"encargado" if a.contenido.get("rol") == "encargado" else "responsable" for a in vigentes(inf_rat)}
    return tuple(p for p in D.PARTES if p in roles)


def partes_efectivas(pedidas, disponibles: tuple[str, ...]) -> tuple[str, ...]:
    """Las partes pedidas que tienen actividades (sin pedir nada: todas las disponibles)."""
    pedidas = [p for p in (pedidas or []) if p in D.PARTES]
    if not pedidas:
        return disponibles
    return tuple(p for p in D.PARTES if p in pedidas and p in disponibles)


# ============================================================ huella y armado
def huella(acts: list[ActividadRopa], partes: tuple[str, ...], datos: dict, claves: list[str]) -> str:
    d = D.completar(datos)
    contacto = {k: d.get(k) for k in D.CAMPOS_EMPRESA}
    contacto["mandantes"] = {k: d["mandantes"].get(k) for k in sorted(claves)}
    partes_act = sorted([a.id, a.version, a.huella_version, a.rol, a.mandante_clave] for a in acts)
    texto = json.dumps({"formato": FORMATO, "partes": list(partes), "actividades": partes_act, "datos": contacto},
                       sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def armar(inf_rat: I.InformeRat, datos: dict | None, partes=None, generado: datetime | None = None) -> InformeRopa:
    """El informe RoPA completo, sin código ni versión (los pone el caso de uso al emitir)."""
    d = D.completar(datos)
    disponibles = partes_disponibles(inf_rat)
    efectivas = partes_efectivas(partes, disponibles)
    nombres = mandantes(inf_rat)
    acts = [_actividad(0, a, nombres) for a in vigentes(inf_rat)]
    resp = [a for a in acts if a.rol == "responsable"] if "responsable" in efectivas else []
    enc = [a for a in acts if a.rol == "encargado"] if "encargado" in efectivas else []
    numero = 0
    numeradas_resp = []
    for a in resp:
        numero += 1
        numeradas_resp.append(replace(a, numero=numero))
    grupos = []
    for clave, nombre in nombres.items():
        del_grupo = [a for a in enc if a.mandante_clave == clave]
        if not del_grupo:
            continue
        numeradas = []
        for a in del_grupo:
            numero += 1
            numeradas.append(replace(a, numero=numero))
        m = d["mandantes"].get(clave) or {}
        grupos.append(GrupoEncargado(clave=clave, nombre=nombre, actividades=tuple(numeradas),
                                     contacto={"direccion": m.get("direccion"), "correo": m.get("correo"),
                                               "dpo": m.get("dpo")}))
    incluidas = numeradas_resp + [a for g in grupos for a in g.actividades]
    return InformeRopa(
        empresa=inf_rat.empresa, rut=inf_rat.rut, generado=generado or inf_rat.generado, datos=d,
        partes=efectivas, responsable=tuple(numeradas_resp), encargado=tuple(grupos),
        excluidas=sum(1 for a in inf_rat.actividades if a.origen != "vigente"),
        huella=huella(incluidas, efectivas, d, [g.clave for g in grupos]), disponibles=disponibles)


# ============================================================ textos legibles (PDF, XLSX y panel)
def texto_contacto_empresa(inf: InformeRopa) -> list[str]:
    d = inf.datos
    lineas = [inf.empresa + (f" (RUT {inf.rut})" if inf.rut else "")]
    if d.get("direccion"):
        lineas.append(d["direccion"])
    contacto = " · ".join(x for x in (d.get("correo"), d.get("telefono")) if x)
    if contacto:
        lineas.append(contacto)
    return lineas


def texto_delegado(inf: InformeRopa) -> str:
    d = inf.datos
    if d.get("tiene_dpo") is True:
        return " · ".join(x for x in (d.get("dpo_cargo"), d.get("dpo_correo")) if x) or "Designado"
    if d.get("tiene_dpo") is False:
        return "No designado"
    return "Sin indicar"


def texto_mandante(g: GrupoEncargado) -> list[str]:
    lineas = [g.nombre]
    if g.contacto.get("direccion"):
        lineas.append(g.contacto["direccion"])
    if g.contacto.get("correo"):
        lineas.append(g.contacto["correo"])
    lineas.append(f"Delegado de protección de datos: {g.contacto['dpo']}" if g.contacto.get("dpo")
                  else "Delegado de protección de datos: sin informar")
    return lineas


def texto_transferencia(t: dict) -> str:
    return f"{t['pais']} · {t['destino']} · {t['garantia']}"


def texto_medidas(medidas: dict) -> list[str]:
    return [f"{g}: {', '.join(v)}" for g, v in medidas.items()] or ["Sin medidas registradas"]


def texto_tratamientos(a: ActividadRopa) -> list[str]:
    lineas = [a.descripcion] if a.descripcion else []
    return lineas + list(a.finalidades) or [a.nombre]


def campos_responsable(inf: InformeRopa, a: ActividadRopa) -> list[tuple[str, str, list[str]]]:
    """(código, título, líneas) de una actividad como responsable."""
    valores = {
        "responsable": texto_contacto_empresa(inf) + [f"Delegado de protección de datos: {texto_delegado(inf)}"],
        "finalidades": list(a.finalidades) or ["Sin indicar"],
        "titulares": list(a.titulares) or ["Sin indicar"],
        "datos": list(a.datos) or ["Sin indicar"],
        "destinatarios": list(a.destinatarios) or ["Sin indicar"],
        "transferencias": [texto_transferencia(t) for t in a.transferencias] or ["No hay transferencias internacionales."],
        "plazos": list(a.plazos) or ["Sin indicar"],
        "medidas": texto_medidas(a.medidas),
    }
    return [(k, t, valores[k]) for k, t in CAMPOS_RESPONSABLE]


def campos_encargado(inf: InformeRopa, g: GrupoEncargado, a: ActividadRopa) -> list[tuple[str, str, list[str]]]:
    valores = {
        "encargado": texto_contacto_empresa(inf) + [f"Delegado de protección de datos: {texto_delegado(inf)}"],
        "mandante": texto_mandante(g),
        "tratamientos": texto_tratamientos(a),
        "transferencias": [texto_transferencia(t) for t in a.transferencias] or ["No hay transferencias internacionales."],
        "medidas": texto_medidas(a.medidas),
    }
    return [(k, t, valores[k]) for k, t in CAMPOS_ENCARGADO]


def _actividad_publica(a: ActividadRopa) -> dict:
    return {
        "id": a.id, "numero": a.numero, "nombre": a.nombre, "version": a.version, "area": a.area,
        "descripcion": a.descripcion, "finalidades": list(a.finalidades), "titulares": list(a.titulares),
        "datos": list(a.datos), "sensibles": a.sensibles, "destinatarios": list(a.destinatarios),
        "transferencias": list(a.transferencias), "plazos": list(a.plazos), "medidas": a.medidas,
        "mandante": a.mandante_clave,
    }


def previa_publica(inf: InformeRopa) -> dict:
    """Vista previa para el panel: lo mismo que dirá el informe, sin los textos ya armados."""
    return {
        "partes": list(inf.partes),
        "disponibles": list(inf.disponibles),
        "responsable": [_actividad_publica(a) for a in inf.responsable],
        "encargado": [{"clave": g.clave, "nombre": g.nombre, "actividades": [_actividad_publica(a) for a in g.actividades]}
                      for g in inf.encargado],
        "transferencias": inf.transferencias,
        "resumen": inf.resumen,
        "huella": inf.huella,
        "aviso": {"version": inf.aviso.version, "pie": inf.aviso.pie},
    }


__all__ = [
    "AVISO_ROPA", "TITULO", "TITULO_PARTE", "NOMBRE_PARTE", "CAMPOS_RESPONSABLE", "CAMPOS_ENCARGADO",
    "ActividadRopa", "GrupoEncargado", "InformeRopa", "armar", "codigo", "nombre_archivo", "huella", "mandantes",
    "vigentes", "partes_disponibles", "partes_efectivas", "texto_contacto_empresa", "texto_delegado",
    "texto_mandante", "texto_transferencia", "texto_medidas", "texto_tratamientos", "campos_responsable",
    "campos_encargado", "previa_publica",
]

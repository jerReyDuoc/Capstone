"""
HU-41 · Mapa de datos, RAT y RoPA de la PROPIA plataforma, generados desde el inventario (lógica PURA).

Sin BD, sin red y sin reportlab, como app/application/rat/informe.py: recibe la configuración (`conf`, el
objeto Settings o uno equivalente) y el plazo de titulares vigente, y arma las MISMAS estructuras que el
registro de una empresa cliente (Elemento, Flujo, contenido de actividad, FuenteActividad). Después se usan
los mismos módulos del cliente sin cambiarlos: rat/analisis.py calcula lo que la actividad toma del mapa y
su completitud, rat/informe.py arma el informe y pdf_rat/xlsx_rat/pdf_ropa/xlsx_ropa lo dibujan.

  Actividades   app/core/catalogo_datos_personales.py: ACTIVIDADES_PLATAFORMA (tablas, finalidades, base,
                titulares, elementos y medidas). Las categorías de datos salen de las columnas personales
                de sus tablas.
  Plazos        uno por categoría de datos. Se agrupan las columnas de la categoría por su conservación; las
                que nombran un ajuste (AJUSTE_POR_CONSERVACION) toman su VALOR VIGENTE. Con más de uno, rige
                el más largo y el fundamento los nombra todos. Sin ningún valor, el plazo queda sin número
                (y la actividad incompleta): se informa, no se inventa.
  Mapa          la plataforma (Chile, quien la opera) envía datos a la base, los archivos y las colas (en el
                país de alojamiento) y a cada proveedor activo. Las transferencias internacionales y sus
                garantías las calcula app/domain/mapa_datos/analisis.py, igual que para un cliente.
  Proveedores   solo los que usa la configuración activa: Groq con LLM_PROVIDER=groq, el correo con
                CORREO_MODO=smtp y Turnstile con TURNSTILE_SECRET_KEY. Azure siempre (alojamiento).

Todas las actividades entran como vigentes (el inventario revisado en cada cambio de código es la versión
aprobada) y el informe es OFICIAL solo si todas están completas; si no, sale como BORRADOR con los motivos
exactos (decisión D12). El RoPA las incluye todas: muestra "Sin plazo definido" donde falta.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from datetime import datetime

from app.application.informes.ficha import AvisoInforme
from app.application.rat import informe as I
from app.core import catalogo_datos_personales as inv
from app.domain import catalogo_tratamiento as cat_mapa
from app.domain.mapa_datos.modelo import Elemento, Flujo
from app.domain.rat import analisis
from app.domain.rat import catalogo as cat
from app.domain.rat import versiones as V

FORMATO = 1
PREFIJO_RAT = "CIA-PLAT-REG"
PREFIJO_ROPA = "CIA-PLAT-ROPA"
RUBRO_THERION = "Tecnología: software como servicio (SaaS)"
RESPONSABLE_INTERNO = "Equipo de plataforma de Therion Labs"

FUENTE_PANEL = "panel"          # plazo de titulares fijado en Retención de datos
FUENTE_ENTORNO = "entorno"      # valor de la configuración del despliegue
TEXTO_FUENTE = {FUENTE_PANEL: "fijado en Retención de datos", FUENTE_ENTORNO: "valor de la configuración"}

AVISO_RAT_PLATAFORMA = AvisoInforme(
    version="2026-11-rat-plataforma-v1",
    titulo="Aviso legal",
    texto=(
        "Este informe describe cómo la plataforma ComplianceIA trata datos personales. Se genera directamente "
        "del inventario de datos del sistema y de los plazos de retención configurados, con las mismas "
        "herramientas que Therion Labs ofrece a sus clientes.",
        "Therion Labs, como responsable del tratamiento, responde por la exactitud y la actualización de este "
        "registro y por el cumplimiento de la Ley N.º 21.719 sobre protección de datos personales. Este documento "
        "no es una auditoría externa, no certifica el cumplimiento de ninguna norma y no constituye asesoría "
        "legal.",
        "Las bases de licitud, el rol de Therion Labs en cada actividad y las garantías de las transferencias "
        "deben validarse con el delegado de protección de datos y con un abogado antes de presentarlo.",
    ),
    pie="Registro generado desde el inventario de datos de la plataforma; no reemplaza la asesoría legal.",
)
NOTA_BORRADOR = ("Para emitir el informe oficial, define en la configuración de la plataforma los plazos y las "
                 "garantías que faltan y vuelve a generarlo.")

_ID_ELEMENTO = {e.clave: i for i, e in enumerate(inv.ELEMENTOS_PLATAFORMA, start=1)}
_ID_PROVEEDOR = {p.clave: 10 + i for i, p in enumerate(inv.PROVEEDORES_PLATAFORMA, start=1)}
_ID_FLUJO_BASE = 100


# ============================================================ ajustes y proveedores
@dataclass(frozen=True)
class AjustePlazo:
    clave: str                 # nombre técnico (RETENCION_ARCOP_CERRADAS_DIAS…)
    nombre: str                # en lenguaje simple
    dias: int | None           # None = regla desactivada (o 0: sin plazo de gracia)
    fuente: str                # panel | entorno

    @property
    def activo(self) -> bool:
        return bool(self.dias and self.dias >= 1)

    def como_dict(self) -> dict:
        return {"clave": self.clave, "nombre": self.nombre, "dias": self.dias, "fuente": self.fuente,
                "fuente_texto": TEXTO_FUENTE.get(self.fuente, ""), "activo": self.activo}


def ajustes_efectivos(conf, plazo_titular: tuple[int | None, str] | None = None) -> dict[str, AjustePlazo]:
    """El valor VIGENTE de cada ajuste de plazo. `plazo_titular` = (días, fuente) del panel de retención."""
    salida: dict[str, AjustePlazo] = {}
    for clave in dict.fromkeys(inv.AJUSTE_POR_CONSERVACION.values()):
        if clave == "RETENCION_DATOS_TITULAR_DIAS" and plazo_titular is not None:
            dias, fuente = plazo_titular
        else:
            dias, fuente = getattr(conf, clave, None), FUENTE_ENTORNO
        salida[clave] = AjustePlazo(clave, inv.NOMBRE_AJUSTE[clave], dias, fuente)
    return salida


@dataclass(frozen=True)
class Proveedor:
    clave: str
    nombre: str
    subtipo: str
    descripcion: str
    pais: str | None
    garantia: str | None
    contrato_confirmado: bool
    categorias: frozenset[str] | None

    @property
    def garantia_valida(self) -> bool:
        return self.garantia in cat_mapa.GARANTIAS_VALIDAS

    def como_dict(self) -> dict:
        return {"clave": self.clave, "nombre": self.nombre, "descripcion": self.descripcion,
                "pais": self.pais, "pais_nombre": cat_mapa.nombre_pais(self.pais) if self.pais else None,
                "rol": "encargado", "rol_nombre": cat_mapa.etiqueta("rol", "encargado"),
                "garantia": self.garantia,
                "garantia_nombre": cat_mapa.etiqueta("garantia", self.garantia) if self.garantia else None,
                "garantia_valida": self.garantia_valida, "contrato_confirmado": self.contrato_confirmado}


def _confirmados(conf) -> set[str]:
    return {x.strip().lower() for x in (getattr(conf, "PROVEEDORES_CONTRATO_CONFIRMADO", "") or "").split(",")
            if x.strip()}


def proveedores_activos(conf) -> list[Proveedor]:
    """Los encargados que usa la configuración activa, con su país y su garantía."""
    confirmados = _confirmados(conf)
    activos = {"azure": True,
               "llm": getattr(conf, "LLM_PROVIDER", None) == "groq",
               "correo": getattr(conf, "CORREO_MODO", None) == "smtp",
               "verificacion": bool(getattr(conf, "TURNSTILE_SECRET_KEY", None))}
    salida = []
    for p in inv.PROVEEDORES_PLATAFORMA:
        if not activos.get(p.clave):
            continue
        nombre, pais, garantia = p.nombre, p.pais, p.garantia
        if p.clave == "correo":
            nombre = (getattr(conf, "CORREO_PROVEEDOR_NOMBRE", None) or "").strip() or p.nombre
            pais = getattr(conf, "CORREO_PROVEEDOR_PAIS", None) or None
            garantia = getattr(conf, "CORREO_PROVEEDOR_GARANTIA", None) or None
        salida.append(Proveedor(p.clave, nombre, p.subtipo, p.descripcion, pais, garantia,
                                p.clave in confirmados, p.categorias))
    return salida


# ============================================================ plazos de una actividad
@dataclass(frozen=True)
class PlazoCategoria:
    categoria: str
    dias: int | None
    ajuste: str | None              # el que rige (el de más días)
    ajustes: tuple[str, ...]        # todos los ajustes que nombra la categoría
    desactivados: tuple[str, ...]   # ajustes nombrados pero sin valor
    sin_numero: tuple[str, ...]     # conservaciones que dependen de un evento o están pendientes
    fundamento: str

    def como_dict(self) -> dict:
        return {"categoria": self.categoria, "categoria_nombre": cat_mapa.nombre_dato(self.categoria),
                "dias": self.dias, "ajuste": self.ajuste, "ajustes": list(self.ajustes),
                "desactivados": list(self.desactivados), "sin_numero": list(self.sin_numero),
                "fundamento": self.fundamento}


def _recortar(texto: str, maximo: int = 300) -> str:
    return texto if len(texto) <= maximo else texto[: maximo - 1].rstrip(" ;,") + "…"


def plazos_actividad(act: inv.ActividadPlataforma, ajustes: dict[str, AjustePlazo]) -> list[PlazoCategoria]:
    grupos: dict[str, list[str]] = {}
    for tabla, columna, dato in inv.columnas_de_actividad(act):
        lista = grupos.setdefault(inv.categoria_rat(tabla, columna, dato), [])
        if dato.conservacion not in lista:
            lista.append(dato.conservacion)
    salida = []
    for categoria, conservaciones in grupos.items():
        ajustes_cat = list(dict.fromkeys(inv.AJUSTE_POR_CONSERVACION[c] for c in conservaciones
                                         if c in inv.AJUSTE_POR_CONSERVACION))
        activos = [ajustes[k] for k in ajustes_cat if ajustes[k].activo]
        desactivados = tuple(k for k in ajustes_cat if not ajustes[k].activo)
        sin_numero = tuple(c for c in conservaciones if c not in inv.AJUSTE_POR_CONSERVACION)
        rige = max(activos, key=lambda a: a.dias) if activos else None
        partes = [f"{a.nombre} ({TEXTO_FUENTE[a.fuente]})" for a in sorted(activos, key=lambda a: -a.dias)]
        partes += [f"{ajustes[k].nombre}: regla desactivada" for k in desactivados]
        partes += [inv.TEXTO_SIN_PLAZO.get(c, c) for c in sin_numero]
        salida.append(PlazoCategoria(categoria, rige.dias if rige else None, rige.clave if rige else None,
                                     tuple(ajustes_cat), desactivados, sin_numero, _recortar("; ".join(partes))))
    return salida


# ============================================================ registro completo
@dataclass(frozen=True)
class ActividadGenerada:
    id: int
    definicion: inv.ActividadPlataforma
    contenido: dict                 # mismo formato que rat_actividad.contenido
    derivados: dict                 # lo que toma del mapa (rat/analisis.py: derivados)
    completitud: dict               # rat/analisis.py: completitud
    plazos: tuple[PlazoCategoria, ...]
    instantanea: dict               # rat/versiones.py: instantanea (lo que entra al informe)
    huella: str

    @property
    def completa(self) -> bool:
        return not self.completitud["faltantes"]

    @property
    def clave(self) -> str:
        return self.definicion.clave


@dataclass(frozen=True)
class RegistroPlataforma:
    elementos: tuple[Elemento, ...]
    flujos: tuple[Flujo, ...]
    actividades: tuple[ActividadGenerada, ...]
    proveedores: tuple[Proveedor, ...]
    ajustes: dict
    huella: str
    pais_alojamiento: str
    razon_social: str
    rut: str | None = None
    incompletas: tuple[str, ...] = field(default=())

    @property
    def oficial(self) -> bool:
        return not self.incompletas


def _huella(obj) -> str:
    texto = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _categorias_actividad(act: inv.ActividadPlataforma) -> list[str]:
    vistas: list[str] = []
    for tabla, columna, dato in inv.columnas_de_actividad(act):
        c = inv.categoria_rat(tabla, columna, dato)
        if c not in vistas:
            vistas.append(c)
    return vistas


def generar(conf, plazo_titular: tuple[int | None, str] | None = None) -> RegistroPlataforma:
    """El registro completo de la plataforma con la configuración y el plazo de titulares vigentes."""
    ajustes = ajustes_efectivos(conf, plazo_titular)
    proveedores = proveedores_activos(conf)
    prov_por_clave = {p.clave: p for p in proveedores}
    pais_aloj = getattr(conf, "PLATAFORMA_PAIS_ALOJAMIENTO", "US") or "US"
    elem_def = {e.clave: e for e in inv.ELEMENTOS_PLATAFORMA}

    # 1. Qué categorías y titulares usa cada actividad en cada elemento (solo elementos disponibles)
    uso: dict[str, dict[str, tuple[list[str], list[str]]]] = {}
    for act in inv.ACTIVIDADES_PLATAFORMA:
        cats = _categorias_actividad(act)
        sel: dict[str, tuple[list[str], list[str]]] = {}
        for clave in act.elementos:
            definicion = elem_def.get(clave) or prov_por_clave.get(clave)
            if definicion is None:          # proveedor que la configuración no usa
                continue
            filtro = definicion.categorias
            propias = [c for c in cats if filtro is None or c in filtro]
            if propias:
                sel[clave] = (propias, list(act.titulares))
        uso[act.clave] = sel

    def union(clave: str, i: int) -> list[str]:
        vistos: list[str] = []
        for sel in uso.values():
            for c in sel.get(clave, ([], []))[i]:
                if c not in vistos:
                    vistos.append(c)
        return vistos

    # 2. Elementos del mapa (solo los que alguna actividad usa)
    usados = {k for sel in uso.values() for k in sel}
    elementos: list[Elemento] = []
    for e in inv.ELEMENTOS_PLATAFORMA:
        if e.clave not in usados:
            continue
        elementos.append(Elemento(
            id=_ID_ELEMENTO[e.clave], tipo=e.tipo, nombre=e.nombre, subtipo=e.subtipo, descripcion=e.descripcion,
            proveedor=e.proveedor, pais=cat_mapa.PAIS_LOCAL if e.ubicacion == "local" else pais_aloj,
            responsable=RESPONSABLE_INTERNO, categorias_datos=union(e.clave, 0),
            categorias_titulares=union(e.clave, 1), origen="plantilla", clave=e.clave))
    for p in proveedores:
        if p.clave not in usados:
            continue
        elementos.append(Elemento(
            id=_ID_PROVEEDOR[p.clave], tipo="tercero", nombre=p.nombre, subtipo=p.subtipo, descripcion=p.descripcion,
            proveedor=p.nombre, pais=p.pais, categorias_datos=union(p.clave, 0), categorias_titulares=union(p.clave, 1),
            rol_tercero="encargado", contrato_firmado=True if p.contrato_confirmado else None, origen="plantilla",
            clave=p.clave))
    por_clave = {e.clave: e for e in elementos}
    origen = por_clave["plataforma"]
    garantia_aloj = prov_por_clave["azure"].garantia if "azure" in prov_por_clave else None

    # 3. Flujos: de la plataforma a cada elemento (la garantía del alojamiento cubre la base, los archivos y
    #    las colas, que viven en la nube del proveedor de alojamiento)
    flujos: list[Flujo] = []
    for e in elementos:
        if e.clave == "plataforma":
            continue
        if e.es_tercero:
            garantia = prov_por_clave[e.clave].garantia
            finalidad = prov_por_clave[e.clave].descripcion
        else:
            garantia = garantia_aloj if e.pais != cat_mapa.PAIS_LOCAL else None
            finalidad = f"Guardar los datos en {e.nombre.lower()}"
        flujos.append(Flujo(
            id=_ID_FLUJO_BASE + e.id, origen_id=origen.id, destino_id=e.id, finalidad=finalidad[:300],
            categorias_datos=list(e.categorias_datos), categorias_titulares=list(e.categorias_titulares),
            frecuencia="tiempo_real", medio="correo" if e.clave == "correo" else "api", cifrado=True,
            garantia=garantia, origen="plantilla", clave=e.clave))
    flujo_de = {f.clave: f for f in flujos}

    # 4. Contenido de cada actividad (mismo formato que una actividad del cliente) y lo que toma del mapa
    actividades: list[ActividadGenerada] = []
    for numero, act in enumerate(inv.ACTIVIDADES_PLATAFORMA, start=1):
        sel = uso[act.clave]
        plazos = plazos_actividad(act, ajustes)
        contenido = {
            "nombre": act.nombre, "descripcion": act.descripcion, "area": act.area,
            "elementos": [{"id": por_clave[k].id, "categorias_datos": c, "categorias_titulares": t}
                          for k, (c, t) in sel.items()],
            "flujos": [{"id": flujo_de[k].id, "categorias_datos": c, "categorias_titulares": t}
                       for k, (c, t) in sel.items() if k in flujo_de],
            "finalidades": list(act.finalidades),
            "fuentes": [{"tipo": tipo, "detalle": detalle} for tipo, detalle in act.fuentes],
            "base_licitud": act.base_licitud, "interes_legitimo": act.interes_legitimo, "base_sensibles": None,
            "sin_destinatarios": False,
            "plazos": [{"categoria": p.categoria, "plazo": p.dias, "unidad": "dias" if p.dias else None,
                        "desde": inv.INICIO_POR_AJUSTE.get(p.ajuste) if p.ajuste else None,
                        "fundamento": p.fundamento} for p in plazos],
            "decisiones": {"existe": False, "perfilamiento": False, "logica": None, "consecuencias": None,
                           "intervencion_humana": None},
            "medidas": {"codigos": list(act.medidas), "otras": None},
            "rol": "responsable", "responsable_mandante": None, "ambito_nota": act.ambito_nota,
        }
        deriv = analisis.derivados(contenido, elementos, flujos)
        comp = analisis.completitud(contenido, deriv)
        inst = V.instantanea(contenido, deriv)
        actividades.append(ActividadGenerada(
            id=numero, definicion=act, contenido=contenido, derivados=deriv, completitud=comp,
            plazos=tuple(plazos), instantanea=inst, huella=V.huella(inst)))

    huella = _huella({"formato": FORMATO, "actividades": [[a.clave, a.huella] for a in actividades],
                      "proveedores": [p.como_dict() for p in proveedores]})
    return RegistroPlataforma(
        elementos=tuple(elementos), flujos=tuple(flujos), actividades=tuple(actividades),
        proveedores=tuple(proveedores), ajustes=ajustes, huella=huella, pais_alojamiento=pais_aloj,
        razon_social=getattr(conf, "THERION_RAZON_SOCIAL", "Therion Labs SpA"),
        rut=getattr(conf, "THERION_RUT", None) or None,
        incompletas=tuple(a.clave for a in actividades if not a.completa))


# ============================================================ informes (mismo formato que el cliente)
def motivos_borrador(reg: RegistroPlataforma) -> list[str]:
    motivos = []
    for a in reg.actividades:
        if a.completa:
            continue
        faltan = "; ".join(f["mensaje"] for f in a.completitud["faltantes"])
        motivos.append(f"{a.definicion.nombre}: {faltan}")
    return motivos


def informe_rat(reg: RegistroPlataforma, version: int, generado: datetime) -> I.InformeRat:
    """El informe RAT de la plataforma con el armado y los textos del informe del cliente."""
    fuentes = [I.FuenteActividad(
        id=a.id, nombre=a.definicion.nombre, estado=cat.VIGENTE, version_vigente=version, fecha_vigencia=generado,
        fecha_actualizacion=generado, instantanea=a.instantanea,
        huella_version=a.huella, fecha_version=generado) for a in reg.actividades]
    inf = I.armar(fuentes, generado, reg.razon_social, reg.rut, RUBRO_THERION, 0)
    motivos = motivos_borrador(reg)
    return replace(inf, huella=reg.huella, aviso=AVISO_RAT_PLATAFORMA, borrador=bool(motivos),
                   motivos_borrador=tuple(motivos), nota_borrador=NOTA_BORRADOR)


def huella_ropa(reg: RegistroPlataforma, datos: dict | None) -> str:
    from app.domain.ropa import datos as D
    d = D.completar(datos)
    return _huella({"formato": FORMATO, "registro": reg.huella, "datos": {k: d.get(k) for k in D.CAMPOS_EMPRESA}})


def informe_ropa(reg: RegistroPlataforma, datos: dict | None, version_registro: int, generado: datetime):
    """El RoPA de la plataforma (Therion Labs como responsable) con el armado del cliente."""
    from app.application.ropa import informe as R
    inf = R.armar(informe_rat(reg, version_registro, generado), datos, None, generado)
    return replace(inf, huella=huella_ropa(reg, datos))


def codigo(prefijo: str, emision_id: int, anio: int) -> str:
    from app.application.informes.ficha import digito_verificador
    return f"{prefijo}-{anio:04d}-{emision_id:06d}-{digito_verificador(emision_id)}"


def leer_codigo(texto: str) -> tuple[str, int, int] | None:
    """(tipo "rat"|"ropa", año, id) si el código está bien formado y el dígito cuadra; si no, None."""
    from app.application.informes.ficha import digito_verificador
    t = (texto or "").strip().upper().replace(" ", "")
    for tipo, prefijo in (("ropa", PREFIJO_ROPA), ("rat", PREFIJO_RAT)):
        if not t.startswith(prefijo + "-"):
            continue
        partes = t[len(prefijo) + 1:].split("-")
        if len(partes) != 3:
            return None
        anio, numero, dv = partes
        if not (anio.isdigit() and len(anio) == 4 and numero.isdigit() and 6 <= len(numero) <= 9):
            return None
        if digito_verificador(int(numero)) != dv:
            return None
        return tipo, int(anio), int(numero)
    return None


# ============================================================ vistas para el panel
def vista_actividad(a: ActividadGenerada, proveedores: dict[str, Proveedor]) -> dict:
    d = a.definicion
    deriv = a.derivados
    return {
        "clave": d.clave, "numero": a.id, "nombre": d.nombre, "area": d.area, "descripcion": d.descripcion,
        "tablas": list(d.tablas), "finalidades": list(d.finalidades),
        "base_licitud": d.base_licitud, "base_nombre": I.texto_base(a.contenido),
        "rol": "responsable", "rol_nombre": I.texto_rol(a.contenido),
        "fuentes": [I.texto_fuente(f) for f in a.contenido["fuentes"]],
        "titulares": [t["nombre"] for t in deriv["titulares"]],
        "datos": [t["nombre"] for t in deriv["tipos_datos"]],
        "plazos": [{**p.como_dict(), "texto": I.texto_plazo(c)}
                   for p, c in zip(a.plazos, a.contenido["plazos"])],
        "proveedores": [proveedores[k].como_dict() for k in d.elementos if k in proveedores],
        "transferencias": deriv["transferencias"],
        "medidas": I.medidas_por_grupo(a.contenido),
        "decisiones": I.texto_decisiones(a.contenido),
        "completa": a.completa, "porcentaje": a.completitud["porcentaje"],
        "faltantes": [f["mensaje"] for f in a.completitud["faltantes"]],
        "advertencias": list(a.completitud["advertencias"]),
    }


def vista_mapa(reg: RegistroPlataforma) -> dict:
    from app.domain.mapa_datos import analisis as am
    por_id = {e.id: e for e in reg.elementos}
    usos = {e.id: [a.definicion.nombre for a in reg.actividades
                   if any(x["id"] == e.id for x in a.contenido["elementos"])] for e in reg.elementos}
    return {
        "elementos": [{
            "id": e.id, "clave": e.clave, "tipo": e.tipo, "tipo_nombre": cat_mapa.etiqueta("tipo", e.tipo),
            "subtipo_nombre": cat_mapa.etiqueta_subtipo(e.tipo, e.subtipo), "nombre": e.nombre,
            "descripcion": e.descripcion, "proveedor": e.proveedor, "pais": e.pais,
            "pais_nombre": cat_mapa.nombre_pais(e.pais) if e.pais else None,
            "categorias": [cat_mapa.nombre_dato(c) for c in e.categorias_datos], "actividades": usos[e.id],
        } for e in reg.elementos],
        "flujos": [{
            "id": f.id, "origen_id": f.origen_id, "destino_id": f.destino_id, "destino": por_id[f.destino_id].nombre,
            "categorias": [cat_mapa.nombre_dato(c) for c in f.categorias_datos],
            **{k: v for k, v in am.derivados_flujo(f, por_id).como_dict().items()
               if k in ("internacional", "pais_destino", "garantia_valida")},
            "garantia": f.garantia,
            "garantia_nombre": cat_mapa.etiqueta("garantia", f.garantia) if f.garantia else None,
        } for f in reg.flujos],
        "resumen": am.resumen(list(reg.elementos), list(reg.flujos)),
    }


__all__ = [
    "AVISO_RAT_PLATAFORMA", "NOTA_BORRADOR", "PREFIJO_RAT", "PREFIJO_ROPA", "AjustePlazo", "Proveedor",
    "PlazoCategoria", "ActividadGenerada", "RegistroPlataforma", "ajustes_efectivos", "proveedores_activos",
    "plazos_actividad", "generar", "motivos_borrador", "informe_rat", "informe_ropa", "huella_ropa", "codigo",
    "leer_codigo", "vista_actividad", "vista_mapa",
]

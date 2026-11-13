"""
HU-39 · Anclaje: de lo que devolvió el modelo a propuestas que el sistema puede guardar como "sugeridas".

El modelo puede inventar códigos, referirse a cosas que no existen o escribir más de la cuenta. Aquí se
aplican las MISMAS validaciones que el mapa (HU-34) y el RAT (HU-35) aplican a lo que escribe una persona
(normalizar_elemento, normalizar_flujo, rat.modelo.normalizar), de forma tolerante: un campo inválido se
quita (y la propuesta queda para que el usuario lo complete); una propuesta sin lo esencial se descarta.

  elemento   tipo y nombre obligatorios; códigos del catálogo; sin datos de contacto (minimización T-06).
  flujo      origen y destino obligatorios: "id:<n>" de un elemento del mapa o "nuevo:<clave>" de un
             elemento propuesto (en esta respuesta o pendiente).
  actividad  nombre obligatorio; sus elementos y flujos se filtran a referencias válidas.

Las referencias "nuevo:<clave>" se resuelven al ACEPTAR (app/application/use_cases/asistente_rat.py):
primero hay que aceptar el elemento que el flujo o la actividad usa.

Lógica pura: se prueba sin BD ni LLM.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from types import SimpleNamespace

from app.application.asistente.contexto import clave_segura
from app.application.schemas.asistente_rat import AsistenteRatRespuesta, PropuestaIA
from app.domain import catalogo_tratamiento as cat
from app.domain.mapa_datos import modelo as modelo_mapa
from app.domain.mapa_datos.modelo import ErrorValidacion
from app.domain.rat import catalogo as cat_rat
from app.domain.rat import modelo as modelo_rat

MAX_PROPUESTAS = 6
MAX_EXPLICACIONES = 12
MAX_CHARS_EXPLICACION = 400
MAX_INTENTOS = 12
RIESGOS = ("Bajo", "Medio", "Alto", "Crítico")
CAMPOS_ELEMENTO = ("tipo", "subtipo", "nombre", "descripcion", "proveedor", "pais", "responsable",
                   "categorias_datos", "categorias_titulares", "rol_tercero", "contrato_firmado")
CAMPOS_FLUJO = ("origen", "destino", "finalidad", "categorias_datos", "categorias_titulares", "frecuencia",
                "medio", "cifrado", "garantia")
CAMPOS_ACTIVIDAD = ("nombre", "descripcion", "area", "elementos", "flujos", "finalidades", "fuentes",
                    "base_licitud", "interes_legitimo", "base_sensibles", "plazos", "decisiones", "medidas", "rol")


@dataclass
class PropuestaAnclada:
    tipo: str
    clave: str
    payload: dict
    explicaciones: dict[str, str] = field(default_factory=dict)
    confianza: str = "media"
    riesgo_sugerido: str | None = None

    @property
    def nombre(self) -> str:
        if self.tipo == "flujo":
            return self.payload.get("finalidad") or "Flujo de datos"
        return self.payload.get("nombre") or ""


@dataclass
class ContextoAnclaje:
    """Lo que existe: ids del mapa y propuestas pendientes {clave: tipo}; `claves_usadas` incluye las decididas."""
    ids_elementos: set[int] = field(default_factory=set)
    ids_flujos: set[int] = field(default_factory=set)
    pendientes: dict[str, str] = field(default_factory=dict)
    claves_usadas: set[str] = field(default_factory=set)


@dataclass
class ResultadoAnclaje:
    propuestas: list[PropuestaAnclada]
    descartes: list[str]          # códigos de por qué se descartó o recortó algo (para la bitácora)


# ------------------------------------------------------------------ utilidades
_VACIO = dict(
    descripcion=None, tipo_elemento=None, subtipo=None, proveedor=None, pais=None, responsable=None,
    rol_tercero=None, contrato_firmado=None, categorias_datos=[], categorias_titulares=[], origen=None, destino=None,
    finalidad=None, frecuencia=None, medio=None, cifrado=None, garantia=None, area=None, elementos=[], flujos=[],
    finalidades=[], fuentes=[], base_licitud=None, interes_legitimo=None, base_sensibles=None, plazos=[],
    decisiones_automatizadas=None, medidas=[], rol_empresa=None, riesgo_sugerido=None,
)


def plano(p: PropuestaIA) -> SimpleNamespace:
    """La propuesta con todos los campos al mismo nivel (solo los del bloque de su tipo; el resto vacío)."""
    datos = {**copy.deepcopy(_VACIO), "tipo": p.tipo, "clave": p.clave, "nombre": p.nombre,
             "explicaciones": list(p.explicaciones), "confianza": p.confianza}
    bloque = {"elemento": p.elemento, "flujo": p.flujo, "actividad": p.actividad}.get(p.tipo)
    if bloque is not None:
        datos.update({k: v for k, v in bloque.model_dump().items() if v is not None})
        if p.tipo == "actividad":
            datos["plazos"] = list(bloque.plazos)
    return SimpleNamespace(**datos)



def _recortar(texto: str | None, maximo: int) -> str | None:
    if texto is None:
        return None
    t = " ".join(str(texto).split())
    return t[:maximo].rstrip() or None


def _validos(codigos: list[str] | None, validos) -> list[str]:
    salida: list[str] = []
    for c in codigos or []:
        c = (c or "").strip()
        if c in validos and c not in salida:
            salida.append(c)
    return salida


def _tolerante(normalizar, datos: dict, obligatorios: tuple[str, ...], descartes: list[str], tipo: str):
    """Llama a `normalizar` quitando los campos que no pasan la validación. None si falla un obligatorio."""
    datos = dict(datos)
    for _ in range(MAX_INTENTOS):
        try:
            return normalizar(datos), datos
        except ErrorValidacion as e:
            if e.campo in obligatorios or e.campo not in datos:
                descartes.append(f"{tipo}_invalido:{e.campo}")
                return None, datos
            descartes.append(f"campo_quitado:{tipo}.{e.campo}")
            datos.pop(e.campo)
    descartes.append(f"{tipo}_invalido")
    return None, datos


def parsear_ref(ref: str | None) -> tuple[str, str | int] | None:
    """'id:3' -> ('id', 3); 'nuevo:crm' -> ('nuevo', 'crm'); otra cosa -> None."""
    if not isinstance(ref, str) or ":" not in ref:
        return None
    tipo, _, valor = ref.strip().partition(":")
    tipo = tipo.strip().lower()
    if tipo == "id":
        try:
            n = int(valor.strip())
        except ValueError:
            return None
        return ("id", n) if n > 0 else None
    if tipo == "nuevo":
        c = clave_segura(valor, "")
        return ("nuevo", c) if c else None
    return None


def _ref_valida(ref: str | None, ids: set[int], claves_tipo: dict[str, str], tipo: str) -> str | None:
    p = parsear_ref(ref)
    if p is None:
        return None
    if p[0] == "id":
        return f"id:{p[1]}" if p[1] in ids else None
    return f"nuevo:{p[1]}" if claves_tipo.get(p[1]) == tipo else None


def _explicaciones(p: PropuestaIA) -> dict[str, str]:
    salida: dict[str, str] = {}
    for e in p.explicaciones[:MAX_EXPLICACIONES]:
        campo = clave_segura(e.campo, "general")
        campo = {"riesgo_sugerido": "riesgo", "tipo_elemento": "tipo", "rol_empresa": "rol"}.get(campo, campo)
        texto = _recortar(e.texto, MAX_CHARS_EXPLICACION)
        if texto and campo not in salida:
            salida[campo] = texto
    return salida


# ------------------------------------------------------------------ por tipo
def _elemento(p: PropuestaIA, descartes: list[str]) -> dict | None:
    l = modelo_mapa.LARGOS
    tipo = (p.tipo_elemento or "").strip()
    datos = {
        "tipo": tipo, "subtipo": (p.subtipo or "").strip() or None,
        "nombre": _recortar(p.nombre, l["nombre"][1]),
        "descripcion": _recortar(p.descripcion, l["descripcion"][1]),
        "proveedor": _recortar(p.proveedor, l["proveedor"][1]),
        "pais": (p.pais or "").strip().upper() or None,
        "responsable": _recortar(p.responsable, l["responsable"][1]),
        "categorias_datos": _validos(p.categorias_datos, cat.DATOS_POR_CODIGO),
        "categorias_titulares": _validos(p.categorias_titulares, cat.TITULARES_POR_CODIGO),
    }
    if tipo == "tercero":
        datos["rol_tercero"] = (p.rol_tercero or "").strip() or None
        datos["contrato_firmado"] = p.contrato_firmado
    campos, _ = _tolerante(modelo_mapa.normalizar_elemento, datos, ("tipo", "nombre"), descartes, "elemento")
    if campos is None:
        return None
    # Todas las claves (las vacías en null): el formulario de edición muestra el elemento completo
    return {k: campos.get(k) for k in CAMPOS_ELEMENTO}


def _flujo(p: PropuestaIA, ctx: ContextoAnclaje, claves_tipo: dict[str, str], descartes: list[str]) -> dict | None:
    origen = _ref_valida(p.origen, ctx.ids_elementos, claves_tipo, "elemento")
    destino = _ref_valida(p.destino, ctx.ids_elementos, claves_tipo, "elemento")
    if origen is None or destino is None or origen == destino:
        descartes.append("flujo_sin_extremos")
        return None
    datos = {
        "origen_id": 1, "destino_id": 2,   # los extremos reales se resuelven al aceptar
        "finalidad": _recortar(p.finalidad or p.nombre, modelo_mapa.LARGOS["finalidad"][1]),
        "categorias_datos": _validos(p.categorias_datos, cat.DATOS_POR_CODIGO),
        "categorias_titulares": _validos(p.categorias_titulares, cat.TITULARES_POR_CODIGO),
        "frecuencia": (p.frecuencia or "").strip() or None, "medio": (p.medio or "").strip() or None,
        "cifrado": p.cifrado, "garantia": (p.garantia or "").strip() or None,
    }
    campos, _ = _tolerante(modelo_mapa.normalizar_flujo, datos, ("origen_id", "destino_id"), descartes, "flujo")
    if campos is None:
        return None
    salida = {k: campos.get(k) for k in CAMPOS_FLUJO if k not in ("origen", "destino")}
    return {"origen": origen, "destino": destino, **salida}


def _plazos(p: PropuestaIA) -> list[dict]:
    salida = []
    for pl in p.plazos:
        if pl.categoria not in cat.DATOS_POR_CODIGO:
            continue
        unidad = pl.unidad if pl.unidad in cat_rat.UNIDADES_POR_CODIGO else None
        plazo = pl.plazo if isinstance(pl.plazo, int) and not isinstance(pl.plazo, bool) and pl.plazo >= 1 else None
        if plazo is not None and unidad and plazo > cat_rat.MAX_PLAZO[unidad]:
            plazo = None
        salida.append({
            "categoria": pl.categoria, "plazo": plazo, "unidad": unidad,
            "desde": pl.desde if pl.desde in cat_rat.INICIOS_POR_CODIGO else None,
            "fundamento": _recortar(pl.fundamento, modelo_rat.LARGOS["fundamento"][1]),
        })
    return salida


def _actividad(p: PropuestaIA, ctx: ContextoAnclaje, claves_tipo: dict[str, str], descartes: list[str]) -> dict | None:
    l = modelo_rat.LARGOS
    elementos = [r for r in dict.fromkeys(_ref_valida(x, ctx.ids_elementos, claves_tipo, "elemento")
                                          for x in p.elementos) if r]
    flujos = [r for r in dict.fromkeys(_ref_valida(x, ctx.ids_flujos, claves_tipo, "flujo") for x in p.flujos) if r]
    if len(elementos) < len(p.elementos) or len(flujos) < len(p.flujos):
        descartes.append("actividad_referencias_quitadas")
    datos = {
        "nombre": _recortar(p.nombre, l["nombre"][1]),
        "descripcion": _recortar(p.descripcion, l["descripcion"][1]),
        "area": _recortar(p.area, l["area"][1]),
        "finalidades": [x for x in (_recortar(f, l["finalidad"][1]) for f in p.finalidades) if x],
        "fuentes": [{"tipo": f, "detalle": None} for f in _validos(p.fuentes, cat_rat.FUENTES_POR_CODIGO)
                    if f != "otro"],
        "base_licitud": p.base_licitud if p.base_licitud in cat_rat.BASES_POR_CODIGO else None,
        "interes_legitimo": _recortar(p.interes_legitimo, l["interes_legitimo"][1]),
        "base_sensibles": p.base_sensibles if p.base_sensibles in cat_rat.BASES_SENSIBLES_POR_CODIGO else None,
        "plazos": _plazos(p),
        "decisiones": {"existe": p.decisiones_automatizadas},
        "medidas": {"codigos": _validos(p.medidas, cat_rat.MEDIDAS_POR_CODIGO), "otras": None},
        "rol": p.rol_empresa if p.rol_empresa in cat_rat.ROLES_POR_CODIGO else None,
    }
    contenido, _ = _tolerante(modelo_rat.normalizar, datos, ("nombre",), descartes, "actividad")
    if contenido is None:
        return None
    salida = {k: copy.deepcopy(contenido.get(k)) for k in CAMPOS_ACTIVIDAD if k not in ("elementos", "flujos")}
    return {**salida, "elementos": elementos, "flujos": flujos}


# ------------------------------------------------------------------ entrada
def anclar(r: AsistenteRatRespuesta, ctx: ContextoAnclaje) -> ResultadoAnclaje:
    descartes: list[str] = []
    if r.fuera_de_alcance:
        return ResultadoAnclaje([], ["fuera_de_alcance"] if r.propuestas else [])
    crudas = list(r.propuestas)
    if len(crudas) > MAX_PROPUESTAS:
        descartes.append("demasiadas_propuestas")
        crudas = crudas[:MAX_PROPUESTAS]

    # 1. Claves únicas en la empresa. Una clave del modelo que choca con una propuesta YA existente se
    #    renombra y sus referencias dentro de esta respuesta se reescriben a la clave nueva.
    renombres: dict[str, str] = {}
    usadas = set(ctx.claves_usadas) | set(ctx.pendientes)
    claves_lote: list[str] = []
    for p in crudas:
        base = clave_segura(p.clave or p.nombre)
        c, n = base, 2
        while c in usadas:
            c, n = f"{base[:46]}_{n}", n + 1
        usadas.add(c)
        renombres.setdefault(base, c)
        claves_lote.append(c)

    def remapear(ref: str | None) -> str | None:
        parsed = parsear_ref(ref)
        if parsed and parsed[0] == "nuevo" and parsed[1] in renombres:
            return f"nuevo:{renombres[parsed[1]]}"
        return ref

    # 2. Elementos primero (los flujos y actividades se refieren a ellos), luego flujos y actividades
    salida: list[PropuestaAnclada] = []
    validas: dict[str, str] = dict(ctx.pendientes)
    orden = {"elemento": 0, "flujo": 1, "actividad": 2}
    for c, cruda in sorted(zip(claves_lote, crudas), key=lambda x: orden[x[1].tipo]):
        p = plano(cruda)
        p.origen, p.destino = remapear(p.origen), remapear(p.destino)
        p.elementos = [remapear(x) for x in p.elementos]
        p.flujos = [remapear(x) for x in p.flujos]
        # Solo se puede referir lo pendiente o lo de esta respuesta que ya sobrevivió al anclaje
        tipos_validos = dict(validas)
        if p.tipo == "elemento":
            payload = _elemento(p, descartes)
        elif p.tipo == "flujo":
            payload = _flujo(p, ctx, tipos_validos, descartes)
        else:
            payload = _actividad(p, ctx, tipos_validos, descartes)
        if payload is None:
            continue
        validas[c] = p.tipo
        riesgo = p.riesgo_sugerido if p.riesgo_sugerido in RIESGOS else None
        salida.append(PropuestaAnclada(tipo=p.tipo, clave=c, payload=payload, explicaciones=_explicaciones(p),
                                       confianza=p.confianza if p.confianza in ("alta", "media", "baja") else "media",
                                       riesgo_sugerido=riesgo if p.tipo == "actividad" else None))
    return ResultadoAnclaje(salida, descartes)


# ------------------------------------------------------------------ edición del usuario
def aplicar_edicion(tipo: str, propuesto: dict, editado: dict | None) -> tuple[dict, list[str]]:
    """
    El payload final que confirmó el usuario: el propuesto con los campos que editó (solo los campos del
    tipo). Devuelve (payload, campos que cambió). La validación la hacen los casos de uso del mapa y del
    RAT al aceptar, igual que si lo hubiera escrito a mano.
    """
    permitidos = {"elemento": CAMPOS_ELEMENTO, "flujo": CAMPOS_FLUJO, "actividad": CAMPOS_ACTIVIDAD}[tipo]
    final = copy.deepcopy(propuesto)
    cambiados: list[str] = []
    for k, v in (editado or {}).items():
        if k in permitidos and final.get(k) != v:
            final[k] = copy.deepcopy(v)
            cambiados.append(k)
    return final, sorted(cambiados)

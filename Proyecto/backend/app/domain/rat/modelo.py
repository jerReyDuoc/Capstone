"""
HU-35 · Contenido de una actividad de tratamiento: validación y normalización.

El contenido se guarda como un documento JSON (rat_actividad.contenido) con esta forma:

  nombre, descripcion, area                 qué actividad es y qué área interna la lleva (cargo o área)
  elementos  [{id, categorias_datos, categorias_titulares}]   sistemas, bases y terceros ELEGIDOS DEL MAPA
  flujos     [{id, categorias_datos, categorias_titulares}]   flujos ELEGIDOS DEL MAPA
             (las categorías son el subconjunto que usa la actividad; se cruzan con las del mapa al leer)
  finalidades               [texto]
  fuentes                   [{tipo, detalle}]   (tipo "acceso_publico" = fuente de acceso público)
  base_licitud, interes_legitimo, base_sensibles
  sin_destinatarios         confirma que no se comunican a terceros
  plazos                    [{categoria, plazo, unidad, desde, fundamento}]   uno por categoría de datos
  decisiones                {existe, perfilamiento, logica, consecuencias, intervencion_humana}
  medidas                   {codigos, otras}
  rol, responsable_mandante (si la empresa es encargada: por cuenta de qué organización)
  ambito_nota               aclaración opcional del ámbito territorial

Nada de lo anterior se repite del mapa: los nombres, países, terceros y transferencias se calculan
con app/domain/rat/analisis.py. Minimización: los textos se rechazan si traen correos, RUT o
teléfonos (como el mapa): el registro describe actividades de la organización, no a personas.
"""
from __future__ import annotations

import copy

from app.domain import catalogo_tratamiento as cat_mapa
from app.domain.mapa_datos.modelo import ErrorValidacion, contiene_contacto
from app.domain.rat import catalogo as cat

MAX_FINALIDADES = 15
MAX_FUENTES = 12
MAX_SELECCION = 200
MAX_PLAZOS = 80

LARGOS = {
    "nombre": (3, 150), "descripcion": (1, 1000), "area": (2, 120), "finalidad": (5, 300), "detalle": (1, 300),
    "interes_legitimo": (10, 1500), "responsable_mandante": (2, 150), "fundamento": (1, 300),
    "logica": (10, 1500), "consecuencias": (1, 1000), "otras": (2, 1000), "ambito_nota": (2, 300),
}

CAMPOS_EDITABLES = (
    "nombre", "descripcion", "area", "elementos", "flujos", "finalidades", "fuentes", "base_licitud",
    "interes_legitimo", "base_sensibles", "sin_destinatarios", "plazos", "decisiones", "medidas", "rol",
    "responsable_mandante", "ambito_nota",
)


def contenido_vacio() -> dict:
    return {
        "nombre": "", "descripcion": None, "area": None, "elementos": [], "flujos": [], "finalidades": [],
        "fuentes": [], "base_licitud": None, "interes_legitimo": None, "base_sensibles": None,
        "sin_destinatarios": False, "plazos": [],
        "decisiones": {"existe": None, "perfilamiento": False, "logica": None, "consecuencias": None,
                       "intervencion_humana": None},
        "medidas": {"codigos": [], "otras": None}, "rol": None, "responsable_mandante": None, "ambito_nota": None,
    }


def completar(contenido: dict | None) -> dict:
    """El contenido guardado con todas sus claves (lo que falte, con su valor vacío)."""
    base = contenido_vacio()
    for k, v in (contenido or {}).items():
        if k in base:
            if isinstance(base[k], dict) and isinstance(v, dict):
                base[k] = {**base[k], **{kk: vv for kk, vv in v.items() if kk in base[k]}}
            else:
                base[k] = v
    return base


# ------------------------------------------------------------ piezas
_MENSAJE_CONTACTO = ("No escribas correos, RUT ni teléfonos de personas en el registro: describe la actividad, "
                     "no a una persona.")


def _texto(valor, campo: str, largo: str | None = None, obligatorio: bool = False,
           mensaje_vacio: str = "Completa este dato.") -> str | None:
    if valor is None:
        if obligatorio:
            raise ErrorValidacion(campo, mensaje_vacio)
        return None
    if not isinstance(valor, str):
        raise ErrorValidacion(campo, "El valor no es un texto válido.")
    clave = largo or campo
    multilinea = clave in ("descripcion", "interes_legitimo", "logica", "consecuencias", "otras")
    if multilinea:
        lineas = [" ".join(l.split()) for l in valor.replace("\r", "").split("\n")]
        valor = "\n".join(lineas).strip()
        while "\n\n\n" in valor:
            valor = valor.replace("\n\n\n", "\n\n")
    else:
        valor = " ".join(valor.split())
    if not valor:
        if obligatorio:
            raise ErrorValidacion(campo, mensaje_vacio)
        return None
    minimo, maximo = LARGOS[clave]
    if len(valor) < minimo:
        raise ErrorValidacion(campo, f"Usa al menos {minimo} caracteres.")
    if len(valor) > maximo:
        raise ErrorValidacion(campo, f"Usa como máximo {maximo} caracteres.")
    if contiene_contacto(valor):
        if campo == "area":
            raise ErrorValidacion(campo, "Indica el cargo o el área (por ejemplo, «Gerencia comercial»), sin correos, "
                                         "RUT ni teléfonos de personas.")
        raise ErrorValidacion(campo, _MENSAJE_CONTACTO)
    return valor


def _opcion(valor, campo: str, validas: dict, mensaje: str) -> str | None:
    if valor in (None, ""):
        return None
    if not isinstance(valor, str) or valor not in validas or not validas[valor].vigente:
        raise ErrorValidacion(campo, mensaje)
    return valor


def _bool(valor, campo: str, nulo: bool = False) -> bool | None:
    if valor is None:
        return None if nulo else False
    if not isinstance(valor, bool):
        raise ErrorValidacion(campo, "El valor debe ser sí o no.")
    return valor


def _lista(valor, campo: str, maximo: int, nombre: str) -> list:
    if valor is None:
        return []
    if not isinstance(valor, list):
        raise ErrorValidacion(campo, f"{nombre} deben venir como una lista.")
    if len(valor) > maximo:
        raise ErrorValidacion(campo, f"Registra como máximo {maximo} {nombre.lower()}.")
    return valor


def _codigos(valor, campo: str, validos: dict, nombre: str) -> list[str]:
    salida: list[str] = []
    for c in _lista(valor, campo, 60, nombre):
        if not isinstance(c, str) or c not in validos or not getattr(validos[c], "vigente", True):
            raise ErrorValidacion(campo, f"Una de las {nombre.lower()} elegidas no existe en el catálogo.")
        if c not in salida:
            salida.append(c)
    return salida


def _seleccion(valor, campo: str) -> list[dict]:
    """Elementos o flujos elegidos del mapa con el subconjunto de categorías que usa la actividad."""
    nombre = "Los sistemas elegidos" if campo == "elementos" else "Los flujos elegidos"
    salida: list[dict] = []
    vistos: set[int] = set()
    for item in _lista(valor, campo, MAX_SELECCION, nombre):
        if not isinstance(item, dict) or not isinstance(item.get("id"), int) or isinstance(item.get("id"), bool) \
                or item["id"] < 1:
            raise ErrorValidacion(campo, "Uno de los elementos elegidos no es válido. Vuelve a elegirlo del mapa.")
        if item["id"] in vistos:
            continue
        vistos.add(item["id"])
        salida.append({
            "id": item["id"],
            "categorias_datos": _codigos(item.get("categorias_datos"), campo, cat_mapa.DATOS_POR_CODIGO,
                                         "Categorías de datos"),
            "categorias_titulares": _codigos(item.get("categorias_titulares"), campo, cat_mapa.TITULARES_POR_CODIGO,
                                             "Categorías de titulares"),
        })
    return salida


def _finalidades(valor) -> list[str]:
    salida: list[str] = []
    for f in _lista(valor, "finalidades", MAX_FINALIDADES, "Finalidades"):
        texto = _texto(f, "finalidades", "finalidad")
        if texto and texto.lower() not in {x.lower() for x in salida}:
            salida.append(texto)
    return salida


def _fuentes(valor) -> list[dict]:
    salida: list[dict] = []
    for f in _lista(valor, "fuentes", MAX_FUENTES, "Fuentes"):
        if not isinstance(f, dict):
            raise ErrorValidacion("fuentes", "Una de las fuentes no es válida.")
        tipo = _opcion(f.get("tipo"), "fuentes", cat.FUENTES_POR_CODIGO, "Elige de dónde vienen los datos.")
        if tipo is None:
            raise ErrorValidacion("fuentes", "Elige de dónde vienen los datos en cada fuente.")
        detalle = _texto(f.get("detalle"), "fuentes", "detalle")
        if tipo == "otro" and not detalle:
            raise ErrorValidacion("fuentes", "Describe la fuente cuando eliges «Otra fuente».")
        if not any(x["tipo"] == tipo and x["detalle"] == detalle for x in salida):
            salida.append({"tipo": tipo, "detalle": detalle})
    return salida


def _plazos(valor) -> list[dict]:
    salida: list[dict] = []
    vistos: set[str] = set()
    for p in _lista(valor, "plazos", MAX_PLAZOS, "Plazos"):
        if not isinstance(p, dict):
            raise ErrorValidacion("plazos", "Uno de los plazos no es válido.")
        categoria = p.get("categoria")
        if not isinstance(categoria, str) or categoria not in cat_mapa.DATOS_POR_CODIGO:
            raise ErrorValidacion("plazos", "Uno de los plazos es de una categoría de datos que no existe.")
        if categoria in vistos:
            continue
        vistos.add(categoria)
        unidad = _opcion(p.get("unidad"), "plazos", cat.UNIDADES_POR_CODIGO, "Elige si el plazo es en días, meses o años.")
        plazo = p.get("plazo")
        if plazo is not None:
            if not isinstance(plazo, int) or isinstance(plazo, bool) or plazo < 1:
                raise ErrorValidacion("plazos", "El plazo debe ser un número entero mayor que cero.")
            if unidad and plazo > cat.MAX_PLAZO[unidad]:
                raise ErrorValidacion("plazos", f"El plazo es demasiado largo (máximo {cat.MAX_PLAZO[unidad]} "
                                                f"{cat.UNIDADES_POR_CODIGO[unidad].nombre}).")
        salida.append({
            "categoria": categoria, "plazo": plazo, "unidad": unidad,
            "desde": _opcion(p.get("desde"), "plazos", cat.INICIOS_POR_CODIGO, "Elige desde cuándo se cuenta el plazo."),
            "fundamento": _texto(p.get("fundamento"), "plazos", "fundamento"),
        })
    return salida


def _decisiones(valor) -> dict:
    if valor is None:
        return contenido_vacio()["decisiones"]
    if not isinstance(valor, dict):
        raise ErrorValidacion("decisiones", "La información de decisiones automatizadas no es válida.")
    existe = _bool(valor.get("existe"), "decisiones", nulo=True)
    d = {
        "existe": existe,
        "perfilamiento": bool(_bool(valor.get("perfilamiento"), "decisiones")),
        "logica": _texto(valor.get("logica"), "decisiones", "logica"),
        "consecuencias": _texto(valor.get("consecuencias"), "decisiones", "consecuencias"),
        "intervencion_humana": _bool(valor.get("intervencion_humana"), "decisiones", nulo=True),
    }
    if existe is False:     # sin decisiones automatizadas no queda nada que describir
        d.update(perfilamiento=False, logica=None, consecuencias=None, intervencion_humana=None)
    return d


def _medidas(valor) -> dict:
    if valor is None:
        return contenido_vacio()["medidas"]
    if not isinstance(valor, dict):
        raise ErrorValidacion("medidas", "Las medidas de seguridad no son válidas.")
    return {"codigos": _codigos(valor.get("codigos"), "medidas", cat.MEDIDAS_POR_CODIGO, "Medidas de seguridad"),
            "otras": _texto(valor.get("otras"), "medidas", "otras")}


# ------------------------------------------------------------ normalización
def normalizar(datos: dict, actual: dict | None = None) -> dict:
    """
    Valida lo que envió el usuario y devuelve el contenido COMPLETO resultante. Al editar (`actual`
    no es None) solo cambian las claves que vienen en `datos`; un null borra el valor.
    """
    if not isinstance(datos, dict):
        raise ErrorValidacion("contenido", "El contenido de la actividad no es válido.")
    desconocidas = set(datos) - set(CAMPOS_EDITABLES)
    if desconocidas:
        raise ErrorValidacion(sorted(desconocidas)[0], "Ese dato no es parte de una actividad del registro.")
    nuevo = completar(copy.deepcopy(actual)) if actual is not None else contenido_vacio()
    if actual is None and "nombre" not in datos:
        raise ErrorValidacion("nombre", "Escribe un nombre para identificar la actividad.")

    for campo, valor in datos.items():
        if campo == "nombre":
            nuevo["nombre"] = _texto(valor, "nombre", obligatorio=True,
                                     mensaje_vacio="Escribe un nombre para identificar la actividad.")
        elif campo in ("descripcion", "area", "interes_legitimo", "responsable_mandante", "ambito_nota"):
            nuevo[campo] = _texto(valor, campo)
        elif campo in ("elementos", "flujos"):
            nuevo[campo] = _seleccion(valor, campo)
        elif campo == "finalidades":
            nuevo[campo] = _finalidades(valor)
        elif campo == "fuentes":
            nuevo[campo] = _fuentes(valor)
        elif campo == "base_licitud":
            nuevo[campo] = _opcion(valor, campo, cat.BASES_POR_CODIGO, "Elige una base de licitud del listado.")
        elif campo == "base_sensibles":
            nuevo[campo] = _opcion(valor, campo, cat.BASES_SENSIBLES_POR_CODIGO,
                                   "Elige una base para los datos sensibles del listado.")
        elif campo == "sin_destinatarios":
            nuevo[campo] = bool(_bool(valor, campo))
        elif campo == "plazos":
            nuevo[campo] = _plazos(valor)
        elif campo == "decisiones":
            nuevo[campo] = _decisiones(valor)
        elif campo == "medidas":
            nuevo[campo] = _medidas(valor)
        elif campo == "rol":
            nuevo[campo] = _opcion(valor, campo, cat.ROLES_POR_CODIGO, "Elige si tu empresa es responsable o encargada.")

    # Coherencia: lo que deja de aplicar no se guarda
    if nuevo["base_licitud"] != cat.INTERES_LEGITIMO:
        nuevo["interes_legitimo"] = None
    if nuevo["rol"] != "encargado":
        nuevo["responsable_mandante"] = None
    return nuevo


def campos_cambiados(antes: dict, despues: dict) -> list[str]:
    a, d = completar(antes), completar(despues)
    return [k for k in CAMPOS_EDITABLES if a.get(k) != d.get(k)]

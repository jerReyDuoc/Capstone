"""
HU-34 · Elementos y flujos del mapa de datos, y la validación de lo que escribe el usuario.

  Elemento   un sistema, una base de datos o un tercero (criterio 1): nombre, tipo, proveedor,
             país de alojamiento y responsable interno, con las categorías de datos y de
             titulares del catálogo común con el RAT (criterio 2).
  Flujo      datos que viajan de un elemento a otro: entre sistemas y bases de datos, hacia
             terceros y, si cambia el país, una transferencia internacional (se calcula, no se
             declara: app/domain/mapa_datos/analisis.py).

Minimización: el mapa describe a la ORGANIZACIÓN (qué sistemas tiene), no a personas. El
"responsable interno" es un cargo o un área, nunca una persona con sus datos de contacto: los
textos libres se rechazan si traen un correo, un RUT o un teléfono (contiene_contacto).
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from app.domain import catalogo_tratamiento as cat

MAX_CATEGORIAS = 30
LARGOS = {
    "nombre": (2, 120),
    "descripcion": (0, 500),
    "proveedor": (0, 120),
    "responsable": (0, 120),
    "finalidad": (0, 300),
}
ORIGENES = ("manual", "plantilla", "evaluacion", "ia")

CAMPOS_ELEMENTO = (
    "tipo", "subtipo", "nombre", "descripcion", "proveedor", "pais", "responsable", "categorias_datos",
    "categorias_titulares", "nna_declarado", "rol_tercero", "contrato_firmado", "pendiente_revision",
)
CAMPOS_FLUJO = (
    "origen_id", "destino_id", "finalidad", "categorias_datos", "categorias_titulares", "nna_declarado",
    "frecuencia", "medio", "cifrado", "garantia", "pendiente_revision",
)

# Datos de contacto o identificadores de personas que no deben ir en los textos del mapa
_EMAIL = re.compile(r"[^\s@]+@[^\s@]+\.[A-Za-z]{2,}")
_RUT = re.compile(r"\b\d{1,2}\.?\d{3}\.?\d{3}\s?-\s?[\dkK]\b")
_TELEFONO = re.compile(r"(?:\+?56[\s-]?)?(?:\(?\d\)?[\s-]?)?\b9[\s-]?\d{4}[\s-]?\d{4}\b|\+\d[\d\s-]{8,}\d")


class ErrorValidacion(ValueError):
    def __init__(self, campo: str, mensaje: str):
        super().__init__(mensaje)
        self.campo = campo
        self.mensaje = mensaje


def contiene_contacto(texto: str | None) -> bool:
    """¿El texto trae un correo, un RUT o un teléfono? (minimización: el mapa no guarda personas)."""
    if not texto:
        return False
    return bool(_EMAIL.search(texto) or _RUT.search(texto) or _TELEFONO.search(texto))


@dataclass
class Elemento:
    id: int | None
    tipo: str
    nombre: str
    subtipo: str | None = None
    descripcion: str | None = None
    proveedor: str | None = None
    pais: str | None = None
    responsable: str | None = None
    categorias_datos: list[str] = field(default_factory=list)
    categorias_titulares: list[str] = field(default_factory=list)
    nna_declarado: bool = False
    rol_tercero: str | None = None
    contrato_firmado: bool | None = None
    origen: str = "manual"
    clave: str | None = None
    pendiente_revision: bool = False

    @property
    def es_tercero(self) -> bool:
        return self.tipo == "tercero"

    @property
    def sensibles(self) -> list[str]:
        return cat.sensibles_de(self.categorias_datos)

    @property
    def incluye_nna(self) -> bool:
        return bool(self.nna_declarado or cat.titulares_nna(self.categorias_titulares))

    @property
    def fuera_de_chile(self) -> bool:
        return bool(self.pais) and self.pais != cat.PAIS_LOCAL

    def como_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def desde_dict(cls, d: dict) -> "Elemento":
        return cls(**{k: d.get(k) if k not in ("categorias_datos", "categorias_titulares") else list(d.get(k) or [])
                      for k in cls.__dataclass_fields__ if k in d or k in ("id", "tipo", "nombre")})


@dataclass
class Flujo:
    id: int | None
    origen_id: int
    destino_id: int
    finalidad: str | None = None
    categorias_datos: list[str] = field(default_factory=list)
    categorias_titulares: list[str] = field(default_factory=list)
    nna_declarado: bool = False
    frecuencia: str | None = None
    medio: str | None = None
    cifrado: bool | None = None
    garantia: str | None = None
    origen: str = "manual"
    clave: str | None = None
    pendiente_revision: bool = False

    @property
    def sensibles(self) -> list[str]:
        return cat.sensibles_de(self.categorias_datos)

    @property
    def incluye_nna(self) -> bool:
        return bool(self.nna_declarado or cat.titulares_nna(self.categorias_titulares))

    def como_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def desde_dict(cls, d: dict) -> "Flujo":
        return cls(**{k: d.get(k) if k not in ("categorias_datos", "categorias_titulares") else list(d.get(k) or [])
                      for k in cls.__dataclass_fields__ if k in d or k in ("id", "origen_id", "destino_id")})


# ============================================================ validación
def _texto(datos: dict, campo: str, obligatorio: bool = False) -> str | None:
    valor = datos.get(campo)
    if valor is None:
        if obligatorio:
            raise ErrorValidacion(campo, "Escribe un nombre para identificarlo en el mapa.")
        return None
    if not isinstance(valor, str):
        raise ErrorValidacion(campo, "El valor no es un texto válido.")
    valor = " ".join(valor.split())  # sin saltos de línea ni espacios repetidos
    minimo, maximo = LARGOS[campo]
    if not valor:
        if obligatorio:
            raise ErrorValidacion(campo, "Escribe un nombre para identificarlo en el mapa.")
        return None
    if len(valor) < minimo:
        raise ErrorValidacion(campo, f"Usa al menos {minimo} caracteres.")
    if len(valor) > maximo:
        raise ErrorValidacion(campo, f"Usa como máximo {maximo} caracteres.")
    if contiene_contacto(valor):
        if campo == "responsable":
            raise ErrorValidacion(campo, "Indica el cargo o el área responsable (por ejemplo, «Jefatura de TI»), "
                                         "sin correos, RUT ni teléfonos de personas.")
        raise ErrorValidacion(campo, "No escribas correos, RUT ni teléfonos de personas en el mapa: describe el "
                                     "sistema o el flujo, no a una persona.")
    return valor


def _codigos(datos: dict, campo: str, validos: dict, nombre: str) -> list[str]:
    valor = datos.get(campo)
    if valor is None:
        return []
    if not isinstance(valor, (list, tuple)):
        raise ErrorValidacion(campo, f"Las {nombre} deben venir como una lista.")
    vistos: list[str] = []
    for codigo in valor:
        if not isinstance(codigo, str) or codigo not in validos or not validos[codigo].vigente:
            raise ErrorValidacion(campo, f"Una de las {nombre} elegidas no existe en el catálogo.")
        if codigo not in vistos:
            vistos.append(codigo)
    if len(vistos) > MAX_CATEGORIAS:
        raise ErrorValidacion(campo, f"Elige como máximo {MAX_CATEGORIAS} {nombre}.")
    return vistos


def _bool(datos: dict, campo: str, nulo: bool = False) -> bool | None:
    valor = datos.get(campo)
    if valor is None:
        return None if nulo else False
    if not isinstance(valor, bool):
        raise ErrorValidacion(campo, "El valor debe ser sí o no.")
    return valor


def _opcion(datos: dict, campo: str, validos, mensaje: str) -> str | None:
    valor = datos.get(campo)
    if valor in (None, ""):
        return None
    if not isinstance(valor, str) or valor not in validos:
        raise ErrorValidacion(campo, mensaje)
    return valor


def _pais(datos: dict) -> str | None:
    valor = datos.get("pais")
    if valor in (None, ""):
        return None
    if not isinstance(valor, str) or valor.strip().upper() not in cat.NOMBRE_PAIS:
        raise ErrorValidacion("pais", "Elige el país de la lista.")
    return valor.strip().upper()


def normalizar_elemento(datos: dict, actual: Elemento | None = None) -> dict:
    """
    Valida y normaliza los campos de un elemento. Con `actual` es una edición parcial: solo se
    validan los campos presentes y se devuelven los que cambian a su valor normalizado.
    """
    presentes = {k for k in CAMPOS_ELEMENTO if k in datos}
    if actual is None:
        presentes |= {"tipo", "nombre"}
    tipo = datos.get("tipo", actual.tipo if actual else None)
    if tipo not in cat.TIPOS:
        raise ErrorValidacion("tipo", "Elige si es un sistema, una base de datos o un tercero.")
    salida: dict = {}
    if "tipo" in presentes:
        salida["tipo"] = tipo
    if "nombre" in presentes:
        salida["nombre"] = _texto(datos, "nombre", obligatorio=True)
    for campo in ("descripcion", "proveedor", "responsable"):
        if campo in presentes:
            salida[campo] = _texto(datos, campo)
    if "subtipo" in presentes or ("tipo" in presentes and actual is not None and actual.tipo != tipo):
        sub = datos.get("subtipo") if "subtipo" in datos else (actual.subtipo if actual else None)
        if sub in (None, ""):
            salida["subtipo"] = None
        elif sub not in cat.SUBTIPOS_POR_TIPO[tipo]:
            if "subtipo" in datos:
                raise ErrorValidacion("subtipo", "Elige una categoría de la lista para este tipo de elemento.")
            salida["subtipo"] = None  # cambió el tipo: la categoría anterior ya no aplica
        else:
            salida["subtipo"] = sub
    if "pais" in presentes:
        salida["pais"] = _pais(datos)
    if "categorias_datos" in presentes:
        salida["categorias_datos"] = _codigos(datos, "categorias_datos", cat.DATOS_POR_CODIGO, "categorías de datos")
    if "categorias_titulares" in presentes:
        salida["categorias_titulares"] = _codigos(datos, "categorias_titulares", cat.TITULARES_POR_CODIGO,
                                                  "categorías de titulares")
    if "nna_declarado" in presentes:
        salida["nna_declarado"] = bool(_bool(datos, "nna_declarado"))
    if "pendiente_revision" in presentes:
        salida["pendiente_revision"] = bool(_bool(datos, "pendiente_revision"))
    if tipo == "tercero":
        if "rol_tercero" in presentes:
            salida["rol_tercero"] = _opcion(datos, "rol_tercero", cat.ROLES, "Elige el rol del tercero de la lista.")
        if "contrato_firmado" in presentes:
            salida["contrato_firmado"] = _bool(datos, "contrato_firmado", nulo=True)
    else:
        if "rol_tercero" in datos and datos["rol_tercero"] not in (None, ""):
            raise ErrorValidacion("rol_tercero", "Solo un tercero tiene rol de encargado o destinatario.")
        if actual is not None and actual.tipo == "tercero" or "tipo" in presentes:
            salida["rol_tercero"] = None
            salida["contrato_firmado"] = None
    if actual is not None:
        salida = {k: v for k, v in salida.items() if getattr(actual, k) != v}
    return salida


def normalizar_flujo(datos: dict, actual: Flujo | None = None) -> dict:
    presentes = {k for k in CAMPOS_FLUJO if k in datos}
    if actual is None:
        presentes |= {"origen_id", "destino_id"}
    salida: dict = {}
    for campo in ("origen_id", "destino_id"):
        if campo in presentes:
            valor = datos.get(campo)
            if not isinstance(valor, int) or isinstance(valor, bool) or valor < 1:
                raise ErrorValidacion(campo, "Elige el origen y el destino del flujo." if campo == "origen_id"
                                      else "Elige el destino del flujo.")
            salida[campo] = valor
    origen = salida.get("origen_id", actual.origen_id if actual else None)
    destino = salida.get("destino_id", actual.destino_id if actual else None)
    if origen is not None and origen == destino:
        raise ErrorValidacion("destino_id", "El origen y el destino del flujo deben ser distintos.")
    if "finalidad" in presentes:
        salida["finalidad"] = _texto(datos, "finalidad")
    if "categorias_datos" in presentes:
        salida["categorias_datos"] = _codigos(datos, "categorias_datos", cat.DATOS_POR_CODIGO, "categorías de datos")
    if "categorias_titulares" in presentes:
        salida["categorias_titulares"] = _codigos(datos, "categorias_titulares", cat.TITULARES_POR_CODIGO,
                                                  "categorías de titulares")
    if "nna_declarado" in presentes:
        salida["nna_declarado"] = bool(_bool(datos, "nna_declarado"))
    if "pendiente_revision" in presentes:
        salida["pendiente_revision"] = bool(_bool(datos, "pendiente_revision"))
    if "frecuencia" in presentes:
        salida["frecuencia"] = _opcion(datos, "frecuencia", cat.CODIGOS_FRECUENCIA, "Elige la frecuencia de la lista.")
    if "medio" in presentes:
        salida["medio"] = _opcion(datos, "medio", cat.CODIGOS_MEDIO, "Elige el medio de la lista.")
    if "cifrado" in presentes:
        salida["cifrado"] = _bool(datos, "cifrado", nulo=True)
    if "garantia" in presentes:
        salida["garantia"] = _opcion(datos, "garantia", cat.GARANTIAS, "Elige la garantía de la lista.")
    if actual is not None:
        salida = {k: v for k, v in salida.items() if getattr(actual, k) != v}
    return salida

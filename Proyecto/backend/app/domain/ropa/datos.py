"""
HU-37 criterio 3 · Datos que el RoPA pide y el registro de actividades no tiene.

Se piden una vez antes de generar y quedan guardados en la empresa (ropa_datos) para la próxima emisión:

  direccion, correo, telefono         contacto de la empresa (responsable o encargada)
  tiene_dpo, dpo_cargo, dpo_correo    delegado de protección de datos (cargo o área, no el nombre de una persona)
  mandantes {clave: {nombre, direccion, correo, dpo}}
                                      contacto de cada organización por cuenta de la cual la empresa actúa
                                      como encargada. El nombre sale de la actividad del registro
                                      (responsable_mandante); la clave es ese nombre normalizado.

A diferencia del registro (que rechaza correos y teléfonos: describe actividades, no personas), estos
campos SÍ son datos de contacto: el RoPA los exige. Se piden canales de la organización y nunca se
escriben en la bitácora de auditoría.

Guardar admite datos parciales (se valida el formato de lo que viene); `faltantes()` dice qué falta para
generar las partes elegidas.
"""
from __future__ import annotations

import copy
import re
import unicodedata

from app.domain.mapa_datos.modelo import ErrorValidacion

PARTES = ("responsable", "encargado")
MAX_MANDANTES = 100

EMAIL_VALIDO = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s.]{2,}$")
TELEFONO_VALIDO = re.compile(r"^\+?[0-9][0-9 ()-]{5,22}$")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

LARGOS = {
    "direccion": (5, 200), "correo": (6, 100), "telefono": (6, 25), "dpo_cargo": (3, 120), "dpo_correo": (6, 100),
    "dpo": (3, 150), "nombre": (2, 150),
}

CAMPOS_EMPRESA = ("direccion", "correo", "telefono", "tiene_dpo", "dpo_cargo", "dpo_correo")


def datos_vacios() -> dict:
    return {"direccion": None, "correo": None, "telefono": None, "tiene_dpo": None, "dpo_cargo": None,
            "dpo_correo": None, "mandantes": {}}


def completar(datos: dict | None) -> dict:
    """Los datos guardados con todas sus claves."""
    base = datos_vacios()
    for k, v in (datos or {}).items():
        if k in base:
            base[k] = copy.deepcopy(v)
    if not isinstance(base["mandantes"], dict):
        base["mandantes"] = {}
    return base


def clave_mandante(nombre: str | None) -> str:
    """«Retail Pacífico S.A.C.» → «retail pacifico s.a.c.»: sin tildes, minúsculas y espacios simples."""
    t = unicodedata.normalize("NFKD", nombre or "")
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return " ".join(t.lower().split())[:150]


# ------------------------------------------------------------ piezas
def _texto(valor, campo: str, etiqueta: str) -> str | None:
    if valor is None:
        return None
    if not isinstance(valor, str):
        raise ErrorValidacion(campo, f"{etiqueta}: el valor no es un texto válido.")
    valor = " ".join(_CONTROL.sub("", valor).split())
    if not valor:
        return None
    minimo, maximo = LARGOS[campo.split(".")[-1]]
    if len(valor) < minimo:
        raise ErrorValidacion(campo, f"{etiqueta}: usa al menos {minimo} caracteres.")
    if len(valor) > maximo:
        raise ErrorValidacion(campo, f"{etiqueta}: usa como máximo {maximo} caracteres.")
    return valor


def _correo(valor, campo: str, etiqueta: str) -> str | None:
    v = _texto(valor, campo, etiqueta)
    if v is None:
        return None
    v = v.lower()
    if not EMAIL_VALIDO.match(v):
        raise ErrorValidacion(campo, f"{etiqueta}: revisa el formato del correo (ejemplo: privacidad@empresa.cl).")
    return v


def _telefono(valor, campo: str) -> str | None:
    v = _texto(valor, campo, "Teléfono")
    if v is None:
        return None
    if not TELEFONO_VALIDO.match(v):
        raise ErrorValidacion(campo, "Teléfono: usa solo números, espacios, guiones y el signo + (ejemplo: +56 2 2345 6789).")
    return v


def _sin_correo(valor: str | None, campo: str, etiqueta: str) -> str | None:
    if valor and "@" in valor:
        raise ErrorValidacion(campo, f"{etiqueta}: indica el cargo o el área, sin correos.")
    return valor


def _dpo_mandante(valor, campo: str) -> str | None:
    """El delegado de una organización mandante: un correo o un cargo, en un solo campo."""
    v = _texto(valor, campo, "Delegado de protección de datos")
    if v and "@" in v and not EMAIL_VALIDO.match(v.lower()):
        raise ErrorValidacion(campo, "Delegado de protección de datos: revisa el formato del correo.")
    return v.lower() if v and "@" in v else v


def _mandante(clave: str, valor, nombres: dict[str, str]) -> dict:
    if not isinstance(valor, dict):
        raise ErrorValidacion("mandantes", "Los datos de una organización no son válidos.")
    campo = f"mandantes.{clave}"
    return {
        "nombre": nombres.get(clave) or _texto(valor.get("nombre"), f"{campo}.nombre", "Nombre") or clave,
        "direccion": _texto(valor.get("direccion"), f"{campo}.direccion", "Dirección"),
        "correo": _correo(valor.get("correo"), f"{campo}.correo", "Correo de contacto"),
        "dpo": _dpo_mandante(valor.get("dpo"), f"{campo}.dpo"),
    }


# ------------------------------------------------------------ normalización
def normalizar(entrada: dict, actual: dict | None = None, nombres_mandantes: dict[str, str] | None = None) -> dict:
    """
    Valida lo que envió el usuario y devuelve los datos COMPLETOS resultantes. Solo cambian las claves que
    vienen en `entrada` (un null borra el valor); los mandantes se actualizan por clave. `nombres_mandantes`
    {clave: nombre} son los mandantes de las actividades vigentes: el nombre visible sale del registro.
    """
    if not isinstance(entrada, dict):
        raise ErrorValidacion("datos", "Los datos no son válidos.")
    desconocidas = set(entrada) - set(CAMPOS_EMPRESA) - {"mandantes"}
    if desconocidas:
        raise ErrorValidacion(sorted(desconocidas)[0], "Ese dato no es parte del informe RoPA.")
    nombres = nombres_mandantes or {}
    nuevo = completar(actual)
    for campo, valor in entrada.items():
        if campo == "direccion":
            nuevo[campo] = _texto(valor, campo, "Dirección")
        elif campo == "correo":
            nuevo[campo] = _correo(valor, campo, "Correo de contacto")
        elif campo == "telefono":
            nuevo[campo] = _telefono(valor, campo)
        elif campo == "tiene_dpo":
            if valor is not None and not isinstance(valor, bool):
                raise ErrorValidacion(campo, "Indica sí o no para el delegado de protección de datos.")
            nuevo[campo] = valor
        elif campo == "dpo_cargo":
            nuevo[campo] = _sin_correo(_texto(valor, campo, "Cargo o área del delegado"), campo,
                                       "Cargo o área del delegado")
        elif campo == "dpo_correo":
            nuevo[campo] = _correo(valor, campo, "Correo del delegado")
        elif campo == "mandantes":
            if valor is None:
                continue
            if not isinstance(valor, list):
                raise ErrorValidacion(campo, "Las organizaciones deben venir como una lista.")
            if len(valor) > MAX_MANDANTES:
                raise ErrorValidacion(campo, f"Registra como máximo {MAX_MANDANTES} organizaciones.")
            for item in valor:
                if not isinstance(item, dict) or not isinstance(item.get("clave") or item.get("nombre"), str):
                    raise ErrorValidacion(campo, "Una de las organizaciones no es válida.")
                clave = clave_mandante(item.get("clave") or item.get("nombre"))
                if not clave:
                    raise ErrorValidacion(campo, "Una de las organizaciones no tiene nombre.")
                previo = nuevo["mandantes"].get(clave) or {}
                nuevo["mandantes"][clave] = _mandante(clave, {**previo, **item}, nombres)
            if len(nuevo["mandantes"]) > MAX_MANDANTES:
                # Se quedan las de las actividades vigentes y las más recientes
                sobran = [k for k in nuevo["mandantes"] if k not in nombres]
                for k in sobran[: len(nuevo["mandantes"]) - MAX_MANDANTES]:
                    nuevo["mandantes"].pop(k, None)
    # Coherencia: sin delegado no se guarda su cargo ni su correo
    if nuevo["tiene_dpo"] is not True:
        nuevo["dpo_cargo"] = None
        nuevo["dpo_correo"] = None
    return nuevo


def campos_cambiados(antes: dict | None, despues: dict) -> list[str]:
    """Nombres de los campos que cambiaron (para la bitácora: nunca sus valores)."""
    a, d = completar(antes), completar(despues)
    cambiados = [k for k in CAMPOS_EMPRESA if a.get(k) != d.get(k)]
    if a["mandantes"] != d["mandantes"]:
        cambiados.append("mandantes")
    return cambiados


# ------------------------------------------------------------ lo que falta para generar
def faltantes(datos: dict | None, partes: list[str] | tuple[str, ...], mandantes: dict[str, str]) -> list[dict]:
    """
    [{grupo, campo, mensaje}] de lo que falta para generar las `partes` elegidas. `mandantes` {clave: nombre}
    son las organizaciones de las actividades vigentes en que la empresa es encargada. El grupo es
    "empresa" o la clave del mandante.
    """
    d = completar(datos)
    salida: list[dict] = []

    def falta(grupo: str, campo: str, mensaje: str):
        salida.append({"grupo": grupo, "campo": campo, "mensaje": mensaje})

    if not d["direccion"]:
        falta("empresa", "direccion", "Escribe la dirección de tu empresa.")
    if not d["correo"]:
        falta("empresa", "correo", "Escribe el correo de contacto de tu empresa.")
    if d["tiene_dpo"] is None:
        falta("empresa", "tiene_dpo", "Indica si tu empresa tiene delegado de protección de datos.")
    elif d["tiene_dpo"]:
        if not d["dpo_cargo"]:
            falta("empresa", "dpo_cargo", "Escribe el cargo o el área del delegado de protección de datos.")
        if not d["dpo_correo"]:
            falta("empresa", "dpo_correo", "Escribe el correo del delegado de protección de datos.")
    if "encargado" in partes:
        for clave, nombre in mandantes.items():
            m = d["mandantes"].get(clave) or {}
            if not m.get("direccion"):
                falta(clave, "direccion", f"Escribe la dirección de {nombre}.")
            if not m.get("correo"):
                falta(clave, "correo", f"Escribe el correo de contacto de {nombre}.")
    return salida


def texto_faltantes(lista: list[dict], mandantes: dict[str, str]) -> str:
    """«Completa los datos de la empresa y Grupo Sur S.A.» (un resumen para el botón y los errores)."""
    grupos: list[str] = []
    for f in lista:
        nombre = "los datos de la empresa" if f["grupo"] == "empresa" else mandantes.get(f["grupo"], f["grupo"])
        if nombre not in grupos:
            grupos.append(nombre)
    if not grupos:
        return ""
    texto = "Completa " + (grupos[0] if len(grupos) == 1 else ", ".join(grupos[:-1]) + f" y {grupos[-1]}")
    return texto if texto.endswith(".") else texto + "."


__all__ = ["PARTES", "datos_vacios", "completar", "clave_mandante", "normalizar", "campos_cambiados", "faltantes",
           "texto_faltantes", "EMAIL_VALIDO"]

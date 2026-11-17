"""
HU-24 · Edición del BORRADOR de la matriz (lógica pura, sin BD).

Todas las funciones reciben el contenido del borrador (ver contenido.py), lo modifican en
el lugar y devuelven un `Cambio` con lo necesario para el audit log. Ninguna toca la
versión publicada: eso solo ocurre al publicar.

Reglas que protegen a las evaluaciones anteriores:
  - Nada se borra: "eliminar" un elemento publicado lo RETIRA (activo=false). Solo un
    elemento nuevo (id negativo, aún sin publicar) se quita del borrador.
  - El código de un control, una brecha o una pregunta de filtro ya publicados no cambia:
    identifica a ese elemento en las evaluaciones y los informes anteriores. Para cambiarlo,
    se retira y se crea uno nuevo.
  - No se retira lo que otro elemento activo usa (una brecha asignada a un control, una
    ruta asignada a una brecha, una pregunta de filtro usada por una regla).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping

from app.domain.matriz.contenido import (
    CAMPOS, CRITICIDADES, ENTIDADES, NIVELES, activos, esta_activo, etiqueta, por_id,
)

PATRON_CODIGO = {
    "controles": re.compile(r"^[A-Z][A-Z0-9]{1,9}-\d{2,4}$"),
    "brechas": re.compile(r"^[A-Z][A-Z0-9]{1,9}(-[A-Z0-9]{1,10}){1,3}$"),
    "preguntas_filtro": re.compile(r"^[A-Z][A-Z0-9]{0,9}$"),
}
NOMBRES = {"controles": "control", "brechas": "brecha", "rutas": "ruta formativa",
           "preguntas_filtro": "pregunta de filtro"}


class EdicionError(Exception):
    def __init__(self, codigo: str, mensaje: str, status_code: int = 422, **extra: Any):
        super().__init__(mensaje)
        self.codigo = codigo
        self.status_code = status_code
        self.extra = extra


@dataclass
class Cambio:
    """Qué se hizo, para el audit log. Nunca lleva textos completos: solo campos y valores cortos."""
    operacion: str                    # creado | modificado | retirado | restaurado | quitado
    entidad: str
    id: int
    etiqueta: str
    campos: list[dict] = field(default_factory=list)   # [{campo, antes, despues}]

    def como_detalle(self) -> dict:
        return {"operacion": self.operacion, "tipo": self.entidad, "elemento_id": self.id,
                "elemento": _resumir(self.etiqueta, 60), "campos": self.campos}


# --------------------------------------------------------------------- normalización de valores
def _resumir(valor: Any, largo: int = 120) -> Any:
    """Valor corto para el audit log (sin correos: la bitácora no los admite)."""
    if isinstance(valor, str):
        texto = valor.replace("@", "(at)")
        return texto if len(texto) <= largo else texto[: largo - 1] + "…"
    return valor


def _normalizar_valor(entidad: str, nombre: str, valor: Any) -> Any:
    campo = CAMPOS[entidad].get(nombre)
    if campo is None:
        raise EdicionError("CAMPO_DESCONOCIDO", f"El campo '{nombre}' no existe en {NOMBRES[entidad]}.", campo=nombre)
    if campo.tipo == "str":
        if valor is None:
            return None
        if not isinstance(valor, str):
            raise EdicionError("VALOR_INVALIDO", f"'{nombre}' debe ser texto.", campo=nombre)
        texto = valor.strip()
        if nombre in ("codigo_control", "codigo_brecha", "codigo"):
            texto = texto.upper()
        if nombre == "criticidad" and texto:
            texto = _criticidad(texto, nombre)
        if nombre == "nivel" and texto:
            texto = _nivel(texto)
        if len(texto) > campo.largo:
            raise EdicionError("VALOR_DEMASIADO_LARGO", f"'{nombre}' admite hasta {campo.largo} caracteres.",
                               campo=nombre, maximo=campo.largo)
        return texto or None
    if campo.tipo == "int":
        if valor is None:
            return None
        if isinstance(valor, bool) or not isinstance(valor, int):
            raise EdicionError("VALOR_INVALIDO", f"'{nombre}' debe ser un número entero.", campo=nombre)
        if valor < 0 or valor > 100_000:
            raise EdicionError("VALOR_INVALIDO", f"'{nombre}' está fuera de rango.", campo=nombre)
        return valor
    if campo.tipo == "bool":
        if not isinstance(valor, bool):
            raise EdicionError("VALOR_INVALIDO", f"'{nombre}' debe ser verdadero o falso.", campo=nombre)
        return valor
    if campo.tipo.startswith("ref:"):
        if valor is None:
            return None
        if isinstance(valor, bool) or not isinstance(valor, int):
            raise EdicionError("VALOR_INVALIDO", f"'{nombre}' debe ser un id.", campo=nombre)
        return valor
    if campo.tipo.startswith("refs:"):
        if valor is None:
            return []
        if not isinstance(valor, (list, tuple)) or any(isinstance(v, bool) or not isinstance(v, int) for v in valor):
            raise EdicionError("VALOR_INVALIDO", f"'{nombre}' debe ser una lista de ids.", campo=nombre)
        if len(valor) > 50:
            raise EdicionError("VALOR_INVALIDO", f"'{nombre}' admite hasta 50 elementos.", campo=nombre)
        return sorted(set(valor))
    raise EdicionError("CAMPO_DESCONOCIDO", f"Tipo de campo no soportado: {campo.tipo}", campo=nombre)


def _criticidad(texto: str, campo: str) -> str:
    for c in CRITICIDADES:
        if texto.lower() in (c.lower(), c.lower().replace("í", "i")):
            return c
    raise EdicionError("VALOR_INVALIDO", f"Criticidad inválida. Usa: {', '.join(CRITICIDADES)}.", campo=campo)


def _nivel(texto: str) -> str:
    for n in NIVELES:
        if texto.lower() == n.lower():
            return n
    raise EdicionError("VALOR_INVALIDO", f"Nivel inválido. Usa: {', '.join(NIVELES)}.", campo="nivel")


def _revisar_referencias(contenido: Mapping, entidad: str, datos: Mapping) -> None:
    """Toda referencia debe apuntar a un elemento que exista en el borrador (activo o no:
    la validación de publicación exige que esté activo, así se puede reordenar en pasos)."""
    for nombre, valor in datos.items():
        tipo = CAMPOS[entidad][nombre].tipo
        if tipo.startswith("ref:") and valor is not None:
            destino = tipo.split(":", 1)[1]
            if int(valor) not in por_id(contenido, destino):
                raise EdicionError("REFERENCIA_INVALIDA", f"'{nombre}' apunta a un elemento que no existe ({valor}).",
                                   campo=nombre)
        if tipo.startswith("refs:"):
            destino = tipo.split(":", 1)[1]
            existentes = por_id(contenido, destino)
            faltan = [v for v in valor if int(v) not in existentes]
            if faltan:
                raise EdicionError("REFERENCIA_INVALIDA", f"'{nombre}' incluye elementos que no existen: {faltan}.",
                                   campo=nombre)


def _revisar_codigo(contenido: Mapping, entidad: str, codigo: str | None, propio_id: int | None) -> None:
    patron = PATRON_CODIGO.get(entidad)
    if patron is None or codigo is None:
        return
    if not patron.match(codigo):
        ejemplos = {"controles": "DAT-011", "brechas": "ERR-DAT-012", "preguntas_filtro": "F8"}
        raise EdicionError("CODIGO_INVALIDO", f"Código con formato inválido (ejemplo: {ejemplos[entidad]}).",
                           campo=ENTIDADES[entidad]["codigo"])
    clave = ENTIDADES[entidad]["codigo"]
    for x in contenido.get(entidad, []):
        if int(x["id"]) != propio_id and (x.get(clave) or "").upper() == codigo:
            raise EdicionError("CODIGO_DUPLICADO",
                               f"El código {codigo} ya lo usa otro elemento"
                               f"{'' if esta_activo(entidad, x) else ' retirado (puedes restaurarlo)'}.",
                               status_code=409, campo=clave)


def _nuevo_id(contenido: Mapping, entidad: str) -> int:
    ids = [int(x["id"]) for x in contenido.get(entidad, [])]
    return min([0, *ids]) - 1


def _buscar(contenido: Mapping, entidad: str, item_id: int) -> dict:
    if entidad not in ENTIDADES:
        raise EdicionError("ENTIDAD_DESCONOCIDA", f"No existe la entidad '{entidad}'.", status_code=404)
    item = por_id(contenido, entidad).get(int(item_id))
    if item is None:
        raise EdicionError("NO_ENCONTRADO", f"No existe {NOMBRES[entidad]} #{item_id} en el borrador.", status_code=404)
    return item


# --------------------------------------------------------------------- operaciones
def crear(contenido: dict, entidad: str, datos: Mapping) -> Cambio:
    if entidad not in ENTIDADES:
        raise EdicionError("ENTIDAD_DESCONOCIDA", f"No existe la entidad '{entidad}'.", status_code=404)
    limpios = {k: _normalizar_valor(entidad, k, v) for k, v in datos.items()}
    _revisar_referencias(contenido, entidad, limpios)
    clave_codigo = ENTIDADES[entidad]["codigo"]
    if clave_codigo:
        if not limpios.get(clave_codigo):
            raise EdicionError("CAMPO_REQUERIDO", "El código es obligatorio.", campo=clave_codigo)
        _revisar_codigo(contenido, entidad, limpios[clave_codigo], None)
    nuevo: dict[str, Any] = {"id": _nuevo_id(contenido, entidad)}
    for nombre, campo in CAMPOS[entidad].items():
        if campo.tipo == "bool":
            nuevo[nombre] = bool(limpios.get(nombre, False))
        elif campo.tipo.startswith("refs:"):
            nuevo[nombre] = limpios.get(nombre, [])
        else:
            nuevo[nombre] = limpios.get(nombre)
    nuevo[ENTIDADES[entidad]["activo"]] = True
    if entidad == "preguntas_filtro" and nuevo.get("orden") is None:
        nuevo["orden"] = max([0, *(int(p.get("orden") or 0) for p in contenido.get(entidad, []))]) + 1
    contenido.setdefault(entidad, []).append(nuevo)
    campos = [{"campo": k, "antes": None, "despues": _resumir(v)} for k, v in nuevo.items()
              if k not in ("id",) and v not in (None, [], False)]
    return Cambio("creado", entidad, nuevo["id"], etiqueta(entidad, nuevo), campos)


def actualizar(contenido: dict, entidad: str, item_id: int, datos: Mapping) -> Cambio:
    item = _buscar(contenido, entidad, item_id)
    if not datos:
        raise EdicionError("SIN_CAMBIOS", "No enviaste campos para modificar.")
    limpios = {k: _normalizar_valor(entidad, k, v) for k, v in datos.items()}
    _revisar_referencias(contenido, entidad, limpios)
    clave_codigo = ENTIDADES[entidad]["codigo"]
    if clave_codigo and clave_codigo in limpios and limpios[clave_codigo] != item.get(clave_codigo):
        if int(item["id"]) > 0:
            raise EdicionError(
                "CODIGO_INMUTABLE",
                "El código de un elemento ya publicado no se cambia: identifica sus respuestas en evaluaciones "
                "anteriores. Retíralo y crea uno nuevo con el código correcto.",
                status_code=409, campo=clave_codigo,
            )
        if not limpios[clave_codigo]:
            raise EdicionError("CAMPO_REQUERIDO", "El código es obligatorio.", campo=clave_codigo)
        _revisar_codigo(contenido, entidad, limpios[clave_codigo], int(item["id"]))
    campos = []
    for k, v in limpios.items():
        antes = item.get(k)
        if (sorted(antes or []) if isinstance(v, list) else antes) != v:
            campos.append({"campo": k, "antes": _resumir(antes), "despues": _resumir(v)})
            item[k] = v
    if not campos:
        raise EdicionError("SIN_CAMBIOS", "Los valores enviados son iguales a los del borrador.")
    return Cambio("modificado", entidad, int(item["id"]), etiqueta(entidad, item), campos)


def _en_uso(contenido: Mapping, entidad: str, item_id: int) -> list[str]:
    """Etiquetas de los elementos ACTIVOS que dependen de este."""
    if entidad == "brechas":
        return sorted(etiqueta("controles", c) for c in activos(contenido, "controles") if c.get("brecha_id") == item_id)
    if entidad == "rutas":
        return sorted(etiqueta("brechas", b) for b in activos(contenido, "brechas")
                      if b.get("ruta_formativa_id") == item_id)
    if entidad == "preguntas_filtro":
        return sorted(etiqueta("controles", c) for c in activos(contenido, "controles")
                      if item_id in (c.get("filtros") or []))
    return []


def retirar(contenido: dict, entidad: str, item_id: int) -> Cambio:
    """Publicado → activo=false. Nuevo (id < 0) → se quita del borrador."""
    item = _buscar(contenido, entidad, item_id)
    clave_activo = ENTIDADES[entidad]["activo"]
    if not item.get(clave_activo, True):
        raise EdicionError("YA_RETIRADO", f"{etiqueta(entidad, item)} ya está retirado del borrador.",
                           status_code=409)
    usan = _en_uso(contenido, entidad, int(item["id"]))
    if usan:
        raise EdicionError(
            "EN_USO",
            f"No se puede retirar: lo usan {len(usan)} elemento(s) activo(s) ({', '.join(usan[:5])}"
            f"{'…' if len(usan) > 5 else ''}). Reasígnalos primero.",
            status_code=409, usado_por=usan,
        )
    if int(item["id"]) < 0:
        contenido[entidad] = [x for x in contenido[entidad] if int(x["id"]) != int(item["id"])]
        # Un nuevo que se quita no deja referencias colgando en otros nuevos retirados
        return Cambio("quitado", entidad, int(item["id"]), etiqueta(entidad, item))
    item[clave_activo] = False
    return Cambio("retirado", entidad, int(item["id"]), etiqueta(entidad, item),
                  [{"campo": clave_activo, "antes": True, "despues": False}])


def restaurar(contenido: dict, entidad: str, item_id: int) -> Cambio:
    item = _buscar(contenido, entidad, item_id)
    clave_activo = ENTIDADES[entidad]["activo"]
    if item.get(clave_activo, True):
        raise EdicionError("YA_ACTIVO", f"{etiqueta(entidad, item)} ya está activo en el borrador.",
                           status_code=409)
    clave_codigo = ENTIDADES[entidad]["codigo"]
    if clave_codigo:
        codigo = (item.get(clave_codigo) or "").upper()
        for x in activos(contenido, entidad):
            if (x.get(clave_codigo) or "").upper() == codigo and int(x["id"]) != int(item["id"]):
                raise EdicionError("CODIGO_DUPLICADO", f"Ya hay otro elemento activo con el código {codigo}.",
                                   status_code=409, campo=clave_codigo)
    item[clave_activo] = True
    return Cambio("restaurado", entidad, int(item["id"]), etiqueta(entidad, item),
                  [{"campo": clave_activo, "antes": False, "despues": True}])


def fijar_aplicabilidad(contenido: dict, control_id: int, aplica_siempre: bool, filtros: list[int]) -> Cambio:
    """Editor del árbol: reemplaza las reglas de un control (siempre y/o filtros que lo suman)."""
    return actualizar(contenido, "controles", control_id, {"aplica_siempre": aplica_siempre, "filtros": filtros})

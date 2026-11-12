"""
HU-39 · Lo que ve el LLM, separado en lo confiable y lo no confiable.

  catalogos_texto()   CONFIABLE: los códigos válidos de los catálogos comunes del mapa y del RAT
                      (app/domain/catalogo_tratamiento.py y app/domain/rat/catalogo.py) con su nombre.
  mapa_texto()        NO CONFIABLE: los nombres de los sistemas, flujos y actividades los escribió la
                      empresa. Va al campo no confiable "mapa" de la política: pasa por el filtro del agente
                      (línea por línea) y por el NER del gateway. Una línea por cosa, con su referencia
                      "[elemento id:<n>]" o "[flujo id:<n>]" para que el modelo la cite. Las propuestas pendientes (texto del modelo
                      sobre texto de la empresa) también van aquí, con "[nuevo:<clave>]".

Solo códigos, nombres y países: nunca la razón social, el RUT ni datos de contacto de la empresa.
"""
from __future__ import annotations

import re

from app.domain import catalogo_tratamiento as cat
from app.domain.mapa_datos import analisis as am
from app.domain.mapa_datos.modelo import Elemento, Flujo
from app.domain.rat import catalogo as cat_rat
from app.domain.rat.modelo import completar

MAX_LINEAS_MAPA = 160
_CLAVE = re.compile(r"[^a-z0-9_]+")


def clave_segura(texto: str | None, por_defecto: str = "propuesta") -> str:
    """Clave en minúsculas, dígitos y guiones bajos (máx. 50): la usan las referencias "nuevo:<clave>"."""
    c = _CLAVE.sub("_", (texto or "").strip().lower()).strip("_")[:50]
    return c or por_defecto


def _lista(opciones) -> str:
    return ", ".join(f"{o.codigo} ({o.nombre})" for o in opciones)


def catalogos_texto() -> str:
    sub = "\n".join(f"  subtipos de {t}: {_lista(ops)}" for t, ops in cat.SUBTIPOS.items())
    datos = ", ".join(f"{c.codigo} ({c.nombre}{', SENSIBLE' if c.sensible else ''})" for c in cat.CATEGORIAS_DATOS)
    return "\n".join([
        "- tipo_elemento: sistema, base_datos, tercero",
        sub,
        f"- categorias_datos: {datos}",
        f"- categorias_titulares: {_lista(cat.CATEGORIAS_TITULARES)}",
        f"- rol_tercero: {_lista(cat.ROLES_TERCERO)}",
        f"- garantia (solo envíos fuera de Chile): {_lista(cat.GARANTIAS_TRANSFERENCIA)}",
        f"- frecuencia: {_lista(cat.FRECUENCIAS)}",
        f"- medio: {_lista(cat.MEDIOS)}",
        "- pais: código ISO de 2 letras (CL = Chile)",
        f"- fuentes: {_lista(cat_rat.FUENTES)}",
        f"- base_licitud: {_lista(cat_rat.BASES_LICITUD)}",
        f"- base_sensibles: {_lista(cat_rat.BASES_SENSIBLES)}",
        f"- unidad de plazo: {_lista(cat_rat.UNIDADES_PLAZO)}",
        f"- desde (inicio del plazo): {_lista(cat_rat.INICIOS_PLAZO)}",
        f"- medidas: {_lista(cat_rat.MEDIDAS_SEGURIDAD)}",
        f"- rol_empresa: {_lista(cat_rat.ROLES_EMPRESA)}",
        "- riesgo_sugerido: Bajo, Medio, Alto, Crítico",
    ])


def _nombre(texto: str | None, maximo: int = 80) -> str:
    t = re.sub(r"\s+", " ", texto or "").strip()
    return t[:maximo]


def mapa_texto(elementos: list[Elemento], flujos: list[Flujo], actividades: list[dict],
               pendientes: list[dict] | None = None) -> str:
    """
    `actividades`: [{"nombre", "contenido"}] del RAT (no archivadas). `pendientes`: propuestas sugeridas
    [{"clave", "tipo", "nombre"}]. Devuelve una línea por cosa, a lo más MAX_LINEAS_MAPA.
    """
    lineas: list[str] = []
    por_id = {e.id: e for e in elementos}
    for e in elementos:
        partes = [e.tipo, e.subtipo or "-", f"«{_nombre(e.nombre)}»", f"país {am.pais_efectivo(e) or 'sin informar'}"]
        if e.categorias_datos:
            partes.append("datos: " + ", ".join(e.categorias_datos))
        if e.categorias_titulares:
            partes.append("titulares: " + ", ".join(e.categorias_titulares))
        if e.es_tercero:
            partes.append(f"rol {e.rol_tercero or 'sin informar'}, contrato "
                          + ("sí" if e.contrato_firmado else "no" if e.contrato_firmado is False else "sin informar"))
        lineas.append(f"[elemento id:{e.id}] " + " · ".join(partes))
    for f in flujos:
        d = am.derivados_flujo(f, por_id)
        partes = [f"de elemento id:{f.origen_id} a elemento id:{f.destino_id}",
                  f"«{_nombre(f.finalidad) or 'sin finalidad'}»"]
        if f.categorias_datos:
            partes.append("datos: " + ", ".join(f.categorias_datos))
        if d.internacional:
            partes.append(f"sale de Chile a {d.pais_destino}, garantía {f.garantia or 'sin informar'}")
        lineas.append(f"[flujo id:{f.id}] " + " · ".join(partes))
    for a in actividades:
        c = completar(a.get("contenido"))
        usa = [f"elemento id:{x['id']}" for x in c["elementos"]] + [f"flujo id:{x['id']}" for x in c["flujos"]]
        lineas.append(f"[actividad] «{_nombre(a.get('nombre'))}» · usa: {', '.join(usa) or 'nada aún'} · base "
                      f"{c['base_licitud'] or 'sin informar'}")
    for p in pendientes or []:
        lineas.append(f"[nuevo:{p['clave']}] propuesta pendiente · {p['tipo']} · «{_nombre(p.get('nombre'))}»")
    return "\n".join(lineas[:MAX_LINEAS_MAPA])

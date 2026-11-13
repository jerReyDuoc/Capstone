"""
HU-38 criterio 2 · Los borradores toman lo que ya dice el registro de actividades (lógica pura).

  PIA (evaluación de impacto)  se pre-llena con las actividades de ALTO RIESGO del registro (las que tienen
                               una evaluación de impacto recomendada por app/domain/rat/riesgos.py, o las
                               que la empresa elija): qué actividades se evalúan, por qué se recomienda,
                               la descripción sistemática (finalidad, titulares, datos, origen, sistemas,
                               proveedores, ubicación y la versión del registro), la base de licitud, los
                               riesgos calculados (factores, probabilidad, impacto y nivel) y las medidas
                               sugeridas.
  Aviso de privacidad          toma las FINALIDADES y BASES DE LICITUD de cada actividad, y también las
                               categorías de datos, los proveedores, las transferencias, los datos
                               sensibles o de NNA, el uso de IA y los plazos de conservación. Es un texto
                               para las personas: nunca nombra los sistemas internos de la empresa.

Entrada: el InformeRat (app/application/rat/informe.py), el mismo que el PDF del registro, así el borrador
usa la versión VIGENTE de cada actividad (o su copia de trabajo si nunca estuvo vigente, con aviso).

Salida: `textos(tipo)` → {id de cláusula: texto} que reemplazan el texto base de la plantilla
(generador.generar_markdown). Esas cláusulas no las reescribe el Agente IA: son hechos del registro.
El LLM nunca ve este contenido (se arma en el backend después de la IA).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace

from app.domain import catalogo_tratamiento as cat_mapa
from app.domain.rat import catalogo as cat
from app.domain.rat import riesgos as rg

MAX_ACTIVIDADES_PIA = 10
_DIAS = {"dias": 1, "meses": 30, "anios": 365}


def _lista(nombres, vacio: str = "—", y: bool = False) -> str:
    n = [x for x in dict.fromkeys(nombres) if x]
    if not n:
        return vacio
    if y and len(n) > 1:
        return ", ".join(n[:-1]) + " y " + n[-1]
    return ", ".join(n)


def _celda(texto: str) -> str:
    return (texto or "").replace("|", "/").replace("\n", " ").strip()


@dataclass(frozen=True)
class ActividadBorrador:
    id: int
    nombre: str
    vigente: bool                         # se informa una versión vigente (no la copia de trabajo)
    version: int | None
    fecha_version: str | None
    finalidades: tuple[str, ...]
    base: str                             # nombre de la base de licitud
    base_referencia: str
    base_sensibles: str | None
    interes_legitimo: str | None
    datos: tuple[str, ...]                # nombres, sensibles marcados
    categorias: tuple[str, ...]           # nombres sin marcas (para el aviso)
    sensibles: tuple[str, ...]
    titulares: tuple[str, ...]
    nna: bool
    fuentes: tuple[str, ...]
    sistemas: tuple[str, ...]             # internos: solo para la PIA
    terceros: tuple[str, ...]             # "Nombre (rol, país)"
    terceros_nombres: tuple[str, ...]
    paises: tuple[str, ...]               # ámbito territorial
    transferencias: tuple[str, ...]       # "País: garantía"
    paises_destino: tuple[str, ...]
    plazos: tuple[tuple[str, str, int], ...]   # (categoría, texto, días para comparar)
    decisiones: str
    usa_ia: bool
    toma_decisiones: bool
    riesgo: rg.RiesgoActividad


@dataclass(frozen=True)
class RegistroBorrador:
    actividades: tuple[ActividadBorrador, ...] = ()
    seleccion: tuple[int, ...] | None = None          # actividades elegidas para la PIA (None = las recomendadas)
    huella_registro: str = ""

    @property
    def vacio(self) -> bool:
        return not self.actividades

    def con_seleccion(self, ids) -> "RegistroBorrador":
        return replace(self, seleccion=tuple(dict.fromkeys(int(i) for i in ids)) if ids else None)

    def recomendadas_pia(self) -> list[ActividadBorrador]:
        return sorted((a for a in self.actividades if a.riesgo.requiere_pia),
                      key=lambda a: (-a.riesgo.puntaje, -a.riesgo.impacto, a.nombre.lower()))

    def para_pia(self) -> list[ActividadBorrador]:
        if self.seleccion:
            por_id = {a.id: a for a in self.actividades}
            return [por_id[i] for i in self.seleccion if i in por_id][:MAX_ACTIVIDADES_PIA]
        return self.recomendadas_pia()[:MAX_ACTIVIDADES_PIA]

    def huella(self) -> str:
        base = {"r": self.huella_registro, "s": list(self.seleccion or [])}
        return hashlib.sha256(json.dumps(base).encode()).hexdigest()[:32]

    # ------------------------------------------------------------ textos por plantilla
    def textos(self, tipo: str) -> dict[str, str]:
        if self.vacio:
            return {}
        if tipo == "pia":
            return _textos_pia(self.para_pia())
        if tipo == "aviso_privacidad":
            return _textos_aviso(list(self.actividades))
        return {}

    def resumen(self, tipo: str) -> dict:
        """Lo que el borrador tomó del registro (para la respuesta de la API, sin contenido)."""
        acts = self.para_pia() if tipo == "pia" else list(self.actividades) if tipo == "aviso_privacidad" else []
        return {"actividades": len(acts), "ids": [a.id for a in acts],
                "sin_version_vigente": sum(1 for a in acts if not a.vigente)}

    def advertencias(self, tipo: str) -> list[str]:
        if tipo not in ("pia", "aviso_privacidad"):
            return []
        if self.vacio:
            return ["registro_vacio"]
        acts = self.para_pia() if tipo == "pia" else list(self.actividades)
        if tipo == "pia" and not acts:
            return ["pia_sin_alto_riesgo"]
        salida = ["registro_aplicado"]
        if any(not a.vigente for a in acts):
            salida.append("registro_no_vigente")
        return salida


# ============================================================ desde el informe del registro
def _actividad(a) -> ActividadBorrador:
    from app.application.rat import informe as I

    c, mp = a.contenido, a.mapa
    base_op = cat.BASES_POR_CODIGO.get(c.get("base_licitud") or "")
    tipos = mp.get("tipos_datos") or []
    titulares = mp.get("titulares") or []
    plazos = []
    for p in c.get("plazos") or []:
        if p.get("plazo") and p.get("unidad"):
            plazos.append((cat_mapa.nombre_dato(p["categoria"]), I.texto_plazo(p), p["plazo"] * _DIAS.get(p["unidad"], 1)))
    terceros, terceros_nombres = [], []
    for t in mp.get("terceros") or []:
        extras = [x for x in (cat_mapa.etiqueta("rol", t.get("rol_tercero")) if t.get("rol_tercero") else "",
                              cat_mapa.nombre_pais(t.get("pais")) if t.get("pais") else "") if x]
        terceros.append(t.get("nombre", "?") + (f" ({', '.join(extras)})" if extras else ""))
        terceros_nombres.append(t.get("nombre", "?"))
    transf = mp.get("transferencias") or []
    d = c.get("decisiones") or {}
    return ActividadBorrador(
        id=a.id, nombre=a.nombre, vigente=a.origen == "vigente", version=a.version,
        fecha_version=a.fecha_version.strftime("%d-%m-%Y") if a.fecha_version else None,
        finalidades=tuple(c.get("finalidades") or []),
        base=base_op.nombre if base_op else "Sin base de licitud indicada",
        base_referencia=base_op.referencia if base_op else "",
        base_sensibles=cat.nombre(cat.BASES_SENSIBLES_POR_CODIGO, c.get("base_sensibles")) or None,
        interes_legitimo=c.get("interes_legitimo"),
        datos=tuple(f"{t.get('nombre') or cat_mapa.nombre_dato(t['codigo'])}{' (sensible)' if t.get('sensible') else ''}"
                    for t in tipos),
        categorias=tuple(t.get("nombre") or cat_mapa.nombre_dato(t["codigo"]) for t in tipos),
        sensibles=tuple(t.get("nombre") or cat_mapa.nombre_dato(t["codigo"]) for t in tipos if t.get("sensible")),
        titulares=tuple(f"{t.get('nombre') or cat_mapa.nombre_titular(t['codigo'])}{' (niños, niñas o adolescentes)' if t.get('nna') else ''}"
                        for t in titulares),
        nna=any(t.get("nna") for t in titulares),
        fuentes=tuple(I.texto_fuente(f) for f in c.get("fuentes") or []),
        sistemas=tuple(b.get("nombre", "?") for b in mp.get("bases_datos") or []),
        terceros=tuple(terceros), terceros_nombres=tuple(terceros_nombres),
        paises=tuple(p.get("nombre") or cat_mapa.nombre_pais(p.get("codigo")) for p in mp.get("paises") or []),
        transferencias=tuple(f"{t.get('pais_nombre') or cat_mapa.nombre_pais(t.get('pais_destino'))}: "
                             f"{t.get('garantia_nombre') or 'sin garantía registrada'}" for t in transf),
        paises_destino=tuple(t.get("pais_nombre") or cat_mapa.nombre_pais(t.get("pais_destino")) for t in transf),
        plazos=tuple(plazos), decisiones=I.texto_decisiones(c),
        usa_ia=any(f.titulo == "Uso de inteligencia artificial" for f in a.riesgo.factores),
        toma_decisiones=bool(d.get("existe")), riesgo=a.riesgo,
    )


def desde_informe(inf) -> RegistroBorrador:
    acts = tuple(_actividad(a) for a in inf.actividades if a.riesgo is not None)
    return RegistroBorrador(actividades=acts, huella_registro=inf.huella)


# ============================================================ PIA
def _textos_pia(acts: list[ActividadBorrador]) -> dict[str, str]:
    from app.application.borradores.plantillas import PIA

    if not acts:
        return {}
    nombres = _lista((f"«{a.nombre}»" for a in acts), y=True)
    salida: dict[str, str] = {}
    ident = PIA.clausula("pia-identificacion").texto
    salida["pia-identificacion"] = ident.replace(
        "| Sistema de IA evaluado | [COMPLETAR: nombre del sistema o proyecto] |",
        f"| Actividades del registro evaluadas | {_celda(nombres)} |")

    cuando = PIA.clausula("pia-cuando").texto
    lineas = [cuando, "", "**Por qué se recomienda esta evaluación según tu registro de actividades:**", ""]
    for a in acts:
        motivos = " ".join(a.riesgo.motivos_pia) or f"Riesgo {a.riesgo.nivel.lower()} en la matriz del registro."
        lineas.append(f"- «{a.nombre}»: {motivos}")
    salida["pia-cuando"] = "\n".join(lineas)

    partes: list[str] = []
    for a in acts:
        version = (f"versión vigente {a.version}" + (f" del {a.fecha_version}" if a.fecha_version else "")
                   if a.vigente else "sin versión vigente (borrador de trabajo)")
        partes += [
            f"**Actividad «{a.nombre}»**", "",
            f"- **Finalidad del tratamiento:** {_lista(a.finalidades, '[COMPLETAR: finalidad]')}",
            f"- **Categorías de titulares:** {_lista(a.titulares, '[COMPLETAR: titulares]')}",
            f"- **Datos tratados:** {_lista(a.datos, '[COMPLETAR: datos]')}",
            f"- **Origen de los datos:** {_lista(a.fuentes, '[COMPLETAR: origen]')}",
            f"- **Sistemas y bases de datos:** {_lista(a.sistemas, '[COMPLETAR: sistemas]')}",
            f"- **Proveedores y ubicación del procesamiento:** {_lista(a.terceros, 'Sin terceros destinatarios')}; "
            f"se trata en {_lista(a.paises, '[COMPLETAR: países]', y=True)}"
            + (f". Transferencias internacionales: {_lista(a.transferencias)}" if a.transferencias else ""),
            f"- **Decisiones automatizadas:** {a.decisiones}",
            f"- **Registro en el RAT:** «{a.nombre}», {version}.",
            "",
        ]
    partes.append("- **Flujo del sistema de IA:** captura → anonimización/seudonimización → modelo de IA → revisión "
                  "humana → uso del resultado → conservación y eliminación. [COMPLETAR: ajusta el flujo al sistema "
                  "evaluado]")
    salida["pia-descripcion"] = "\n".join(partes).strip()

    bases = []
    for a in acts:
        b = a.base + (f" ({a.base_referencia})" if a.base_referencia else "")
        if a.interes_legitimo:
            b += f"; interés legítimo: {a.interes_legitimo}"
        if a.base_sensibles:
            b += f"; para los datos sensibles: {a.base_sensibles}"
        bases.append(f"- «{a.nombre}»: {b}.")
    salida["pia-necesidad"] = "\n".join([
        "Se justifica por qué el tratamiento es necesario para la finalidad, por qué no existe una alternativa menos "
        "invasiva y por qué los datos tratados son los mínimos necesarios. [COMPLETAR: justificación de la necesidad "
        "y la proporcionalidad]", "",
        "La base de licitud de cada actividad, según el registro de actividades, es:", "", *bases, "",
        "Los datos no se usan para fines distintos de los informados a los titulares.",
    ])

    filas = ["**Riesgos identificados en el registro de actividades** (valoración orientativa: probabilidad × "
             "impacto, de 1 a 5):", "",
             "| Actividad | Factores de riesgo | Probabilidad | Impacto | Nivel |", "|---|---|---|---|---|"]
    for a in acts:
        r = a.riesgo
        factores = "; ".join(f"{f.titulo}: {f.detalle}" for f in r.factores) or "Sin factores relevantes"
        filas.append(f"| {_celda(a.nombre)} | {_celda(factores)} | {r.probabilidad} ({rg.ETIQUETA_PROBABILIDAD[r.probabilidad].lower()}) "
                     f"| {r.impacto} ({rg.ETIQUETA_IMPACTO[r.impacto].lower()}) | {r.nivel} ({r.puntaje} de 25) |")
    base_riesgos = PIA.clausula("pia-riesgos").texto
    salida["pia-riesgos"] = "\n".join(filas + ["", "**Riesgos del sistema de IA para los titulares** (completa la "
                                                   "valoración):", "", base_riesgos])

    tratamientos = list(dict.fromkeys(t for a in acts for t in a.riesgo.tratamientos))
    medidas = PIA.clausula("pia-medidas").texto
    if tratamientos:
        medidas += "\n\n**Medidas sugeridas a partir de tu registro de actividades:**\n\n" + "\n".join(
            f"- {t}" for t in tratamientos)
    salida["pia-medidas"] = medidas
    return salida


# ============================================================ aviso de privacidad
def _textos_aviso(acts: list[ActividadBorrador]) -> dict[str, str]:
    from app.application.borradores.plantillas import AVISO_PRIVACIDAD as AV

    salida: dict[str, str] = {}
    categorias = [c.lower() for a in acts for c in a.categorias]
    salida["avi-datos"] = AV.clausula("avi-datos").texto.replace(
        "[COMPLETAR: categorías de datos, p. ej. identificación, contacto, transacciones, uso del servicio]",
        _lista(categorias, "[COMPLETAR: categorías de datos]", y=True))

    filas = ["Usamos tus datos para las siguientes finalidades, cada una con la base que la autoriza:", "",
             "| Finalidad | Base que la autoriza |", "|---|---|"]
    vistas: set[tuple[str, str]] = set()
    for a in acts:
        base = a.base + (f" (para los datos sensibles: {a.base_sensibles.lower()})" if a.base_sensibles else "")
        for f in a.finalidades or ("[COMPLETAR: finalidad]",):
            if (f.lower(), base) in vistas:
                continue
            vistas.add((f.lower(), base))
            filas.append(f"| {_celda(f)} | {_celda(base)} |")
    filas += ["", "No usaremos tus datos para fines distintos de los informados sin una nueva base que lo permita."]
    salida["avi-finalidades"] = "\n".join(filas)

    con_ia = [f for a in acts if a.usa_ia or a.toma_decisiones for f in a.finalidades]
    if con_ia:
        salida["avi-ia"] = AV.clausula("avi-ia").texto.replace(
            "[COMPLETAR: usos, p. ej. atención automatizada, análisis de solicitudes]",
            _lista((f[0].lower() + f[1:] for f in con_ia), y=True))

    terceros = [t for a in acts for t in a.terceros_nombres]
    if terceros:
        salida["avi-proveedores"] = AV.clausula("avi-proveedores").texto.replace(
            "[COMPLETAR: categorías o nombres de proveedores]", _lista(terceros, y=True))

    destinos = [p for a in acts for p in a.paises_destino]
    if destinos:
        salida["avi-transferencias"] = AV.clausula("avi-transferencias").texto.replace(
            "[COMPLETAR: países o regiones]", _lista(destinos, y=True))
    else:
        salida["avi-transferencias"] = ("Según nuestro registro de actividades, hoy tus datos no se envían fuera de "
                                        "Chile. Si eso cambia, actualizaremos este aviso e indicaremos la garantía que "
                                        "protege cada transferencia.")

    sensibles = list(dict.fromkeys(s.lower() for a in acts for s in a.sensibles))
    nna = any(a.nna for a in acts)
    if sensibles or nna:
        partes = []
        if sensibles:
            para = [f for a in acts if a.sensibles for f in a.finalidades]
            partes.append(f"Tratamos datos sensibles ({_lista(sensibles, y=True)}) para: "
                          f"{_lista((f[0].lower() + f[1:] for f in para), '[COMPLETAR: finalidad]', y=True)}.")
        if nna:
            partes.append("Tratamos datos de niños, niñas y adolescentes guiados por su interés superior y con la "
                          "autorización de sus padres o representantes cuando la ley la exige.")
        salida["avi-sensibles"] = AV.clausula("avi-sensibles").texto.replace(
            "[COMPLETAR: indicar si se tratan y para qué, o eliminar este apartado]", " ".join(partes))
    else:
        salida["avi-sensibles"] = "No tratamos datos sensibles ni datos de niños, niñas y adolescentes."

    plazos: dict[str, tuple[str, int]] = {}
    for a in acts:
        for categoria, texto, dias in a.plazos:
            if categoria not in plazos or dias > plazos[categoria][1]:
                plazos[categoria] = (texto, dias)
    if plazos:
        salida["avi-conservacion"] = AV.clausula("avi-conservacion").texto.replace(
            "[COMPLETAR: plazos por categoría]",
            "; ".join(f"{c.lower()}, {t}" for c, (t, _) in plazos.items()))
    return salida

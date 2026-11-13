"""
HU-41 · Revisión interna del tratamiento que hace la plataforma (lógica PURA).

Recorre el registro generado (registro.py), la configuración y la última ejecución de la retención, y
devuelve dos listas para el panel:

  revisiones   comprobaciones automáticas con su estado (ok, alerta o error), siempre las mismas.
  hallazgos    lo que conviene resolver, con nivel (critico, alto, medio, bajo), explicación y qué hacer.

Los textos están en lenguaje simple (se muestran tal cual). El nombre técnico de un ajuste va aparte, en
`ajuste`, para el equipo que lo cambia.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from app.application.plataforma.registro import RegistroPlataforma
from app.core import catalogo_datos_personales as inv

NIVELES = ("critico", "alto", "medio", "bajo")
_ORDEN = {n: i for i, n in enumerate(NIVELES)}
# Conservaciones que dependen de una decisión pendiente (no de un evento natural como "mientras exista la cuenta")
PENDIENTES = {inv.C_SESION: "Sesiones y enlaces vencidos", inv.C_AUDITORIA: "Registro de auditoría",
              inv.C_CONTRATACION: "Solicitudes de contratación descartadas"}
MAX_HORAS_RETENCION = 48


def _hallazgo(codigo: str, nivel: str, titulo: str, detalle: str, recomendacion: str,
              actividades: list[str] | None = None, ajuste: str | None = None) -> dict:
    return {"codigo": codigo, "nivel": nivel, "titulo": titulo, "detalle": detalle, "recomendacion": recomendacion,
            "actividades": actividades or [], "ajuste": ajuste}


def _revision(codigo: str, estado: str, titulo: str, detalle: str = "") -> dict:
    return {"codigo": codigo, "estado": estado, "titulo": titulo, "detalle": detalle}


def _lista(nombres: list[str]) -> str:
    if len(nombres) <= 1:
        return "".join(nombres)
    return ", ".join(nombres[:-1]) + " y " + nombres[-1]


def tablas_sin_actividad() -> list[str]:
    """Tablas del inventario sin decidir (ni en una actividad ni declaradas sin tratamiento) o con datos
    personales declaradas sin tratamiento."""
    p = inv.problemas_de_cobertura()
    return sorted(set(p["sin_actividad"]) | set(p["personales_sin_tratamiento"]))


def revisar(reg: RegistroPlataforma, conf, ultima_retencion: dict | None, ahora: datetime) -> dict:
    """
    {revisiones, hallazgos, conteo}. `ultima_retencion` = {fecha (UTC sin zona), resultado, detalle} de la
    última ejecución real de la retención (no simulación), o None si nunca corrió.
    """
    hallazgos: list[dict] = []
    revisiones: list[dict] = []

    # 1. Cobertura del inventario
    sueltas = tablas_sin_actividad()
    con_dp = sum(1 for cols in inv.CATALOGO.values() if any(d.es_personal for d in cols.values()))
    if sueltas:
        revisiones.append(_revision("cobertura", "error", "Hay tablas sin actividad de tratamiento",
                                    _lista(sueltas)))
        hallazgos.append(_hallazgo(
            "cobertura", "critico", "Tablas sin actividad de tratamiento",
            f"Estas tablas no están en el registro de la plataforma: {_lista(sueltas)}.",
            "Asigna cada tabla a una actividad en el inventario de datos de la plataforma."))
    else:
        revisiones.append(_revision("cobertura", "ok", "Todas las tablas con datos personales tienen una actividad",
                                    f"{len(inv.CATALOGO)} tablas revisadas · {con_dp} con datos personales"))

    # 2. Reglas de retención activas
    desactivadas = [a for a in reg.ajustes.values() if not a.activo]
    if desactivadas:
        revisiones.append(_revision("retencion_activa", "error", "Hay reglas de retención desactivadas",
                                    _lista([a.nombre for a in desactivadas])))
        for a in desactivadas:
            usan = [x.definicion.nombre for x in reg.actividades if any(a.clave in p.ajustes for p in x.plazos)]
            hallazgos.append(_hallazgo(
                f"regla_desactivada:{a.clave}", "alto", f"La regla «{a.nombre}» está desactivada",
                "Sin un plazo configurado, la plataforma conserva estos datos sin límite de tiempo y el registro "
                "no puede informar un plazo.",
                "Fija el plazo en la configuración de la plataforma"
                + (" o en Retención de datos." if a.clave == "RETENCION_DATOS_TITULAR_DIAS" else "."),
                usan, a.clave))
    else:
        revisiones.append(_revision("retencion_activa", "ok", "Los plazos del registro coinciden con la retención "
                                    "configurada", f"{len(reg.ajustes)} reglas activas"))

    # 3. Plazos que dependen de una decisión pendiente
    pendientes: dict[str, list[str]] = {}
    for x in reg.actividades:
        for p in x.plazos:
            for c in p.sin_numero:
                if c in PENDIENTES:
                    lista = pendientes.setdefault(c, [])
                    if x.definicion.nombre not in lista:
                        lista.append(x.definicion.nombre)
    textos = {
        inv.C_SESION: ("Sesiones y enlaces vencidos sin depuración",
                       "Las sesiones cerradas y los enlaces de activación o recuperación ya usados se conservan "
                       "mientras exista la cuenta.", "Define un plazo para depurar sesiones y enlaces vencidos."),
        inv.C_AUDITORIA: ("El registro de auditoría no tiene plazo de conservación",
                          "El registro es inmutable y guarda la dirección IP de cada acción. Falta definir cuánto se "
                          "conserva y cómo se purga por lotes sellados.",
                          "Define el plazo y el procedimiento de purga del registro de auditoría."),
        inv.C_CONTRATACION: ("Solicitudes de contratación sin plazo cuando se descartan",
                             "Si una solicitud no termina en contrato, sus datos de contacto no tienen un plazo de "
                             "eliminación.", "Define un plazo de eliminación para las solicitudes descartadas."),
    }
    for c, acts in pendientes.items():
        titulo, detalle, rec = textos[c]
        hallazgos.append(_hallazgo(f"plazo_pendiente:{PENDIENTES[c]}", "medio", titulo, detalle, rec, acts))
    if pendientes:
        revisiones.append(_revision("plazos_pendientes", "alerta",
                                    f"{len(pendientes)} plazo(s) dependen de una decisión pendiente",
                                    _lista(list(PENDIENTES[c] for c in pendientes))))
    else:
        revisiones.append(_revision("plazos_pendientes", "ok", "No hay plazos pendientes de definir"))

    # 4. Actividades incompletas (el informe sale como borrador)
    for x in reg.actividades:
        if x.completa:
            continue
        hallazgos.append(_hallazgo(
            f"incompleta:{x.clave}", "medio", f"«{x.definicion.nombre}» está incompleta",
            "; ".join(f["mensaje"] for f in x.completitud["faltantes"]),
            "Mientras falte, el registro de actividades se emite como borrador.", [x.definicion.nombre]))
    revisiones.append(_revision(
        "completitud", "ok" if reg.oficial else "alerta",
        "Todas las actividades están completas" if reg.oficial
        else f"{len(reg.incompletas)} actividad(es) incompletas: el informe sale como borrador"))

    # 5. Proveedores: país, garantía y contrato
    sin_pais = [p for p in reg.proveedores if not p.pais]
    sin_garantia = [p for p in reg.proveedores if not p.garantia_valida]
    for p in {x.clave: x for x in sin_pais + sin_garantia}.values():
        falta = [t for t, cond in (("país", not p.pais), ("garantía", not p.garantia_valida)) if cond]
        usan = [x.definicion.nombre for x in reg.actividades if p.clave in x.definicion.elementos]
        ajuste = "CORREO_PROVEEDOR_PAIS / CORREO_PROVEEDOR_GARANTIA" if p.clave == "correo" else None
        hallazgos.append(_hallazgo(
            f"proveedor:{p.clave}", "alto", f"{p.nombre}: sin {' ni '.join(falta)} declarados",
            "El proveedor trata datos por cuenta de Therion Labs, pero el registro no sabe dónde está o qué respalda "
            "la transferencia internacional.",
            f"Indica el {' y la '.join(falta)} del proveedor en la configuración de la plataforma.", usan, ajuste))
    if sin_pais or sin_garantia:
        revisiones.append(_revision("proveedores", "error",
                                    f"{len({p.clave for p in sin_pais + sin_garantia})} proveedor(es) sin país o sin "
                                    "garantía", _lista([p.nombre for p in {x.clave: x for x in sin_pais + sin_garantia}.values()])))
    else:
        revisiones.append(_revision("proveedores", "ok", "Todos los proveedores tienen país y garantía declarados",
                                    f"{len(reg.proveedores)} proveedor(es)"))
    por_confirmar = [p for p in reg.proveedores if not p.contrato_confirmado]
    if por_confirmar:
        hallazgos.append(_hallazgo(
            "contratos", "medio", "Contratos con proveedores por confirmar",
            f"No está confirmado que Therion Labs haya aceptado el acuerdo de tratamiento de datos de "
            f"{_lista([p.nombre for p in por_confirmar])}.",
            "Confirma con el área legal cada acuerdo y márcalo como confirmado en la configuración.",
            ["Todas"], "PROVEEDORES_CONTRATO_CONFIRMADO"))
        revisiones.append(_revision("contratos", "alerta", f"{len(por_confirmar)} contrato(s) con proveedores por "
                                    "confirmar", _lista([p.nombre for p in por_confirmar])))
    else:
        revisiones.append(_revision("contratos", "ok", "Los contratos con los proveedores están confirmados"))

    # 6. La retención automática corre
    if ultima_retencion is None:
        revisiones.append(_revision("ultima_retencion", "alerta", "No hay registro de una ejecución de la retención"))
        hallazgos.append(_hallazgo(
            "retencion_sin_ejecucion", "medio", "La retención automática no ha corrido",
            "No hay ninguna ejecución de la anonimización automática en el registro de auditoría.",
            "Revisa que el worker esté encendido o ejecútala desde Retención de datos."))
    else:
        fecha = ultima_retencion.get("fecha")
        detalle = ultima_retencion.get("detalle") or {}
        fallo = ultima_retencion.get("resultado") not in (None, "ok") or bool(detalle.get("error"))
        vieja = bool(fecha and ahora - fecha > timedelta(hours=MAX_HORAS_RETENCION))
        if fallo or vieja:
            revisiones.append(_revision("ultima_retencion", "error", "La retención automática no está al día",
                                        "La última ejecución falló." if fallo
                                        else f"La última ejecución tiene más de {MAX_HORAS_RETENCION} horas."))
            hallazgos.append(_hallazgo(
                "retencion_atrasada", "alto", "La retención automática no está al día",
                "La última ejecución falló." if fallo else
                f"La última ejecución tiene más de {MAX_HORAS_RETENCION} horas: los plazos del registro no se "
                "están cumpliendo.", "Revisa el worker y el historial en Retención de datos."))
        else:
            revisiones.append(_revision("ultima_retencion", "ok", "La última anonimización automática terminó bien"))

    # 7. Capa de IA
    if getattr(conf, "GUARDAR_MAPA_ENTIDADES_CIFRADO", False):
        revisiones.append(_revision("mapa_reversible", "error", "El mapa reversible de entidades está activo"))
        hallazgos.append(_hallazgo(
            "mapa_reversible", "critico", "La anonimización se puede revertir",
            "Está activo el guardado del mapa cifrado de entidades: la anonimización deja de ser irreversible.",
            "Desactiva el guardado del mapa de entidades (solo se permite para depurar en desarrollo).",
            ajuste="GUARDAR_MAPA_ENTIDADES_CIFRADO"))
    else:
        revisiones.append(_revision("mapa_reversible", "ok", "La anonimización es irreversible"))
    if any(p.clave == "llm" for p in reg.proveedores) and not getattr(conf, "SANITIZER_ENABLED", True):
        revisiones.append(_revision("sanitizador", "error", "Los textos van al modelo de lenguaje sin anonimizar"))
        hallazgos.append(_hallazgo(
            "sanitizador", "critico", "Los textos llegan sin anonimizar al proveedor de IA",
            "La anonimización previa está desactivada: los datos personales viajan en claro al proveedor.",
            "Activa la anonimización previa (solo se puede desactivar para depurar en desarrollo).",
            ajuste="SANITIZER_ENABLED"))

    hallazgos.sort(key=lambda h: (_ORDEN[h["nivel"]], h["titulo"]))
    conteo = {n: sum(1 for h in hallazgos if h["nivel"] == n) for n in NIVELES}
    return {"revisiones": revisiones, "hallazgos": hallazgos, "conteo": conteo}


__all__ = ["NIVELES", "PENDIENTES", "revisar", "tablas_sin_actividad"]

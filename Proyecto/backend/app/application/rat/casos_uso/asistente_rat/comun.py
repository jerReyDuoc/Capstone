"""Constantes, errores y serializadores comunes del asistente de IA del RAT (HU-39)."""
from __future__ import annotations

from datetime import datetime, timezone

from app.application.rat.asistente import banco, documento
from app.domain.models.asistente import AsistenteDocumento, AsistenteMensaje, AsistentePropuesta, AsistenteSesion


MAX_MENSAJES_VISTA = 80
MAX_PROPUESTAS_VISTA = 200
MUESTRA_DENSIDAD = 30000
MIN_CARACTERES_DOCUMENTO = 200
TEXTO_BLOQUEADO = "[Respuesta bloqueada por seguridad: no se guardó su contenido]"
TEXTO_OMITIDA = "(Pregunta omitida)"
TEXTO_NO_GUARDADO = "(Respuesta no guardada: el servicio de anonimización no está disponible)"

AVISOS = {
    "ia_deshabilitada": "La ayuda automática no está activada. Puedes seguir respondiendo y completar todo a mano; "
                        "te mostramos sugerencias según tu evaluación.",
    "cuota_ia_agotada": "Tu empresa usó la ayuda automática de hoy. Puedes seguir respondiendo y completar todo a "
                        "mano; mañana podrás volver a usarla.",
    "ia_no_disponible": "La ayuda automática no respondió esta vez. Tu respuesta quedó guardada: puedes seguir y "
                        "completar a mano, o volver a intentarlo más tarde.",
    "salida_ia_descartada": "Descartamos lo que propuso la ayuda automática porque no pasó la revisión de seguridad. "
                            "Puedes seguir y completar a mano.",
    "anonimizacion": "No pudimos proteger los datos de esta respuesta, así que no usamos la ayuda automática. "
                     "Puedes seguir y completar a mano.",
    "sin_propuestas": None,
    "sin_ayuda": "Guardamos tu respuesta sin ayuda automática. Puedes agregar lo que falte a mano en el mapa o en el "
                 "registro.",
}
# Cuando la ayuda automática falla por algo pasajero, la pregunta NO avanza: el usuario reintenta o guarda sin ayuda
MENSAJES_FALLA_IA = {
    "rate_limit": "La ayuda automática está ocupada: se hicieron muchas consultas en el último minuto. Espera un "
                  "momento y vuelve a enviar tu respuesta, o guárdala sin ayuda.",
    "timeout": "La ayuda automática tardó demasiado en responder. Vuelve a enviar tu respuesta o guárdala sin ayuda.",
}
MENSAJE_FALLA_IA = ("La ayuda automática no respondió esta vez. Vuelve a enviar tu respuesta o guárdala sin ayuda: "
                    "no se pierde nada.")
MENSAJE_BLOQUEO = ("Tu respuesta contiene texto que intenta cambiar las reglas del asistente, así que no la "
                   "procesamos. Cuéntanos con tus palabras qué hace tu empresa (por ejemplo, «usamos un sistema de "
                   "remuneraciones en la nube»).")
MENSAJE_ETICA = ("No podemos ayudarte con eso: el registro debe reflejar lo que tu empresa realmente hace, sin ocultar "
                 "tratamientos, transferencias ni el uso de IA (Ley 21.719).")
ESTADO_DOCUMENTO_MENSAJE = {
    "ilegible": "No pudimos leer el archivo. Revisa que no esté dañado ni protegido con contraseña.",
    "sin_texto": "No encontramos texto en el archivo (¿es un documento escaneado?). Sube una versión con texto "
                 "seleccionable.",
    "rechazado_pii": "Este archivo parece una lista o planilla con datos de personas. Sube la política, el contrato "
                     "o el aviso, no la base de datos: el asistente describe procesos, no personas.",
}


class AsistenteError(Exception):
    def __init__(self, status: int, codigo: str, mensaje: str, **extra):
        super().__init__(mensaje)
        self.status, self.codigo, self.mensaje, self.extra = status, codigo, mensaje, extra


def _ahora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso(d: datetime | None) -> str | None:
    return d.isoformat() if d else None


def etiqueta_ia(modelo: str | None, prompt_version: str | None) -> str | None:
    """«Sugerido por IA · Modelo X · Guía v1.0.0» (lo que ve el usuario, sin jerga)."""
    if not modelo or modelo == "sin_ia":
        return None
    version = (prompt_version or "").split("/")[-1] or "?"
    return f"Sugerido por IA · Modelo {modelo} · Guía v{version}"


def propuesta_a_dict(p: AsistentePropuesta) -> dict:
    payload = p.payload_final if p.payload_final is not None else p.payload_propuesto
    return {
        "id": p.id, "tipo": p.tipo, "clave": p.clave, "estado": p.estado, "origen": p.origen, "area": p.area,
        "nombre": (payload.get("finalidad") or "Flujo de datos") if p.tipo == "flujo" else payload.get("nombre"),
        "payload": p.payload_propuesto, "payload_final": p.payload_final, "campos_editados": p.campos_editados or [],
        "explicaciones": p.explicaciones or {}, "inconsistencias": p.inconsistencias or [],
        "riesgo_nivel": p.riesgo_nivel, "confianza": p.confianza,
        "ia": {"modelo": p.modelo, "prompt_version": p.prompt_version, "traza_id": p.traza_id,
               "etiqueta": etiqueta_ia(p.modelo, p.prompt_version)},
        "entidad_destino": p.entidad_destino, "entidad_destino_id": p.entidad_destino_id,
        "motivo_descarte": p.motivo_descarte, "documento_id": p.documento_id,
        "fecha_creacion": _iso(p.fecha_creacion), "fecha_decision": _iso(p.fecha_decision),
    }


def mensaje_a_dict(m: AsistenteMensaje) -> dict:
    return {"id": m.id, "rol": m.rol, "area": m.area, "pregunta_codigo": m.pregunta_codigo, "contenido": m.contenido,
            "bloqueado": bool(m.bloqueado), "motivo_sin_ia": m.motivo_sin_ia, "fecha": _iso(m.fecha)}


def documento_a_dict(d: AsistenteDocumento) -> dict:
    return {"id": d.id, "nombre_archivo": d.nombre_archivo, "tipo_documento": d.tipo_documento,
            "tipo_documento_nombre": documento.NOMBRES_TIPO.get(d.tipo_documento, "Otro documento"),
            "estado": d.estado, "lineas_omitidas": d.lineas_omitidas, "pasajes_usados": d.pasajes_usados,
            "pasajes_total": d.pasajes_total, "motivo_sin_ia": d.motivo_sin_ia, "fecha": _iso(d.fecha)}


def sesion_a_dict(s: AsistenteSesion) -> dict:
    completadas = list(s.areas_completadas or [])
    p = banco.pregunta(s.area_actual, s.paso)
    a = banco.area(s.area_actual)
    return {
        "id": s.id, "estado": s.estado, "area_actual": s.area_actual, "area_nombre": a.nombre, "paso": s.paso,
        "total_pasos": len(a.preguntas), "areas": banco.resumen_areas(s.area_actual, completadas),
        "pregunta": p.como_dict() if p else None,
        "terminada": banco.terminada(s.area_actual, s.paso, completadas),
        "fecha_actualizacion": _iso(s.fecha_actualizacion),
    }

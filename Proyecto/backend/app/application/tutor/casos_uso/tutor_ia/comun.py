"""Constantes, errores y serializadores compartidos del tutor."""
from __future__ import annotations

from datetime import datetime, timezone

from app.application.ai.agente.salida_tutor import RESPUESTA_FUGA, SUGERENCIAS_FUGA
from app.application.ai.schemas.tutor import NivelTutor
from app.domain.models.tutor_conversaciones import ConversacionTutor, MensajeTutor

MAX_TITULO = 80
TEXTO_BLOQUEADO_USUARIO = "[Mensaje bloqueado por seguridad: no se guardó su contenido]"
RESPUESTA_BLOQUEADO = (
    "No puedo procesar ese mensaje porque contiene instrucciones que intentan cambiar mis reglas. "
    "Reformula tu pregunta sobre las brechas de tu empresa y con gusto te ayudo."
)
SUGERENCIAS_BLOQUEO = ["¿Qué brecha debería cerrar primero?", "Explícame la brecha más crítica de mi evaluación."]
# HU-18: respuesta fija ante un pedido de fraude u ocultamiento (no se llama al LLM)
RESPUESTA_ETICA = (
    "No puedo ayudarte con eso: falsificar o adulterar evidencia, aparentar un cumplimiento que no existe u ocultar "
    "un incidente va contra la Ley 21.719 y contra la gobernanza que esta plataforma evalúa. Sí puedo ayudarte a "
    "preparar la evidencia real del control o a entender cómo y cuándo notificar un incidente."
)
SUGERENCIAS_ETICA = ["¿Qué evidencia real necesito para este control?", "¿Cómo se notifica un incidente de datos personales?"]
ADVERTENCIA_ABUSO = (
    "Hemos bloqueado varios mensajes seguidos que intentaban cambiar las reglas del tutor. El tutor sigue disponible "
    "para tus brechas de gobernanza; estos intentos quedan registrados y se informan al equipo de Therion Labs."
)


def respuesta_de_bloqueo(categoria: str | None) -> tuple[str, list[str]]:
    if categoria == "uso_indebido":
        return RESPUESTA_ETICA, SUGERENCIAS_ETICA
    if categoria == "fuga_prompt":
        return RESPUESTA_FUGA, SUGERENCIAS_FUGA
    return RESPUESTA_BLOQUEADO, SUGERENCIAS_BLOQUEO


class TutorError(Exception):
    def __init__(self, status: int, codigo: str, mensaje: str, **extra):
        super().__init__(mensaje)
        self.status, self.codigo, self.mensaje, self.extra = status, codigo, mensaje, extra
        self.auditado = False  # HU-18: ya quedó en la bitácora (no registrarlo dos veces)


def _ahora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso(d: datetime | None) -> str | None:
    return d.isoformat() if d else None


def _nivel(valor: str | None, por_defecto: NivelTutor) -> NivelTutor:
    if valor is None or valor == "":
        return por_defecto
    n = NivelTutor.normalizar(valor)
    if n is None:
        raise TutorError(422, "NIVEL_INVALIDO", "El nivel debe ser Inicial, Intermedio o Avanzado.",
                         niveles=NivelTutor.valores())
    return n


def mensaje_a_dict(m: MensajeTutor) -> dict:
    datos = m.datos or {}
    return {
        "id": m.id, "rol": m.rol, "tipo": m.tipo, "contenido": m.contenido, "nivel": m.nivel,
        "bloqueado": bool(m.bloqueado), "fecha": _iso(m.fecha),
        "pasos": datos.get("pasos", []), "brechas": datos.get("brechas", []),
        "referencias_normativas": datos.get("referencias_normativas", []),
        "sugerencias": datos.get("sugerencias", []),
    }


def conversacion_a_dict(c: ConversacionTutor, evaluacion_vigente: int | None) -> dict:
    vigente = evaluacion_vigente is not None and c.evaluacion_id == evaluacion_vigente
    return {
        "id": c.id, "titulo": c.titulo, "nivel": c.nivel, "evaluacion_id": c.evaluacion_id,
        "ruta_id": c.ruta_formativa_id, "mensajes_total": c.mensajes_total or 0,
        "fecha_creacion": _iso(c.fecha_creacion), "fecha_ultimo_mensaje": _iso(c.fecha_ultimo_mensaje),
        # Una conversación de una evaluación anterior queda de solo lectura
        "estado": "activa" if vigente else "solo_lectura",
    }

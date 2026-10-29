from app.domain.models.dominio import Dominio
from app.domain.models.rubro import Rubro
from app.domain.models.ruta_formativa import RutaFormativa
from app.domain.models.usuario_temporal import UsuarioTemporal
from app.domain.models.catalogo_brechas import CatalogoBrechas
from app.domain.models.evaluacion import Evaluacion
from app.domain.models.matriz_control import MatrizControl
from app.domain.models.respuesta import Respuesta, EstadoClasificacion, FuenteClasificacion
from app.domain.models.evidencia import Evidencia, EstadoValidacion
from app.domain.models.benchmark import Benchmark
from app.domain.models.resumen import Resumen
from app.domain.models.pregunta_filtro import PreguntaFiltro
from app.domain.models.respuesta_filtro import RespuestaFiltro
from app.domain.models.evento_seguridad import EventoSeguridad, OrigenEvento
from app.domain.models.llamada_llm import LlamadaLLM
from app.domain.models.sanitizacion import Sanitizacion
from app.domain.models.usuario_admin import UsuarioAdmin
from app.domain.models.solicitud_arcop import (
    SolicitudARCOP,
    EventoSolicitud,
    TipoSolicitudARCOP,
    EstadoSolicitudARCOP,
)
# HU-27 (con las bases mínimas de HU-31 y HU-09)
from app.domain.models.empresa import Empresa
from app.domain.models.usuario_definitivo import (
    UsuarioDefinitivo,
    TokenActivacion,
    EstadoUsuarioDefinitivo,
)
from app.domain.models.solicitud_contratacion import (
    SolicitudContratacion,
    EstadoSolicitudContratacion,
)
from app.domain.models.bitacora_auditoria import BitacoraAuditoria
# HU-28: sesiones revocables y recuperación de contraseña
from app.domain.models.sesion import SesionUsuario, TokenRecuperacion
# HU-26: recorrido de módulos formativos y avance de la empresa
from app.domain.models.formacion import (
    AvanceFormativo,
    EstadoAvance,
    LeccionFormativa,
    PreguntaVerificacion,
)
# HU-15: conversaciones del Agente IA Tutor
from app.domain.models.tutor import (
    ConversacionTutor,
    MensajeTutor,
    RolMensajeTutor,
    TipoMensajeTutor,
)

__all__ = [
    "Dominio",
    "Rubro",
    "RutaFormativa",
    "UsuarioTemporal",
    "CatalogoBrechas",
    "Evaluacion",
    "MatrizControl",
    "Respuesta",
    "EstadoClasificacion",
    "FuenteClasificacion",
    "Evidencia",
    "EstadoValidacion",
    "Benchmark",
    "Resumen",
    "PreguntaFiltro",
    "RespuestaFiltro",
    "EventoSeguridad",
    "OrigenEvento",
    "LlamadaLLM",
    "Sanitizacion",
    "UsuarioAdmin",
    "SolicitudARCOP",
    "EventoSolicitud",
    "TipoSolicitudARCOP",
    "EstadoSolicitudARCOP",
    "Empresa",
    "UsuarioDefinitivo",
    "TokenActivacion",
    "EstadoUsuarioDefinitivo",
    "SolicitudContratacion",
    "EstadoSolicitudContratacion",
    "BitacoraAuditoria",
    "SesionUsuario",
    "TokenRecuperacion",
    "AvanceFormativo",
    "EstadoAvance",
    "LeccionFormativa",
    "PreguntaVerificacion",
    "ConversacionTutor",
    "MensajeTutor",
    "RolMensajeTutor",
    "TipoMensajeTutor",
]
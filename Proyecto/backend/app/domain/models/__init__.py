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
from app.domain.models.bitacora_auditoria import BitacoraAuditoria, AuditLog
# HU-09: sellos por lote del audit_log y cuentas del Auditor Externo
from app.domain.models.auditoria_externa import AuditLogSello, UsuarioAuditor
# HU-28: sesiones revocables y recuperación de contraseña
from app.domain.models.sesion import SesionUsuario, TokenRecuperacion
# HU-26: recorrido de módulos formativos y avance de la empresa
from app.domain.models.formacion import (
    AvanceFormativo,
    EstadoAvance,
    LeccionFormativa,
    PreguntaVerificacion,
)
# HU-29: documentos generados de la empresa ("Mis documentos")
from app.domain.models.documento_empresa import DocumentoEmpresa
# HU-16: borradores de documentos de cumplimiento
from app.domain.models.borrador import BorradorDocumento, EstadoBorrador
# HU-15: conversaciones del Agente IA Tutor
# HU-24: versiones de la matriz normativa y reglas de aplicabilidad
from app.domain.models.matriz_version import MatrizVersion, ReglaAplicabilidad
from app.domain.models.tutor import (
    ConversacionTutor,
    MensajeTutor,
    RolMensajeTutor,
    TipoMensajeTutor,
)
# HU-25: plazo de retención de usuarios temporales configurable desde el panel
from app.domain.models.configuracion_retencion import ConfiguracionRetencion
from app.domain.models.mapa_datos import MapaDatos, MapaDatosVersion, MapaElemento, MapaFlujo  # HU-34

__all__ = [
    "BorradorDocumento",
    "EstadoBorrador",
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
    "DocumentoEmpresa",
    "UsuarioDefinitivo",
    "TokenActivacion",
    "EstadoUsuarioDefinitivo",
    "SolicitudContratacion",
    "EstadoSolicitudContratacion",
    "BitacoraAuditoria",
    "AuditLog",
    "AuditLogSello",
    "UsuarioAuditor",
    "SesionUsuario",
    "TokenRecuperacion",
    "AvanceFormativo",
    "EstadoAvance",
    "LeccionFormativa",
    "PreguntaVerificacion",
    "MatrizVersion",
    "ReglaAplicabilidad",
    "ConversacionTutor",
    "MensajeTutor",
    "RolMensajeTutor",
    "TipoMensajeTutor",
    "ConfiguracionRetencion",
    "MapaDatos",
    "MapaElemento",
    "MapaFlujo",
    "MapaDatosVersion",
]
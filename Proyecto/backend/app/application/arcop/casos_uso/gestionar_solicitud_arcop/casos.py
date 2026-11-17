"""Caso de uso del ciclo de vida de solicitudes ARCOP: composición de los mixins por responsabilidad."""
from app.application.arcop.casos_uso.gestionar_solicitud_arcop.acciones_titular import AccionesTitularMixin
from app.application.arcop.casos_uso.gestionar_solicitud_arcop.base_solicitud import BaseSolicitudMixin
from app.application.arcop.casos_uso.gestionar_solicitud_arcop.gestion_admin import GestionAdminMixin
from app.application.arcop.casos_uso.gestionar_solicitud_arcop.lectura import LecturaMixin
from app.application.arcop.casos_uso.gestionar_solicitud_arcop.resolucion_solicitud import ResolucionSolicitudMixin


class GestionarSolicitudARCOPUseCase(
    BaseSolicitudMixin, AccionesTitularMixin, LecturaMixin, GestionAdminMixin, ResolucionSolicitudMixin,
):
    def __init__(self, repo, anonimizacion_repo=None, storage=None,
                 plazo_respuesta_dias: int | None = None,
                 plazo_informacion_dias: int | None = None,
                 plazo_prorroga_dias: int | None = None,
                 plazo_bloqueo_dias_habiles: int | None = None):
        self.repo = repo
        self.anonimizacion_repo = anonimizacion_repo
        self.storage = storage
        self.plazo_respuesta_dias = plazo_respuesta_dias
        self.plazo_informacion_dias = plazo_informacion_dias
        self.plazo_prorroga_dias = plazo_prorroga_dias
        self.plazo_bloqueo_dias_habiles = plazo_bloqueo_dias_habiles

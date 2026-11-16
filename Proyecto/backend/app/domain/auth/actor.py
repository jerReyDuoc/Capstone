"""
Identidad del solicitante: roles del sistema y `Actor` (quién hace la petición).

Roles (referente y admin_therion son los mismos que usa el frontend):
  - referente      -> usuario temporal invitado (sub = usuario_temporal.id).
  - encuestado     -> encuestado anónimo de la encuesta pública (sub = evaluacion.id).
  - admin_therion  -> administrador (sub = usuarios_admin.id). Gestiona las solicitudes.
  - cliente        -> usuario definitivo de una empresa cliente (sub = usuario_definitivo.id).
                      HU-27: rol único del servicio pagado; ve las evaluaciones migradas
                      a su empresa. NO es titular ARCOP (no usa esas rutas).
  - auditor_externo -> Auditor Externo (sub = usuario_auditor.id). HU-09: SOLO LECTURA del
                      audit_log (consultar, verificar, exportar). Cuenta con vencimiento.
referente y encuestado son TITULARES de sus datos en las solicitudes ARCOP.
"""
from dataclasses import dataclass
from enum import Enum


class Rol(str, Enum):
    REFERENTE = "referente"
    ENCUESTADO = "encuestado"
    ADMIN_THERION = "admin_therion"
    CLIENTE = "cliente"  # HU-27
    AUDITOR_EXTERNO = "auditor_externo"  # HU-09

    @classmethod
    def valores(cls) -> list[str]:
        return [r.value for r in cls]


@dataclass(frozen=True)
class Actor:
    """
    Quién hace la petición. `id` es usuario_temporal.id (referente),
    evaluacion.id (encuestado), usuarios_admin.id (admin), usuario_definitivo.id (cliente)
    o usuario_auditor.id (auditor_externo, HU-09).
    """
    id: int
    rol: str
    # HU-28: identificador de la sesión (solo en tokens de admin y cliente emitidos al iniciar sesión)
    sid: str | None = None

    @property
    def es_admin(self) -> bool:
        return self.rol == Rol.ADMIN_THERION.value

    @property
    def es_encuestado(self) -> bool:
        return self.rol == Rol.ENCUESTADO.value

    @property
    def es_cliente(self) -> bool:
        return self.rol == Rol.CLIENTE.value

    @property
    def es_auditor(self) -> bool:
        return self.rol == Rol.AUDITOR_EXTERNO.value

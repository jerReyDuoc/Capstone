from fastapi import APIRouter

from app.api.routes import respuestas, evidencias, catalogos, controles, evaluaciones, filtro, reportes, eventos_seguridad, metricas_ia, arcop, acceso, encuesta_publica, informes
from app.api.routes import contratacion, admin_clientes  # HU-27 (+ bases de HU-31 y HU-09)
from app.api.routes import cliente  # HU-28: espacio de la empresa del usuario definitivo
from app.api.routes import formacion, remediacion  # HU-26 (módulos formativos) y HU-17 (remediación)
from app.api.routes import conversacion_tutor  # HU-15: Agente IA Tutor del panel de formación
from app.api.routes import borradores  # HU-16: borradores de cumplimiento adaptados por el Agente IA
from app.api.routes import auditoria  # HU-09: log inmutable para el Auditor Externo
from app.api.routes import admin_matriz  # HU-24: mantenedor de la matriz normativa con versionado
from app.api.routes import admin_rubros  # correcciones 05-11: rubros desde el panel interno
from app.api.routes import admin_revision  # HU-22: bandeja de revisión del Oficial de Cumplimiento
from app.api.routes import admin_retencion  # HU-25: retención de usuarios temporales vencidos
from app.api.routes import mapa_datos  # HU-34: mapa de datos personales (base del RAT y del RoPA)
from app.api.routes import registro_actividades  # HU-35: registro de actividades de tratamiento (RAT)
from app.api.routes import informe_rat  # HU-36: informe del RAT (PDF y XLSX)
from app.api.routes import informe_ropa  # HU-37: informe RoPA desde el registro (PDF y XLSX)
from app.api.routes import asistente_registro_rat  # HU-39: asistente de IA para el mapa de datos y el RAT
from app.api.routes import admin_privacidad  # HU-41: registro de tratamiento de la propia plataforma
from app.api.routes import revision_interna  # HU-40: revisión interna del registro (auditoría interna)

# Orden de registro idéntico al que tenía app/main.py: importa para colisiones de rutas.
api_router = APIRouter()
api_router.include_router(respuestas.router)
api_router.include_router(evidencias.router)
api_router.include_router(catalogos.router)
api_router.include_router(controles.router)
api_router.include_router(reportes.router)
api_router.include_router(evaluaciones.router)
api_router.include_router(filtro.router)
api_router.include_router(eventos_seguridad.router)
api_router.include_router(metricas_ia.router)
api_router.include_router(arcop.router)
api_router.include_router(acceso.router)
api_router.include_router(encuesta_publica.router)
api_router.include_router(informes.router)
api_router.include_router(contratacion.router)
api_router.include_router(admin_clientes.router)
api_router.include_router(cliente.router)
api_router.include_router(formacion.router)
api_router.include_router(remediacion.router)
api_router.include_router(conversacion_tutor.router)
api_router.include_router(borradores.router)
api_router.include_router(auditoria.router)
api_router.include_router(auditoria.router_admin)
api_router.include_router(admin_matriz.router)
api_router.include_router(admin_rubros.router)
api_router.include_router(admin_revision.router)
api_router.include_router(admin_retencion.router)
api_router.include_router(mapa_datos.router)
api_router.include_router(registro_actividades.router)
api_router.include_router(informe_rat.router)
api_router.include_router(revision_interna.router)
api_router.include_router(informe_ropa.router)
api_router.include_router(asistente_registro_rat.router)
api_router.include_router(admin_privacidad.router)

__all__ = ["api_router"]

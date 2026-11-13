"""
HU-09 · audit_log (nació como la bitácora mínima de HU-27).

`registrar()` solo agrega la fila a la sesión: la confirma el commit de la acción de
negocio que se está auditando (misma transacción). Para un intento rechazado, el caso
de uso registra y hace commit él mismo antes de responder el error.

Campos obligatorios de cada registro (criterio 2): fecha, actor (rol + id, o "sistema"),
IP, acción y resultado. La IP la toma sola de la petición en curso
(app/core/contexto_auditoria.py); fuera de una petición queda "sistema:worker"/"sistema:cli".
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.autenticacion import Actor
from app.core.contexto_auditoria import ip_actual, normalizar_ip
from app.domain.models.bitacora_auditoria import RESULTADO_OK, RESULTADOS, ROLES_SIN_ID, BitacoraAuditoria
from app.infrastructure.repositories import bitacora_cadena  # noqa: F401  HU-18: instala la cadena de hashes

# Actor "sistema" (sin token): p. ej. quien abre un enlace de activación.
ROL_SISTEMA = "sistema"
ROL_ANONIMO = "anonimo"


class Accion:
    """Acciones auditadas. HU-09 puede agregar más; no cambiar las existentes."""
    SOLICITUD_CONTRATACION_CREADA = "solicitud_contratacion.creada"
    SOLICITUD_CONTRATACION_ESTADO = "solicitud_contratacion.estado_cambiado"
    SOLICITUD_CONTRATACION_AVISO = "solicitud_contratacion.aviso_comercial"  # HU-31
    EMPRESA_CREADA = "empresa.creada"
    USUARIO_DEFINITIVO_CREADO = "usuario_definitivo.creado"
    EVALUACION_MIGRADA = "evaluacion.migrada_a_empresa"
    USUARIO_TEMPORAL_CERRADO = "usuario_temporal.cerrado_por_migracion"
    ACTIVACION_EMITIDA = "activacion.enlace_emitido"
    ACTIVACION_CORREO = "activacion.correo"
    ACTIVACION_USADA = "activacion.cuenta_activada"
    ACTIVACION_RECHAZADA = "activacion.rechazada"
    CLIENTE_LOGIN = "cliente.inicio_sesion"
    # HU-28: inicio y cierre de sesión (admin y cliente) y recuperación de contraseña.
    # Inicio exitoso del cliente: CLIENTE_LOGIN (HU-27); del admin: ADMIN_LOGIN.
    ADMIN_LOGIN = "admin.inicio_sesion"
    LOGIN_FALLIDO = "sesion.inicio_fallido"          # credenciales, contrato no vigente...
    LOGIN_BLOQUEADO = "sesion.inicio_bloqueado"      # rechazado por exceso de intentos fallidos
    SESION_CERRADA = "sesion.cierre"
    RECUPERACION_SOLICITADA = "recuperacion.solicitada"
    RECUPERACION_USADA = "recuperacion.contrasena_restablecida"
    RECUPERACION_RECHAZADA = "recuperacion.rechazada"
    # HU-26: recorrido de módulos formativos de la empresa cliente
    FORMACION_MODULO_INICIADO = "formacion.modulo_iniciado"
    FORMACION_VERIFICACION = "formacion.verificacion_intento"
    FORMACION_MODULO_COMPLETADO = "formacion.modulo_completado"
    FORMACION_CONSTANCIA = "formacion.constancia_descargada"
    # HU-17: re-evaluación de un control con evidencia nueva (remediación)
    REMEDIACION_EVIDENCIA_SUBIDA = "remediacion.evidencia_subida"
    REMEDIACION_RESULTADO = "remediacion.resultado"
    # HU-30: vigencia del contrato (detalle: estado/situación/fechas antes y después y el motivo)
    CONTRATO_RENOVADO = "contrato.renovado"
    CONTRATO_SUSPENDIDO = "contrato.suspendido"
    CONTRATO_REACTIVADO = "contrato.reactivado"
    CONTRATO_TERMINADO = "contrato.terminado"
    # HU-15: Agente IA Tutor (el detalle nunca lleva el texto de los mensajes)
    TUTOR_CONVERSACION_CREADA = "tutor.conversacion_creada"
    TUTOR_MENSAJE = "tutor.mensaje"
    TUTOR_MENSAJE_BLOQUEADO = "tutor.mensaje_bloqueado"
    TUTOR_NIVEL_CAMBIADO = "tutor.nivel_cambiado"
    TUTOR_CONVERSACION_ELIMINADA = "tutor.conversacion_eliminada"
    # HU-18: gobernanza del agente
    TUTOR_SALIDA_BLOQUEADA = "tutor.salida_bloqueada"      # la respuesta filtró el system prompt
    TUTOR_ADVERTENCIA_ABUSO = "tutor.advertencia_abuso"    # bloqueos reiterados de la misma empresa
    # HU-16: borradores de cumplimiento (el detalle nunca lleva el texto del borrador ni las
    # instrucciones: solo el tipo, la versión, conteos y la huella HMAC de las instrucciones)
    BORRADOR_GENERADO = "borrador.generado"
    BORRADOR_EDITADO = "borrador.editado"
    BORRADOR_DESCARGADO = "borrador.descargado"            # descarga previa (Markdown o PDF)
    BORRADOR_CONSOLIDADO = "borrador.consolidado"          # PDF guardado en "Mis documentos"
    BORRADOR_DESCARTADO = "borrador.descartado"
    BORRADOR_INSTRUCCIONES_BLOQUEADAS = "borrador.instrucciones_bloqueadas"  # ataque en las instrucciones
    # HU-29: historial, reevaluación y "Mis documentos" del usuario definitivo
    EVALUACION_REEVALUACION_INICIADA = "evaluacion.reevaluacion_iniciada"
    EVALUACION_COMPLETADA_EMPRESA = "evaluacion.completada_empresa"   # reevaluación completada
    DOCUMENTO_GENERADO = "documento.generado"      # informe PDF archivado (o borrador HU-16)
    DOCUMENTO_DESCARGADO = "documento.descargado"  # informe, borrador o evidencia
    DOCUMENTO_ELIMINADO = "documento.eliminado"    # informe, borrador, evidencia o constancia
    # HU-09: modificaciones y supresiones de datos que faltaban en el log
    RESPUESTA_MODIFICADA = "respuesta.modificada"            # cambió la declaración (estado/justificación)
    RESPUESTA_REVISADA = "respuesta.revision_humana"         # el admin fijó la clasificación final
    # HU-22: el Oficial de Cumplimiento resolvió un evento de seguridad (ataque o falso positivo)
    EVENTO_SEGURIDAD_REVISADO = "seguridad.evento_revisado"
    EVALUACION_PRUEBA = "evaluacion.marcada_prueba"          # entra o sale del benchmark
    ENCUESTADO_CLAVE_GENERADA = "encuestado.clave_generada"  # el admin regeneró la clave de acceso
    EVIDENCIA_ORIGINAL_SUPRIMIDO = "evidencia.original_suprimido"  # HU-06: queda solo el texto anonimizado
    ARCOP_SOLICITUD_CREADA = "arcop.solicitud_creada"
    ARCOP_ESTADO = "arcop.estado_cambiado"
    ARCOP_INFORMACION = "arcop.informacion_aportada"
    ARCOP_PRORROGA = "arcop.plazo_prorrogado"
    ARCOP_RESOLUCION = "arcop.solicitud_resuelta"            # detalle.resultado: resuelta | rechazada
    ARCOP_CANCELADA = "arcop.solicitud_cancelada"
    ARCOP_SUPRESION = "arcop.datos_suprimidos"               # supresión aprobada: datos del titular anonimizados
    RETENCION_TITULAR = "retencion.titular_anonimizado"      # T-06 R1
    RETENCION_ARCOP = "retencion.arcop_anonimizada"          # T-06 R2
    RETENCION_EVENTOS = "retencion.extractos_eliminados"     # T-06 R3
    RETENCION_TUTOR = "retencion.conversaciones_eliminadas"  # T-06 R4
    # HU-25: cada ejecución de la retención (cron, manual o CLI, también la simulación y la
    # omitida por otra en curso) deja UN registro con plazos, conteos y duración; y cada
    # cambio del plazo desde el panel, el valor anterior y el nuevo.
    RETENCION_EJECUCION = "retencion.ejecucion"
    RETENCION_CONFIGURACION = "retencion.configuracion_cambiada"
    # HU-09: Auditor Externo
    AUDITOR_CREADO = "auditor.cuenta_creada"
    AUDITOR_ACTUALIZADO = "auditor.cuenta_actualizada"       # vigencia, desactivación o contraseña
    AUDITOR_LOGIN = "auditor.inicio_sesion"
    AUDITORIA_CONSULTA = "auditoria.consulta"
    AUDITORIA_VERIFICACION = "auditoria.verificacion"
    AUDITORIA_EXPORTACION = "auditoria.exportacion"
    # HU-24: mantenedor de la matriz normativa. El detalle lleva qué elemento cambió y los
    # campos con su valor anterior y nuevo (recortados); el contenido completo de cada
    # versión publicada queda en matriz_version y no cambia nunca.
    MATRIZ_BORRADOR_CREADO = "matriz.borrador_creado"
    MATRIZ_BORRADOR_EDITADO = "matriz.borrador_editado"       # crear, modificar, retirar, restaurar, reglas
    MATRIZ_BORRADOR_DESCARTADO = "matriz.borrador_descartado"
    MATRIZ_PUBLICADA = "matriz.version_publicada"             # detalle: etiqueta, huella y conteo de cambios
    MATRIZ_PUBLICACION_RECHAZADA = "matriz.publicacion_rechazada"  # errores de validación o sin cambios
    # Correcciones 05-11: rubros desde el panel interno (detalle: el nombre del rubro)
    RUBRO_CREADO = "rubro.creado"
    RUBRO_RENOMBRADO = "rubro.renombrado"
    # HU-34: mapa de datos personales del cliente. Cada cambio deja además una versión completa
    # en mapa_datos_version; el detalle aquí solo lleva ids, tipos, campos cambiados y conteos
    # (nunca los nombres ni los textos que escribe la empresa).
    MAPA_ELEMENTO_CREADO = "mapa_datos.elemento_creado"
    MAPA_ELEMENTO_EDITADO = "mapa_datos.elemento_editado"
    MAPA_ELEMENTO_ELIMINADO = "mapa_datos.elemento_eliminado"
    MAPA_FLUJO_CREADO = "mapa_datos.flujo_creado"
    MAPA_FLUJO_EDITADO = "mapa_datos.flujo_editado"
    MAPA_FLUJO_ELIMINADO = "mapa_datos.flujo_eliminado"
    MAPA_PLANTILLA_APLICADA = "mapa_datos.plantilla_aplicada"
    MAPA_SUGERENCIA_ACEPTADA = "mapa_datos.sugerencia_aceptada"
    MAPA_SUGERENCIA_DESCARTADA = "mapa_datos.sugerencia_descartada"
    MAPA_REVISION_CONFIRMADA = "mapa_datos.revision_confirmada"
    MAPA_VERSION_RESTAURADA = "mapa_datos.version_restaurada"
    MAPA_CAMBIO_RECHAZADO = "mapa_datos.cambio_rechazado"     # versión desactualizada o límite
    MAPA_INFORME_DESCARGADO = "mapa_datos.informe_descargado"
    MAPA_INFORME_ENVIADO = "mapa_datos.informe_enviado"
    # HU-35: registro de actividades de tratamiento (RAT). Cada vez que una actividad queda vigente
    # se guarda además una versión inmutable en rat_actividad_version; el detalle aquí solo lleva ids,
    # estados, códigos de campos y conteos (nunca los textos que escribe la empresa).
    RAT_ACTIVIDAD_CREADA = "rat.actividad_creada"
    RAT_ACTIVIDAD_EDITADA = "rat.actividad_editada"
    RAT_ESTADO_CAMBIADO = "rat.estado_cambiado"           # detalle: accion, desde, hacia
    RAT_VERSION_VIGENTE = "rat.version_vigente"           # detalle: numero, huella (prefijo), campos cambiados
    RAT_MARCADA_REVISION = "rat.marcada_revision"         # un cambio en el mapa la devolvió a revisión
    RAT_CAMBIO_RECHAZADO = "rat.cambio_rechazado"         # versión desactualizada, incompleta o transición inválida
    # HU-36: informe del RAT (PDF y XLSX). El detalle lleva el id de la emisión, la versión del RAT, si es
    # borrador, el formato y conteos; nunca los textos del registro ni el correo de destino.
    RAT_INFORME_GENERADO = "rat.informe_generado"
    RAT_INFORME_DESCARGADO = "rat.informe_descargado"
    RAT_INFORME_ENVIADO = "rat.informe_enviado"
    RAT_INFORME_VERIFICADO = "rat.informe_verificado"
    # HU-37: informe RoPA. El detalle lleva ids, versión, partes, nombres de campos y conteos; nunca las
    # direcciones, correos ni teléfonos que la empresa informa para el RoPA.
    ROPA_DATOS_ACTUALIZADOS = "ropa.datos_actualizados"   # detalle: campos cambiados, organizaciones
    ROPA_INFORME_GENERADO = "ropa.informe_generado"
    ROPA_INFORME_DESCARGADO = "ropa.informe_descargado"
    # HU-39: asistente de IA para el mapa de datos y el RAT (sin texto: huellas, códigos y conteos)
    ASISTENTE_SESION_CREADA = "asistente.sesion_creada"
    ASISTENTE_RESPUESTA = "asistente.respuesta"                     # detalle: area, propuestas, motivo_sin_ia
    ASISTENTE_RESPUESTA_BLOQUEADA = "asistente.respuesta_bloqueada"  # filtro de entrada (HU-18)
    ASISTENTE_SALIDA_BLOQUEADA = "asistente.salida_bloqueada"        # la salida filtró el system prompt
    ASISTENTE_DOCUMENTO_ANALIZADO = "asistente.documento_analizado"  # detalle: tipo, estado, regla
    ASISTENTE_PROPUESTA_ACEPTADA = "asistente.propuesta_aceptada"
    ASISTENTE_PROPUESTA_EDITADA = "asistente.propuesta_editada"      # aceptada con cambios del usuario
    ASISTENTE_PROPUESTA_DESCARTADA = "asistente.propuesta_descartada"
    # HU-41: registro de tratamiento de la propia plataforma (RAT y RoPA de ComplianceAI). El detalle lleva
    # el tipo, la versión, si es oficial, conteos y prefijos de huellas; nunca los datos de contacto del RoPA.
    PLATAFORMA_INFORME_GENERADO = "plataforma.informe_generado"
    PLATAFORMA_INFORME_DESCARGADO = "plataforma.informe_descargado"
    PLATAFORMA_INFORME_VERIFICADO = "plataforma.informe_verificado"
    PLATAFORMA_MAPA_DESCARGADO = "plataforma.mapa_descargado"
    PLATAFORMA_ROPA_DATOS_ACTUALIZADOS = "plataforma.ropa_datos_actualizados"   # detalle: campos cambiados


# HU-09: categoría de cada acción, para que el Auditor Externo filtre el historial de
# MODIFICACIONES y SUPRESIONES (art. 14 ter). Se calcula al leer: no se guarda.
class Categoria:
    MODIFICACION = "modificacion"
    SUPRESION = "supresion"
    CREACION = "creacion"
    ACCESO = "acceso"
    SEGURIDAD = "seguridad"
    AUDITORIA = "auditoria"

    @classmethod
    def valores(cls) -> list[str]:
        return [cls.MODIFICACION, cls.SUPRESION, cls.CREACION, cls.ACCESO, cls.SEGURIDAD, cls.AUDITORIA]


_CATEGORIAS: dict[str, str] = {
    # supresiones (borrado o anonimización de datos)
    Accion.ARCOP_SUPRESION: Categoria.SUPRESION,
    Accion.RETENCION_TITULAR: Categoria.SUPRESION,
    Accion.RETENCION_ARCOP: Categoria.SUPRESION,
    Accion.RETENCION_EVENTOS: Categoria.SUPRESION,
    Accion.RETENCION_TUTOR: Categoria.SUPRESION,
    Accion.RETENCION_EJECUCION: Categoria.SUPRESION,         # HU-25: el resumen de cada corrida
    Accion.DOCUMENTO_ELIMINADO: Categoria.SUPRESION,
    Accion.TUTOR_CONVERSACION_ELIMINADA: Categoria.SUPRESION,
    Accion.BORRADOR_DESCARTADO: Categoria.SUPRESION,
    Accion.EVIDENCIA_ORIGINAL_SUPRIMIDO: Categoria.SUPRESION,
    Accion.USUARIO_TEMPORAL_CERRADO: Categoria.SUPRESION,  # se anonimiza al migrar (HU-27)
    Accion.MATRIZ_BORRADOR_DESCARTADO: Categoria.SUPRESION,  # HU-24
    Accion.MAPA_ELEMENTO_ELIMINADO: Categoria.SUPRESION,     # HU-34
    Accion.MAPA_FLUJO_ELIMINADO: Categoria.SUPRESION,
    # modificaciones
    Accion.RESPUESTA_MODIFICADA: Categoria.MODIFICACION,
    Accion.RESPUESTA_REVISADA: Categoria.MODIFICACION,
    Accion.EVENTO_SEGURIDAD_REVISADO: Categoria.MODIFICACION,   # HU-22
    Accion.EVALUACION_PRUEBA: Categoria.MODIFICACION,
    Accion.ENCUESTADO_CLAVE_GENERADA: Categoria.MODIFICACION,
    Accion.ARCOP_ESTADO: Categoria.MODIFICACION,
    Accion.ARCOP_INFORMACION: Categoria.MODIFICACION,
    Accion.ARCOP_PRORROGA: Categoria.MODIFICACION,
    Accion.ARCOP_RESOLUCION: Categoria.MODIFICACION,
    Accion.ARCOP_CANCELADA: Categoria.MODIFICACION,
    Accion.SOLICITUD_CONTRATACION_ESTADO: Categoria.MODIFICACION,
    Accion.EVALUACION_MIGRADA: Categoria.MODIFICACION,
    Accion.EVALUACION_COMPLETADA_EMPRESA: Categoria.MODIFICACION,
    Accion.ACTIVACION_USADA: Categoria.MODIFICACION,
    Accion.RECUPERACION_USADA: Categoria.MODIFICACION,
    Accion.REMEDIACION_RESULTADO: Categoria.MODIFICACION,
    Accion.FORMACION_MODULO_COMPLETADO: Categoria.MODIFICACION,
    Accion.CONTRATO_RENOVADO: Categoria.MODIFICACION,
    Accion.CONTRATO_SUSPENDIDO: Categoria.MODIFICACION,
    Accion.CONTRATO_REACTIVADO: Categoria.MODIFICACION,
    Accion.CONTRATO_TERMINADO: Categoria.MODIFICACION,
    Accion.TUTOR_NIVEL_CAMBIADO: Categoria.MODIFICACION,
    Accion.BORRADOR_EDITADO: Categoria.MODIFICACION,
    Accion.BORRADOR_CONSOLIDADO: Categoria.MODIFICACION,
    Accion.AUDITOR_ACTUALIZADO: Categoria.MODIFICACION,
    Accion.MATRIZ_BORRADOR_EDITADO: Categoria.MODIFICACION,      # HU-24
    Accion.MATRIZ_PUBLICADA: Categoria.MODIFICACION,
    Accion.MATRIZ_PUBLICACION_RECHAZADA: Categoria.MODIFICACION,
    Accion.RUBRO_RENOMBRADO: Categoria.MODIFICACION,             # correcciones 05-11
    Accion.RETENCION_CONFIGURACION: Categoria.MODIFICACION,      # HU-25
    Accion.MAPA_ELEMENTO_EDITADO: Categoria.MODIFICACION,        # HU-34
    Accion.MAPA_FLUJO_EDITADO: Categoria.MODIFICACION,
    Accion.MAPA_REVISION_CONFIRMADA: Categoria.MODIFICACION,
    Accion.MAPA_VERSION_RESTAURADA: Categoria.MODIFICACION,
    Accion.MAPA_SUGERENCIA_DESCARTADA: Categoria.MODIFICACION,
    Accion.MAPA_CAMBIO_RECHAZADO: Categoria.MODIFICACION,
    Accion.RAT_ACTIVIDAD_EDITADA: Categoria.MODIFICACION,        # HU-35
    Accion.RAT_ESTADO_CAMBIADO: Categoria.MODIFICACION,
    Accion.RAT_VERSION_VIGENTE: Categoria.MODIFICACION,
    Accion.RAT_MARCADA_REVISION: Categoria.MODIFICACION,
    Accion.RAT_CAMBIO_RECHAZADO: Categoria.MODIFICACION,
    Accion.ROPA_DATOS_ACTUALIZADOS: Categoria.MODIFICACION,      # HU-37
    Accion.ASISTENTE_PROPUESTA_DESCARTADA: Categoria.MODIFICACION,  # HU-39
    Accion.PLATAFORMA_ROPA_DATOS_ACTUALIZADOS: Categoria.MODIFICACION,  # HU-41
    # creaciones
    Accion.SOLICITUD_CONTRATACION_CREADA: Categoria.CREACION,
    Accion.EMPRESA_CREADA: Categoria.CREACION,
    Accion.USUARIO_DEFINITIVO_CREADO: Categoria.CREACION,
    Accion.ACTIVACION_EMITIDA: Categoria.CREACION,
    Accion.RECUPERACION_SOLICITADA: Categoria.CREACION,
    Accion.ARCOP_SOLICITUD_CREADA: Categoria.CREACION,
    Accion.REMEDIACION_EVIDENCIA_SUBIDA: Categoria.CREACION,
    Accion.EVALUACION_REEVALUACION_INICIADA: Categoria.CREACION,
    Accion.DOCUMENTO_GENERADO: Categoria.CREACION,
    Accion.TUTOR_CONVERSACION_CREADA: Categoria.CREACION,
    Accion.BORRADOR_GENERADO: Categoria.CREACION,
    Accion.FORMACION_MODULO_INICIADO: Categoria.CREACION,
    Accion.AUDITOR_CREADO: Categoria.CREACION,
    Accion.MATRIZ_BORRADOR_CREADO: Categoria.CREACION,           # HU-24
    Accion.RUBRO_CREADO: Categoria.CREACION,                     # correcciones 05-11
    Accion.MAPA_ELEMENTO_CREADO: Categoria.CREACION,             # HU-34
    Accion.MAPA_FLUJO_CREADO: Categoria.CREACION,
    Accion.MAPA_PLANTILLA_APLICADA: Categoria.CREACION,
    Accion.MAPA_SUGERENCIA_ACEPTADA: Categoria.CREACION,
    Accion.RAT_ACTIVIDAD_CREADA: Categoria.CREACION,             # HU-35
    Accion.RAT_INFORME_GENERADO: Categoria.CREACION,             # HU-36 (descargas y envíos: acceso)
    Accion.ROPA_INFORME_GENERADO: Categoria.CREACION,            # HU-37 (descargas: acceso)
    Accion.ASISTENTE_SESION_CREADA: Categoria.CREACION,          # HU-39
    Accion.ASISTENTE_PROPUESTA_ACEPTADA: Categoria.CREACION,
    Accion.ASISTENTE_PROPUESTA_EDITADA: Categoria.CREACION,
    Accion.PLATAFORMA_INFORME_GENERADO: Categoria.CREACION,      # HU-41 (descargas y verificaciones: acceso)
    # seguridad
    Accion.LOGIN_FALLIDO: Categoria.SEGURIDAD,
    Accion.LOGIN_BLOQUEADO: Categoria.SEGURIDAD,
    Accion.ACTIVACION_RECHAZADA: Categoria.SEGURIDAD,
    Accion.RECUPERACION_RECHAZADA: Categoria.SEGURIDAD,
    Accion.TUTOR_MENSAJE_BLOQUEADO: Categoria.SEGURIDAD,
    Accion.TUTOR_SALIDA_BLOQUEADA: Categoria.SEGURIDAD,
    Accion.TUTOR_ADVERTENCIA_ABUSO: Categoria.SEGURIDAD,
    Accion.BORRADOR_INSTRUCCIONES_BLOQUEADAS: Categoria.SEGURIDAD,
    Accion.ASISTENTE_RESPUESTA_BLOQUEADA: Categoria.SEGURIDAD,   # HU-39
    Accion.ASISTENTE_SALIDA_BLOQUEADA: Categoria.SEGURIDAD,
    # actividad del propio log
    Accion.AUDITORIA_CONSULTA: Categoria.AUDITORIA,
    Accion.AUDITORIA_VERIFICACION: Categoria.AUDITORIA,
    Accion.AUDITORIA_EXPORTACION: Categoria.AUDITORIA,
}


def categoria(accion: str) -> str:
    """Categoría de una acción. Lo no clasificado (inicios de sesión, descargas, mensajes) es acceso."""
    return _CATEGORIAS.get(accion, Categoria.ACCESO)


def acciones_conocidas() -> list[str]:
    return sorted(v for k, v in vars(Accion).items() if k.isupper() and isinstance(v, str))


def acciones_de_categoria(nombre: str) -> list[str]:
    if nombre not in Categoria.valores():
        raise ValueError(f"Categoría inválida. Debe ser una de: {', '.join(Categoria.valores())}")
    return [a for a in acciones_conocidas() if categoria(a) == nombre]


# Claves que nunca pueden ir en `detalle` (datos personales o secretos).
_CLAVES_PROHIBIDAS = frozenset({
    "email", "correo", "nombre", "telefono", "password", "contrasena", "clave", "token", "rut_persona",
})


def _validar_detalle(valor, ruta: str = "detalle") -> None:
    if isinstance(valor, dict):
        for k, v in valor.items():
            if str(k).lower() in _CLAVES_PROHIBIDAS:
                raise ValueError(f"La bitácora no admite '{k}' en {ruta}: no guarda datos personales ni secretos.")
            _validar_detalle(v, f"{ruta}.{k}")
    elif isinstance(valor, (list, tuple)):
        for i, v in enumerate(valor):
            _validar_detalle(v, f"{ruta}[{i}]")
    elif isinstance(valor, str) and "@" in valor:
        raise ValueError(f"La bitácora no admite correos en {ruta}.")


def _ahora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class BitacoraRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    def registrar(self, *, accion: str, entidad: str, entidad_id: int | None = None,
                  actor: Actor | None = None, actor_rol: str | None = None, actor_id: int | None = None,
                  detalle: dict | None = None, resultado: str = RESULTADO_OK,
                  fecha: datetime | None = None, ip: str | None = None) -> BitacoraAuditoria:
        if detalle is not None:
            _validar_detalle(detalle)
        # HU-09 criterio 2: los campos obligatorios se validan aquí (y en PostgreSQL con CHECK)
        if not accion or not entidad:
            raise ValueError("audit_log: la acción y la entidad son obligatorias.")
        if resultado not in RESULTADOS:
            raise ValueError(f"audit_log: resultado inválido ({resultado}); debe ser uno de {', '.join(RESULTADOS)}.")
        rol = actor.rol if actor else (actor_rol or ROL_ANONIMO)
        uid = actor.id if actor else actor_id
        if uid is None and rol not in ROLES_SIN_ID:
            raise ValueError(f"audit_log: el actor '{rol}' debe llevar su id (solo anonimo y sistema van sin id).")
        fila = BitacoraAuditoria(
            fecha=fecha or _ahora(),
            actor_rol=rol,
            actor_id=uid,
            accion=accion,
            entidad=entidad,
            entidad_id=entidad_id,
            resultado=resultado,
            detalle=detalle,
            ip=normalizar_ip(ip) if ip else ip_actual(),
        )
        self.session.add(fila)
        return fila

    async def listar(self, *, entidad: str | None = None, entidad_id: int | None = None,
                     accion: str | None = None, page: int = 1, size: int = 50,
                     desde: datetime | None = None, hasta: datetime | None = None,
                     categoria: str | None = None, resultado: str | None = None,
                     actor_rol: str | None = None) -> tuple[list[BitacoraAuditoria], int]:
        filtros = []
        if entidad:
            filtros.append(BitacoraAuditoria.entidad == entidad)
        if entidad_id is not None:
            filtros.append(BitacoraAuditoria.entidad_id == entidad_id)
        if accion:
            filtros.append(BitacoraAuditoria.accion == accion)
        # HU-09: filtros del Auditor Externo
        if desde is not None:
            filtros.append(BitacoraAuditoria.fecha >= desde)
        if hasta is not None:
            filtros.append(BitacoraAuditoria.fecha < hasta)
        if categoria:
            filtros.append(BitacoraAuditoria.accion.in_(acciones_de_categoria(categoria)))
        if resultado:
            filtros.append(BitacoraAuditoria.resultado == resultado)
        if actor_rol:
            filtros.append(BitacoraAuditoria.actor_rol == actor_rol)
        total = (await self.session.execute(
            select(func.count()).select_from(BitacoraAuditoria).where(*filtros)
        )).scalar_one()
        filas = (await self.session.execute(
            select(BitacoraAuditoria).where(*filtros)
            .order_by(BitacoraAuditoria.id.desc()).offset((page - 1) * size).limit(size)
        )).scalars().all()
        return list(filas), total

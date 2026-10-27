"""
HU-31: solicitud de contratación desde los resultados, y HU-27: alta de la empresa
cliente y de su usuario definitivo.

Solicitudes de contratación (HU-31)
  - El encuestado (o el referente invitado) la registra desde sus resultados con nombre,
    cargo, empresa, correo y teléfono opcional, y DOS consentimientos separados (contacto
    comercial y traspaso de la evaluación), cada uno con su versión y fecha.
  - Llega a la bandeja del admin como 'nueva'; el admin la pasa a 'contactada',
    'contratada' o 'descartada'. Solo 'contratada' habilita la migración (HU-27).

Alta (criterios 1, 2 y 3), en UNA transacción:
  empresa -> usuario definitivo (rol único 'cliente', sin contraseña) -> migración de las
  evaluaciones autorizadas (migrar_evaluacion.py) -> enlace de activación -> bitácora.
  Si algo falla no queda nada a medias. El correo con el enlace se envía DESPUÉS del
  commit: si falla, la empresa queda creada y el admin reenvía el enlace.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.informes import correo
from app.application.use_cases.activacion_cuenta import (
    ResultadoCorreo, emitir_token, enviar_correo_activacion,
)
from app.application.use_cases import consentimientos_contratacion
from app.application.use_cases.migrar_evaluacion import EvaluacionMigrada, MigracionError, MigradorEvaluaciones
from app.core.autenticacion import Actor, Rol
from app.core.config import settings
from app.core.rut import RutInvalidoError, normalizar_rut
from app.domain.models.empresa import Empresa
from app.domain.models.evaluacion import ORIGEN_PUBLICA, Evaluacion
from app.domain.models.rubro import Rubro
from app.domain.models.solicitud_contratacion import EstadoSolicitudContratacion, SolicitudContratacion
from app.domain.models.usuario_definitivo import (
    ROL_CLIENTE, EstadoUsuarioDefinitivo, UsuarioDefinitivo,
)
from app.infrastructure.repositories.bitacora_repository import Accion, BitacoraRepository

E = EstadoSolicitudContratacion

# Transiciones que puede hacer un admin a mano (bandeja HU-31 / HU-28).
# 'migrada' solo la fija la migración (HU-27); 'descartada' y 'migrada' son finales.
# 'contratada' -> 'contactada' corrige un "contratada" marcado por error.
TRANSICIONES = {
    E.NUEVA.value: {E.CONTACTADA.value, E.CONTRATADA.value, E.DESCARTADA.value},
    E.CONTACTADA.value: {E.CONTRATADA.value, E.DESCARTADA.value},
    E.CONTRATADA.value: {E.CONTACTADA.value, E.DESCARTADA.value},
    E.MIGRADA.value: set(),
    E.DESCARTADA.value: set(),
}

_TELEFONO = re.compile(r"^\+?[0-9 ()-]{8,20}$")


@dataclass(frozen=True)
class ConsentimientoDado:
    """Lo que la persona marcó en el formulario: si aceptó y QUÉ versión del texto vio."""
    aceptado: bool
    version: str


class ContratacionError(Exception):
    def __init__(self, mensaje: str, codigo: str, status_code: int, **extra):
        super().__init__(mensaje)
        self.codigo = codigo
        self.status_code = status_code
        self.extra = extra


def _ahora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _texto(valor: str | None, campo: str, minimo: int, maximo: int, obligatorio: bool = True) -> str | None:
    limpio = " ".join((valor or "").split())
    if not limpio:
        if obligatorio:
            raise ContratacionError(f"{campo} es obligatorio.", "DATOS_INVALIDOS", 422, campo=campo)
        return None
    if len(limpio) < minimo or len(limpio) > maximo:
        raise ContratacionError(f"{campo} debe tener entre {minimo} y {maximo} caracteres.",
                                "DATOS_INVALIDOS", 422, campo=campo)
    return limpio


def _email(valor: str | None, campo: str = "email") -> str:
    email = (valor or "").strip().lower()
    if not email or len(email) > 100 or not correo.EMAIL_VALIDO.match(email):
        raise ContratacionError("Revisa el formato del correo (ejemplo: nombre@empresa.cl).",
                                "EMAIL_INVALIDO", 422, campo=campo)
    return email


# ======================================================================= HU-31
class SolicitudesContratacionUseCase:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.bitacora = BitacoraRepository(db)

    async def evaluacion_del_actor(self, actor: Actor, evaluacion_id: int) -> Evaluacion:
        evaluacion = await self.db.get(Evaluacion, evaluacion_id)
        propia = evaluacion is not None and (
            (actor.es_encuestado and actor.id == evaluacion.id)
            or (actor.rol == Rol.REFERENTE.value and evaluacion.usuario_temporal_id == actor.id
                and evaluacion.origen != ORIGEN_PUBLICA)
        )
        if not propia:  # 404 también a lo ajeno: no confirma que el id existe
            raise ContratacionError("Evaluación no encontrada.", "EVALUACION_NO_ENCONTRADA", 404)
        return evaluacion

    async def crear(self, actor: Actor, *, evaluacion_id: int, nombre: str, cargo: str, empresa: str,
                    email: str, telefono: str | None, consentimiento_contacto: ConsentimientoDado,
                    consentimiento_migracion: ConsentimientoDado) -> SolicitudContratacion:
        """
        Registra la solicitud (criterios 1 y 2). NO envía el aviso a Therion: lo hace quien
        llama, después del commit (aviso_contratacion.avisar_nueva_solicitud), para que un
        correo caído no deje sin registrar la solicitud.
        """
        evaluacion = await self.evaluacion_del_actor(actor, evaluacion_id)
        if not evaluacion.esta_cerrada:
            raise ContratacionError("Termina tu evaluación antes de solicitar la contratación.",
                                    "EVALUACION_NO_COMPLETADA", 409)
        if evaluacion.empresa_id is not None:
            raise ContratacionError("Esta evaluación ya pertenece a una empresa cliente.", "EVALUACION_YA_MIGRADA", 409)
        if await self.db.scalar(select(SolicitudContratacion.id).where(
                SolicitudContratacion.evaluacion_id == evaluacion_id)) is not None:
            raise ContratacionError("Ya enviaste una solicitud para esta evaluación. Therion Labs te contactará.",
                                    "SOLICITUD_EXISTENTE", 409)

        # Criterio 2: dos consentimientos separados, cada uno aceptado con la versión vigente
        textos = consentimientos_contratacion.vigentes()
        for clave, dado in ((consentimientos_contratacion.CONTACTO, consentimiento_contacto),
                            (consentimientos_contratacion.MIGRACION, consentimiento_migracion)):
            if not dado.aceptado:
                raise ContratacionError(
                    "Para enviar la solicitud debes aceptar las dos autorizaciones.",
                    "CONSENTIMIENTO_REQUERIDO", 422, consentimiento=clave)
            if dado.version != textos[clave].version:
                raise ContratacionError(
                    "El texto de una autorización cambió. Léelo de nuevo y acéptalo para continuar.",
                    "CONSENTIMIENTO_DESACTUALIZADO", 409, consentimiento=clave,
                    version_vigente=textos[clave].version)

        tel = " ".join((telefono or "").split()) or None
        if tel and not _TELEFONO.match(tel):
            raise ContratacionError("Revisa el teléfono: usa solo números, espacios o +, por ejemplo +56 9 1234 5678.",
                                    "DATOS_INVALIDOS", 422, campo="telefono")
        datos = {
            "nombre_contacto": _texto(nombre, "nombre", 2, 120),
            "cargo_contacto": _texto(cargo, "cargo", 2, 80),
            "razon_social_declarada": _texto(empresa, "empresa", 2, 150),
            "email_contacto": _email(email),
        }
        ahora = _ahora()
        solicitud = SolicitudContratacion(
            evaluacion_id=evaluacion_id,
            telefono_contacto=tel,
            consentimiento_contacto_version=consentimiento_contacto.version,
            fecha_consentimiento_contacto=ahora,
            autoriza_migracion=True,
            consentimiento_version=consentimiento_migracion.version,
            fecha_autorizacion=ahora,
            estado=E.NUEVA.value,
            fecha_creacion=ahora,
            **datos,
        )
        self.db.add(solicitud)
        try:
            await self.db.flush()
        except IntegrityError:  # doble clic: otra petición registró la misma evaluación a la vez
            await self.db.rollback()
            raise ContratacionError("Ya enviaste una solicitud para esta evaluación. Therion Labs te contactará.",
                                    "SOLICITUD_EXISTENTE", 409)
        self.bitacora.registrar(
            accion=Accion.SOLICITUD_CONTRATACION_CREADA, entidad="solicitud_contratacion",
            entidad_id=solicitud.id, actor=actor, fecha=ahora,
            detalle={"evaluacion_id": evaluacion_id, "autoriza_migracion": True,
                     "consentimiento_contacto_version": consentimiento_contacto.version,
                     "consentimiento_migracion_version": consentimiento_migracion.version},
        )
        await self.db.commit()
        return solicitud

    async def conteo_por_estado(self) -> dict[str, int]:
        """Para las pestañas de la bandeja (HU-31 criterio 3 / HU-28)."""
        filas = (await self.db.execute(
            select(SolicitudContratacion.estado, func.count()).group_by(SolicitudContratacion.estado))).all()
        conteo = {e: 0 for e in E.valores()}
        conteo.update({estado: n for estado, n in filas})
        return conteo

    async def listar(self, estado: str | None, page: int, size: int) -> tuple[list[SolicitudContratacion], int]:
        filtros = []
        if estado:
            if estado not in E.valores():
                raise ContratacionError(f"Estado inválido. Usa: {', '.join(E.valores())}", "ESTADO_INVALIDO", 422)
            filtros.append(SolicitudContratacion.estado == estado)
        total = (await self.db.execute(
            select(func.count()).select_from(SolicitudContratacion).where(*filtros))).scalar_one()
        filas = (await self.db.execute(
            select(SolicitudContratacion).where(*filtros)
            .order_by(SolicitudContratacion.id.desc()).offset((page - 1) * size).limit(size)
        )).scalars().all()
        return list(filas), total

    async def obtener(self, solicitud_id: int) -> SolicitudContratacion:
        solicitud = await self.db.get(SolicitudContratacion, solicitud_id)
        if solicitud is None:
            raise ContratacionError("Solicitud no encontrada.", "SOLICITUD_NO_ENCONTRADA", 404)
        return solicitud

    async def cambiar_estado(self, actor: Actor, solicitud_id: int, estado: str) -> SolicitudContratacion:
        solicitud = await self.obtener(solicitud_id)
        anterior = solicitud.estado
        if estado not in TRANSICIONES.get(anterior, set()):
            raise ContratacionError(f"No se puede pasar de '{anterior}' a '{estado}'.", "TRANSICION_INVALIDA", 409,
                                    estado_actual=anterior)
        ahora = _ahora()
        solicitud.estado = estado
        solicitud.fecha_actualizacion = ahora
        if estado == E.DESCARTADA.value:
            # Sin contrato no hay finalidad para conservar el contacto (minimización)
            solicitud.nombre_contacto = solicitud.cargo_contacto = None
            solicitud.email_contacto = solicitud.telefono_contacto = None
        self.bitacora.registrar(
            accion=Accion.SOLICITUD_CONTRATACION_ESTADO, entidad="solicitud_contratacion",
            entidad_id=solicitud.id, actor=actor, fecha=ahora,
            detalle={"estado_anterior": anterior, "estado_nuevo": estado},
        )
        await self.db.commit()
        return solicitud


# ======================================================================= HU-27
@dataclass(frozen=True)
class DatosEmpresa:
    razon_social: str
    rut: str
    rubro_id: int
    fecha_inicio_contrato: date
    fecha_termino_contrato: date


@dataclass(frozen=True)
class DatosUsuario:
    nombre: str
    email: str


@dataclass
class ResultadoAlta:
    empresa: Empresa
    usuario: UsuarioDefinitivo
    migradas: list[EvaluacionMigrada] = field(default_factory=list)
    correo: ResultadoCorreo | None = None


class EmpresasClienteUseCase:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.bitacora = BitacoraRepository(db)
        self.migrador = MigradorEvaluaciones(db)

    async def _validar_empresa(self, d: DatosEmpresa, hoy: date) -> tuple[str, str]:
        razon = _texto(d.razon_social, "razon_social", 2, 150)
        try:
            rut = normalizar_rut(d.rut)
        except RutInvalidoError as e:
            raise ContratacionError(str(e), "RUT_INVALIDO", 422, campo="rut")
        if await self.db.get(Rubro, d.rubro_id) is None:
            raise ContratacionError("El rubro elegido no existe.", "RUBRO_INVALIDO", 422, campo="rubro_id")
        if d.fecha_termino_contrato < d.fecha_inicio_contrato:
            raise ContratacionError("La fecha de término del contrato debe ser igual o posterior a la de inicio.",
                                    "FECHAS_CONTRATO_INVALIDAS", 422, campo="fecha_termino_contrato")
        if d.fecha_termino_contrato < hoy:
            raise ContratacionError("El contrato ya terminó: revisa la fecha de término.",
                                    "CONTRATO_VENCIDO", 422, campo="fecha_termino_contrato")
        if await self.db.scalar(select(Empresa.id).where(Empresa.rut == rut)) is not None:
            raise ContratacionError("Ya existe una empresa con ese RUT.", "RUT_DUPLICADO", 409, campo="rut")
        return razon, rut

    async def _validar_usuario(self, u: DatosUsuario) -> tuple[str, str]:
        nombre = _texto(u.nombre, "nombre", 2, 120)
        email = _email(u.email)
        if await self.db.scalar(select(UsuarioDefinitivo.id).where(
                func.lower(UsuarioDefinitivo.email) == email)) is not None:
            raise ContratacionError("Ese correo ya pertenece a otro usuario cliente.", "EMAIL_DUPLICADO", 409,
                                    campo="email")
        return nombre, email

    async def crear(self, actor: Actor, datos: DatosEmpresa, usuario: DatosUsuario,
                    solicitudes_ids: list[int]) -> ResultadoAlta:
        ahora = _ahora()
        hoy = ahora.date()
        try:
            MigradorEvaluaciones.normalizar_ids(solicitudes_ids)  # 422 antes de escribir nada
            razon, rut = await self._validar_empresa(datos, hoy)
            nombre, email = await self._validar_usuario(usuario)

            empresa = Empresa(
                razon_social=razon, rut=rut, rubro_id=datos.rubro_id,
                fecha_inicio_contrato=datos.fecha_inicio_contrato,
                fecha_termino_contrato=datos.fecha_termino_contrato,
                fecha_creacion=ahora, creada_por_admin_id=actor.id if actor.es_admin else None,
            )
            self.db.add(empresa)
            await self.db.flush()
            definitivo = UsuarioDefinitivo(
                empresa_id=empresa.id, nombre=nombre, email=email, password_hash=None,
                rol=ROL_CLIENTE, estado=EstadoUsuarioDefinitivo.PENDIENTE_ACTIVACION.value, fecha_creacion=ahora,
            )
            self.db.add(definitivo)
            await self.db.flush()
            self.bitacora.registrar(
                accion=Accion.EMPRESA_CREADA, entidad="empresa", entidad_id=empresa.id, actor=actor, fecha=ahora,
                detalle={"rubro_id": datos.rubro_id, "fecha_inicio_contrato": datos.fecha_inicio_contrato.isoformat(),
                         "fecha_termino_contrato": datos.fecha_termino_contrato.isoformat()},
            )
            self.bitacora.registrar(
                accion=Accion.USUARIO_DEFINITIVO_CREADO, entidad="usuario_definitivo", entidad_id=definitivo.id,
                actor=actor, fecha=ahora, detalle={"empresa_id": empresa.id, "rol": ROL_CLIENTE},
            )
            migradas = await self.migrador.migrar(empresa, solicitudes_ids, actor, ahora)
            token = await emitir_token(self.db, definitivo, actor, ahora)
            await self.db.commit()
        except (ContratacionError, MigracionError):
            await self.db.rollback()
            raise
        except IntegrityError:
            # Carrera con otro admin (mismo RUT, email o evaluación a la vez)
            await self.db.rollback()
            raise ContratacionError("Otro administrador registró los mismos datos recién. Recarga y revisa.",
                                    "CONFLICTO_CONCURRENTE", 409)

        resultado = ResultadoAlta(empresa=empresa, usuario=definitivo, migradas=migradas)
        resultado.correo = await enviar_correo_activacion(self.db, definitivo, empresa, token, actor)
        return resultado

    async def _empresa_y_usuario(self, empresa_id: int) -> tuple[Empresa, UsuarioDefinitivo]:
        empresa = await self.db.get(Empresa, empresa_id)
        if empresa is None:
            raise ContratacionError("Empresa no encontrada.", "EMPRESA_NO_ENCONTRADA", 404)
        usuario = await self.db.scalar(select(UsuarioDefinitivo).where(UsuarioDefinitivo.empresa_id == empresa_id))
        if usuario is None:  # no debería pasar: se crean juntos
            raise ContratacionError("La empresa no tiene usuario definitivo.", "USUARIO_NO_ENCONTRADO", 404)
        return empresa, usuario

    async def asociar_evaluaciones(self, actor: Actor, empresa_id: int,
                                   solicitudes_ids: list[int]) -> list[EvaluacionMigrada]:
        """Criterio 2 después del alta: asociar más evaluaciones autorizadas a la misma empresa."""
        empresa, _ = await self._empresa_y_usuario(empresa_id)
        try:
            migradas = await self.migrador.migrar(empresa, solicitudes_ids, actor, _ahora())
            await self.db.commit()
        except MigracionError:
            await self.db.rollback()
            raise
        except IntegrityError:
            await self.db.rollback()
            raise ContratacionError("Otro administrador modificó estas solicitudes recién. Recarga y revisa.",
                                    "CONFLICTO_CONCURRENTE", 409)
        return migradas

    async def reenviar_activacion(self, actor: Actor, empresa_id: int) -> ResultadoCorreo:
        empresa, usuario = await self._empresa_y_usuario(empresa_id)
        if usuario.estado != EstadoUsuarioDefinitivo.PENDIENTE_ACTIVACION.value:
            raise ContratacionError("El usuario ya activó su cuenta (o está bloqueado): no se reenvía el enlace.",
                                    "USUARIO_NO_PENDIENTE", 409, estado=usuario.estado)
        token = await emitir_token(self.db, usuario, actor)
        await self.db.commit()
        return await enviar_correo_activacion(self.db, usuario, empresa, token, actor)

    async def listar(self, page: int, size: int) -> tuple[list[tuple[Empresa, UsuarioDefinitivo | None, int]], int]:
        total = (await self.db.execute(select(func.count()).select_from(Empresa))).scalar_one()
        n_evals = (
            select(func.count()).select_from(Evaluacion).where(Evaluacion.empresa_id == Empresa.id)
            .correlate(Empresa).scalar_subquery()
        )
        filas = (await self.db.execute(
            select(Empresa, UsuarioDefinitivo, n_evals)
            .outerjoin(UsuarioDefinitivo, UsuarioDefinitivo.empresa_id == Empresa.id)
            .order_by(Empresa.id.desc()).offset((page - 1) * size).limit(size)
        )).all()
        return [(e, u, n or 0) for e, u, n in filas], total

    async def detalle(self, empresa_id: int) -> tuple[Empresa, UsuarioDefinitivo, list[Evaluacion]]:
        empresa, usuario = await self._empresa_y_usuario(empresa_id)
        evaluaciones = (await self.db.execute(
            select(Evaluacion).where(Evaluacion.empresa_id == empresa_id).order_by(Evaluacion.id)
        )).scalars().all()
        return empresa, usuario, list(evaluaciones)

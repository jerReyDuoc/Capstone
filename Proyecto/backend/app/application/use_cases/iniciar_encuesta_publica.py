"""
HU-19: iniciar el autodiagnóstico desde la landing, sin invitación ni registro.

En UNA transacción:
  1. crea el usuario temporal anónimo (rubro elegido, sin email, aviso legal aceptado),
  2. crea su evaluación con origen='publica',
  3. genera la clave de acceso para retomarla (solo se guarda su hash),
y después emite el token del rol `encuestado` (sub = id de la evaluación).

La clave se devuelve UNA sola vez. El CAPTCHA y los límites por IP los aplica la
ruta antes de llamar a este caso de uso (app/api/routes/encuesta_publica.py).
"""
import asyncio
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.use_cases.clave_acceso_encuestado import hash_clave, nueva_clave
from app.core.autenticacion import Rol, emitir_token
from app.core.config import settings
from app.domain.models.evaluacion import ORIGEN_PUBLICA, Evaluacion
from app.domain.models.rubro import Rubro
from app.domain.models.usuario_temporal import UsuarioTemporal


class EncuestaPublicaError(Exception):
    def __init__(self, mensaje: str, codigo: str, status_code: int):
        super().__init__(mensaje)
        self.codigo = codigo
        self.status_code = status_code


@dataclass(frozen=True)
class EncuestaIniciada:
    evaluacion_id: int
    clave_acceso: str
    access_token: str
    expira_en: int  # epoch (s)


class IniciarEncuestaPublicaUseCase:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def execute(self, rubro_id: int, version_aviso: str) -> EncuestaIniciada:
        if version_aviso != settings.AVISO_LEGAL_VERSION:
            raise EncuestaPublicaError(
                "El aviso legal cambió. Vuelve a leerlo y acéptalo para continuar.",
                "AVISO_DESACTUALIZADO", 409,
            )
        if await self.db.get(Rubro, rubro_id) is None:
            raise EncuestaPublicaError("El rubro elegido no existe.", "RUBRO_INVALIDO", 422)

        clave = nueva_clave()
        # PBKDF2 de 600.000 iteraciones (~0,5 s de CPU): fuera del event loop
        clave_hash = await asyncio.to_thread(hash_clave, clave)

        hoy = date.today()
        usuario = UsuarioTemporal(
            email=None,
            rubro_id=rubro_id,
            fecha_expiracion=hoy + timedelta(days=settings.ENCUESTA_DIAS_VIGENCIA),
            aviso_legal_version=version_aviso,
            fecha_aceptacion_aviso=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        self.db.add(usuario)
        await self.db.flush()

        evaluacion = Evaluacion(
            fecha_inicio=hoy,
            estado_progreso="en_progreso",
            usuario_temporal_id=usuario.id,
            filtro_completado=False,
            origen=ORIGEN_PUBLICA,
            es_prueba=False,
            clave_acceso_hash=clave_hash,
        )
        self.db.add(evaluacion)
        await self.db.commit()

        return EncuestaIniciada(
            evaluacion_id=evaluacion.id,
            clave_acceso=clave,
            access_token=emitir_token(evaluacion.id, Rol.ENCUESTADO.value),
            expira_en=int(time.time()) + settings.AUTH_TOKEN_TTL_MIN * 60,
        )

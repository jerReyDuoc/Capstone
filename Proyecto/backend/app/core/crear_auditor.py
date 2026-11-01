"""
HU-09 · Crea, extiende o desactiva la cuenta de un Auditor Externo (rol auditor_externo).

Con Docker, desde Proyecto/:
    docker compose exec api python -m app.core.crear_auditor --email auditora@firma.cl --organizacion "Firma Auditora SpA" --dias 30
La contraseña se pide por teclado (no queda en el historial de la terminal).

Opciones:
    --dias N        vigencia en días desde hoy (máx. AUDITOR_VIGENCIA_MAX_DIAS); en una cuenta
                    existente la extiende
    --password      en una cuenta existente, cambia la contraseña (cierra sus sesiones)
    --desactivar    bloquea el acceso (sus tokens dejan de servir al instante)

La acción queda en el audit_log con actor "sistema" e IP "sistema:cli". También se puede
hacer desde la API del admin: POST/PATCH /api/admin/auditores.
"""
import argparse
import asyncio
import getpass

from sqlalchemy import func, select

from app.application.use_cases.auditoria_externa import AuditoriaError, GestionarAuditoresUseCase
from app.core.config import settings
from app.core.contexto_auditoria import ORIGEN_CLI, fijar_origen_por_defecto
from app.core.database import AsyncSessionLocal, engine
from app.domain.models.auditoria_externa import UsuarioAuditor


def _pedir_password() -> str:
    pwd = getpass.getpass("Contraseña del auditor: ")
    if pwd != getpass.getpass("Repite la contraseña: "):
        raise SystemExit("Las contraseñas no coinciden.")
    return pwd


async def _ejecutar(email: str, organizacion: str | None, dias: int | None, cambiar_password: bool,
                    desactivar: bool) -> None:
    fijar_origen_por_defecto(ORIGEN_CLI)
    async with AsyncSessionLocal() as s:
        uc = GestionarAuditoresUseCase(s)
        existente = await s.scalar(select(UsuarioAuditor).where(func.lower(UsuarioAuditor.email) == email))
        try:
            if existente is None:
                if desactivar:
                    raise SystemExit(f"No existe el auditor {email}.")
                if not organizacion:
                    raise SystemExit("Para crear la cuenta indica --organizacion.")
                a = await uc.crear(None, email, organizacion, _pedir_password(), dias or 30)
                print(f"Auditor {a.email} creado; vence el {a.fecha_expiracion:%Y-%m-%d %H:%M} UTC.")
                return
            a = await uc.actualizar(None, existente.id, activo=False if desactivar else None,
                                    dias_vigencia=dias, password=_pedir_password() if cambiar_password else None)
            estado = "desactivado" if not a.activo else f"vigente hasta el {a.fecha_expiracion:%Y-%m-%d %H:%M} UTC"
            print(f"Auditor {a.email} actualizado: {estado}.")
        except AuditoriaError as e:
            raise SystemExit(str(e))


async def _main(*args) -> None:
    try:
        await _ejecutar(*args)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Crea o actualiza la cuenta de un Auditor Externo (HU-09).")
    p.add_argument("--email", required=True)
    p.add_argument("--organizacion", help="firma auditora (obligatoria al crear)")
    p.add_argument("--dias", type=int, help=f"vigencia en días (1-{settings.AUDITOR_VIGENCIA_MAX_DIAS})")
    p.add_argument("--password", action="store_true", help="cambiar la contraseña de una cuenta existente")
    p.add_argument("--desactivar", action="store_true")
    a = p.parse_args()
    asyncio.run(_main(a.email.strip().lower(), a.organizacion, a.dias, a.password, a.desactivar))

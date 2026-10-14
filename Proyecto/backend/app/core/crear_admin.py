"""
Crea (o reactiva / cambia la contraseña de) un administrador admin_therion.

Con Docker, desde Proyecto/:
    docker compose exec api python -m app.core.crear_admin --email admin@therionlabs.cl
La contraseña se pide por teclado (no queda en el historial de la terminal).

Opciones:
    --desactivar   bloquea el acceso del admin (sus tokens dejan de servir al instante)
"""
import argparse
import asyncio
import getpass
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.core.autenticacion import hash_password
from app.core.database import AsyncSessionLocal, engine
from app.domain.models.usuario_admin import UsuarioAdmin

MIN_PASSWORD = 12


async def _main(email: str, desactivar: bool) -> None:
    try:
        await _ejecutar(email.strip().lower(), desactivar)
    finally:
        await engine.dispose()


async def _ejecutar(email: str, desactivar: bool) -> None:
    async with AsyncSessionLocal() as s:
        admin = (await s.execute(
            select(UsuarioAdmin).where(func.lower(UsuarioAdmin.email) == email)
        )).scalar_one_or_none()

        if desactivar:
            if not admin:
                raise SystemExit(f"No existe el administrador {email}.")
            admin.activo = False
            await s.commit()
            print(f"Administrador {email} desactivado.")
            return

        pwd = getpass.getpass("Contraseña: ")
        if len(pwd) < MIN_PASSWORD:
            raise SystemExit(f"La contraseña debe tener al menos {MIN_PASSWORD} caracteres.")
        if pwd != getpass.getpass("Repite la contraseña: "):
            raise SystemExit("Las contraseñas no coinciden.")

        if admin:
            admin.password_hash = hash_password(pwd)
            admin.activo = True
            accion = "actualizado"
        else:
            s.add(UsuarioAdmin(
                email=email,
                password_hash=hash_password(pwd),
                activo=True,
                fecha_creacion=datetime.now(timezone.utc).replace(tzinfo=None),
            ))
            accion = "creado"
        await s.commit()
        print(f"Administrador {email} {accion}.")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Crea o actualiza un administrador admin_therion.")
    p.add_argument("--email", required=True)
    p.add_argument("--desactivar", action="store_true")
    a = p.parse_args()
    asyncio.run(_main(a.email, a.desactivar))

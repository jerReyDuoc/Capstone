"""
T-06 — Ejecuta a mano los plazos de conservación (lo mismo que el cron diario del worker).

Por defecto SIMULA: muestra cuántos titulares, solicitudes ARCOP y eventos de
seguridad se anonimizarían, sin cambiar nada. Con --aplicar los anonimiza.
Nunca imprime datos personales, solo conteos.

    docker compose exec worker python -m app.cli.retencion
    docker compose exec worker python -m app.cli.retencion --aplicar

HU-25: el plazo de los titulares (usuarios temporales) es el que fijó el Oficial de
Privacidad en /admin/retencion; si no lo ha fijado, RETENCION_DATOS_TITULAR_DIAS. Cada
corrida (también la simulación) queda en el audit_log como retencion.ejecucion, origen "cli".

Los demás plazos salen de RETENCION_* (Proyecto/.env). Para probar sin tocar el .env:
    docker compose exec -e RETENCION_DATOS_TITULAR_DIAS=365 worker python -m app.cli.retencion

Respaldar antes de --aplicar: la anonimización no se deshace.
    docker compose exec -T db pg_dump -U postgres complaince_db > respaldo_pre_t06.sql
"""
import argparse
import asyncio
import json

from app.application.retencion.casos_uso.aplicar_retencion import ORIGEN_CLI, AplicarRetencionUseCase
from app.bootstrap import configurar, crear_storage_evidencias
from app.core.contexto_auditoria import ORIGEN_CLI as IP_CLI, fijar_origen_por_defecto
from app.core.database import AsyncSessionLocal, engine


async def _ejecutar(aplicar: bool) -> dict:
    fijar_origen_por_defecto(IP_CLI)  # HU-09: el registro queda con origen "sistema:cli"
    async with AsyncSessionLocal() as session:
        storage = crear_storage_evidencias() if aplicar else None
        resultado = await AplicarRetencionUseCase(session, storage=storage, origen=ORIGEN_CLI).execute(aplicar=aplicar)
        return resultado.como_dict()


async def _main(aplicar: bool) -> dict:
    try:
        return await _ejecutar(aplicar)
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Plazos de conservación de datos personales (T-06)")
    p.add_argument("--aplicar", action="store_true", help="anonimiza (sin esto, solo simula)")
    args = p.parse_args(argv)
    configurar()  # raíz de composición (A-40)
    r = asyncio.run(_main(args.aplicar))
    print(json.dumps(r, ensure_ascii=False, indent=2))
    if r["omitida_por_ejecucion_en_curso"]:
        print("No se ejecutó: hay otra ejecución de la retención en curso (cron o panel).")
    if r["reglas_desactivadas"]:
        print("Reglas sin plazo configurado (no se aplicaron):", ", ".join(r["reglas_desactivadas"]))


if __name__ == "__main__":
    main()

"""
T-06 — Ejecuta a mano los plazos de conservación (lo mismo que el cron diario del worker).

Por defecto SIMULA: muestra cuántos titulares, solicitudes ARCOP y eventos de
seguridad se anonimizarían, sin cambiar nada. Con --aplicar los anonimiza.
Nunca imprime datos personales, solo conteos.

    docker compose exec worker python scripts/retencion_datos.py
    docker compose exec worker python scripts/retencion_datos.py --aplicar

HU-25: el plazo de los titulares (usuarios temporales) es el que fijó el Oficial de
Privacidad en /admin/retencion; si no lo ha fijado, RETENCION_DATOS_TITULAR_DIAS. Cada
corrida (también la simulación) queda en el audit_log como retencion.ejecucion, origen "cli".

Los demás plazos salen de RETENCION_* (Proyecto/.env). Para probar sin tocar el .env:
    docker compose exec -e RETENCION_DATOS_TITULAR_DIAS=365 worker python scripts/retencion_datos.py

Respaldar antes de --aplicar: la anonimización no se deshace.
    docker compose exec -T db pg_dump -U postgres complaince_db > respaldo_pre_t06.sql
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.application.use_cases.aplicar_retencion import ORIGEN_CLI, AplicarRetencionUseCase  # noqa: E402
from app.core.contexto_auditoria import ORIGEN_CLI as IP_CLI, fijar_origen_por_defecto  # noqa: E402
from app.core.database import AsyncSessionLocal  # noqa: E402
from app.infrastructure.llm.factory import crear_storage_evidencias  # noqa: E402


async def _main(aplicar: bool) -> dict:
    fijar_origen_por_defecto(IP_CLI)  # HU-09: el registro queda con origen "sistema:cli"
    async with AsyncSessionLocal() as session:
        storage = crear_storage_evidencias() if aplicar else None
        resultado = await AplicarRetencionUseCase(session, storage=storage, origen=ORIGEN_CLI).execute(aplicar=aplicar)
        return resultado.como_dict()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Plazos de conservación de datos personales (T-06)")
    p.add_argument("--aplicar", action="store_true", help="anonimiza (sin esto, solo simula)")
    args = p.parse_args()
    r = asyncio.run(_main(args.aplicar))
    print(json.dumps(r, ensure_ascii=False, indent=2))
    if r["omitida_por_ejecucion_en_curso"]:
        print("No se ejecutó: hay otra ejecución de la retención en curso (cron o panel).")
    if r["reglas_desactivadas"]:
        print("Reglas sin plazo configurado (no se aplicaron):", ", ".join(r["reglas_desactivadas"]))

"""
T-06 — Corrige los datos que se guardaron ANTES de los cambios de minimización.

  1. evidencias.datos_extraidos          -> NULL (ya no se persiste, hallazgo H2)
  2. usuario_temporal.email de encuestados públicos con una supresión ARCOP ya
     resuelta -> NULL y fecha_anonimizacion (hallazgo H1: la supresión no lo borraba)
  3. sanitizaciones.mapa_cifrado         -> NULL (si quedó alguno; HU-06 lo dejó irreversible)

Por defecto SIMULA (solo conteos). Idempotente. Nunca imprime datos personales.

    docker compose exec -T db pg_dump -U postgres complaince_db > respaldo_pre_t06.sql
    docker compose exec worker python scripts/migrar_t06.py             # simulación
    docker compose exec worker python scripts/migrar_t06.py --aplicar   # aplica
"""
import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, text  # noqa: E402

PASOS = [
    ("evidencias.datos_extraidos",
     "SELECT count(*) FROM evidencias WHERE datos_extraidos IS NOT NULL",
     "UPDATE evidencias SET datos_extraidos = NULL WHERE datos_extraidos IS NOT NULL"),
    ("usuario_temporal.email (encuestado con supresión resuelta)",
     """SELECT count(DISTINCT u.id) FROM usuario_temporal u
        JOIN evaluacion e ON e."Usuario_temporal_id" = u.id AND e.origen = 'publica'
        JOIN solicitudes_arcop s ON s."Evaluacion_id" = e.id AND s.tipo = 'supresion' AND s.estado = 'resuelta'
        WHERE u.email IS NOT NULL""",
     """UPDATE usuario_temporal SET email = NULL, fecha_anonimizacion = COALESCE(fecha_anonimizacion, :ahora)
        WHERE email IS NOT NULL AND id IN (
            SELECT e."Usuario_temporal_id" FROM evaluacion e
            JOIN solicitudes_arcop s ON s."Evaluacion_id" = e.id AND s.tipo = 'supresion' AND s.estado = 'resuelta'
            WHERE e.origen = 'publica')"""),
    ("sanitizaciones.mapa_cifrado",
     "SELECT count(*) FROM sanitizaciones WHERE mapa_cifrado IS NOT NULL",
     "UPDATE sanitizaciones SET mapa_cifrado = NULL WHERE mapa_cifrado IS NOT NULL"),
]


def main() -> int:
    p = argparse.ArgumentParser(description="Migración de datos T-06")
    p.add_argument("--aplicar", action="store_true")
    p.add_argument("--url", default=os.environ.get("DATABASE_URL_SYNC"))
    args = p.parse_args()
    ahora = datetime.now(timezone.utc).replace(tzinfo=None)
    with create_engine(args.url).begin() as conn:
        for nombre, contar, corregir in PASOS:
            n = conn.execute(text(contar)).scalar() or 0
            if args.aplicar and n:
                conn.execute(text(corregir), {"ahora": ahora})
            print(f"{'corregidas' if args.aplicar else 'a corregir'}: {n:>5}  {nombre}")
        if not args.aplicar:
            conn.rollback()
            print("Simulación: no se cambió nada. Agrega --aplicar para corregir.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

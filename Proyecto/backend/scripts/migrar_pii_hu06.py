"""
HU-06 — Migración de los datos que se guardaron ANTES de la anonimización previa a persistir.

Qué hace (idempotente: se puede correr varias veces):
  1. respuestas.justificacion_usuario  -> anonimizada con el motor NER (etiquetas fijas)
  2. evidencias.nombre_archivo          -> anonimizado
     archivos de evidencia              -> ya procesados: se reemplazan por su texto anonimizado
                                           pendientes/en proceso: se cifran (los procesa el worker)
  3. sanitizaciones.mapa_cifrado        -> NULL (irreversible), salvo GUARDAR_MAPA_ENTIDADES_CIFRADO=true
  4. eventos_seguridad.extracto         -> re-anonimizado con el motor NER
  5. textos ARCOP (descripcion, respuesta, comentarios del historial) -> cifrados (excepción ARCOP)

Por defecto es una SIMULACIÓN (no cambia nada) y muestra cuántas filas tocaría.
Para aplicar los cambios:

    docker compose exec worker python scripts/migrar_pii_hu06.py            # simulación
    docker compose exec worker python scripts/migrar_pii_hu06.py --aplicar   # aplica

Se corre en el WORKER porque necesita spaCy, ENTITY_MAP_KEY y el volumen de evidencias.
Haz un respaldo de la BD antes de aplicar (pg_dump): la anonimización no se puede deshacer.
El script no imprime ningún texto de las filas, solo conteos.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from app.core.cifrado_columnas import cifrador_arcop  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.database import AsyncSessionLocal  # noqa: E402
from app.infrastructure.llm.factory import crear_anonimizador, crear_storage_evidencias  # noqa: E402
from app.infrastructure.security.cifrado import CifradorDatos  # noqa: E402

PROCESADAS = ("validated", "rejected", "error")
TEXTOS_ARCOP = [
    ("solicitudes_arcop", "id_solicitud", "descripcion"),
    ("solicitudes_arcop", "id_solicitud", "respuesta"),
    ("eventos_solicitud_arcop", "id_evento", "comentario"),
]


async def migrar(aplicar: bool) -> dict:
    if not settings.SANITIZER_ENABLED:
        raise SystemExit("SANITIZER_ENABLED=false: no se puede anonimizar. Actívalo antes de migrar.")
    anon = crear_anonimizador()
    storage = crear_storage_evidencias()
    arcop = cifrador_arcop()
    conteo = {k: 0 for k in (
        "justificaciones", "nombres_archivo", "archivos_anonimizados", "archivos_cifrados",
        "archivos_inexistentes", "mapas_eliminados", "extractos", "textos_arcop_cifrados",
    )}
    borrar_despues: list[str] = []

    async with AsyncSessionLocal() as s:
        # 1. justificaciones
        filas = (await s.execute(text(
            "SELECT id_respuesta, justificacion_usuario FROM respuestas "
            "WHERE justificacion_usuario IS NOT NULL AND justificacion_usuario <> ''"))).all()
        for rid, valor in filas:
            nuevo = await anon.anonimizar(valor)
            if nuevo != valor:
                conteo["justificaciones"] += 1
                await s.execute(text("UPDATE respuestas SET justificacion_usuario = :v WHERE id_respuesta = :i"),
                                {"v": nuevo, "i": rid})

        # 2. evidencias: nombre y archivo
        filas = (await s.execute(text(
            "SELECT id_evidencia, nombre_archivo, storage_path, estado_validacion FROM evidencias"))).all()
        for eid, nombre, ruta, estado in filas:
            nuevo_nombre = await anon.anonimizar_nombre_archivo(nombre) if nombre else nombre
            if nuevo_nombre != nombre:
                conteo["nombres_archivo"] += 1
                await s.execute(text("UPDATE evidencias SET nombre_archivo = :v WHERE id_evidencia = :i"),
                                {"v": nuevo_nombre, "i": eid})
            if not ruta:
                continue
            if not os.path.exists(ruta):
                conteo["archivos_inexistentes"] += 1
                continue
            crudo = await storage.interno.get(ruta)
            if estado in PROCESADAS:
                contenido = storage.cifrador.descifrar_bytes(crudo).decode("utf-8", errors="ignore")
                anonimo = await anon.anonimizar(contenido) or ""
                if anonimo.encode("utf-8") == crudo:
                    continue  # ya es el texto anonimizado
                conteo["archivos_anonimizados"] += 1
                if aplicar:
                    nueva = await storage.save_plano(anonimo.encode("utf-8"), "evidencia_anonimizada.txt")
                    await s.execute(text("UPDATE evidencias SET storage_path = :v WHERE id_evidencia = :i"),
                                    {"v": nueva, "i": eid})
                    borrar_despues.append(ruta)
            elif not CifradorDatos.esta_cifrado(crudo):
                conteo["archivos_cifrados"] += 1
                if aplicar:
                    nueva = await storage.save(crudo, nombre or "evidencia")
                    await s.execute(text("UPDATE evidencias SET storage_path = :v WHERE id_evidencia = :i"),
                                    {"v": nueva, "i": eid})
                    borrar_despues.append(ruta)

        # 3. mapa de entidades reversible
        if not settings.GUARDAR_MAPA_ENTIDADES_CIFRADO:
            conteo["mapas_eliminados"] = (await s.execute(text(
                "SELECT count(*) FROM sanitizaciones WHERE mapa_cifrado IS NOT NULL"))).scalar() or 0
            await s.execute(text("UPDATE sanitizaciones SET mapa_cifrado = NULL WHERE mapa_cifrado IS NOT NULL"))

        # 4. extractos de eventos de seguridad
        filas = (await s.execute(text(
            "SELECT id_evento, extracto FROM eventos_seguridad WHERE extracto IS NOT NULL"))).all()
        for evid, valor in filas:
            nuevo = await anon.anonimizar(valor)
            if nuevo != valor:
                conteo["extractos"] += 1
                await s.execute(text("UPDATE eventos_seguridad SET extracto = :v WHERE id_evento = :i"),
                                {"v": nuevo, "i": evid})

        # 5. textos ARCOP: se cifran (se leen en crudo, sin el tipo TextoCifrado)
        for tabla, pk, col in TEXTOS_ARCOP:
            filas = (await s.execute(text(
                f"SELECT {pk}, {col} FROM {tabla} WHERE {col} IS NOT NULL AND {col} NOT LIKE 'enc:v1:%'"))).all()
            for i, valor in filas:
                conteo["textos_arcop_cifrados"] += 1
                await s.execute(text(f"UPDATE {tabla} SET {col} = :v WHERE {pk} = :i"),
                                {"v": arcop.cifrar_texto(valor), "i": i})

        if aplicar:
            await s.commit()
        else:
            await s.rollback()

    # Los archivos viejos se borran DESPUÉS del commit (si el commit falla, siguen ahí)
    for ruta in borrar_despues:
        try:
            await storage.delete(ruta)
        except OSError:
            print(f"  aviso: no se pudo borrar un archivo antiguo ({Path(ruta).name})")
    return conteo


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--aplicar", action="store_true", help="aplica los cambios (por defecto solo simula)")
    a = p.parse_args()
    conteo = asyncio.run(migrar(a.aplicar))
    print(("APLICADO" if a.aplicar else "SIMULACIÓN (usa --aplicar para guardar)") + " — HU-06")
    for k, v in conteo.items():
        print(f"  {k:24s} {v}")


if __name__ == "__main__":
    main()

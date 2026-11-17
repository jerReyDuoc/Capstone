"""Mantenedor de rubros del panel interno (solo admin_therion): listar, agregar y renombrar."""
from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.fabricas import fabricas
from app.domain.auditoria.acciones import Accion
from app.domain.auth.actor import Actor
from app.domain.ports.repositorios_admin import RubrosRepositoryPort

NOMBRE_MIN, NOMBRE_MAX = 2, 50
_ESPACIOS = re.compile(r"\s+")


class RubroError(Exception):
    def __init__(self, status_code: int, codigo: str, mensaje: str):
        super().__init__(mensaje)
        self.status_code = status_code
        self.codigo = codigo
        self.mensaje = mensaje


@dataclass(frozen=True)
class FilaRubro:
    id: int
    nombre: str
    evaluaciones: int
    empresas: int


def normalizar_nombre(nombre: str) -> str:
    limpio = _ESPACIOS.sub(" ", nombre or "").strip()
    if len(limpio) < NOMBRE_MIN or not re.search(r"[^\W\d_]", limpio):
        raise RubroError(422, "RUBRO_INVALIDO", f"Escribe un nombre de al menos {NOMBRE_MIN} letras.")
    if len(limpio) > NOMBRE_MAX:
        raise RubroError(422, "RUBRO_INVALIDO", f"El nombre admite hasta {NOMBRE_MAX} caracteres.")
    return limpio


class MantenedorRubrosUseCase:
    def __init__(self, session: AsyncSession, repo: RubrosRepositoryPort):
        self.session = session
        self.repo = repo

    async def listar(self) -> list[FilaRubro]:
        evaluaciones = await self.repo.conteo_evaluaciones_por_rubro()
        empresas = await self.repo.conteo_empresas_por_rubro()
        return [FilaRubro(id=r.id, nombre=(r.nombre_rubro or "").strip() or f"Rubro {r.id}",
                          evaluaciones=int(evaluaciones.get(r.id, 0)), empresas=int(empresas.get(r.id, 0)))
                for r in await self.repo.listar()]

    async def crear(self, actor: Actor, nombre_crudo: str) -> FilaRubro:
        nombre = normalizar_nombre(nombre_crudo)
        if await self.repo.existe_nombre(nombre):
            raise RubroError(409, "RUBRO_DUPLICADO", f"Ya existe el rubro «{nombre}».")
        # Los rubros sembrados por la migración llevan id explícito y la secuencia de PostgreSQL
        # no avanzó con ellos: el id se calcula en el repositorio (solo admin, sin concurrencia real).
        for _ in range(3):
            rubro = await self.repo.intentar_agregar(nombre)
            if rubro is not None:
                break
        else:
            raise RubroError(409, "RUBRO_CONFLICTO", "No pudimos guardar el rubro. Inténtalo de nuevo.")
        fabricas().bitacora(self.session).registrar(
            accion=Accion.RUBRO_CREADO, entidad="rubro", entidad_id=rubro.id, actor=actor,
            detalle={"rubro": nombre})
        await self.session.commit()
        return FilaRubro(id=rubro.id, nombre=nombre, evaluaciones=0, empresas=0)

    async def renombrar(self, actor: Actor, rubro_id: int, nombre_crudo: str) -> tuple[int, str]:
        rubro = await self.repo.obtener(rubro_id)
        if rubro is None:
            raise RubroError(404, "RUBRO_NO_ENCONTRADO", "El rubro no existe.")
        nombre = normalizar_nombre(nombre_crudo)
        if await self.repo.existe_nombre(nombre, excepto=rubro_id):
            raise RubroError(409, "RUBRO_DUPLICADO", f"Ya existe el rubro «{nombre}».")
        antes = (rubro.nombre_rubro or "").strip()
        if antes != nombre:
            rubro.nombre_rubro = nombre
            fabricas().bitacora(self.session).registrar(
                accion=Accion.RUBRO_RENOMBRADO, entidad="rubro", entidad_id=rubro.id, actor=actor,
                detalle={"antes": antes, "despues": nombre})
            await self.session.commit()
        return rubro.id, nombre

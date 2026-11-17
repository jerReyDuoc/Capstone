from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from app.domain.rat.estados import ACCIONES


# ------------------------------------------------------------------ esquemas de entrada
class _Base(BaseModel):
    # Los campos desconocidos se rechazan: un error de tipeo no debe pasar en silencio
    model_config = ConfigDict(extra="forbid")


class SeleccionEntrada(_Base):
    id: int = Field(..., ge=1)
    categorias_datos: list[str] = Field(default_factory=list, max_length=60)
    categorias_titulares: list[str] = Field(default_factory=list, max_length=60)


class FuenteEntrada(_Base):
    tipo: str = Field(..., max_length=30)
    detalle: str | None = Field(None, max_length=600)


class PlazoEntrada(_Base):
    categoria: str = Field(..., max_length=40)
    plazo: int | None = Field(None, ge=1, le=100_000)
    unidad: str | None = Field(None, max_length=10)
    desde: str | None = Field(None, max_length=30)
    fundamento: str | None = Field(None, max_length=600)


class DecisionesEntrada(_Base):
    existe: bool | None = None
    perfilamiento: bool = False
    logica: str | None = Field(None, max_length=3000)
    consecuencias: str | None = Field(None, max_length=2000)
    intervencion_humana: bool | None = None


class MedidasEntrada(_Base):
    codigos: list[str] = Field(default_factory=list, max_length=40)
    otras: str | None = Field(None, max_length=2000)


class ActividadEntrada(_Base):
    nombre: str | None = Field(None, max_length=300)
    descripcion: str | None = Field(None, max_length=2000)
    area: str | None = Field(None, max_length=240)
    elementos: list[SeleccionEntrada] | None = Field(None, max_length=200)
    flujos: list[SeleccionEntrada] | None = Field(None, max_length=200)
    finalidades: list[str] | None = Field(None, max_length=15)
    fuentes: list[FuenteEntrada] | None = Field(None, max_length=12)
    base_licitud: str | None = Field(None, max_length=30)
    interes_legitimo: str | None = Field(None, max_length=3000)
    base_sensibles: str | None = Field(None, max_length=30)
    sin_destinatarios: bool | None = None
    plazos: list[PlazoEntrada] | None = Field(None, max_length=80)
    decisiones: DecisionesEntrada | None = None
    medidas: MedidasEntrada | None = None
    rol: str | None = Field(None, max_length=20)
    responsable_mandante: str | None = Field(None, max_length=300)
    ambito_nota: str | None = Field(None, max_length=600)
    volumen: str | None = Field(None, max_length=20)      # HU-38: opcional (catalogo.VOLUMENES)


class EditarEntrada(ActividadEntrada):
    revision: int = Field(..., ge=1, description="Revisión de la actividad que vio el usuario")


class EstadoEntrada(_Base):
    revision: int = Field(..., ge=1)
    accion: Literal[ACCIONES]  # type: ignore[valid-type]

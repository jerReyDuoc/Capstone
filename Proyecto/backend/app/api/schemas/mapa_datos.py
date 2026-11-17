from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


# ------------------------------------------------------------------ esquemas de entrada
class _Base(BaseModel):
    # Los campos desconocidos se rechazan: un error de tipeo no debe pasar en silencio
    model_config = ConfigDict(extra="forbid")


class ElementoEntrada(_Base):
    version: int = Field(..., ge=0, description="Versión del mapa que vio el usuario")
    tipo: str | None = Field(None, max_length=20)
    subtipo: str | None = Field(None, max_length=30)
    nombre: str | None = Field(None, max_length=200)
    descripcion: str | None = Field(None, max_length=800)
    proveedor: str | None = Field(None, max_length=200)
    pais: str | None = Field(None, max_length=2)
    responsable: str | None = Field(None, max_length=200)
    categorias_datos: list[str] | None = Field(None, max_length=60)
    categorias_titulares: list[str] | None = Field(None, max_length=60)
    nna_declarado: bool | None = None
    rol_tercero: str | None = Field(None, max_length=20)
    contrato_firmado: bool | None = None
    pendiente_revision: bool | None = None


class FlujoEntrada(_Base):
    version: int = Field(..., ge=0)
    origen_id: int | None = Field(None, ge=1)
    destino_id: int | None = Field(None, ge=1)
    finalidad: str | None = Field(None, max_length=500)
    categorias_datos: list[str] | None = Field(None, max_length=60)
    categorias_titulares: list[str] | None = Field(None, max_length=60)
    nna_declarado: bool | None = None
    frecuencia: str | None = Field(None, max_length=20)
    medio: str | None = Field(None, max_length=20)
    cifrado: bool | None = None
    garantia: str | None = Field(None, max_length=30)
    pendiente_revision: bool | None = None


class VersionEntrada(_Base):
    version: int = Field(..., ge=0)


class RevisionEntrada(_Base):
    version: int = Field(..., ge=0)
    todo: bool = False
    elementos: list[int] | None = Field(None, max_length=2000)
    flujos: list[int] | None = Field(None, max_length=5000)


class PlantillaEntrada(_Base):
    version: int = Field(..., ge=0)
    codigo: str = Field(..., max_length=30)


class AceptarSugerenciaEntrada(_Base):
    version: int = Field(..., ge=0)
    origen_id: int | None = Field(None, ge=1)


class EnviarInformeEntrada(_Base):
    email: str | None = Field(None, max_length=100, description="Vacío = el correo del usuario de la empresa")
    sensibles: bool = False
    nna: bool = False
    internacional: bool = False
    tercero: int | None = Field(None, ge=1)
    pais: str | None = Field(None, max_length=2)
    tipo: str | None = Field(None, max_length=20)

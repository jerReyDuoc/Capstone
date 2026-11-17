"""
HU-40 · Datos de la constancia de revisión interna del RAT (puro): DTO y nombre del archivo.
El PDF se dibuja en app/infrastructure/documentos/pdf/revision_interna_pdf.py (A-14).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.application.informes.formato import fecha_local


@dataclass
class DatosConstancia:
    empresa: str
    rut: str | None
    numero: int
    estado: str                       # en_curso | revisada
    fecha_inicio: datetime
    generado: datetime
    lista: list[dict]                 # objetos consolidados (revision.consolidar)
    observaciones: list[dict]
    resumen: dict
    fecha_revision: datetime | None = None
    revisor: str | None = None
    cargo: str | None = None
    conclusion: str | None = None
    version_rat: int | None = None
    huella: str | None = None
    version_mapa: int | None = None
    informe_codigo: str | None = None
    proxima_revision: str | None = None
    plazo_meses: int | None = None
    diferencias: dict | None = None
    diferencias_desde: str | None = None
    notas: list[str] = field(default_factory=list)

    @property
    def revisada(self) -> bool:
        return self.estado == "revisada"


def nombre_archivo(d: DatosConstancia) -> str:
    fecha = fecha_local(d.fecha_revision or d.generado, con_hora=False)
    dd, mm, aaaa = fecha.split("-")
    v = f"_v{d.version_rat}" if d.version_rat else ""
    return f"revision_interna_{d.numero}{v}_{aaaa}-{mm}-{dd}{'' if d.revisada else '_en_curso'}.pdf"

"""
HU-34 criterio 3 · Datos del informe PDF del mapa de datos personales (puro): DTOs, nombre del archivo,
huella legible y cuerpo del correo. El PDF se dibuja en app/infrastructure/documentos/pdf/mapa_datos_pdf.py (A-14).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from html import escape

from app.domain.mapa_datos import analisis_mapa as analisis
from app.domain.mapa_datos.modelo_mapa import Elemento, Flujo


@dataclass(frozen=True)
class VersionResumen:
    numero: int
    fecha: datetime
    resumen: str


@dataclass
class DatosInformeMapa:
    razon_social: str
    rubro: str | None
    version: int
    fecha_version: datetime | None
    huella: str
    elementos: list[Elemento]
    flujos: list[Flujo]
    filtros: analisis.FiltrosMapa
    generado: datetime
    historial: list[VersionResumen] = field(default_factory=list)


def nombre_archivo(version: int, fecha: datetime) -> str:
    return f"mapa_datos_personales_v{version}_{fecha:%Y-%m-%d}.pdf"


def nombre_archivo(version: int, fecha: datetime) -> str:
    return f"mapa_datos_personales_v{version}_{fecha:%Y-%m-%d}.pdf"


def huella_legible(h: str) -> str:
    h = (h or "").upper()
    return " ".join(h[i:i + 4] for i in range(0, min(len(h), 32), 4))


def cuerpo_correo(razon_social: str, version: int, res: dict, cuenta: dict[str, int], completitud: int) -> tuple[str, str]:
    """(texto plano, html) del correo con el informe. Sin datos personales: solo cifras del mapa."""
    from html import escape

    graves = cuenta.get("Crítica", 0) + cuenta.get("Alta", 0)
    texto = (
        "Hola,\n\n"
        f"Te enviamos el informe del mapa de datos personales de {razon_social} (versión {version}).\n\n"
        f"Sistemas: {res['sistemas']} · Bases de datos: {res['bases_datos']} · Terceros: {res['terceros']}\n"
        f"Flujos: {res['flujos']} · Transferencias internacionales: {res['transferencias_internacionales']}\n"
        f"Hallazgos críticos o altos: {graves} · Completitud del mapa: {completitud} %\n\n"
        "El informe completo va adjunto en PDF: incluye el diagrama, el inventario, los flujos, las "
        "transferencias internacionales, los hallazgos de riesgo y la base para el registro de actividades "
        "de tratamiento.\n\n"
        "Este correo se generó automáticamente; no es necesario responderlo.\nComplianceIA\n"
    )
    empresa = escape(razon_social)

    def celda(titulo: str, cifra, pie: str) -> str:
        return (f'<td style="padding:14px;font-size:12px;color:#5b6b64">{titulo}<br>'
                f'<span style="font-size:22px;font-weight:bold;color:#14201b">{cifra}</span><br>{pie}</td>')

    html = f"""<!doctype html><html lang="es"><body style="margin:0;background:#f3f6f5;font-family:Arial,Helvetica,sans-serif;color:#14201b">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:24px 12px">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;background:#ffffff;border-radius:12px;border-top:4px solid #0b7a5a">
<tr><td style="padding:28px 28px 8px">
<p style="margin:0 0 4px;font-size:12px;color:#5b6b64">ComplianceIA · Protección de datos</p>
<h1 style="margin:0 0 12px;font-size:22px;line-height:1.25">Mapa de datos personales de {empresa}</h1>
<p style="margin:0 0 16px;font-size:15px;line-height:1.5">Adjuntamos el informe de la <b>versión {version}</b> del mapa: qué datos personales trata tu empresa, de quién, dónde están y con quién se comparten.</p>
</td></tr>
<tr><td style="padding:0 28px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#e3f4ee;border-radius:8px"><tr>
{celda("Elementos", res["elementos"], f"{res['sistemas']} sistemas · {res['bases_datos']} bases · {res['terceros']} terceros")}
{celda("Flujos", res["flujos"], f"{res['transferencias_internacionales']} internacionales")}
{celda("Riesgos", graves, "críticos o altos")}
{celda("Completitud", f"{completitud}&nbsp;%", "del mapa")}
</tr></table>
</td></tr>
<tr><td style="padding:20px 28px 28px;font-size:12px;line-height:1.5;color:#5b6b64">
Este correo se generó automáticamente; no es necesario responderlo. El informe es una herramienta de apoyo a la gestión y no constituye asesoría legal.
</td></tr></table>
</td></tr></table></body></html>"""
    return texto, html

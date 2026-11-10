"""
HU-32 · Exportación de los datos personales del titular (derechos de Acceso y Portabilidad).

Cuando el administrador RESUELVE una solicitud de tipo `acceso` o `portabilidad`, el titular
descarga sus datos desde la página de sus derechos ARCOP:

    GET /api/arcop/solicitudes/{id}/exportacion?formato=json|csv

Reglas (el backend decide, nunca el cliente):
  - Solo el titular dueño de la solicitud (invitado, encuestado o usuario definitivo). Una
    solicitud ajena responde 404, igual que el resto de /api/arcop.
  - Solo solicitudes de acceso o portabilidad en estado `resuelta`; en cualquier otro caso
    409 EXPORTACION_NO_DISPONIBLE (el titular espera la respuesta del responsable).
  - JSON = formato estructurado, de uso común y lectura mecánica (portabilidad, Ley 21.719).
    CSV = la misma información en filas (seccion, referencia, campo, valor) para una planilla.
  - Se exporta lo que la plataforma guarda HOY de la persona. Los textos ya anonimizados
    (HU-06: justificaciones con etiquetas como <PERSONA_1>) salen tal como están guardados,
    porque el valor original no se conserva.
  - Nunca salen secretos ni datos internos: hashes de claves o contraseñas, tokens, rutas en
    disco, huellas de archivos ni ids de los administradores.
  - Usuario definitivo: sus datos de la cuenta y sus solicitudes. Las evaluaciones de la
    empresa son de la persona jurídica (HU-30) y se descargan desde "Mis documentos".
  - Cada descarga queda en el audit_log (HU-09) sin datos personales: tipo de solicitud,
    formato y conteos.
"""
from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.autenticacion import Actor
from app.domain.models.solicitud_arcop import (
    EstadoSolicitudARCOP,
    SolicitudARCOP,
    TipoSolicitudARCOP,
)

FORMATOS = ("json", "csv")
TIPOS_EXPORTABLES = frozenset({TipoSolicitudARCOP.ACCESO.value, TipoSolicitudARCOP.PORTABILIDAD.value})
VERSION_FORMATO = 1
ACCION_BITACORA = "arcop.datos_exportados"  # categoría "acceso" del audit_log (HU-09)

TITULAR_INVITADO = "invitado"
TITULAR_ENCUESTADO = "encuestado"
TITULAR_USUARIO_DEFINITIVO = "usuario_definitivo"

NOTA_EMPRESA = (
    "Las evaluaciones, informes y documentos de la empresa pertenecen a la persona jurídica "
    "contratante y se descargan desde 'Mis documentos' del espacio de la empresa."
)
NOTA_ANONIMIZACION = (
    "Los textos libres se guardan anonimizados desde su ingreso (los datos personales se "
    "reemplazan por etiquetas como <PERSONA_1>); se entregan tal como están almacenados."
)


class ExportacionNoDisponibleError(Exception):
    """La solicitud no es de acceso/portabilidad o todavía no está resuelta."""


@dataclass(frozen=True)
class Exportacion:
    contenido: bytes
    media_type: str
    nombre_archivo: str
    conteos: dict[str, int]


def _ahora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso(valor) -> str | None:
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.replace(microsecond=0).isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    return str(valor)


def validar_exportable(solicitud: SolicitudARCOP) -> None:
    if solicitud.tipo not in TIPOS_EXPORTABLES:
        raise ExportacionNoDisponibleError(
            "La descarga de datos está disponible solo para solicitudes de acceso o portabilidad."
        )
    if solicitud.estado != EstadoSolicitudARCOP.RESUELTA.value:
        raise ExportacionNoDisponibleError(
            "Podrás descargar tus datos cuando la solicitud esté resuelta."
        )


def tipo_titular(solicitud: SolicitudARCOP) -> str:
    if solicitud.usuario_definitivo_id is not None:
        return TITULAR_USUARIO_DEFINITIVO
    if solicitud.evaluacion_id is not None:
        return TITULAR_ENCUESTADO
    return TITULAR_INVITADO


# ---------------------------------------------------------------- lectura de la BD
def _solicitud_dict(s: SolicitudARCOP) -> dict:
    return {
        "codigo_seguimiento": s.codigo_seguimiento,
        "tipo": s.tipo,
        "estado": s.estado,
        "descripcion": s.descripcion,
        "respuesta": s.respuesta,
        "fecha_creacion": _iso(s.fecha_creacion),
        "fecha_cierre": _iso(s.fecha_cierre),
    }


async def _solicitudes_del_titular(db: AsyncSession, s: SolicitudARCOP) -> list[dict]:
    if s.usuario_definitivo_id is not None:
        filtro = SolicitudARCOP.usuario_definitivo_id == s.usuario_definitivo_id
    elif s.evaluacion_id is not None:
        filtro = SolicitudARCOP.evaluacion_id == s.evaluacion_id
    else:
        filtro = SolicitudARCOP.usuario_temporal_id == s.usuario_temporal_id
    filas = (await db.execute(select(SolicitudARCOP).where(filtro).order_by(SolicitudARCOP.id))).scalars().all()
    return [_solicitud_dict(x) for x in filas]


async def _nombre_rubro(db: AsyncSession, rubro_id: int | None) -> str | None:
    if rubro_id is None:
        return None
    from app.domain.models.rubro import Rubro

    rubro = await db.get(Rubro, rubro_id)
    return rubro.nombre_rubro if rubro else None


async def _evaluacion_dict(db: AsyncSession, evaluacion) -> dict:
    from app.domain.models.dominio import Dominio
    from app.domain.models.evidencia import Evidencia
    from app.domain.models.matriz_control import MatrizControl
    from app.domain.models.respuesta import Respuesta
    from app.domain.models.respuesta_filtro import RespuestaFiltro
    from app.domain.models.resumen import Resumen

    filtro = (await db.execute(
        select(RespuestaFiltro).where(RespuestaFiltro.evaluacion_id == evaluacion.id)
        .order_by(RespuestaFiltro.id_respuesta_filtro)
    )).scalars().all()

    filas = (await db.execute(
        select(Respuesta, MatrizControl)
        .outerjoin(MatrizControl, MatrizControl.id_control == Respuesta.matriz_controles_id_control)
        .where(Respuesta.evaluacion_id == evaluacion.id)
        .order_by(Respuesta.id)
    )).all()
    ids_respuesta = [r.id for r, _ in filas]
    evidencias_por_respuesta: dict[int, list[dict]] = {}
    if ids_respuesta:
        evidencias = (await db.execute(
            select(Evidencia).where(Evidencia.respuesta_id.in_(ids_respuesta)).order_by(Evidencia.id_evidencia)
        )).scalars().all()
        for e in evidencias:
            if getattr(e, "fecha_eliminacion", None) is not None:
                continue  # eliminada por el titular (HU-29): ya no se conserva
            evidencias_por_respuesta.setdefault(e.respuesta_id, []).append({
                "nombre_archivo": e.nombre_archivo,
                "tipo_archivo": e.mime_type,
                "fecha_subida": _iso(e.fecha_subida),
                "estado_validacion": e.estado_validacion,
            })

    resumen = (await db.execute(
        select(Resumen, Dominio)
        .outerjoin(Dominio, Dominio.id == Resumen.dominio_id)
        .where(Resumen.evaluacion_id == evaluacion.id)
        .order_by(Resumen.id_resumen)
    )).all()

    return {
        "numero_evaluacion": evaluacion.id,
        "origen": evaluacion.origen,
        "estado": evaluacion.estado_progreso,
        "fecha_inicio": _iso(evaluacion.fecha_inicio),
        "fecha_completado": _iso(evaluacion.fecha_completado),
        "filtro_aplicabilidad": [
            {
                "codigo": f.pregunta.codigo if f.pregunta else None,
                "pregunta": f.pregunta.pregunta if f.pregunta else None,
                "respuesta": "si" if f.respuesta else "no",
                "fecha": _iso(f.fecha_respuesta),
            }
            for f in filtro
        ],
        "respuestas": [
            {
                "control": c.codigo_control if c else None,
                "pregunta": c.pregunta_evaluacion if c else None,
                "estado_declarado": r.estado_clasificacion,
                "justificacion": r.justificacion_usuario,
                "estado_final": r.estado_clasificacion_final,
                "evidencias": evidencias_por_respuesta.get(r.id, []),
            }
            for r, c in filas
        ],
        "resultados": [
            {
                "dominio": d.nombre_dominio if d else "General",
                "puntaje": x.puntaje_obtenido,
                "nivel_madurez": x.nivel_madurez,
                "controles_evaluados": x.total_controles_evaluados,
            }
            for x, d in resumen
        ],
    }


async def recopilar_datos(db: AsyncSession, solicitud: SolicitudARCOP, generado: datetime | None = None) -> dict:
    """Todo lo que la plataforma guarda del titular de la solicitud (sin secretos)."""
    from app.domain.models.evaluacion import Evaluacion
    from app.domain.models.usuario_temporal import UsuarioTemporal

    tipo = tipo_titular(solicitud)
    datos: dict = {
        "formato": "ComplianceIA · Exportación de datos personales (Ley N.º 21.719)",
        "version_formato": VERSION_FORMATO,
        "generado_en": _iso(generado or _ahora()),
        "solicitud": {
            "codigo_seguimiento": solicitud.codigo_seguimiento,
            "tipo": solicitud.tipo,
            "fecha_resolucion": _iso(solicitud.fecha_cierre),
        },
        "titular": {"tipo": tipo},
        "evaluaciones": [],
        "solicitudes_arcop": await _solicitudes_del_titular(db, solicitud),
        "notas": [NOTA_ANONIMIZACION],
    }

    if tipo == TITULAR_USUARIO_DEFINITIVO:
        from app.domain.models.empresa import Empresa
        from app.domain.models.usuario_definitivo import UsuarioDefinitivo

        u = await db.get(UsuarioDefinitivo, solicitud.usuario_definitivo_id)
        empresa = await db.get(Empresa, u.empresa_id) if u else None
        if u:
            datos["titular"].update({
                "nombre": u.nombre,
                "correo": u.email,
                "estado_cuenta": u.estado,
                "fecha_creacion": _iso(u.fecha_creacion),
                "fecha_activacion": _iso(u.fecha_activacion),
                "ultimo_acceso": _iso(u.ultimo_acceso),
                "empresa": empresa.razon_social if empresa else None,
            })
        datos["notas"].append(NOTA_EMPRESA)
        return datos

    if tipo == TITULAR_ENCUESTADO:
        ev = await db.get(Evaluacion, solicitud.evaluacion_id)
        evaluaciones = [ev] if ev else []
        usuario_id = ev.usuario_temporal_id if ev else None
    else:
        usuario_id = solicitud.usuario_temporal_id
        evaluaciones = list((await db.execute(
            select(Evaluacion).where(Evaluacion.usuario_temporal_id == usuario_id).order_by(Evaluacion.id)
        )).scalars().all())

    usuario = await db.get(UsuarioTemporal, usuario_id) if usuario_id is not None else None
    if usuario:
        datos["titular"].update({
            "correo": usuario.email,
            "rubro": await _nombre_rubro(db, usuario.rubro_id),
            "aviso_legal_aceptado": usuario.aviso_legal_version,
            "fecha_aceptacion_aviso": _iso(usuario.fecha_aceptacion_aviso),
        })
    # Una evaluación ya migrada a una empresa cliente (HU-27) es de esa empresa
    propias = [e for e in evaluaciones if e.empresa_id is None]
    if len(propias) < len(evaluaciones):
        datos["notas"].append(NOTA_EMPRESA)
    datos["evaluaciones"] = [await _evaluacion_dict(db, e) for e in propias]
    return datos


# ---------------------------------------------------------------- formatos (puros)
def conteos(datos: dict) -> dict[str, int]:
    evaluaciones = datos.get("evaluaciones", [])
    return {
        "evaluaciones": len(evaluaciones),
        "respuestas": sum(len(e["respuestas"]) for e in evaluaciones),
        "evidencias": sum(len(r["evidencias"]) for e in evaluaciones for r in e["respuestas"]),
        "solicitudes_arcop": len(datos.get("solicitudes_arcop", [])),
    }


def a_json(datos: dict) -> bytes:
    return json.dumps(datos, ensure_ascii=False, indent=2).encode("utf-8")


def _texto(valor) -> str:
    if valor is None:
        return ""
    if isinstance(valor, bool):
        return "si" if valor else "no"
    return str(valor)


def _limpiar_celda(texto: str) -> str:
    # Evita que una planilla interprete un texto del usuario como fórmula (CSV injection)
    return "'" + texto if texto[:1] in ("=", "+", "-", "@", "\t", "\r") else texto


def a_csv(datos: dict) -> bytes:
    """Formato largo: una fila por dato (seccion, referencia, campo, valor). BOM para Excel."""
    filas: list[tuple[str, str, str, str]] = []

    def agregar(seccion: str, referencia: str, obj: dict, omitir: tuple = ()) -> None:
        for campo, valor in obj.items():
            if campo in omitir or isinstance(valor, (list, dict)):
                continue
            filas.append((seccion, referencia, campo, _texto(valor)))

    agregar("exportacion", "", {k: datos.get(k) for k in ("formato", "version_formato", "generado_en")})
    agregar("solicitud", datos["solicitud"].get("codigo_seguimiento") or "", datos["solicitud"])
    agregar("titular", "", datos["titular"])
    for ev in datos.get("evaluaciones", []):
        ref = f"evaluacion {ev['numero_evaluacion']}"
        agregar("evaluacion", ref, ev)
        for f in ev["filtro_aplicabilidad"]:
            agregar("filtro_aplicabilidad", f"{ref} · {f.get('codigo') or ''}", f)
        for i, r in enumerate(ev["respuestas"], start=1):
            ref_r = f"{ref} · {r.get('control') or f'respuesta {i}'}"
            agregar("respuesta", ref_r, r)
            for j, e in enumerate(r["evidencias"], start=1):
                agregar("evidencia", f"{ref_r} · archivo {j}", e)
        for x in ev["resultados"]:
            agregar("resultado", f"{ref} · {x.get('dominio') or ''}", x)
    for s in datos.get("solicitudes_arcop", []):
        agregar("solicitud_arcop", s.get("codigo_seguimiento") or "", s)
    for i, nota in enumerate(datos.get("notas", []), start=1):
        filas.append(("nota", str(i), "texto", nota))

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["seccion", "referencia", "campo", "valor"])
    for fila in filas:
        w.writerow([_limpiar_celda(c) for c in fila])
    return ("﻿" + buf.getvalue()).encode("utf-8")


def nombre_archivo(codigo: str | None, formato: str) -> str:
    seguro = "".join(ch for ch in (codigo or "solicitud") if ch.isalnum() or ch == "-")
    return f"mis-datos-{seguro}.{formato}"


# ---------------------------------------------------------------- caso de uso
class ExportarDatosARCOP:
    def __init__(self, db: AsyncSession, gestion):
        """`gestion` = GestionarSolicitudARCOPUseCase (valida que la solicitud sea del titular)."""
        self.db = db
        self.gestion = gestion

    async def ejecutar(self, actor: Actor, solicitud_id: int, formato: str) -> Exportacion:
        if formato not in FORMATOS:
            raise ValueError(f"Formato inválido. Debe ser uno de: {', '.join(FORMATOS)}")
        solicitud = await self.gestion.obtener(actor, solicitud_id)  # 404 si es ajena
        validar_exportable(solicitud)

        datos = await recopilar_datos(self.db, solicitud)
        contenido = a_json(datos) if formato == "json" else a_csv(datos)
        cuenta = conteos(datos)
        # Se leen antes del commit: después, el ORM podría expirar los atributos
        codigo, sid, tipo = solicitud.codigo_seguimiento, solicitud.id, solicitud.tipo

        from app.infrastructure.repositories.bitacora_repository import BitacoraRepository

        BitacoraRepository(self.db).registrar(
            accion=ACCION_BITACORA, entidad="solicitudes_arcop", entidad_id=sid, actor=actor,
            detalle={"tipo_solicitud": tipo, "formato": formato, **cuenta},
        )
        await self.db.commit()
        media = "application/json; charset=utf-8" if formato == "json" else "text/csv; charset=utf-8"
        return Exportacion(contenido, media, nombre_archivo(codigo, formato), cuenta)

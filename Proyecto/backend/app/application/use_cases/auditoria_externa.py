"""
HU-09 · Como Auditor Externo, quiero exportar un log inmutable con el historial de
modificaciones y supresiones de datos, para demostrar la trazabilidad requerida por el
Art. 14 ter de la Ley N.º 21.719.

  Consulta      registros del audit_log con filtros (fechas, categoría, acción, entidad...).
  Verificación  cadena HMAC + sellos por lote (audit_log_lotes.verificar_lotes).
  Exportación   ZIP con lotes COMPLETOS: audit_log.jsonl (verificable), audit_log.csv
                (lectura), lotes.json, verificacion.json, manifiesto.json (SHA-256 de cada
                archivo), verificar_exportacion.py (solo librería estándar) y LEEME.txt.
                El auditor recalcula los hashes de lote sin pedirnos nada.
  Auditores     el admin crea, extiende o desactiva cuentas de auditor (vencen solas).

Cada consulta, verificación y exportación queda en el propio audit_log (quién accedió a
un registro que contiene IPs también es trazable).
"""
from __future__ import annotations

import asyncio
import csv
import hashlib
import io
import json
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.autenticacion import Actor, Rol, hash_password
from app.core.config import settings
from app.domain import auditoria_hash
from app.domain.models.auditoria_externa import ALGORITMO_LOTE, UsuarioAuditor
from app.domain.models.bitacora_auditoria import BitacoraAuditoria
from app.infrastructure.repositories import audit_log_lotes
from app.infrastructure.repositories.bitacora_cadena import filas_en_orden
from app.infrastructure.repositories.bitacora_repository import Accion, BitacoraRepository, categoria

LEY = "Ley N.º 21.719, art. 14 ter (deber de trazabilidad)"
SCRIPT_VERIFICACION = Path(__file__).resolve().parents[2] / "domain" / "verificar_exportacion.py"
_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")


class AuditoriaError(Exception):
    def __init__(self, mensaje: str, codigo: str, status_code: int = 400):
        super().__init__(mensaje)
        self.codigo = codigo
        self.status_code = status_code


def _ahora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso(valor: datetime | None) -> str | None:
    return valor.replace(tzinfo=None).isoformat(timespec="microseconds") if valor else None


def registro_dict(f) -> dict:
    """Fila del log para la API y la exportación (acepta la entidad ORM o el dict de filas_en_orden)."""
    d = f if isinstance(f, dict) else {
        "id": f.id, "fecha": f.fecha, "actor_rol": f.actor_rol, "actor_id": f.actor_id, "accion": f.accion,
        "entidad": f.entidad, "entidad_id": f.entidad_id, "resultado": f.resultado, "detalle": f.detalle,
        "ip": f.ip, "hash_anterior": f.hash_anterior, "hash": f.hash}
    return {
        "id": d["id"], "fecha": _iso(d["fecha"]) if isinstance(d["fecha"], datetime) else d["fecha"],
        "actor_rol": d["actor_rol"], "actor_id": d["actor_id"], "ip": d["ip"],
        "accion": d["accion"], "categoria": categoria(d["accion"]),
        "entidad": d["entidad"], "entidad_id": d["entidad_id"], "resultado": d["resultado"],
        "detalle": d["detalle"], "hash_anterior": d["hash_anterior"], "hash": d["hash"],
    }


def _validar_rango(desde: datetime | None, hasta: datetime | None) -> None:
    if desde and hasta and hasta <= desde:
        raise AuditoriaError("La fecha 'hasta' debe ser posterior a 'desde'.", "RANGO_INVALIDO", 422)


def _sin_tz(valor: datetime | None) -> datetime | None:
    """Las fechas del log son UTC sin zona: una fecha con zona se convierte a UTC."""
    if valor is None or valor.tzinfo is None:
        return valor
    return valor.astimezone(timezone.utc).replace(tzinfo=None)


# ====================================================================== consulta y verificación
class ConsultaAuditLog:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def registros(self, actor: Actor, *, desde=None, hasta=None, categoria_: str | None = None,
                        accion: str | None = None, entidad: str | None = None, entidad_id: int | None = None,
                        resultado: str | None = None, actor_rol: str | None = None,
                        page: int = 1, size: int = 50) -> dict:
        desde, hasta = _sin_tz(desde), _sin_tz(hasta)
        _validar_rango(desde, hasta)
        try:
            filas, total = await BitacoraRepository(self.db).listar(
                desde=desde, hasta=hasta, categoria=categoria_, accion=accion, entidad=entidad,
                entidad_id=entidad_id, resultado=resultado, actor_rol=actor_rol, page=page, size=size)
        except ValueError as e:
            raise AuditoriaError(str(e), "FILTRO_INVALIDO", 422)
        filtros = {k: v for k, v in {"desde": _iso(desde), "hasta": _iso(hasta), "categoria": categoria_,
                                     "accion": accion, "entidad": entidad, "entidad_id": entidad_id,
                                     "resultado": resultado, "actor_rol": actor_rol}.items() if v is not None}
        BitacoraRepository(self.db).registrar(
            accion=Accion.AUDITORIA_CONSULTA, entidad="audit_log", actor=actor,
            detalle={"filtros": filtros, "page": page, "size": size, "total": total})
        await self.db.commit()
        return {"items": [registro_dict(f) for f in filas], "total": total, "page": page, "size": size,
                "filtros": filtros}

    async def verificar(self, actor: Actor) -> dict:
        resultado = await audit_log_lotes.verificar_lotes(self.db)
        BitacoraRepository(self.db).registrar(
            accion=Accion.AUDITORIA_VERIFICACION, entidad="audit_log", actor=actor,
            resultado="ok" if resultado["integra"] else "rechazado",
            detalle={"integra": resultado["integra"], "lotes": resultado["lotes"]["total"],
                     "lotes_con_falla": resultado["lotes"]["con_falla"],
                     "filas": resultado["filas"]["total"], "ultimo_lote": resultado["ancla"]["ultimo_lote"]})
        await self.db.commit()
        return resultado

    async def lotes(self, page: int = 1, size: int = 50) -> dict:
        filas, total = await audit_log_lotes.listar_sellos(self.db, page, size)
        return {"items": [{**audit_log_lotes.sello_dict(s), "fecha": _iso(s.fecha)} for s in filas],
                "total": total, "page": page, "size": size, "algoritmo": ALGORITMO_LOTE}


# ====================================================================== exportación
@dataclass
class Exportacion:
    contenido: bytes
    nombre: str
    sha256: str
    filas: int
    lotes: tuple[int, int]


_LEEME = """\
EXPORTACIÓN DEL LOG INMUTABLE (audit_log) — ComplianceIA / Therion Labs
{ley}

Generado (UTC): {generado}
Rango pedido (UTC): desde {desde} hasta {hasta} (sin incluir 'hasta')
Lotes incluidos: {lote_ini} a {lote_fin} ({filas} registros). Se entregan lotes COMPLETOS: pueden
aparecer algunos registros justo antes o después del rango pedido (si se recortara un lote,
su hash ya no se podría recalcular).

ARCHIVOS
  audit_log.jsonl       un registro por línea; es el archivo que se verifica.
  audit_log.csv         los mismos registros para leer o filtrar en una planilla
                        (columna 'categoria': modificacion, supresion, creacion, acceso,
                        seguridad, auditoria).
  lotes.json            el sello de cada lote: hash_lote, sello y sello_anterior.
  verificacion.json     resultado de la verificación del log COMPLETO hecha por el sistema
                        al momento de exportar (incluye la cadena HMAC, que requiere la clave).
  manifiesto.json       SHA-256 de cada archivo y datos de la exportación.
  verificar_exportacion.py  verificación independiente (Python 3.10+, solo librería estándar).

CÓMO VERIFICAR (sin depender de nosotros)
  python verificar_exportacion.py .            (en la carpeta descomprimida)
  python verificar_exportacion.py . --ancla <sello que anotó en una exportación anterior>

  El script recalcula el SHA-256 de cada archivo, el hash de cada lote a partir de sus
  registros (cualquier registro alterado, agregado, quitado o reordenado lo cambia), la
  cadena de sellos y el enlace entre registros (hash_anterior). Con --ancla comprueba que
  un sello ya conocido sigue siendo exactamente el mismo: el log no se reescribió.

  Recomendación: anote el 'ultimo_sello' del manifiesto. En la próxima exportación úselo
  como --ancla; si el sistema hubiera alterado cualquier registro anterior, no coincidirá.

DATOS PERSONALES
  La columna 'ip' es un dato personal (Ley 21.719). Úsela solo para la auditoría y no la
  comparta fuera de ella. 'detalle' no contiene nombres, correos ni textos libres.
"""


class ExportarAuditLog:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def generar(self, actor: Actor, desde: datetime | None = None, hasta: datetime | None = None) -> Exportacion:
        desde, hasta = _sin_tz(desde), _sin_tz(hasta)
        _validar_rango(desde, hasta)
        # 1) Sellar lo pendiente: así la exportación cubre todo lo registrado hasta ahora.
        #    Se confirma enseguida: el sellado toma el lock del log y armar el ZIP no debe
        #    frenar mientras tanto los registros del resto del sistema.
        await audit_log_lotes.sellar_pendientes(self.db)
        await self.db.commit()
        sellos = await audit_log_lotes.sellos_que_cubren(self.db, desde, hasta)
        if not sellos:
            raise AuditoriaError("No hay registros en el rango pedido.", "SIN_REGISTROS", 404)
        filas_total = sum(s.cantidad for s in sellos)
        if filas_total > settings.AUDIT_EXPORT_MAX_FILAS:
            raise AuditoriaError(
                f"El rango tiene {filas_total} registros y el máximo por exportación es "
                f"{settings.AUDIT_EXPORT_MAX_FILAS}: acota las fechas.", "EXPORTACION_DEMASIADO_GRANDE", 413)

        registros: list[dict] = []
        lote_de: dict[int, int] = {}
        for s in sellos:
            async for f in filas_en_orden(self.db, desde_id=s.desde_id - 1, hasta_id=s.hasta_id):
                registros.append(registro_dict(f))
                lote_de[f["id"]] = s.id
        verificacion = await audit_log_lotes.verificar_lotes(self.db)
        generado = _ahora()
        archivos = await asyncio.to_thread(self._archivos, registros, lote_de, sellos, verificacion,
                                           desde, hasta, generado, actor)
        contenido = await asyncio.to_thread(self._zip, archivos)
        sha = hashlib.sha256(contenido).hexdigest()
        nombre = f"audit_log_lotes_{sellos[0].id}-{sellos[-1].id}_{generado:%Y%m%dT%H%M%SZ}.zip"

        BitacoraRepository(self.db).registrar(
            accion=Accion.AUDITORIA_EXPORTACION, entidad="audit_log", actor=actor,
            detalle={"desde": _iso(desde), "hasta": _iso(hasta), "lote_inicial": sellos[0].id,
                     "lote_final": sellos[-1].id, "filas": len(registros), "sha256_zip": sha,
                     "ultimo_sello": sellos[-1].sello, "log_integro": verificacion["integra"]})
        await self.db.commit()
        return Exportacion(contenido, nombre, sha, len(registros), (sellos[0].id, sellos[-1].id))

    @staticmethod
    def _archivos(registros, lote_de, sellos, verificacion, desde, hasta, generado, actor) -> dict[str, bytes]:
        def jdump(obj) -> bytes:
            return json.dumps(obj, ensure_ascii=False, indent=2, default=str).encode()

        jsonl = "".join(json.dumps({**r, "lote": lote_de[r["id"]]}, ensure_ascii=False, sort_keys=True,
                                   separators=(",", ":"), default=str) + "\n" for r in registros).encode()
        buf = io.StringIO()
        w = csv.writer(buf)
        columnas = ["id", "fecha", "actor_rol", "actor_id", "ip", "accion", "categoria", "entidad",
                    "entidad_id", "resultado", "detalle", "lote", "hash_anterior", "hash"]
        w.writerow(columnas)
        for r in registros:
            w.writerow([*(r[c] for c in columnas[:10]),
                        json.dumps(r["detalle"], ensure_ascii=False, sort_keys=True) if r["detalle"] is not None else "",
                        lote_de[r["id"]], r["hash_anterior"], r["hash"]])
        csv_bytes = ("﻿" + buf.getvalue()).encode()  # BOM: Excel abre bien las tildes
        lotes = [{**audit_log_lotes.sello_dict(s), "fecha": _iso(s.fecha)} for s in sellos]
        archivos = {
            "audit_log.jsonl": jsonl,
            "audit_log.csv": csv_bytes,
            "lotes.json": jdump(lotes),
            "verificacion.json": jdump(verificacion),
            "verificar_exportacion.py": SCRIPT_VERIFICACION.read_bytes(),
            "LEEME.txt": _LEEME.format(ley=LEY, generado=_iso(generado), desde=_iso(desde) or "el inicio",
                                       hasta=_iso(hasta) or "ahora", lote_ini=sellos[0].id,
                                       lote_fin=sellos[-1].id, filas=len(registros)).encode(),
        }
        manifiesto = {
            "formato": "complianceia-audit-log-export/1",
            "ley": LEY,
            "generado_en": _iso(generado),
            "generado_por": {"rol": actor.rol, "id": actor.id},
            "rango_pedido": {"desde": _iso(desde), "hasta": _iso(hasta)},
            "lotes": {"primero": sellos[0].id, "ultimo": sellos[-1].id, "cantidad": len(sellos)},
            "registros": len(registros),
            "sello_anterior_al_primer_lote": sellos[0].sello_anterior,
            "ultimo_sello": sellos[-1].sello,
            "algoritmos": {
                "lote": ALGORITMO_LOTE,
                "huella_registro": "sha256('<id>|' + canonico(registro))",
                "hash_lote": "sha256('\\n'.join(huella_registro))",
                "sello": "sha256(canonico_sello) encadenado por sello_anterior",
                "canonico": "JSON con claves ordenadas, sin espacios, ensure_ascii=False (ver verificar_exportacion.py)",
            },
            "log_integro_al_exportar": verificacion["integra"],
            "archivos": {n: hashlib.sha256(c).hexdigest() for n, c in archivos.items()},
        }
        archivos["manifiesto.json"] = jdump(manifiesto)
        return archivos

    @staticmethod
    def _zip(archivos: dict[str, bytes]) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for nombre, contenido in archivos.items():
                info = zipfile.ZipInfo(nombre, date_time=(2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                z.writestr(info, contenido)
        return buf.getvalue()


# ====================================================================== cuentas de auditor
def auditor_dict(a: UsuarioAuditor) -> dict:
    return {"id": a.id, "email": a.email, "organizacion": a.organizacion, "activo": a.activo,
            "vigente": a.vigente(_ahora()), "fecha_creacion": a.fecha_creacion,
            "fecha_expiracion": a.fecha_expiracion, "ultimo_acceso": a.ultimo_acceso}


class GestionarAuditoresUseCase:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _validar_password(password: str) -> None:
        if len(password or "") < settings.AUDITOR_PASSWORD_MIN:
            raise AuditoriaError(f"La contraseña debe tener al menos {settings.AUDITOR_PASSWORD_MIN} caracteres.",
                                 "PASSWORD_DEBIL", 422)

    @staticmethod
    def _validar_dias(dias: int) -> None:
        if not 1 <= int(dias) <= settings.AUDITOR_VIGENCIA_MAX_DIAS:
            raise AuditoriaError(f"La vigencia debe estar entre 1 y {settings.AUDITOR_VIGENCIA_MAX_DIAS} días.",
                                 "VIGENCIA_INVALIDA", 422)

    async def crear(self, admin: Actor | None, email: str, organizacion: str, password: str,
                    dias_vigencia: int) -> UsuarioAuditor:
        email = (email or "").strip().lower()
        organizacion = " ".join((organizacion or "").split())
        if not _EMAIL.match(email) or len(email) > 100:
            raise AuditoriaError("Correo inválido.", "EMAIL_INVALIDO", 422)
        if not 2 <= len(organizacion) <= 120:
            raise AuditoriaError("Indica la organización auditora (2 a 120 caracteres).", "ORGANIZACION_INVALIDA", 422)
        self._validar_password(password)
        self._validar_dias(dias_vigencia)
        existe = await self.db.scalar(select(func.count()).select_from(UsuarioAuditor)
                                      .where(func.lower(UsuarioAuditor.email) == email))
        if existe:
            raise AuditoriaError("Ya existe una cuenta de auditor con ese correo.", "AUDITOR_DUPLICADO", 409)
        ahora = _ahora()
        auditor = UsuarioAuditor(
            email=email, organizacion=organizacion,
            password_hash=await asyncio.to_thread(hash_password, password),
            activo=True, fecha_creacion=ahora, fecha_expiracion=ahora + timedelta(days=int(dias_vigencia)),
            creado_por_admin_id=admin.id if admin and admin.es_admin else None)
        self.db.add(auditor)
        await self.db.flush()
        BitacoraRepository(self.db).registrar(
            accion=Accion.AUDITOR_CREADO, entidad="usuario_auditor", entidad_id=auditor.id,
            actor=admin, actor_rol=None if admin else "sistema",
            detalle={"dias_vigencia": int(dias_vigencia), "fecha_expiracion": _iso(auditor.fecha_expiracion)})
        await self.db.commit()
        return auditor

    async def actualizar(self, admin: Actor | None, auditor_id: int, *, activo: bool | None = None,
                         dias_vigencia: int | None = None, password: str | None = None) -> UsuarioAuditor:
        from app.application.use_cases.sesiones import cerrar_todas
        from app.domain.models.sesion import MotivoCierre

        auditor = await self.db.get(UsuarioAuditor, auditor_id)
        if auditor is None:
            raise AuditoriaError("Auditor no encontrado.", "AUDITOR_NO_ENCONTRADO", 404)
        ahora = _ahora()
        cambios: list[str] = []
        if dias_vigencia is not None:
            self._validar_dias(dias_vigencia)
            auditor.fecha_expiracion = ahora + timedelta(days=int(dias_vigencia))
            cambios.append("vigencia")
        if password is not None:
            self._validar_password(password)
            auditor.password_hash = await asyncio.to_thread(hash_password, password)
            cambios.append("password")
        if activo is not None and activo != auditor.activo:
            auditor.activo = activo
            cambios.append("activado" if activo else "desactivado")
        if not cambios:
            raise AuditoriaError("No hay cambios que aplicar.", "SIN_CAMBIOS", 422)
        sesiones = 0
        if "password" in cambios or "desactivado" in cambios:
            sesiones = await cerrar_todas(self.db, Rol.AUDITOR_EXTERNO.value, auditor.id,
                                          MotivoCierre.CAMBIO_CONTRASENA if "password" in cambios else MotivoCierre.DESACTIVACION,
                                          ahora)
        BitacoraRepository(self.db).registrar(
            accion=Accion.AUDITOR_ACTUALIZADO, entidad="usuario_auditor", entidad_id=auditor.id,
            actor=admin, actor_rol=None if admin else "sistema",
            detalle={"cambios": cambios, "activo": auditor.activo,
                     "fecha_expiracion": _iso(auditor.fecha_expiracion), "sesiones_cerradas": sesiones})
        await self.db.commit()
        return auditor

    async def listar(self) -> list[UsuarioAuditor]:
        return list((await self.db.execute(select(UsuarioAuditor).order_by(UsuarioAuditor.id.desc()))).scalars().all())

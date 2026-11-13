"""
HU-40 criterio 4 · Paquete de evidencia de una revisión interna (ZIP verificable con hash).

Sigue el mismo esquema que la exportación del log inmutable para el Auditor Externo (HU-09,
app/application/use_cases/auditoria_externa.py): archivos de lectura y de verificación, un manifiesto con
el SHA-256 de cada archivo y un script que lo comprueba todo con la librería estándar de Python, sin
depender de la plataforma.

  LEEME.txt                               qué contiene y cómo verificarlo
  manifiesto.json                         código del paquete, revisión, versión y huella del registro, y el
                                          SHA-256 de cada archivo
  verificar_paquete.py                    verificación independiente (Python 3.10+)
  informe/                                el informe del RAT de esa versión (PDF y Excel), si sigue en
                                          "Mis documentos"
  revision/constancia_revision.pdf        el informe de la revisión interna
  revision/lista_verificacion.{csv,json}  cada punto revisado: resultado, decisión, justificación y fecha
  revision/observaciones.{csv,json}       observaciones con su apertura y su cierre
  historial/versiones_actividades.json    la versión vigente de cada actividad (instantánea y huella): con
                                          ella el script recalcula la huella del registro
  historial/registro_auditoria.{jsonl,csv} los cambios del registro, del mapa y de la revisión (audit_log),
                                          con el hash de cada registro (cruzable con la exportación del
                                          Auditor Externo). Sin direcciones IP.
  historial/emisiones_informe.json        los informes emitidos de esta versión
  historial/diferencias.json              qué cambió desde la revisión anterior (si la hay)

El ZIP es determinista (fechas internas fijas y orden estable): el mismo contenido produce el mismo hash.
La plataforma guarda el SHA-256 del ZIP con su código, así puede confirmar que un paquete que le muestran
es exactamente el que exportó.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from app.application.informes.ficha import digito_verificador

FORMATO = "complianceia-revision-rat/1"
PREFIJO_CODIGO = "CIA-PAQ"
SCRIPT = Path(__file__).resolve().parents[2] / "domain" / "rat" / "verificar_paquete.py"
FECHA_ZIP = (2026, 1, 1, 0, 0, 0)
MAX_ARCHIVOS = 60
MAX_DESCOMPRIMIDO = 150 * 1024 * 1024


def codigo(paquete_id: int, anio: int) -> str:
    return f"{PREFIJO_CODIGO}-{anio:04d}-{paquete_id:06d}-{digito_verificador(paquete_id)}"


def leer_codigo(texto: str) -> tuple[int, int] | None:
    t = (texto or "").strip().upper().replace(" ", "")
    if not t.startswith(PREFIJO_CODIGO + "-"):
        return None
    partes = t[len(PREFIJO_CODIGO) + 1:].split("-")
    if len(partes) != 3 or not (partes[0].isdigit() and partes[1].isdigit()):
        return None
    if digito_verificador(int(partes[1])) != partes[2]:
        return None
    return int(partes[0]), int(partes[1])


def canonico(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _json(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True, default=str).encode("utf-8")


def _csv(columnas: list[str], filas: list[list]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(columnas)
    for f in filas:
        # Ningún texto se escribe como fórmula (inyección en planillas)
        w.writerow([("'" + v) if isinstance(v, str) and v[:1] in ("=", "+", "-", "@") else v for v in f])
    return ("﻿" + buf.getvalue()).encode("utf-8")


@dataclass
class DatosPaquete:
    codigo: str
    empresa: str
    generado: str                    # ISO (UTC)
    revision: dict                   # numero, estado, version_rat, huella, fechas, revisor, cargo, conclusion
    lista: list[dict]                # objetos consolidados de la lista de verificación
    observaciones: list[dict]
    versiones: list[dict]            # [{actividad_id, numero, estado, huella, fecha, contenido}]
    auditoria: list[dict]            # registros del audit_log (sin ip)
    emisiones: list[dict]
    diferencias: dict | None
    constancia_pdf: bytes
    informe: dict = field(default_factory=dict)      # {"nombre.pdf": bytes, "nombre.xlsx": bytes}
    notas: list[str] = field(default_factory=list)
    # False si alguna actividad no tiene versión vigente (revisión en curso): el manifiesto no trae la huella a recalcular
    huella_recalculable: bool = True


_LEEME = """\
PAQUETE DE EVIDENCIA DE LA REVISIÓN INTERNA DEL REGISTRO — ComplianceIA / Therion Labs
Registro de Actividades de Tratamiento (Ley N.º 21.719 y su reglamento)

Empresa: {empresa}
Código del paquete: {codigo}
Revisión interna N.º {numero} · {estado}
Versión del registro: {version} · huella {huella}
Generado (UTC): {generado}

QUÉ CONTIENE
  informe/                       el informe del registro de esta versión (PDF para presentar y Excel).
  revision/constancia_revision.pdf  el informe de la revisión interna (portada, lista de verificación,
                                 observaciones y diferencias con la revisión anterior).
  revision/lista_verificacion.*  cada punto revisado por actividad y por elemento del mapa de datos:
                                 resultado de la plataforma, decisión de quien revisó, justificación y fecha.
  revision/observaciones.*       las observaciones: qué se observó, cuándo, cómo se cerró y si el elemento
                                 cambió entre la apertura y el cierre.
  historial/versiones_actividades.json  la versión vigente de cada actividad con su huella.
  historial/registro_auditoria.* los cambios del registro, del mapa y de la revisión, con el hash de cada
                                 registro del log inmutable de la plataforma.
  historial/emisiones_informe.json      los informes del registro emitidos para esta versión.
  historial/diferencias.json     qué cambió desde la revisión anterior.
  manifiesto.json                el SHA-256 de cada archivo.
  verificar_paquete.py           verificación independiente.

CÓMO VERIFICAR (sin depender de la plataforma)
  1. Descomprime el ZIP en una carpeta.
  2. Ejecuta:  python verificar_paquete.py .
  El script comprueba el SHA-256 de cada archivo contra el manifiesto, que no sobren ni falten archivos,
  recalcula la huella de cada versión de actividad y, con ellas, la huella del registro que figura en el
  informe y en la constancia. Si alguien cambió una coma de cualquier archivo, la verificación falla.

  También puedes subir el ZIP en ComplianceIA (Registro de actividades › Revisión interna › Verificar un
  paquete): la plataforma confirma que es exactamente el paquete que exportó con este código.

  El hash de cada registro de historial/registro_auditoria.* coincide con el de la exportación del log
  inmutable que la plataforma entrega al Auditor Externo: así se puede cruzar este historial con esa
  exportación.

DATOS PERSONALES
  El paquete describe actividades de la organización. Contiene el nombre y el cargo de quien hizo la
  revisión (los indicó para la constancia). Las direcciones IP del log se omiten. Compártelo solo con
  quien deba verificar el registro (encargado de prevención, certificador o directorio).
{notas}"""


def archivos(d: DatosPaquete) -> dict[str, bytes]:
    """Todos los archivos del paquete, con el manifiesto al final (lleva el SHA-256 de los demás)."""
    a: dict[str, bytes] = {}
    for nombre, contenido in sorted(d.informe.items()):
        a[f"informe/{nombre}"] = contenido
    a["revision/constancia_revision.pdf"] = d.constancia_pdf

    filas_lista, puntos = [], []
    for o in d.lista:
        for i in o["items"]:
            puntos.append({"objeto": o["clave"], "tipo": o["tipo"], "nombre": o["nombre"], "criterio": i["codigo"],
                           "titulo": i["titulo"], "resultado": i["resultado"], "detalle": i["detalle"],
                           "bloqueante": i.get("bloqueante", False), "revision": i["revision"],
                           "justificacion": i.get("nota"), "fecha_revision": i.get("fecha_revision")})
            filas_lista.append([o["clave"], o["tipo"], o["nombre"], i["titulo"], i["resultado"], i["detalle"],
                                i["revision"], i.get("nota") or "", i.get("fecha_revision") or ""])
    a["revision/lista_verificacion.json"] = _json({"objetos": len(d.lista), "puntos": puntos})
    a["revision/lista_verificacion.csv"] = _csv(
        ["objeto", "tipo", "nombre", "criterio", "resultado", "detalle", "revision", "justificacion",
         "fecha_revision"], filas_lista)

    a["revision/observaciones.json"] = _json(d.observaciones)
    a["revision/observaciones.csv"] = _csv(
        ["numero", "objeto", "nombre", "criterio", "prioridad", "estado", "observacion", "abierta", "cerrada",
         "como_se_cerro", "el_elemento_cambio"],
        [[x["numero"], x["objeto_clave"], x["objeto_nombre"], x.get("criterio_titulo") or "", x["prioridad"],
          x["estado"], x["texto"], x["fecha_apertura"], x.get("fecha_cierre") or "", x.get("nota_cierre") or "",
          "" if x.get("objeto_cambio") is None else ("sí" if x["objeto_cambio"] else "no")]
         for x in d.observaciones])

    a["historial/versiones_actividades.json"] = _json({
        "algoritmo_version": "sha256(json({'actividad','mapa'}, sort_keys, ensure_ascii=False, separators=(',',':')))",
        "algoritmo_registro": "sha256(json({'formato':1,'actividades':[[id,'vigente',version,huella,estado]...]}))",
        "versiones": d.versiones})
    a["historial/registro_auditoria.jsonl"] = b"".join(canonico(r) + b"\n" for r in d.auditoria)
    a["historial/registro_auditoria.csv"] = _csv(
        ["id", "fecha", "actor_rol", "accion", "entidad", "entidad_id", "resultado", "detalle", "hash_anterior",
         "hash"],
        [[r["id"], r["fecha"], r["actor_rol"], r["accion"], r["entidad"], r["entidad_id"], r["resultado"],
          json.dumps(r["detalle"], ensure_ascii=False, sort_keys=True) if r["detalle"] is not None else "",
          r["hash_anterior"], r["hash"]] for r in d.auditoria])
    a["historial/emisiones_informe.json"] = _json(d.emisiones)
    if d.diferencias is not None:
        a["historial/diferencias.json"] = _json(d.diferencias)
    a["verificar_paquete.py"] = SCRIPT.read_bytes()
    r = d.revision
    a["LEEME.txt"] = _LEEME.format(
        empresa=d.empresa, codigo=d.codigo, numero=r["numero"],
        estado="REVISADA (constancia)" if r["estado"] == "revisada" else "EN CURSO (todavía no es una constancia)",
        version=f"N.º {r['version_rat']}" if r.get("version_rat") else "sin marcar",
        huella=(r.get("huella") or "")[:16].upper() or "—", generado=d.generado,
        notas=("\nNOTAS\n" + "".join(f"  - {n}\n" for n in d.notas)) if d.notas else "").encode("utf-8")

    manifiesto = {
        "formato": FORMATO,
        "codigo": d.codigo,
        "empresa": d.empresa,
        "generado_en": d.generado,
        "revision": r,
        "huella_registro": r.get("huella") if d.huella_recalculable else None,
        "algoritmos": {"archivo": "sha256", "canonico": "JSON con claves ordenadas, sin espacios, ensure_ascii=False"},
        "archivos": {n: hashlib.sha256(c).hexdigest() for n, c in sorted(a.items())},
    }
    a["manifiesto.json"] = _json(manifiesto)
    return a


def comprimir(a: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for nombre in sorted(a):
            info = zipfile.ZipInfo(nombre, date_time=FECHA_ZIP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, a[nombre])
    return buf.getvalue()


def huella_manifiesto(a: dict[str, bytes]) -> str:
    return hashlib.sha256(a["manifiesto.json"]).hexdigest()


@dataclass
class ResultadoVerificacion:
    integro: bool
    manifiesto: dict | None
    alterados: list[str]
    faltantes: list[str]
    sobrantes: list[str]
    error: str | None = None


def verificar_zip(contenido: bytes) -> ResultadoVerificacion:
    """Comprueba el ZIP contra su manifiesto (sin confiar en él: tamaño y cantidad acotados)."""
    try:
        z = zipfile.ZipFile(io.BytesIO(contenido))
    except zipfile.BadZipFile:
        return ResultadoVerificacion(False, None, [], [], [], "El archivo no es un ZIP válido.")
    with z:
        infos = z.infolist()
        if len(infos) > MAX_ARCHIVOS or sum(i.file_size for i in infos) > MAX_DESCOMPRIMIDO:
            return ResultadoVerificacion(False, None, [], [], [], "El ZIP no tiene la forma de un paquete de evidencia.")
        nombres = {i.filename for i in infos if not i.is_dir()}
        if "manifiesto.json" not in nombres:
            return ResultadoVerificacion(False, None, [], [], [], "El ZIP no trae el manifiesto del paquete.")
        try:
            manifiesto = json.loads(z.read("manifiesto.json").decode("utf-8"))
            esperado = dict(manifiesto["archivos"])
        except (ValueError, KeyError, TypeError):
            return ResultadoVerificacion(False, None, [], [], [], "El manifiesto del paquete está dañado.")
        if manifiesto.get("formato") != FORMATO:
            return ResultadoVerificacion(False, manifiesto, [], [], [], "No es un paquete de evidencia de la revisión.")
        alterados = sorted(n for n, h in esperado.items()
                           if n in nombres and hashlib.sha256(z.read(n)).hexdigest() != h)
        faltantes = sorted(n for n in esperado if n not in nombres)
        sobrantes = sorted(n for n in nombres if n not in esperado and n != "manifiesto.json")
    return ResultadoVerificacion(not (alterados or faltantes or sobrantes), manifiesto, alterados, faltantes, sobrantes)

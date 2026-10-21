"""
T-06 — Auditoría de minimización de datos sobre la base de datos REAL.

Qué hace (todo en una transacción de SOLO LECTURA; nunca imprime valores, solo conteos):

  1. Lee el esquema de PostgreSQL (tablas, columnas, tipos, PK y FK).
  2. Lo cruza con el inventario de app/core/catalogo_datos_personales.py:
     columna sin clasificar o clasificada pero inexistente = hallazgo.
  3. Revisa el CONTENIDO de las columnas según su clasificación:
       pii     -> cuenta filas con RUT (dígito verificador válido), correos o
                  teléfonos chilenos en claro
       cifrado -> cuenta valores que no llevan el prefijo enc:v1:
       nulo    -> cuenta valores que deberían ser NULL
  4. Controles de conservación: correos de titulares ya anonimizados o vencidos,
     solicitudes ARCOP cerradas con texto, eventos de seguridad revisados con extracto.
  5. Genera en --salida:
       der.mmd                   DER completo en Mermaid (columnas con datos personales marcadas)
       der_datos_personales.mmd  DER reducido: solo tablas con datos personales
       der.html                  el mismo DER listo para abrir en el navegador
       matriz_minimizacion.csv   una fila por columna: categoría, finalidad, base, plazo...
       informe_auditoria.md      resultado de cada control y lista de hallazgos

Uso (desde Proyecto/, con el sistema levantado):

    # Con el rol de solo lectura (recomendado, ver scripts/sql/t06_rol_auditor.sql)
    docker compose exec worker python scripts/auditoria_minimizacion.py \
        --url "postgresql+psycopg2://auditor_t06:LA-CLAVE@db:5432/complaince_db" --salida /tmp/t06
    docker compose cp worker:/tmp/t06 ./auditoria_t06

Sin --url usa DATABASE_URL_SYNC. Código de salida: 0 sin hallazgos, 1 con hallazgos.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, inspect, text  # noqa: E402

from app.core.catalogo_datos_personales import CATALOGO, Dato  # noqa: E402

# ----------------------------------------------------------------------- detectores
# Independientes del motor NER del sistema: una auditoría no debe depender solo de
# la pieza que audita.
_RE_RUT = re.compile(r"(?<![\w.])(\d{1,2}(?:\.\d{3}){2}|\d{7,8})\s?-\s?([\dkK])(?![\w])")
_RE_CORREO = re.compile(r"[\w.+%-]+@[\w-]+(?:\.[\w-]+)+", re.UNICODE)
_RE_TELEFONO = re.compile(r"(?<!\d)(?:\+?56[\s.-]?)?9[\s.-]?\d{4}[\s.-]?\d{4}(?!\d)")


def _dv_valido(cuerpo: str, dv: str) -> bool:
    numero = cuerpo.replace(".", "")
    suma, factor = 0, 2
    for d in reversed(numero):
        suma += int(d) * factor
        factor = 2 if factor == 7 else factor + 1
    resto = 11 - suma % 11
    esperado = {11: "0", 10: "K"}.get(resto, str(resto))
    return dv.upper() == esperado


def tipos_pii(valor: str) -> set[str]:
    """Tipos de PII en claro encontrados en un texto (sin devolver los valores)."""
    encontrados = set()
    if any(_dv_valido(c, dv) for c, dv in _RE_RUT.findall(valor)):
        encontrados.add("rut")
    if _RE_CORREO.search(valor):
        encontrados.add("correo")
    if _RE_TELEFONO.search(valor):
        encontrados.add("telefono")
    return encontrados


# ----------------------------------------------------------------------- utilidades
def _q(nombre: str) -> str:
    return '"' + nombre.replace('"', '""') + '"'


def _tipo_corto(tipo: str) -> str:
    t = tipo.lower()
    for largo, corto in (("character varying", "varchar"), ("timestamp without time zone", "timestamp"),
                         ("double precision", "float"), ("integer", "int")):
        t = t.replace(largo, corto)
    return re.sub(r"[^a-z0-9_]", "_", t.split("(")[0])


class Auditoria:
    def __init__(self, conn, plazos: dict[str, int | None]):
        self.conn = conn
        self.hoy = date.today()
        self.plazos = plazos
        self.hallazgos: list[str] = []
        self.controles: list[tuple[str, str, str]] = []  # (control, resultado, detalle)

    def ok(self, control: str, detalle: str = "") -> None:
        self.controles.append((control, "OK", detalle))

    def falla(self, control: str, detalle: str) -> None:
        self.controles.append((control, "HALLAZGO", detalle))
        self.hallazgos.append(f"{control}: {detalle}")

    def info(self, control: str, detalle: str) -> None:
        self.controles.append((control, "INFO", detalle))

    def escalar(self, sql: str, **params) -> int:
        return int(self.conn.execute(text(sql), params).scalar() or 0)


# ----------------------------------------------------------------------- 1-2. esquema
def leer_esquema(conn) -> dict:
    ins = inspect(conn)
    esquema = {}
    for tabla in sorted(ins.get_table_names()):
        if tabla == "alembic_version":
            continue
        pk = set(ins.get_pk_constraint(tabla).get("constrained_columns") or [])
        fks = {}
        for fk in ins.get_foreign_keys(tabla):
            for col, ref in zip(fk["constrained_columns"], fk["referred_columns"]):
                fks[col] = (fk["referred_table"], ref)
        esquema[tabla] = {
            "columnas": [
                {"nombre": c["name"], "tipo": str(c["type"]), "nulo": c["nullable"],
                 "pk": c["name"] in pk, "fk": fks.get(c["name"])}
                for c in ins.get_columns(tabla)
            ],
        }
    return esquema


def cruzar_con_catalogo(a: Auditoria, esquema: dict) -> None:
    sin_clasificar, inexistentes = [], []
    for tabla, info in esquema.items():
        cols = {c["nombre"] for c in info["columnas"]}
        cat = CATALOGO.get(tabla, {})
        sin_clasificar += [f"{tabla}.{c}" for c in sorted(cols - set(cat))]
        inexistentes += [f"{tabla}.{c}" for c in sorted(set(cat) - cols)]
    inexistentes += [f"{t}.*" for t in sorted(set(CATALOGO) - set(esquema))]
    total = sum(len(i["columnas"]) for i in esquema.values())
    if sin_clasificar:
        a.falla("Inventario completo", f"columnas sin clasificar: {', '.join(sin_clasificar)}")
    else:
        a.ok("Inventario completo", f"{len(esquema)} tablas y {total} columnas clasificadas")
    if inexistentes:
        a.falla("Inventario vigente", f"clasificadas pero no existen en la BD: {', '.join(inexistentes)}")
    else:
        a.ok("Inventario vigente", "toda columna clasificada existe en la BD")


# ----------------------------------------------------------------------- 3. contenido
def revisar_contenido(a: Auditoria, esquema: dict) -> None:
    for tabla, cols in CATALOGO.items():
        if tabla not in esquema:
            continue
        existentes = {c["nombre"] for c in esquema[tabla]["columnas"]}
        for col, dato in cols.items():
            if not dato.escaneo or col not in existentes:
                continue
            control = f"Contenido {tabla}.{col} ({dato.escaneo})"
            if dato.escaneo == "nulo":
                n = a.escalar(f"SELECT count(*) FROM {_q(tabla)} WHERE {_q(col)} IS NOT NULL")
                (a.falla(control, f"{n} filas con valor (debería ser NULL)") if n
                 else a.ok(control, "todas NULL"))
            elif dato.escaneo == "cifrado":
                total = a.escalar(f"SELECT count(*) FROM {_q(tabla)} WHERE {_q(col)} IS NOT NULL")
                n = a.escalar(
                    f"SELECT count(*) FROM {_q(tabla)} WHERE {_q(col)} IS NOT NULL "
                    f"AND {_q(col)} NOT LIKE 'enc:v1:%'"
                )
                (a.falla(control, f"{n} de {total} valores sin cifrar") if n
                 else a.ok(control, f"{total} valores, todos cifrados"))
            elif dato.escaneo == "pii":
                conteo: dict[str, int] = defaultdict(int)
                filas = 0
                res = a.conn.execute(text(
                    f"SELECT CAST({_q(col)} AS TEXT) FROM {_q(tabla)} WHERE {_q(col)} IS NOT NULL"
                ))
                for (valor,) in res:
                    filas += 1
                    for tipo in tipos_pii(valor or ""):
                        conteo[tipo] += 1
                if conteo:
                    detalle = ", ".join(f"{t}: {n} filas" for t, n in sorted(conteo.items()))
                    a.falla(control, f"PII en claro en {filas} valores revisados -> {detalle}")
                else:
                    a.ok(control, f"{filas} valores revisados, sin PII en claro")


# ----------------------------------------------------------------------- 4. conservación
def revisar_conservacion(a: Auditoria) -> None:
    n = a.escalar("SELECT count(*) FROM usuario_temporal WHERE fecha_anonimizacion IS NOT NULL "
                  "AND email IS NOT NULL")
    c = "Titulares anonimizados sin correo"
    a.falla(c, f"{n} titulares anonimizados conservan su correo") if n else a.ok(c)

    # H1 de la auditoría: la supresión del encuestado público no borraba su correo opcional
    n = a.escalar("""
        SELECT count(DISTINCT u.id) FROM usuario_temporal u
        JOIN evaluacion e ON e."Usuario_temporal_id" = u.id
        JOIN solicitudes_arcop s ON s."Evaluacion_id" = e.id
        WHERE s.tipo = 'supresion' AND s.estado = 'resuelta' AND u.email IS NOT NULL""")
    c = "Supresión ARCOP del encuestado borra su correo"
    a.falla(c, f"{n} encuestados con supresión resuelta conservan el correo") if n else a.ok(c)

    n = a.escalar("SELECT count(*) FROM usuario_temporal WHERE email IS NOT NULL")
    a.info("Correos almacenados", f"{n} usuarios temporales con correo")

    plazo = a.plazos.get("RETENCION_DATOS_TITULAR_DIAS")
    if plazo is None:
        n = a.escalar("SELECT count(*) FROM usuario_temporal WHERE email IS NOT NULL "
                      "AND fecha_expiracion < :hoy", hoy=a.hoy)
        a.info("Conservación de titulares",
               f"RETENCION_DATOS_TITULAR_DIAS sin definir; {n} titulares con acceso vencido conservan el correo")
    else:
        limite = a.hoy - timedelta(days=plazo)
        n = a.escalar("SELECT count(*) FROM usuario_temporal WHERE fecha_anonimizacion IS NULL "
                      "AND fecha_expiracion < :limite", limite=limite)
        c = f"Conservación de titulares ({plazo} días tras vencer el acceso)"
        a.falla(c, f"{n} titulares superan el plazo y no están anonimizados") if n else a.ok(c)

    # ARCOP: el texto va cifrado (la auditoría no lo descifra); la anonimización por
    # conservación deja un evento 'anonimizacion' en el historial de la solicitud.
    sin_anonimizar = """SELECT count(*) FROM solicitudes_arcop s
        WHERE s.fecha_cierre IS NOT NULL {extra} AND NOT EXISTS (
            SELECT 1 FROM eventos_solicitud_arcop ev
            WHERE ev."Solicitudes_arcop_id_solicitud" = s.id_solicitud AND ev.tipo_evento = 'anonimizacion')"""
    plazo = a.plazos.get("RETENCION_ARCOP_CERRADAS_DIAS")
    if plazo is None:
        n = a.escalar(sin_anonimizar.format(extra=""))
        a.info("Conservación ARCOP", f"plazo sin definir; {n} solicitudes cerradas conservan sus textos")
    else:
        n = a.escalar(sin_anonimizar.format(extra="AND s.fecha_cierre < :limite"),
                      limite=datetime.combine(a.hoy - timedelta(days=plazo), datetime.min.time()))
        c = f"Conservación ARCOP ({plazo} días tras el cierre)"
        a.falla(c, f"{n} solicitudes superan el plazo con sus textos") if n else a.ok(c)

    plazo = a.plazos.get("RETENCION_EVENTOS_SEGURIDAD_DIAS")
    base = "SELECT count(*) FROM eventos_seguridad WHERE revisado AND extracto IS NOT NULL"
    if plazo is None:
        a.info("Conservación de eventos de seguridad",
               f"plazo sin definir; {a.escalar(base)} eventos revisados conservan su extracto")
    else:
        n = a.escalar(base + " AND fecha < :limite",
                      limite=datetime.combine(a.hoy - timedelta(days=plazo), datetime.min.time()))
        c = f"Conservación de eventos de seguridad ({plazo} días)"
        a.falla(c, f"{n} eventos revisados superan el plazo con extracto") if n else a.ok(c)


# ----------------------------------------------------------------------- 5. salidas
def _mermaid(esquema: dict, solo_personales: bool) -> str:
    """DER en Mermaid. Con solo_personales: tablas con datos personales, y de ellas
    solo PK, FK y las columnas personales (la vista para el informe)."""
    lineas, relaciones = ["erDiagram"], []
    tablas = {
        t for t, info in esquema.items()
        if not solo_personales or any(
            (d := CATALOGO.get(t, {}).get(c["nombre"])) is None or d.es_personal for c in info["columnas"])
    }
    for tabla in sorted(tablas):
        cat = CATALOGO.get(tabla, {})
        lineas.append(f"    {tabla} {{")
        for c in esquema[tabla]["columnas"]:
            d: Dato | None = cat.get(c["nombre"])
            personal = d is None or d.es_personal
            if solo_personales and not (personal or c["pk"] or c["fk"]):
                continue
            claves = ",".join(k for k, v in (("PK", c["pk"]), ("FK", c["fk"])) if v)
            nota = "SIN CLASIFICAR" if d is None else (f"DP {d.categoria} / {d.tratamiento}" if d.es_personal else "")
            atributo = f"        {_tipo_corto(c['tipo'])} {c['nombre']}"
            if claves:
                atributo += f" {claves}"
            if nota:
                atributo += f' "{nota}"'
            lineas.append(atributo)
            if c["fk"] and c["fk"][0] in tablas:
                relaciones.append(f'    {c["fk"][0]} ||--o{{ {tabla} : "{c["nombre"]}"')
        lineas.append("    }")
    return "\n".join(lineas + relaciones) + "\n"


def escribir_der(esquema: dict, salida: Path) -> None:
    completo, personales = _mermaid(esquema, False), _mermaid(esquema, True)
    (salida / "der.mmd").write_text(completo, encoding="utf-8")
    (salida / "der_datos_personales.mmd").write_text(personales, encoding="utf-8")
    bloques = "".join(
        f"<h2>{titulo}</h2><pre class='mermaid'>{codigo}</pre>"
        for titulo, codigo in (("Datos personales (tablas con DP: PK, FK y columnas personales)", personales),
                               ("Esquema completo", completo))
    )
    (salida / "der.html").write_text(
        "<!doctype html><html lang='es'><head><meta charset='utf-8'><title>DER ComplianceIA (T-06)</title>"
        "<style>body{font-family:system-ui,sans-serif;margin:16px;background:#fff;color:#111}"
        "p{max-width:70ch}</style></head><body>"
        "<h1>DER ComplianceIA</h1>"
        f"<p>Generado {datetime.now():%Y-%m-%d %H:%M} desde el esquema real de PostgreSQL. "
        "<b>DP</b> marca columnas con datos personales (categoría / tratamiento).</p>"
        f"{bloques}"
        "<script src='https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js'></script>"
        "<script>mermaid.initialize({startOnLoad:true,er:{useMaxWidth:false}});</script>"
        "</body></html>",
        encoding="utf-8",
    )


def escribir_matriz(esquema: dict, salida: Path) -> None:
    with (salida / "matriz_minimizacion.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["tabla", "columna", "tipo", "datos_personales", "categoria", "tratamiento",
                    "finalidad", "base_licitud", "conservacion", "control_contenido"])
        for tabla, info in esquema.items():
            for c in info["columnas"]:
                d = CATALOGO.get(tabla, {}).get(c["nombre"])
                if d is None:
                    w.writerow([tabla, c["nombre"], c["tipo"], "?", "SIN CLASIFICAR", "", "", "", "", ""])
                    continue
                w.writerow([tabla, c["nombre"], c["tipo"], "si" if d.es_personal else "no", d.categoria,
                            d.tratamiento, d.finalidad, d.base, d.conservacion, d.escaneo])


def escribir_informe(a: Auditoria, esquema: dict, salida: Path, url_segura: str) -> None:
    personales = sum(
        1 for t in esquema for c in esquema[t]["columnas"]
        if (d := CATALOGO.get(t, {}).get(c["nombre"])) and d.es_personal
    )
    total = sum(len(i["columnas"]) for i in esquema.values())
    l = [
        "# Auditoría de minimización de datos (T-06)", "",
        f"- Fecha: {datetime.now():%Y-%m-%d %H:%M}",
        f"- Conexión: `{url_segura}` (transacción de solo lectura)",
        f"- Esquema: {len(esquema)} tablas, {total} columnas, {personales} con datos personales",
        f"- Resultado: **{'SIN HALLAZGOS' if not a.hallazgos else f'{len(a.hallazgos)} HALLAZGOS'}**",
        "", "| Control | Resultado | Detalle |", "|---|---|---|",
    ]
    l += [f"| {c} | {r} | {d} |" for c, r, d in a.controles]
    if a.hallazgos:
        l += ["", "## Hallazgos", ""] + [f"- {h}" for h in a.hallazgos]
    l += ["", "Los valores de las columnas nunca se imprimen: solo conteos.", ""]
    (salida / "informe_auditoria.md").write_text("\n".join(l), encoding="utf-8")
    (salida / "resultado.json").write_text(json.dumps(
        {"hallazgos": a.hallazgos, "controles": a.controles}, ensure_ascii=False, indent=1), encoding="utf-8")


PLAZOS = ("RETENCION_DATOS_TITULAR_DIAS", "RETENCION_ARCOP_CERRADAS_DIAS", "RETENCION_EVENTOS_SEGURIDAD_DIAS")


def _plazos() -> dict[str, int | None]:
    """Los mismos plazos de la config (variables de entorno); vacío = sin definir."""
    return {k: (int(os.environ[k]) if os.environ.get(k, "").strip() else None) for k in PLAZOS}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    p.add_argument("--url", default=os.environ.get("DATABASE_URL_SYNC"),
                   help="URL SQLAlchemy síncrona (por defecto DATABASE_URL_SYNC)")
    p.add_argument("--salida", default="auditoria_t06", help="carpeta de salida")
    args = p.parse_args(argv)
    if not args.url:
        p.error("falta --url o DATABASE_URL_SYNC")

    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    engine = create_engine(args.url)
    url_segura = engine.url.render_as_string(hide_password=True)

    with engine.connect() as conn:
        conn.execute(text("SET TRANSACTION READ ONLY"))
        a = Auditoria(conn, _plazos())
        esquema = leer_esquema(conn)
        cruzar_con_catalogo(a, esquema)
        revisar_contenido(a, esquema)
        revisar_conservacion(a)
        conn.rollback()

    escribir_der(esquema, salida)
    escribir_matriz(esquema, salida)
    escribir_informe(a, esquema, salida, url_segura)

    for c, r, d in a.controles:
        print(f"[{r:8}] {c}" + (f" — {d}" if d else ""))
    print(f"\nArchivos en {salida.resolve()}: der.mmd, der_datos_personales.mmd, der.html, "
          "matriz_minimizacion.csv, informe_auditoria.md")
    return 1 if a.hallazgos else 0


if __name__ == "__main__":
    raise SystemExit(main())

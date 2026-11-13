"""
HU-35 · Catálogo del Registro de Actividades de Tratamiento (RAT).

PROPUESTA PARA REVISIÓN DE ASESORÍA LEGAL (criterio de la tarea 4 de la historia)
--------------------------------------------------------------------------------
Los textos de ayuda, el catálogo de bases de licitud y sus referencias se redactaron a partir de
la Ley N.º 21.719 (que modifica la Ley N.º 19.628) y de los campos mínimos del registro que fija su
reglamento (Decreto 662). Son una PROPUESTA: `ESTADO_REVISION_LEGAL` queda en
"pendiente_validacion_legal" hasta que la asesoría legal los apruebe. Para aprobarlos:
  1. revisar este archivo (todo el texto que ve el cliente sobre el RAT vive aquí);
  2. ajustar los textos y las referencias a artículos que correspondan;
  3. cambiar ESTADO_REVISION_LEGAL a "validado", anotar la fecha y subir VERSION_TEXTOS.
Las referencias a artículos (campo `referencia`) se citan como orientación y deben confirmarse.

Reglas (las verifica tests/test_hu35_rat.py):
  - Los códigos son estables: NO se renombran ni se borran (una versión vigente antigua los sigue
    usando). Para retirar una opción se marca `vigente=False`.
  - El texto que ve el cliente no lleva códigos internos ni números de historia o tarea.
  - Las categorías de datos y de titulares NO se repiten aquí: son las del catálogo común con el
    mapa (app/domain/catalogo_tratamiento.py).
"""
from __future__ import annotations

from dataclasses import dataclass, field

VERSION_TEXTOS = "2026.11-propuesta"
ESTADO_REVISION_LEGAL = "pendiente_validacion_legal"     # → "validado" cuando lo apruebe asesoría legal
FECHA_REVISION_LEGAL: str | None = None

AVISO_PROPUESTA = ("Los textos de ayuda de este registro son una guía general y no reemplazan la asesoría legal "
                   "de tu empresa.")


@dataclass(frozen=True)
class Opcion:
    codigo: str
    nombre: str
    descripcion: str = ""
    referencia: str = ""
    vigente: bool = True
    extra: dict = field(default_factory=dict)


# ============================================================ estados
BORRADOR, EN_REVISION, VIGENTE, ARCHIVADA = "borrador", "en_revision", "vigente", "archivada"
ESTADOS: tuple[Opcion, ...] = (
    Opcion(BORRADOR, "Borrador", "La estás completando. Nadie más la considera parte del registro."),
    Opcion(EN_REVISION, "En revisión",
           "Está lista para que la revises antes de dejarla vigente, o cambió algo en el mapa de datos que la afecta."),
    Opcion(VIGENTE, "Vigente", "Es parte del registro oficial de tu empresa. Esta versión ya no se puede modificar."),
    Opcion(ARCHIVADA, "Archivada", "Ya no se realiza. Se conserva con su historial y puedes reactivarla."),
)

# ============================================================ bases de licitud
BASES_LICITUD: tuple[Opcion, ...] = (
    Opcion("consentimiento", "Consentimiento del titular",
           "La persona autorizó el tratamiento de forma libre, informada, específica e inequívoca, y puede retirar "
           "su autorización cuando quiera. Debes poder demostrar que lo otorgó.",
           "Ley N.º 21.719, art. 12"),
    Opcion("contrato", "Ejecución de un contrato",
           "El tratamiento es necesario para cumplir un contrato con la persona o para tomar medidas previas que "
           "ella pidió (por ejemplo, despachar una compra o pagar remuneraciones).",
           "Ley N.º 21.719, art. 13"),
    Opcion("obligacion_legal", "Cumplimiento de una obligación legal",
           "Una ley obliga a tu empresa a tratar estos datos (por ejemplo, obligaciones tributarias, laborales o "
           "de prevención de lavado de activos). Conviene indicar qué norma lo exige.",
           "Ley N.º 21.719, art. 13"),
    Opcion("interes_legitimo", "Interés legítimo",
           "Tu empresa o un tercero tiene un interés legítimo y concreto, siempre que no prevalezcan los derechos "
           "y libertades de la persona. Debes describir ese interés y cómo lo ponderaste.",
           "Ley N.º 21.719, art. 13"),
    Opcion("defensa_derechos", "Ejercicio o defensa de un derecho",
           "Los datos se necesitan para ejercer o defender un derecho ante tribunales u organismos públicos.",
           "Ley N.º 21.719, art. 13"),
    Opcion("funcion_publica", "Funciones legales de un organismo público",
           "Solo para organismos públicos que tratan datos dentro de sus competencias legales.",
           "Ley N.º 21.719, título sobre tratamiento por órganos públicos"),
)
INTERES_LEGITIMO = "interes_legitimo"

# Para los datos sensibles la regla general es el consentimiento expreso; la ley prevé excepciones.
BASES_SENSIBLES: tuple[Opcion, ...] = (
    Opcion("consentimiento_expreso", "Consentimiento expreso del titular",
           "La persona autorizó expresamente el tratamiento de sus datos sensibles.", "Ley N.º 21.719, art. 16"),
    Opcion("manifiestamente_publicos", "Datos que el titular hizo públicos",
           "La propia persona hizo públicos estos datos de forma manifiesta y el uso se relaciona con esa difusión.",
           "Ley N.º 21.719, art. 16"),
    Opcion("interes_vital", "Interés vital o urgencia médica",
           "Se necesitan para proteger la vida o la integridad de la persona cuando no puede dar su consentimiento.",
           "Ley N.º 21.719, art. 16"),
    Opcion("obligacion_laboral", "Obligaciones laborales o de seguridad social",
           "Los exige el cumplimiento de obligaciones laborales, de salud laboral o de seguridad social.",
           "Ley N.º 21.719, art. 16"),
    Opcion("defensa_derechos", "Ejercicio o defensa de un derecho",
           "Se necesitan para ejercer o defender un derecho ante tribunales u organismos públicos.",
           "Ley N.º 21.719, art. 16"),
    Opcion("autorizacion_legal", "Lo autoriza o exige una ley",
           "Una ley autoriza o exige expresamente tratar esta clase de datos.", "Ley N.º 21.719, art. 16"),
    Opcion("fines_investigacion", "Fines históricos, estadísticos o científicos",
           "Se tratan con esos fines, con las garantías que exige la ley (por ejemplo, seudonimización).",
           "Ley N.º 21.719, art. 16"),
)

# ============================================================ fuentes de los datos
FUENTES: tuple[Opcion, ...] = (
    Opcion("titular", "La propia persona", "La persona entrega sus datos (formularios, contratos, postulaciones…)."),
    Opcion("generados", "Los genera tu empresa", "Surgen de la relación con la persona (historial de compras, "
           "registros de uso, evaluaciones internas…)."),
    Opcion("terceros", "Otra organización", "Los entrega un tercero (empresa del grupo, socio comercial, "
           "proveedor de bases de datos…)."),
    Opcion("acceso_publico", "Fuente de acceso público", "Se obtienen de una fuente de acceso público "
           "(registros públicos, publicaciones oficiales…).", extra={"acceso_publico": True}),
    Opcion("dispositivos", "Dispositivos o sensores", "Se capturan con cámaras, sensores, aplicaciones o equipos."),
    Opcion("otro", "Otra fuente", "Describe de dónde vienen."),
)
CODIGOS_FUENTE_PUBLICA = frozenset(f.codigo for f in FUENTES if f.extra.get("acceso_publico"))

# ============================================================ plazos de conservación
UNIDADES_PLAZO: tuple[Opcion, ...] = (
    Opcion("dias", "días"), Opcion("meses", "meses"), Opcion("anios", "años"),
)
INICIOS_PLAZO: tuple[Opcion, ...] = (
    Opcion("recoleccion", "desde que se obtienen"),
    Opcion("termino_relacion", "desde que termina la relación o el contrato"),
    Opcion("ultima_interaccion", "desde la última interacción"),
    Opcion("cumplida_finalidad", "desde que se cumple la finalidad"),
)
MAX_PLAZO = {"dias": 3650, "meses": 600, "anios": 100}

# ============================================================ medidas de seguridad
GRUPOS_MEDIDAS = ("Técnicas", "Organizativas")
MEDIDAS_SEGURIDAD: tuple[Opcion, ...] = (
    Opcion("cifrado_reposo", "Cifrado de datos almacenados", extra={"grupo": GRUPOS_MEDIDAS[0]}),
    Opcion("cifrado_transito", "Cifrado en las comunicaciones", extra={"grupo": GRUPOS_MEDIDAS[0]}),
    Opcion("control_acceso", "Accesos por perfil y mínimo privilegio", extra={"grupo": GRUPOS_MEDIDAS[0]}),
    Opcion("doble_factor", "Autenticación de dos factores", extra={"grupo": GRUPOS_MEDIDAS[0]}),
    Opcion("registro_accesos", "Registro y monitoreo de accesos", extra={"grupo": GRUPOS_MEDIDAS[0]}),
    Opcion("respaldos", "Respaldos y recuperación", extra={"grupo": GRUPOS_MEDIDAS[0]}),
    Opcion("seudonimizacion", "Seudonimización o anonimización", extra={"grupo": GRUPOS_MEDIDAS[0]}),
    Opcion("eliminacion_segura", "Eliminación segura al vencer el plazo", extra={"grupo": GRUPOS_MEDIDAS[0]}),
    Opcion("politicas", "Políticas y procedimientos de privacidad", extra={"grupo": GRUPOS_MEDIDAS[1]}),
    Opcion("capacitacion", "Capacitación del personal", extra={"grupo": GRUPOS_MEDIDAS[1]}),
    Opcion("confidencialidad", "Compromisos de confidencialidad", extra={"grupo": GRUPOS_MEDIDAS[1]}),
    Opcion("contratos_encargados", "Contratos con proveedores que tratan datos", extra={"grupo": GRUPOS_MEDIDAS[1]}),
    Opcion("gestion_incidentes", "Procedimiento ante incidentes de seguridad", extra={"grupo": GRUPOS_MEDIDAS[1]}),
    Opcion("evaluacion_impacto", "Evaluación de impacto o de riesgos", extra={"grupo": GRUPOS_MEDIDAS[1]}),
)

# ============================================================ volumen de personas (HU-38)
# Dato OPCIONAL de la actividad (no es uno de los 13 campos obligatorios): a cuántas personas alcanza.
# Lo usa la matriz de riesgos (app/domain/rat/riesgos.py): `puntos` suma al impacto y `gran_escala`
# activa la recomendación de evaluación de impacto cuando además hay datos sensibles o de NNA.
VOLUMENES: tuple[Opcion, ...] = (
    Opcion("hasta_mil", "Menos de 1.000 personas", extra={"puntos": 0, "gran_escala": False}),
    Opcion("hasta_10_mil", "Entre 1.000 y 10.000 personas", extra={"puntos": 0, "gran_escala": False}),
    Opcion("hasta_100_mil", "Entre 10.000 y 100.000 personas", extra={"puntos": 1, "gran_escala": True}),
    Opcion("mas_100_mil", "Más de 100.000 personas", extra={"puntos": 2, "gran_escala": True}),
)
AYUDA_VOLUMEN = ("Opcional. A cuántas personas alcanza la actividad, aproximadamente. Un volumen alto sube el "
                 "riesgo de la actividad y, con datos sensibles o de menores de edad, hace recomendable una "
                 "evaluación de impacto.")

# ============================================================ rol de la empresa
ROLES_EMPRESA: tuple[Opcion, ...] = (
    Opcion("responsable", "Responsable",
           "Tu empresa decide para qué y cómo se tratan los datos."),
    Opcion("encargado", "Encargado",
           "Tu empresa trata los datos por cuenta de otra organización y siguiendo sus instrucciones."),
)

# ============================================================ campos del registro
@dataclass(frozen=True)
class Campo:
    codigo: str
    titulo: str
    paso: int
    ayuda: str
    desde_mapa: bool = False


# Los 11 campos mínimos del reglamento, más las medidas de seguridad y el rol (que pide el RoPA).
CAMPOS: tuple[Campo, ...] = (
    Campo("tipos_datos", "Tipos de datos", 2,
          "Qué datos personales usa la actividad. Se toman de los sistemas y flujos que elijas del mapa; los "
          "datos sensibles quedan marcados.", True),
    Campo("ambito", "Ámbito territorial", 2,
          "En qué países se tratan los datos. Se calcula con el país de cada sistema elegido del mapa.", True),
    Campo("bases_datos", "Sistemas y bases de datos", 2,
          "Dónde se registran o almacenan los datos de esta actividad. Elígelos de tu mapa de datos.", True),
    Campo("titulares", "Categorías de titulares", 2,
          "De quiénes son los datos (clientes, trabajadores, postulantes…). Si incluye niños, niñas o "
          "adolescentes, queda marcado.", True),
    Campo("finalidades", "Finalidades", 1,
          "Para qué se usan los datos. Escribe finalidades concretas y explícitas: «gestionar el despacho de "
          "las compras» es mejor que «fines comerciales»."),
    Campo("fuentes", "Fuentes de los datos", 3,
          "De dónde vienen los datos e indica si alguna es una fuente de acceso público."),
    Campo("base_licitud", "Base de licitud", 3,
          "La razón legal que permite tratar los datos. Si es el interés legítimo, describe ese interés. Si hay "
          "datos sensibles, indica también la base que permite tratarlos."),
    Campo("destinatarios", "Terceros destinatarios", 4,
          "A quiénes se comunican o ceden los datos. Se toman de los terceros del mapa; si no se comparten con "
          "nadie, confírmalo.", True),
    Campo("transferencias", "Transferencias internacionales", 4,
          "Envíos de datos fuera de Chile y la garantía que los respalda. Se calculan con los flujos del mapa; la "
          "garantía se registra en el flujo.", True),
    Campo("conservacion", "Plazos de conservación", 5,
          "Cuánto tiempo se guarda cada categoría de datos y desde cuándo se cuenta. Al vencer, los datos deben "
          "eliminarse o anonimizarse."),
    Campo("decisiones", "Decisiones automatizadas y perfilamiento", 5,
          "Si la actividad toma decisiones sin intervención humana o arma perfiles de las personas (por ejemplo, "
          "con un sistema de IA). Si es así, explica la lógica que se aplica y sus efectos."),
    Campo("medidas", "Medidas de seguridad", 6,
          "Cómo se protegen los datos de esta actividad, tanto con medidas técnicas como organizativas."),
    Campo("rol", "Rol de tu empresa", 1,
          "Si tu empresa decide sobre el tratamiento (responsable) o lo hace por cuenta de otra organización "
          "(encargado)."),
)
CAMPOS_POR_CODIGO: dict[str, Campo] = {c.codigo: c for c in CAMPOS}
CODIGOS_CAMPO: tuple[str, ...] = tuple(c.codigo for c in CAMPOS)

PASOS: tuple[tuple[int, str, str], ...] = (
    (1, "La actividad", "Qué se hace, para qué y qué rol tiene tu empresa."),
    (2, "Sistemas y datos", "Elige del mapa dónde están los datos y cuáles usa la actividad."),
    (3, "Origen y licitud", "De dónde vienen los datos y qué permite tratarlos."),
    (4, "Destinatarios", "Con quién se comparten y si salen de Chile."),
    (5, "Conservación y decisiones", "Cuánto tiempo se guardan y si hay decisiones automatizadas."),
    (6, "Seguridad y revisión", "Cómo se protegen y qué falta para dejarla vigente."),
)

# ============================================================ índices
def _por_codigo(opciones) -> dict[str, Opcion]:
    return {o.codigo: o for o in opciones}


BASES_POR_CODIGO = _por_codigo(BASES_LICITUD)
BASES_SENSIBLES_POR_CODIGO = _por_codigo(BASES_SENSIBLES)
FUENTES_POR_CODIGO = _por_codigo(FUENTES)
UNIDADES_POR_CODIGO = _por_codigo(UNIDADES_PLAZO)
INICIOS_POR_CODIGO = _por_codigo(INICIOS_PLAZO)
MEDIDAS_POR_CODIGO = _por_codigo(MEDIDAS_SEGURIDAD)
ROLES_POR_CODIGO = _por_codigo(ROLES_EMPRESA)
VOLUMENES_POR_CODIGO = _por_codigo(VOLUMENES)
ESTADOS_POR_CODIGO = _por_codigo(ESTADOS)
CODIGOS_ESTADO = tuple(e.codigo for e in ESTADOS)


def nombre(opciones: dict[str, Opcion], codigo: str | None) -> str:
    if not codigo:
        return ""
    o = opciones.get(codigo)
    return o.nombre if o else codigo


def catalogo_dict() -> dict:
    def op(o: Opcion) -> dict:
        d = {"codigo": o.codigo, "nombre": o.nombre}
        if o.descripcion:
            d["descripcion"] = o.descripcion
        if o.referencia:
            d["referencia"] = o.referencia
        d.update(o.extra)
        return d

    def vig(opciones):
        return [op(o) for o in opciones if o.vigente]

    return {
        "version_textos": VERSION_TEXTOS,
        "revision_legal": {"estado": ESTADO_REVISION_LEGAL, "fecha": FECHA_REVISION_LEGAL},
        "aviso": AVISO_PROPUESTA,
        "estados": vig(ESTADOS),
        "bases_licitud": vig(BASES_LICITUD),
        "bases_sensibles": vig(BASES_SENSIBLES),
        "fuentes": vig(FUENTES),
        "unidades_plazo": vig(UNIDADES_PLAZO),
        "inicios_plazo": vig(INICIOS_PLAZO),
        "max_plazo": dict(MAX_PLAZO),
        "grupos_medidas": list(GRUPOS_MEDIDAS),
        "medidas_seguridad": vig(MEDIDAS_SEGURIDAD),
        "roles_empresa": vig(ROLES_EMPRESA),
        "volumenes": vig(VOLUMENES),
        "ayuda_volumen": AYUDA_VOLUMEN,
        "campos": [{"codigo": c.codigo, "titulo": c.titulo, "paso": c.paso, "ayuda": c.ayuda,
                    "desde_mapa": c.desde_mapa} for c in CAMPOS],
        "pasos": [{"numero": n, "titulo": t, "descripcion": d} for n, t, d in PASOS],
    }

"""
HU-34 · Catálogo común de tratamiento de datos personales (mapa de datos, RAT y RoPA).

Es la ÚNICA fuente de las categorías que usan el mapa de datos (HU-34) y, más adelante, el
Registro de Actividades de Tratamiento (RAT) y el RoPA: ambos guardan los mismos CÓDIGOS, así
que un elemento del mapa y una actividad del RAT hablan el mismo idioma y se pueden cruzar
(qué categorías trata cada sistema, de qué titulares, dónde están y con quién se comparten).

Reglas del catálogo (las verifica tests/test_hu34_mapa_datos.py):
  - Los códigos son estables: NO se renombran ni se borran (un mapa o un RAT antiguo los
    sigue usando). Para retirar una categoría se marca `vigente=False`: deja de ofrecerse en
    la interfaz, pero lo ya registrado se sigue leyendo.
  - Las categorías sensibles siguen la definición de datos sensibles de la Ley N.º 21.719
    (origen étnico o racial, afiliación política, sindical o gremial, situación
    socioeconómica, convicciones ideológicas o filosóficas, creencias religiosas, salud,
    perfil biológico humano, biometría, vida sexual, orientación sexual e identidad de género).
  - Las categorías de titulares marcan a los niños, niñas y adolescentes (NNA, menores de 18):
    `nna=True` siempre lo son; `posible_nna=True` pueden serlo (estudiantes, pacientes...) y la
    interfaz pide confirmarlo.

Sin dependencias de la base de datos ni de FastAPI: lo importan el dominio, la API y las pruebas.
"""
from __future__ import annotations

from dataclasses import dataclass, field

VERSION_CATALOGO = "2026.11"


@dataclass(frozen=True)
class CategoriaDato:
    codigo: str
    nombre: str
    grupo: str
    descripcion: str
    ejemplos: tuple[str, ...] = ()
    sensible: bool = False
    vigente: bool = True


@dataclass(frozen=True)
class CategoriaTitular:
    codigo: str
    nombre: str
    descripcion: str
    nna: bool = False
    posible_nna: bool = False
    vigente: bool = True


@dataclass(frozen=True)
class Opcion:
    codigo: str
    nombre: str
    descripcion: str = ""
    extra: dict = field(default_factory=dict)


# ============================================================ categorías de datos
GRUPOS_DATOS = (
    "Identificación y contacto",
    "Laborales y académicos",
    "Económicos y comerciales",
    "Digitales y de comportamiento",
    "Datos sensibles",
)

CATEGORIAS_DATOS: tuple[CategoriaDato, ...] = (
    # ---------------------------------------------------- identificación y contacto
    CategoriaDato("identificacion", "Datos de identificación", GRUPOS_DATOS[0],
                  "Permiten identificar directamente a una persona.",
                  ("Nombre", "RUT o cédula", "Fecha de nacimiento", "Nacionalidad")),
    CategoriaDato("contacto", "Datos de contacto", GRUPOS_DATOS[0],
                  "Permiten ubicar o comunicarse con la persona.",
                  ("Correo electrónico", "Teléfono", "Dirección")),
    CategoriaDato("credenciales", "Credenciales de acceso", GRUPOS_DATOS[0],
                  "Datos para autenticar a la persona en un sistema.",
                  ("Usuario", "Contraseña (cifrada)", "Preguntas de seguridad")),
    CategoriaDato("imagen_voz", "Imagen y voz", GRUPOS_DATOS[0],
                  "Fotografías, video o grabaciones de voz que no se usan para identificar biométricamente.",
                  ("Fotografía de perfil", "Grabación de llamadas", "Cámaras de seguridad")),
    # ---------------------------------------------------- laborales y académicos
    CategoriaDato("laborales", "Datos laborales", GRUPOS_DATOS[1],
                  "Relación laboral, cargo y desempeño.",
                  ("Cargo", "Remuneración", "Evaluaciones de desempeño", "Licencias y permisos")),
    CategoriaDato("academicos", "Datos académicos", GRUPOS_DATOS[1],
                  "Formación y trayectoria educativa.",
                  ("Notas", "Asistencia", "Títulos", "Historial académico")),
    CategoriaDato("antecedentes", "Antecedentes legales o penales", GRUPOS_DATOS[1],
                  "Información sobre procesos judiciales o antecedentes. Requiere un resguardo especial.",
                  ("Certificado de antecedentes", "Causas judiciales")),
    # ---------------------------------------------------- económicos y comerciales
    CategoriaDato("financieros", "Datos financieros y bancarios", GRUPOS_DATOS[2],
                  "Medios de pago y productos financieros.",
                  ("Cuenta bancaria", "Tarjeta de pago", "Deudas", "Transacciones")),
    CategoriaDato("comerciales", "Datos comerciales", GRUPOS_DATOS[2],
                  "Relación comercial con la empresa.",
                  ("Historial de compras", "Contratos", "Reclamos", "Programa de fidelización")),
    CategoriaDato("solvencia", "Solvencia y comportamiento crediticio", GRUPOS_DATOS[2],
                  "Capacidad de pago y antecedentes comerciales.",
                  ("Puntaje de riesgo crediticio", "Morosidad", "Boletín comercial")),
    # ---------------------------------------------------- digitales y comportamiento
    CategoriaDato("navegacion", "Navegación e identificadores digitales", GRUPOS_DATOS[3],
                  "Rastro digital de la persona en sitios y aplicaciones.",
                  ("Dirección IP", "Cookies", "Identificador del dispositivo", "Registros de acceso")),
    CategoriaDato("geolocalizacion", "Geolocalización", GRUPOS_DATOS[3],
                  "Ubicación física de la persona.",
                  ("Ubicación GPS", "Rutas", "Ubicación de la antena celular")),
    CategoriaDato("comunicaciones", "Contenido de comunicaciones", GRUPOS_DATOS[3],
                  "Lo que la persona escribe o dice a la empresa o a un asistente de IA.",
                  ("Mensajes de chat", "Correos", "Instrucciones (prompts) a un asistente de IA")),
    CategoriaDato("perfilamiento", "Perfilamiento e inferencias", GRUPOS_DATOS[3],
                  "Preferencias, segmentos o predicciones que se infieren de la persona, incluso con IA.",
                  ("Segmento de marketing", "Propensión de compra", "Puntaje de un modelo de IA")),
    # ---------------------------------------------------- sensibles (Ley 21.719)
    CategoriaDato("salud", "Salud", GRUPOS_DATOS[4],
                  "Estado de salud física o mental, diagnósticos y tratamientos.",
                  ("Ficha clínica", "Licencias médicas", "Exámenes", "Discapacidad"), sensible=True),
    CategoriaDato("biometricos", "Datos biométricos", GRUPOS_DATOS[4],
                  "Rasgos físicos usados para identificar a la persona.",
                  ("Huella dactilar", "Reconocimiento facial", "Patrón de voz"), sensible=True),
    CategoriaDato("perfil_biologico", "Perfil biológico y genético", GRUPOS_DATOS[4],
                  "Información genética o del perfil biológico humano.",
                  ("Exámenes genéticos", "ADN"), sensible=True),
    CategoriaDato("origen_etnico", "Origen étnico o racial", GRUPOS_DATOS[4],
                  "Pertenencia a un pueblo originario u origen racial.",
                  ("Pertenencia a un pueblo originario",), sensible=True),
    CategoriaDato("socioeconomicos", "Situación socioeconómica", GRUPOS_DATOS[4],
                  "Condición social o económica que puede exponer a la persona a discriminación.",
                  ("Registro Social de Hogares", "Beneficios sociales", "Nivel de ingresos del hogar"),
                  sensible=True),
    CategoriaDato("afiliacion", "Afiliación política, sindical o gremial", GRUPOS_DATOS[4],
                  "Pertenencia a partidos, sindicatos o gremios.",
                  ("Afiliación sindical", "Militancia política"), sensible=True),
    CategoriaDato("creencias", "Convicciones ideológicas, filosóficas o religiosas", GRUPOS_DATOS[4],
                  "Creencias o convicciones personales.", ("Religión", "Convicciones filosóficas"), sensible=True),
    CategoriaDato("vida_sexual", "Vida sexual, orientación sexual e identidad de género", GRUPOS_DATOS[4],
                  "Información sobre la vida sexual, la orientación sexual o la identidad de género.",
                  ("Orientación sexual", "Identidad de género", "Nombre social"), sensible=True),
)

# ============================================================ categorías de titulares
CATEGORIAS_TITULARES: tuple[CategoriaTitular, ...] = (
    CategoriaTitular("clientes", "Clientes", "Personas que compran o usan los productos o servicios."),
    CategoriaTitular("prospectos", "Potenciales clientes", "Personas contactadas con fines comerciales."),
    CategoriaTitular("usuarios", "Usuarios de plataformas digitales",
                     "Personas que usan el sitio web, la aplicación o el asistente de IA.", posible_nna=True),
    CategoriaTitular("trabajadores", "Trabajadores", "Personas con contrato vigente con la empresa."),
    CategoriaTitular("postulantes", "Postulantes", "Candidatos en procesos de selección."),
    CategoriaTitular("ex_trabajadores", "Ex trabajadores", "Personas que trabajaron en la empresa."),
    CategoriaTitular("contactos_proveedores", "Contactos de proveedores y socios",
                     "Personas de contacto de proveedores, distribuidores o aliados."),
    CategoriaTitular("pacientes", "Pacientes", "Personas atendidas en prestaciones de salud.", posible_nna=True),
    CategoriaTitular("estudiantes", "Estudiantes", "Alumnos y alumnas de la institución.", posible_nna=True),
    CategoriaTitular("apoderados", "Apoderados y familiares",
                     "Padres, madres, tutores o familiares de los titulares principales."),
    CategoriaTitular("beneficiarios", "Beneficiarios y asegurados",
                     "Cargas, beneficiarios o asegurados de un producto o servicio.", posible_nna=True),
    CategoriaTitular("visitantes", "Visitantes", "Personas que ingresan a las instalaciones."),
    CategoriaTitular("nna", "Niños, niñas y adolescentes",
                     "Personas menores de 18 años: su tratamiento exige un resguardo reforzado.", nna=True),
)

# ============================================================ elementos del mapa
TIPOS_ELEMENTO: tuple[Opcion, ...] = (
    Opcion("sistema", "Sistema o aplicación", "Software donde se capturan o usan datos personales."),
    Opcion("base_datos", "Base de datos o repositorio", "Lugar donde se almacenan los datos personales."),
    Opcion("tercero", "Tercero o destinatario", "Organización externa que recibe o trata los datos."),
)

SUBTIPOS: dict[str, tuple[Opcion, ...]] = {
    "sistema": (
        Opcion("aplicacion_propia", "Aplicación propia"),
        Opcion("erp", "ERP o gestión"),
        Opcion("crm", "CRM o atención de clientes"),
        Opcion("ecommerce", "Sitio web o e-commerce"),
        Opcion("app_movil", "Aplicación móvil"),
        Opcion("saas", "Servicio en la nube (SaaS)"),
        Opcion("sistema_ia", "Sistema o asistente con IA"),
        Opcion("rrhh", "Recursos humanos y remuneraciones"),
        Opcion("colaboracion", "Correo y colaboración"),
        Opcion("otro", "Otro sistema"),
    ),
    "base_datos": (
        Opcion("relacional", "Base de datos transaccional"),
        Opcion("analitica", "Data warehouse o analítica"),
        Opcion("archivos", "Repositorio de archivos"),
        Opcion("nube_almacenamiento", "Almacenamiento en la nube"),
        Opcion("vectorial", "Base vectorial o de conocimiento (RAG)"),
        Opcion("respaldo", "Respaldos"),
        Opcion("planillas", "Planillas y documentos"),
        Opcion("otro", "Otro repositorio"),
    ),
    "tercero": (
        Opcion("proveedor_ia", "Proveedor de IA o de modelos de lenguaje"),
        Opcion("proveedor_nube", "Proveedor de nube o hosting"),
        Opcion("proveedor_servicios", "Proveedor de servicios"),
        Opcion("pagos", "Pagos, banca o seguros"),
        Opcion("logistica", "Logística y despacho"),
        Opcion("marketing", "Marketing y publicidad"),
        Opcion("organismo_publico", "Organismo público o regulador"),
        Opcion("grupo_empresarial", "Empresa del mismo grupo"),
        Opcion("otro", "Otro tercero"),
    ),
}

ROLES_TERCERO: tuple[Opcion, ...] = (
    Opcion("encargado", "Encargado del tratamiento",
           "Trata los datos por cuenta de tu empresa y siguiendo sus instrucciones (por ejemplo, un proveedor de nube).",
           {"requiere_contrato": True}),
    Opcion("cesionario", "Destinatario con fines propios",
           "Recibe los datos y los usa para sus propias finalidades (por ejemplo, un socio comercial).",
           {"requiere_contrato": True}),
    Opcion("corresponsable", "Corresponsable",
           "Decide junto con tu empresa para qué y cómo se tratan los datos.", {"requiere_contrato": True}),
    Opcion("obligacion_legal", "Destinatario por obligación legal",
           "Autoridades, reguladores o entidades a las que la ley obliga a informar (SII, previsión, reguladores).",
           {"requiere_contrato": False}),
)

GARANTIAS_TRANSFERENCIA: tuple[Opcion, ...] = (
    Opcion("pais_adecuado", "País con nivel adecuado de protección",
           "El país de destino tiene un nivel de protección reconocido como adecuado.", {"valida": True}),
    Opcion("clausulas_contractuales", "Cláusulas contractuales tipo",
           "El contrato con el destinatario incluye cláusulas de protección de datos.", {"valida": True}),
    Opcion("normas_corporativas", "Normas corporativas vinculantes",
           "Reglas obligatorias dentro del mismo grupo empresarial.", {"valida": True}),
    Opcion("consentimiento", "Consentimiento expreso del titular",
           "La persona autorizó expresamente la transferencia, informada de sus riesgos.", {"valida": True}),
    Opcion("excepcion_legal", "Excepción legal",
           "Por ejemplo, es necesaria para ejecutar un contrato con el propio titular.", {"valida": True}),
    Opcion("ninguna", "Sin garantía documentada",
           "Aún no se ha definido ni documentado cómo se protege la transferencia.", {"valida": False}),
)

FRECUENCIAS: tuple[Opcion, ...] = (
    Opcion("tiempo_real", "En tiempo real"),
    Opcion("diaria", "Diaria"),
    Opcion("semanal", "Semanal"),
    Opcion("mensual", "Mensual"),
    Opcion("bajo_demanda", "Cuando se necesita"),
    Opcion("puntual", "Una sola vez"),
)

MEDIOS: tuple[Opcion, ...] = (
    Opcion("api", "API o integración"),
    Opcion("archivo", "Archivo o carga masiva"),
    Opcion("replicacion", "Replicación o sincronización"),
    Opcion("correo", "Correo electrónico"),
    Opcion("manual", "Ingreso manual"),
    Opcion("otro", "Otro medio"),
)

# ============================================================ países
# ISO 3166-1 alfa-2. Chile primero; luego los destinos más comunes de los servicios en la nube.
PAIS_LOCAL = "CL"
PAISES: tuple[tuple[str, str], ...] = (
    ("CL", "Chile"), ("US", "Estados Unidos"), ("BR", "Brasil"), ("AR", "Argentina"), ("PE", "Perú"),
    ("CO", "Colombia"), ("MX", "México"), ("UY", "Uruguay"), ("PY", "Paraguay"), ("BO", "Bolivia"),
    ("EC", "Ecuador"), ("VE", "Venezuela"), ("PA", "Panamá"), ("CR", "Costa Rica"), ("CA", "Canadá"),
    ("IE", "Irlanda"), ("DE", "Alemania"), ("FR", "Francia"), ("ES", "España"), ("NL", "Países Bajos"),
    ("BE", "Bélgica"), ("IT", "Italia"), ("PT", "Portugal"), ("LU", "Luxemburgo"), ("SE", "Suecia"),
    ("FI", "Finlandia"), ("DK", "Dinamarca"), ("NO", "Noruega"), ("PL", "Polonia"), ("AT", "Austria"),
    ("CH", "Suiza"), ("GB", "Reino Unido"), ("IL", "Israel"), ("AE", "Emiratos Árabes Unidos"),
    ("IN", "India"), ("SG", "Singapur"), ("JP", "Japón"), ("KR", "Corea del Sur"), ("CN", "China"),
    ("HK", "Hong Kong"), ("TW", "Taiwán"), ("AU", "Australia"), ("NZ", "Nueva Zelanda"),
    ("ZA", "Sudáfrica"),
)

# ============================================================ índices y consultas
DATOS_POR_CODIGO: dict[str, CategoriaDato] = {c.codigo: c for c in CATEGORIAS_DATOS}
TITULARES_POR_CODIGO: dict[str, CategoriaTitular] = {c.codigo: c for c in CATEGORIAS_TITULARES}
NOMBRE_PAIS: dict[str, str] = dict(PAISES)
CODIGOS_SENSIBLES = frozenset(c.codigo for c in CATEGORIAS_DATOS if c.sensible)
CODIGOS_TITULARES_NNA = frozenset(c.codigo for c in CATEGORIAS_TITULARES if c.nna)
TIPOS = tuple(t.codigo for t in TIPOS_ELEMENTO)
SUBTIPOS_POR_TIPO: dict[str, frozenset[str]] = {t: frozenset(o.codigo for o in ops) for t, ops in SUBTIPOS.items()}
ROLES = frozenset(r.codigo for r in ROLES_TERCERO)
# HU-38: subtipos de elementos que implican uso de inteligencia artificial (matriz de riesgos del RAT)
SUBTIPOS_IA = frozenset({"sistema_ia", "vectorial", "proveedor_ia"})
ROLES_CON_CONTRATO = frozenset(r.codigo for r in ROLES_TERCERO if r.extra.get("requiere_contrato"))
GARANTIAS = frozenset(g.codigo for g in GARANTIAS_TRANSFERENCIA)
GARANTIAS_VALIDAS = frozenset(g.codigo for g in GARANTIAS_TRANSFERENCIA if g.extra.get("valida"))
CODIGOS_FRECUENCIA = frozenset(f.codigo for f in FRECUENCIAS)
CODIGOS_MEDIO = frozenset(m.codigo for m in MEDIOS)

_ETIQUETAS = {
    "tipo": {o.codigo: o.nombre for o in TIPOS_ELEMENTO},
    "rol": {o.codigo: o.nombre for o in ROLES_TERCERO},
    "garantia": {o.codigo: o.nombre for o in GARANTIAS_TRANSFERENCIA},
    "frecuencia": {o.codigo: o.nombre for o in FRECUENCIAS},
    "medio": {o.codigo: o.nombre for o in MEDIOS},
}


def etiqueta(campo: str, codigo: str | None) -> str:
    """Nombre legible de un código del catálogo (tipo, rol, garantía, frecuencia o medio)."""
    if not codigo:
        return "—"
    return _ETIQUETAS.get(campo, {}).get(codigo, codigo)


def etiqueta_subtipo(tipo: str, subtipo: str | None) -> str:
    if not subtipo:
        return "—"
    return next((o.nombre for o in SUBTIPOS.get(tipo, ()) if o.codigo == subtipo), subtipo)


def nombre_pais(codigo: str | None) -> str:
    if not codigo:
        return "Sin informar"
    return NOMBRE_PAIS.get(codigo, codigo)


def nombre_dato(codigo: str) -> str:
    c = DATOS_POR_CODIGO.get(codigo)
    return c.nombre if c else codigo


def nombre_titular(codigo: str) -> str:
    c = TITULARES_POR_CODIGO.get(codigo)
    return c.nombre if c else codigo


def es_sensible(codigo: str) -> bool:
    return codigo in CODIGOS_SENSIBLES


def sensibles_de(codigos) -> list[str]:
    return [c for c in codigos or () if c in CODIGOS_SENSIBLES]


def titulares_nna(codigos) -> bool:
    return any(c in CODIGOS_TITULARES_NNA for c in codigos or ())


def catalogo_dict() -> dict:
    """El catálogo para la interfaz (y, más adelante, para el RAT): solo lo vigente."""
    def op(o: Opcion) -> dict:
        return {"codigo": o.codigo, "nombre": o.nombre, "descripcion": o.descripcion, **o.extra}

    return {
        "version": VERSION_CATALOGO,
        "grupos_datos": list(GRUPOS_DATOS),
        "categorias_datos": [
            {"codigo": c.codigo, "nombre": c.nombre, "grupo": c.grupo, "descripcion": c.descripcion,
             "ejemplos": list(c.ejemplos), "sensible": c.sensible}
            for c in CATEGORIAS_DATOS if c.vigente
        ],
        "categorias_titulares": [
            {"codigo": c.codigo, "nombre": c.nombre, "descripcion": c.descripcion, "nna": c.nna,
             "posible_nna": c.posible_nna}
            for c in CATEGORIAS_TITULARES if c.vigente
        ],
        "tipos": [op(o) for o in TIPOS_ELEMENTO],
        "subtipos": {t: [op(o) for o in ops] for t, ops in SUBTIPOS.items()},
        "roles_tercero": [op(o) for o in ROLES_TERCERO],
        "garantias": [op(o) for o in GARANTIAS_TRANSFERENCIA],
        "frecuencias": [op(o) for o in FRECUENCIAS],
        "medios": [op(o) for o in MEDIOS],
        "paises": [{"codigo": c, "nombre": n} for c, n in PAISES],
        "pais_local": PAIS_LOCAL,
    }

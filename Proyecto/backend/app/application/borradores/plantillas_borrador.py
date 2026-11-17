"""
HU-16 · Biblioteca de plantillas y cláusulas de los borradores de cumplimiento.

Criterio 1: plantillas editables de Política de uso de LLM, Aviso de privacidad y PIA.
Criterio 2: cláusulas ajustadas a la Ley N.º 21.719 y a las dimensiones del modelo.

Cada cláusula declara:
  dimension   la dimensión del modelo de madurez (HU-03) a la que aporta. None = cláusula
              general del documento (objeto, identificación, aprobación...).
  controles   los controles de la matriz que ayuda a cerrar. Son códigos INTERNOS: nunca se
              escriben en el documento (regla de interfaz del 29-oct); sirven para saber si la
              empresa tiene una brecha en lo que trata la cláusula y para tomar de la matriz la
              fuente normativa real (framework y artículo) del "Fundamento".
  normas      el respaldo sin número de artículo, por si la matriz no está disponible.
  refuerzo    medida prioritaria que se agrega cuando la evaluación de la empresa tiene una
              brecha (no cumplido o parcial) en alguno de sus controles.
  adaptable   si el Agente IA puede reescribirla para la empresa (las de identificación,
              derechos y aprobación quedan fijas: su texto es el que exige la ley).

Marcadores del texto:
  {{RAZON_SOCIAL}} {{RUT_EMPRESA}} {{RUBRO}} {{FECHA}}   los completa el backend.
  [COMPLETAR: ...]                                       los completa la empresa al revisar;
                                                         consolidar con marcadores pendientes
                                                         exige confirmarlo.

BORRADOR TÉCNICO: los textos los valida el Product Owner con asesoría legal. No son
asesoría legal y así lo dice cada documento. Cambiar un texto => subir VERSION_PLANTILLAS
(queda en cada borrador generado).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

VERSION_PLANTILLAS = "2026.11.1"

# Dimensiones del modelo de madurez (catálogo "dominio" de la matriz, HU-03)
PROTECCION_DATOS = "Protección de Datos"
GOBERNANZA_IA = "Gobernanza de IA"
GESTION_RIESGOS = "Gestión de Riesgos"
USO_RESPONSABLE = "Uso Responsable"
DIMENSIONES = (PROTECCION_DATOS, GOBERNANZA_IA, GESTION_RIESGOS, USO_RESPONSABLE)

LEY = "Ley N.º 21.719"
ISO = "ISO/IEC 42001"
NIST = "NIST AI RMF 100-1"
OWASP = "OWASP Top 10 para LLM"

MARCADOR_PENDIENTE = re.compile(r"\[COMPLETAR:[^\]\n]{0,200}\]")


class TipoPlantilla(str, Enum):
    POLITICA_LLM = "politica_llm"
    AVISO_PRIVACIDAD = "aviso_privacidad"
    PIA = "pia"

    @classmethod
    def valores(cls) -> list[str]:
        return [t.value for t in cls]

    @classmethod
    def normalizar(cls, valor: str | None) -> "TipoPlantilla | None":
        v = (valor or "").strip().lower()
        return next((t for t in cls if t.value == v), None)


@dataclass(frozen=True)
class Clausula:
    id: str
    titulo: str
    texto: str
    dimension: str | None = None
    controles: tuple[str, ...] = ()
    normas: tuple[str, ...] = ()
    refuerzo: str | None = None
    adaptable: bool = True


@dataclass(frozen=True)
class Plantilla:
    tipo: TipoPlantilla
    titulo: str
    nombre_corto: str          # para el nombre del archivo
    descripcion: str
    proposito: str             # para qué sirve (va al prompt y a la interfaz)
    clausulas: tuple[Clausula, ...] = field(default_factory=tuple)

    def clausula(self, clausula_id: str) -> Clausula | None:
        return next((c for c in self.clausulas if c.id == clausula_id), None)

    @property
    def controles(self) -> frozenset[str]:
        return frozenset(c for cl in self.clausulas for c in cl.controles)

    @property
    def dimensiones(self) -> tuple[str, ...]:
        return tuple(d for d in DIMENSIONES if any(c.dimension == d for c in self.clausulas))

    def resumen(self) -> dict:
        return {
            "tipo": self.tipo.value, "titulo": self.titulo, "descripcion": self.descripcion,
            "secciones": [c.titulo for c in self.clausulas], "dimensiones": list(self.dimensiones),
            "version": VERSION_PLANTILLAS,
        }


# ===================================================================== Política de uso de LLM
POLITICA_LLM = Plantilla(
    tipo=TipoPlantilla.POLITICA_LLM,
    titulo="Política de Uso de Modelos de Lenguaje (LLM) e IA Generativa",
    nombre_corto="politica_uso_llm",
    descripcion="Reglas corporativas para usar herramientas de IA generativa: roles, uso aceptable, "
                "datos personales, seguridad, supervisión humana y gestión de riesgos.",
    proposito="Política interna que regula cómo los colaboradores y sistemas de la empresa usan modelos de "
              "lenguaje e IA generativa de forma segura, ética y conforme a la Ley 21.719.",
    clausulas=(
        Clausula(
            "pol-objeto", "Objetivo y alcance",
            "Esta política establece las reglas con que **{{RAZON_SOCIAL}}** adopta, usa y supervisa modelos de "
            "lenguaje (LLM) y herramientas de inteligencia artificial generativa en sus procesos de {{RUBRO}}.\n\n"
            "Aplica a todos los colaboradores, contratistas y proveedores que usen estas herramientas con "
            "información de la empresa, sean de pago, gratuitas, integradas en otros sistemas o desarrolladas "
            "internamente. Su cumplimiento es obligatorio desde su aprobación.",
            dimension=GOBERNANZA_IA, controles=("GOB-001",), normas=(ISO,),
            refuerzo="La empresa no tiene una política de IA aprobada y comunicada: esta política debe aprobarse "
                     "formalmente por la alta dirección y difundirse a todo el personal con registro de lectura.",
        ),
        Clausula(
            "pol-definiciones", "Definiciones",
            "- **Herramienta de IA generativa:** sistema que produce texto, imágenes, código u otro contenido a "
            "partir de instrucciones (prompts).\n"
            "- **Herramienta autorizada:** la que figura en el Inventario de Sistemas de IA de la empresa con su "
            "aprobación vigente.\n"
            "- **Dato personal:** información sobre una persona natural identificada o identificable (Ley N.º 19.628, "
            "modificada por la Ley N.º 21.719).\n"
            "- **Dato sensible:** dato personal referido a la salud, datos biométricos, origen étnico, vida sexual, "
            "afiliación política, sindical o religiosa, entre otros que define la ley.\n"
            "- **Información confidencial:** información de la empresa o de terceros cuyo acceso está restringido.",
            dimension=None, normas=(LEY,), adaptable=False,
        ),
        Clausula(
            "pol-roles", "Roles y responsabilidades",
            "- **Alta dirección:** aprueba esta política, asigna recursos y revisa su cumplimiento.\n"
            "- **Responsable de Gobernanza de IA** ([COMPLETAR: cargo designado]): mantiene el inventario de "
            "herramientas, evalúa nuevas solicitudes y coordina la revisión anual.\n"
            "- **Encargado de Protección de Datos** ([COMPLETAR: cargo o nombre del responsable]): verifica la base "
            "de licitud de los tratamientos con IA y atiende los derechos de los titulares.\n"
            "- **Equipo de TI / Seguridad:** habilita las herramientas autorizadas, aplica los controles técnicos y "
            "registra las interacciones.\n"
            "- **Colaboradores:** usan solo herramientas autorizadas y reportan incidentes o resultados erróneos.",
            dimension=GOBERNANZA_IA, controles=("GOB-002",), normas=(ISO,),
            refuerzo="No hay un responsable formal de supervisar la IA: designa por escrito al Responsable de "
                     "Gobernanza de IA y documenta sus funciones en una matriz RACI antes de aprobar esta política.",
        ),
        Clausula(
            "pol-inventario", "Inventario y aprobación de herramientas",
            "Solo se pueden usar herramientas de IA que figuren en el **Inventario de Sistemas de IA**, con su "
            "finalidad, responsable, datos que procesa, proveedor y fecha de aprobación.\n\n"
            "Antes de adoptar una herramienta nueva se evalúa: (a) el valor para el negocio, (b) los riesgos legales, "
            "de privacidad y de reputación, y (c) las condiciones de seguridad, privacidad y ética del proveedor. "
            "El uso de herramientas no inventariadas (\"IA en la sombra\") está prohibido.",
            dimension=GOBERNANZA_IA, controles=("GOB-003", "GOB-005", "GOB-008"), normas=(ISO,),
            refuerzo="Levanta el inventario de todas las herramientas de IA que hoy usa el personal (incluidas las "
                     "gratuitas) en un plazo de [COMPLETAR: plazo, p. ej. 30 días] y bloquea las no autorizadas.",
        ),
        Clausula(
            "pol-uso-aceptable", "Uso aceptable y datos prohibidos",
            "Las herramientas autorizadas se usan solo para las finalidades aprobadas. **Está prohibido ingresar** en "
            "herramientas de IA públicas o no autorizadas:\n\n"
            "- datos personales de clientes, colaboradores o terceros, y en especial datos sensibles;\n"
            "- información confidencial, secretos comerciales, contraseñas, credenciales o código fuente;\n"
            "- documentos sujetos a obligaciones contractuales de reserva.\n\n"
            "Todo contenido generado por IA es revisado por una persona antes de usarse, publicarse o enviarse.",
            dimension=USO_RESPONSABLE, controles=("GOB-009", "DAT-003"), normas=(ISO, LEY),
            refuerzo="Publica una guía breve de uso aceptable con ejemplos de lo que no se puede ingresar y pide a "
                     "cada colaborador confirmar que la leyó.",
        ),
        Clausula(
            "pol-datos-personales", "Protección de datos personales en el uso de IA",
            "Todo tratamiento de datos personales con IA debe tener una **base de licitud documentada** "
            "(consentimiento, contrato, obligación legal u otra que reconozca la ley) y limitarse a la finalidad "
            "informada al titular.\n\n"
            "Antes de enviar datos a un modelo externo se anonimizan o seudonimizan. Los datos sensibles, biométricos "
            "o de niños, niñas y adolescentes solo se tratan con autorización expresa del Encargado de Protección de "
            "Datos y medidas de seguridad reforzadas. Cada tratamiento con IA se registra en el Registro de "
            "Actividades de Tratamiento (RAT).",
            dimension=PROTECCION_DATOS, controles=("DAT-001", "DAT-003", "DAT-005", "DAT-009", "SEG-008"),
            normas=(LEY,),
            refuerzo="Documenta la base de licitud de cada uso de IA con datos personales y regístralo en el RAT antes "
                     "de seguir operándolo.",
        ),
        Clausula(
            "pol-proveedores", "Proveedores de IA y transferencias internacionales",
            "Los proveedores de IA que traten datos personales por cuenta de la empresa actúan como **encargados** y "
            "deben firmar un contrato que regule el objeto, la duración, las medidas de seguridad, la "
            "confidencialidad y la devolución o eliminación de los datos.\n\n"
            "Si el proveedor procesa datos fuera de Chile, se verifica que la transferencia cumpla las condiciones "
            "de la ley (país adecuado, cláusulas contractuales u otra garantía reconocida).",
            dimension=PROTECCION_DATOS, controles=("DAT-007", "DAT-008"), normas=(LEY,),
            refuerzo="Revisa los contratos vigentes con proveedores de IA y agrega el anexo de tratamiento de datos "
                     "donde falte.",
        ),
        Clausula(
            "pol-seguridad", "Seguridad de los sistemas de IA",
            "Los sistemas de IA de la empresa aplican, como mínimo:\n\n"
            "- filtros contra instrucciones maliciosas (prompt injection) y validación de las respuestas antes de "
            "ejecutarlas en otros sistemas;\n"
            "- controles contra la fuga de información sensible en las salidas;\n"
            "- permisos mínimos para las integraciones (la IA no tiene más acceso que el necesario);\n"
            "- cifrado de las comunicaciones y del historial de conversaciones;\n"
            "- límites de uso (cuotas) para evitar abusos y caídas del servicio.",
            dimension=USO_RESPONSABLE,
            controles=("SEG-001", "SEG-002", "SEG-003", "SEG-004", "SEG-006", "SEG-007", "SEG-009"),
            normas=(OWASP,),
            refuerzo="Prioriza los controles técnicos pendientes de los sistemas de IA expuestos a clientes o con "
                     "acceso a datos personales.",
        ),
        Clausula(
            "pol-supervision", "Supervisión humana y decisiones automatizadas",
            "Ninguna decisión que produzca efectos jurídicos o afecte significativamente a una persona (por ejemplo, "
            "contratación, crédito o acceso a un servicio) se toma **solo** con un sistema de IA. Una persona "
            "calificada revisa y puede revertir la recomendación, y el titular puede pedir esa intervención humana y "
            "una explicación de la decisión.\n\n"
            "Los agentes de IA que ejecutan acciones (enviar correos, pagos, cambios en sistemas) tienen límites de "
            "autonomía y requieren aprobación sobre [COMPLETAR: umbral de aprobación].",
            dimension=USO_RESPONSABLE, controles=("SEG-010", "RIE-006", "RIE-009"), normas=(LEY, NIST),
            refuerzo="Identifica las decisiones que hoy se apoyan en IA y define quién las revisa antes de aplicarlas.",
        ),
        Clausula(
            "pol-riesgos", "Gestión de riesgos de IA",
            "Cada sistema de IA tiene sus riesgos identificados y evaluados en la **Matriz de Riesgos de IA** "
            "(precisión, sesgo, privacidad, seguridad, dependencia del proveedor), con un plan de tratamiento para "
            "los riesgos altos y críticos.\n\n"
            "Se monitorea periódicamente la precisión y la tasa de error de los modelos, se prueban los sistemas "
            "sensibles con ejercicios de adversario (red teaming) y se mantiene un plan de contingencia ante la "
            "indisponibilidad del servicio de IA.",
            dimension=GESTION_RIESGOS,
            controles=("RIE-001", "RIE-002", "RIE-003", "RIE-004", "RIE-005", "RIE-007", "RIE-008"),
            normas=(NIST, ISO),
            refuerzo="Construye la Matriz de Riesgos de IA empezando por los sistemas con datos personales o que "
                     "afectan a clientes, y asigna un dueño a cada riesgo alto.",
        ),
        Clausula(
            "pol-evaluacion-impacto", "Evaluación de impacto en protección de datos",
            "Antes de poner en producción un sistema de IA que pueda implicar un alto riesgo para los titulares "
            "(datos sensibles, decisiones automatizadas, tratamiento masivo o monitoreo sistemático) se realiza una "
            "Evaluación de Impacto en Protección de Datos (EIPD/PIA) y se aplican sus medidas de mitigación.",
            dimension=PROTECCION_DATOS, controles=("DAT-002",), normas=(LEY,),
            refuerzo="Ejecuta la EIPD de los sistemas de IA que ya procesan datos de alto riesgo (ComplianceAI puede "
                     "generar un borrador de PIA).",
        ),
        Clausula(
            "pol-incidentes", "Incidentes, registros y mejora continua",
            "Los colaboradores reportan de inmediato a [COMPLETAR: canal de reporte] cualquier incidente con IA: "
            "fuga de datos, respuestas erróneas o discriminatorias, uso no autorizado o comportamiento inesperado.\n\n"
            "Los incidentes que afecten datos personales se gestionan según el protocolo de incidentes y se notifican "
            "a la autoridad y a los titulares cuando la ley lo exige. Las interacciones con los sistemas de IA se "
            "registran en logs de auditoría y cada incidente cierra con una acción correctiva documentada.",
            dimension=GESTION_RIESGOS, controles=("DAT-006", "GOB-010", "RIE-010"), normas=(LEY, ISO),
            refuerzo="Formaliza el protocolo de detección y notificación de incidentes con datos personales y prueba "
                     "el canal de reporte.",
        ),
        Clausula(
            "pol-capacitacion", "Capacitación",
            "Todo colaborador que use herramientas de IA recibe capacitación sobre esta política, el uso seguro y "
            "ético de la IA y la protección de datos personales al incorporarse y al menos [COMPLETAR: periodicidad, "
            "p. ej. una vez al año]. Se mantiene registro de asistencia.",
            dimension=GOBERNANZA_IA, controles=("GOB-004",), normas=(ISO,),
            refuerzo="Incluye esta política en el plan formativo y registra la asistencia de cada colaborador.",
        ),
        Clausula(
            "pol-revision", "Revisión, aprobación y sanciones",
            "La alta dirección revisa esta política y el desempeño de los sistemas de IA al menos una vez al año, o "
            "antes si cambia la normativa o se incorpora un sistema de alto riesgo. El incumplimiento de esta política "
            "se sanciona conforme al Reglamento Interno de la empresa.\n\n"
            "Aprobada por: [COMPLETAR: instancia que aprueba] · Fecha: [COMPLETAR: fecha de aprobación]",
            dimension=GOBERNANZA_IA, controles=("GOB-006", "GOB-007"), normas=(ISO,), adaptable=False,
            refuerzo="Agenda la primera revisión de la dirección sobre IA y deja acta de ella.",
        ),
    ),
)

# ===================================================================== Aviso de privacidad
AVISO_PRIVACIDAD = Plantilla(
    tipo=TipoPlantilla.AVISO_PRIVACIDAD,
    titulo="Aviso de Privacidad y Uso de Inteligencia Artificial",
    nombre_corto="aviso_privacidad",
    descripcion="Información para los titulares sobre qué datos se tratan, con qué finalidad y base, el uso de "
                "IA, proveedores, transferencias, conservación y cómo ejercer sus derechos.",
    proposito="Aviso dirigido a clientes, usuarios y titulares de datos que informa de forma clara el tratamiento "
              "de sus datos personales y el uso de inteligencia artificial, conforme al deber de información de la "
              "Ley 21.719.",
    clausulas=(
        Clausula(
            "avi-responsable", "Quién es el responsable de tus datos",
            "El responsable del tratamiento de tus datos personales es **{{RAZON_SOCIAL}}**, RUT {{RUT_EMPRESA}}, con "
            "domicilio en [COMPLETAR: domicilio]. Puedes contactarnos por cualquier consulta sobre tus datos en "
            "[COMPLETAR: correo o canal de contacto de privacidad].",
            dimension=None, controles=("DAT-010",), normas=(LEY,), adaptable=False,
        ),
        Clausula(
            "avi-datos", "Qué datos tratamos",
            "Tratamos los datos que nos entregas o que se generan al usar nuestros servicios: [COMPLETAR: categorías "
            "de datos, p. ej. identificación, contacto, transacciones, uso del servicio]. No te pediremos más datos "
            "de los necesarios para las finalidades que se indican en este aviso.",
            dimension=PROTECCION_DATOS, controles=("DAT-005",), normas=(LEY,),
        ),
        Clausula(
            "avi-finalidades", "Para qué usamos tus datos y con qué base",
            "Usamos tus datos para: [COMPLETAR: finalidades concretas]. Cada finalidad tiene una base que la "
            "autoriza: tu consentimiento, la ejecución de un contrato contigo, el cumplimiento de una obligación "
            "legal u otra base que reconozca la ley. No usaremos tus datos para fines distintos de los informados "
            "sin una nueva base que lo permita.",
            dimension=PROTECCION_DATOS, controles=("DAT-001", "DAT-003"), normas=(LEY,),
            refuerzo="Antes de publicar este aviso, asocia cada finalidad a su base de licitud documentada.",
        ),
        Clausula(
            "avi-ia", "Uso de inteligencia artificial",
            "Usamos herramientas de inteligencia artificial para [COMPLETAR: usos, p. ej. atención automatizada, "
            "análisis de solicitudes]. Cuando interactúes con un sistema automatizado (por ejemplo, un asistente "
            "virtual) te lo informaremos.\n\n"
            "Antes de enviar tus datos a un modelo de un proveedor externo, los anonimizamos o seudonimizamos cuando "
            "es posible. Ninguna decisión que te afecte significativamente se toma solo de forma automatizada: "
            "puedes pedir que una persona la revise, expresar tu punto de vista y recibir una explicación.",
            dimension=USO_RESPONSABLE, controles=("DAT-010", "SEG-008", "SEG-010"), normas=(LEY,),
            refuerzo="Muestra este apartado también en el punto de contacto donde opera la IA (por ejemplo, al inicio "
                     "del chat) y no solo en el sitio web.",
        ),
        Clausula(
            "avi-proveedores", "Con quién compartimos tus datos",
            "Compartimos tus datos solo con proveedores que nos prestan servicios (incluidos servicios de IA en la "
            "nube) y que actúan por nuestra cuenta, bajo contratos que les exigen confidencialidad y medidas de "
            "seguridad, y con autoridades cuando la ley lo exige. Proveedores principales: [COMPLETAR: categorías o "
            "nombres de proveedores].",
            dimension=PROTECCION_DATOS, controles=("DAT-007",), normas=(LEY,),
        ),
        Clausula(
            "avi-transferencias", "Transferencias internacionales",
            "Algunos proveedores procesan datos en servidores fuera de Chile ([COMPLETAR: países o regiones]). En esos "
            "casos verificamos que exista un nivel adecuado de protección o garantías contractuales que resguarden "
            "tus datos conforme a la ley.",
            dimension=PROTECCION_DATOS, controles=("DAT-008",), normas=(LEY,),
            refuerzo="Identifica qué proveedores de IA procesan datos fuera de Chile y documenta la garantía de cada "
                     "transferencia.",
        ),
        Clausula(
            "avi-sensibles", "Datos sensibles y de niños, niñas y adolescentes",
            "Solo tratamos datos sensibles o de niños, niñas y adolescentes cuando la ley lo permite y con medidas "
            "de seguridad reforzadas. [COMPLETAR: indicar si se tratan y para qué, o eliminar este apartado].",
            dimension=PROTECCION_DATOS, controles=("DAT-009",), normas=(LEY,),
        ),
        Clausula(
            "avi-conservacion", "Cuánto tiempo conservamos tus datos",
            "Conservamos tus datos mientras sean necesarios para las finalidades informadas y por los plazos legales "
            "que correspondan: [COMPLETAR: plazos por categoría]. Cumplido el plazo, los eliminamos o anonimizamos.",
            dimension=PROTECCION_DATOS, controles=("DAT-005",), normas=(LEY,),
        ),
        Clausula(
            "avi-seguridad", "Cómo protegemos tus datos",
            "Aplicamos medidas técnicas y organizativas para proteger tus datos: cifrado de las comunicaciones y del "
            "almacenamiento, control de acceso, registro de las operaciones y protocolos de respuesta ante "
            "incidentes. Si ocurre una vulneración de seguridad que afecte tus datos, te informaremos cuando la ley "
            "lo exija.",
            dimension=USO_RESPONSABLE, controles=("SEG-006", "DAT-006"), normas=(LEY,),
        ),
        Clausula(
            "avi-derechos", "Tus derechos",
            "Puedes ejercer en cualquier momento tus derechos de **acceso, rectificación, supresión, oposición, "
            "portabilidad y bloqueo**, y tu derecho a no ser objeto de decisiones basadas únicamente en tratamiento "
            "automatizado, escribiendo a [COMPLETAR: canal ARCOP]. Responderemos dentro del plazo legal. Si no estás "
            "conforme con la respuesta, puedes reclamar ante la Agencia de Protección de Datos Personales.",
            dimension=PROTECCION_DATOS, controles=("DAT-004",), normas=(LEY,), adaptable=False,
            refuerzo="Habilita y prueba el canal ARCOP antes de publicar el aviso, con un responsable de responder "
                     "dentro del plazo legal.",
        ),
        Clausula(
            "avi-cambios", "Cambios a este aviso",
            "Podemos actualizar este aviso. Publicaremos la versión vigente con su fecha y, si el cambio es relevante, "
            "te lo informaremos por [COMPLETAR: medio]. Última actualización: {{FECHA}}.",
            dimension=None, adaptable=False,
        ),
    ),
)

# ===================================================================== PIA / EIPD
PIA = Plantilla(
    tipo=TipoPlantilla.PIA,
    titulo="Evaluación de Impacto en Protección de Datos (PIA/EIPD) de un sistema de IA",
    nombre_corto="evaluacion_impacto_pia",
    descripcion="Procedimiento y registro de la evaluación de impacto de un sistema de IA: descripción del "
                "tratamiento, necesidad, riesgos para los titulares, medidas y decisión.",
    proposito="Documento que describe un tratamiento de datos con IA, evalúa su necesidad y proporcionalidad, "
              "identifica los riesgos para los derechos de los titulares y define las medidas para mitigarlos, "
              "antes de su puesta en producción.",
    clausulas=(
        Clausula(
            "pia-identificacion", "Identificación de la evaluación",
            "| Campo | Detalle |\n|---|---|\n"
            "| Responsable | {{RAZON_SOCIAL}} (RUT {{RUT_EMPRESA}}) |\n"
            "| Sistema de IA evaluado | [COMPLETAR: nombre del sistema o proyecto] |\n"
            "| Dueño del proceso | [COMPLETAR: cargo] |\n"
            "| Encargado de Protección de Datos | [COMPLETAR: cargo o nombre] |\n"
            "| Fecha de inicio | {{FECHA}} |",
            dimension=None, adaptable=False,
        ),
        Clausula(
            "pia-cuando", "Cuándo se realiza esta evaluación",
            "Esta evaluación es obligatoria antes de poner en producción, o de modificar de forma relevante, un "
            "sistema de IA que pueda implicar un alto riesgo para los titulares, por ejemplo cuando: trata datos "
            "sensibles o de niños, niñas y adolescentes; toma o apoya decisiones automatizadas que los afectan "
            "significativamente; trata datos a gran escala; o monitorea de forma sistemática a personas.",
            dimension=PROTECCION_DATOS, controles=("DAT-002",), normas=(LEY,),
            refuerzo="La empresa no ha ejecutado evaluaciones de impacto: aplica esta plantilla primero a los sistemas "
                     "de IA que ya están en producción con datos de alto riesgo.",
        ),
        Clausula(
            "pia-descripcion", "Descripción sistemática del tratamiento",
            "- **Finalidad del sistema:** [COMPLETAR]\n"
            "- **Categorías de titulares:** [COMPLETAR: clientes, colaboradores, postulantes...]\n"
            "- **Datos tratados** (indicar si hay datos sensibles): [COMPLETAR]\n"
            "- **Origen de los datos:** [COMPLETAR]\n"
            "- **Flujo:** captura → anonimización/seudonimización → modelo de IA → revisión humana → uso del "
            "resultado → conservación y eliminación.\n"
            "- **Proveedores y ubicación del procesamiento:** [COMPLETAR]\n"
            "- **Registro en el RAT:** [COMPLETAR: referencia]",
            dimension=PROTECCION_DATOS, controles=("DAT-005", "GOB-003"), normas=(LEY, ISO),
        ),
        Clausula(
            "pia-necesidad", "Necesidad, proporcionalidad y base de licitud",
            "Se justifica por qué el sistema es necesario para la finalidad, por qué no existe una alternativa menos "
            "invasiva y por qué los datos tratados son los mínimos necesarios. La base de licitud del tratamiento es: "
            "[COMPLETAR: consentimiento, contrato, obligación legal u otra]. Los datos no se usan para fines distintos "
            "de los informados a los titulares.",
            dimension=PROTECCION_DATOS, controles=("DAT-001", "DAT-003"), normas=(LEY,),
            refuerzo="Documenta la base de licitud y la minimización de datos de este sistema antes de evaluar sus "
                     "riesgos.",
        ),
        Clausula(
            "pia-riesgos", "Identificación y evaluación de riesgos para los titulares",
            "| Riesgo para los titulares | Probabilidad | Impacto | Nivel |\n|---|---|---|---|\n"
            "| Acceso no autorizado o fuga de datos en las entradas o salidas del modelo | [COMPLETAR] | [COMPLETAR] | [COMPLETAR] |\n"
            "| Decisiones erróneas o discriminatorias (sesgo) que afectan a una persona | [COMPLETAR] | [COMPLETAR] | [COMPLETAR] |\n"
            "| Uso de los datos para fines no informados o transferencia sin garantías | [COMPLETAR] | [COMPLETAR] | [COMPLETAR] |\n"
            "| Imposibilidad de ejercer derechos (acceso, supresión, oposición) sobre datos usados por la IA | [COMPLETAR] | [COMPLETAR] | [COMPLETAR] |\n"
            "| Manipulación del sistema (prompt injection) para obtener datos de otros titulares | [COMPLETAR] | [COMPLETAR] | [COMPLETAR] |",
            dimension=GESTION_RIESGOS, controles=("RIE-001", "RIE-005"), normas=(NIST,),
            refuerzo="Incluye estos riesgos en la Matriz de Riesgos de IA de la empresa con su dueño y fecha de "
                     "revisión.",
        ),
        Clausula(
            "pia-medidas", "Medidas para mitigar los riesgos",
            "Para cada riesgo alto se define al menos una medida con responsable y plazo:\n\n"
            "- anonimización o seudonimización antes de enviar datos al modelo;\n"
            "- filtros de entrada contra prompt injection y validación de las salidas;\n"
            "- revisión humana de las decisiones que afectan a personas y pruebas periódicas de sesgo;\n"
            "- contrato de encargo y garantías para transferencias internacionales;\n"
            "- registro de auditoría de las interacciones y plan de contingencia;\n"
            "- procedimiento para atender los derechos de los titulares sobre los datos usados por la IA.",
            dimension=USO_RESPONSABLE,
            controles=("SEG-001", "SEG-002", "SEG-008", "SEG-010", "RIE-003", "DAT-004", "DAT-007"),
            normas=(LEY, OWASP, NIST),
            refuerzo="Asigna dueño y fecha a cada medida; las brechas abiertas del autodiagnóstico están en el "
                     "Anexo B de este documento.",
        ),
        Clausula(
            "pia-residual", "Riesgo residual y decisión",
            "Tras aplicar las medidas, el riesgo residual es: [COMPLETAR: bajo / medio / alto]. Si el riesgo residual "
            "sigue siendo alto, el tratamiento no se inicia hasta reducirlo o se consulta a la autoridad cuando la "
            "ley lo exija.\n\n"
            "Decisión: [COMPLETAR: aprobar / aprobar con condiciones / no aprobar] · Aprobado por: [COMPLETAR] · "
            "Fecha: [COMPLETAR]",
            dimension=GESTION_RIESGOS, controles=("RIE-003",), normas=(LEY, NIST), adaptable=False,
        ),
        Clausula(
            "pia-seguimiento", "Seguimiento y revisión",
            "Esta evaluación se revisa cada [COMPLETAR: periodicidad] y cada vez que cambie el sistema, los datos "
            "tratados, el proveedor o la normativa. Se monitorean la precisión del modelo, los incidentes y las "
            "solicitudes de los titulares para detectar riesgos nuevos.",
            dimension=GESTION_RIESGOS, controles=("RIE-002", "RIE-004", "GOB-010"), normas=(NIST, ISO),
        ),
    ),
)

PLANTILLAS: dict[TipoPlantilla, Plantilla] = {p.tipo: p for p in (POLITICA_LLM, AVISO_PRIVACIDAD, PIA)}


def plantilla(tipo: TipoPlantilla | str) -> Plantilla:
    return PLANTILLAS[TipoPlantilla(tipo)]


def catalogo() -> list[dict]:
    """Lo que se muestra al elegir qué borrador generar (sin códigos internos)."""
    return [p.resumen() for p in PLANTILLAS.values()]


def marcadores_pendientes(texto: str) -> int:
    return len(MARCADOR_PENDIENTE.findall(texto or ""))

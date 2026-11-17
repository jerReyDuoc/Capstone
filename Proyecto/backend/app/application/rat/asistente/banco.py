"""
HU-39 · Banco de preguntas de la entrevista guiada (criterio 1).

Las preguntas son FIJAS y las escribe el equipo, no el LLM: así la entrevista sigue igual cuando la IA no
está disponible o se agotó la cuota (criterio 6), el modelo no puede cambiar lo que se pregunta y cada
respuesta queda asociada a un código de pregunta auditable.

Lenguaje simple: se pregunta por lo que la empresa HACE (procesos, sistemas, proveedores), nunca por
personas concretas. Cada pregunta trae una ayuda y respuestas rápidas de ejemplo.
"""
from __future__ import annotations

from dataclasses import dataclass, field

VERSION_BANCO = "banco/1.0.0"


@dataclass(frozen=True)
class Pregunta:
    codigo: str
    texto: str
    ayuda: str
    ejemplos: tuple[str, ...] = field(default_factory=tuple)

    def como_dict(self) -> dict:
        return {"codigo": self.codigo, "texto": self.texto, "ayuda": self.ayuda, "ejemplos": list(self.ejemplos)}


@dataclass(frozen=True)
class Area:
    codigo: str
    nombre: str
    descripcion: str
    preguntas: tuple[Pregunta, ...]

    def como_dict(self) -> dict:
        return {"codigo": self.codigo, "nombre": self.nombre, "descripcion": self.descripcion,
                "preguntas": len(self.preguntas)}


AVISO_PERSONAS = "Describe procesos y sistemas, no a personas: no escribas nombres, RUT, correos ni teléfonos."

AREAS: tuple[Area, ...] = (
    Area("personas", "Personas y equipo", "Trabajadores, postulantes y quienes ya no trabajan contigo.", (
        Pregunta("personas.sistemas",
                 "¿Dónde guardas la información de tus trabajadores? Por ejemplo, contratos, sueldos, asistencia o "
                 "licencias médicas.",
                 "Piensa en sistemas de remuneraciones, planillas, carpetas compartidas o el reloj control. "
                 + AVISO_PERSONAS,
                 ("Usamos un sistema de remuneraciones en la nube y planillas Excel", "Todo está en carpetas físicas y en un disco compartido")),
        Pregunta("personas.terceros",
                 "¿Con quién compartes datos de tus trabajadores? Por ejemplo, la mutual, la caja de compensación, "
                 "una AFP, una isapre o un contador externo.",
                 "Indica a qué organización se envía y para qué. No hace falta el detalle de cada persona.",
                 ("Enviamos las licencias a la mutual y las cotizaciones a Previred", "Un contador externo hace las liquidaciones")),
        Pregunta("personas.seleccion",
                 "¿Cómo reciben y guardan los currículums de las personas que postulan? ¿Cuánto tiempo los conservan?",
                 "Por ejemplo, un portal de empleo, un correo de postulaciones o un formulario en tu sitio web.",
                 ("Llegan a un correo y los guardamos en una carpeta", "Usamos un portal de empleo y no sabemos cuánto los guardamos")),
    )),
    Area("clientes", "Clientes", "Ventas, atención, facturación y despacho.", (
        Pregunta("clientes.sistemas",
                 "¿Qué datos pides a tus clientes y dónde quedan guardados? Por ejemplo, un sistema de ventas, una "
                 "tienda en línea o un CRM.",
                 "Cuenta qué datos se piden (contacto, dirección de despacho, datos de pago) y en qué sistema. "
                 + AVISO_PERSONAS,
                 ("Tenemos una tienda en línea y un CRM", "Registramos a los clientes en el sistema de facturación")),
        Pregunta("clientes.pagos_despacho",
                 "¿Quién procesa los pagos y los despachos? ¿Esa empresa está en Chile o en otro país?",
                 "Por ejemplo, una pasarela de pago, un banco o una empresa de courier.",
                 ("Usamos una pasarela de pago chilena y un courier", "Los pagos los procesa un proveedor de Estados Unidos")),
        Pregunta("clientes.atencion",
                 "¿Cómo atiendes reclamos o consultas de clientes? ¿Grabas llamadas o usas un chat?",
                 "Incluye centros de llamado externos, chats en el sitio web o mesas de ayuda.",
                 ("Tenemos un chat en el sitio y un call center externo", "Solo por correo")),
    )),
    Area("proveedores", "Proveedores", "Empresas que trabajan contigo y pueden ver datos personales.", (
        Pregunta("proveedores.listado",
                 "¿Qué proveedores acceden a datos de tus clientes o trabajadores? Por ejemplo, soporte informático, "
                 "nube, contabilidad, cobranza o seguridad.",
                 "Piensa en quién podría ver o guardar datos personales por trabajar para ti.",
                 ("Una empresa de soporte informático y una de cobranza", "Usamos Google Workspace y un proveedor de respaldos")),
        Pregunta("proveedores.contratos",
                 "¿Tienes contratos firmados con esos proveedores que digan cómo deben cuidar los datos?",
                 "Son los contratos de encargo o las cláusulas de protección de datos. Si no lo sabes, dilo.",
                 ("Sí, con todos", "Con algunos", "No lo sé")),
    )),
    Area("marketing", "Marketing", "Campañas, redes sociales, newsletters y bases de prospectos.", (
        Pregunta("marketing.campanas",
                 "¿Envías publicidad, newsletters o campañas? ¿Con qué herramienta y a quiénes?",
                 "Por ejemplo, una plataforma de correo masivo, WhatsApp o mensajes de texto.",
                 ("Enviamos un newsletter mensual con una plataforma de correo masivo", "No hacemos campañas")),
        Pregunta("marketing.analitica",
                 "¿Mides lo que hacen las personas en tu sitio o app (cookies, píxeles, analítica)? ¿Compras o "
                 "arriendas bases de datos de prospectos?",
                 "Las cookies de publicidad y las bases compradas suelen necesitar una base de licitud distinta.",
                 ("Usamos analítica web y un píxel de redes sociales", "Compramos una base de prospectos")),
    )),
    Area("ti", "Tecnología", "Sistemas internos, respaldos, accesos y seguridad.", (
        Pregunta("ti.infraestructura",
                 "¿Dónde están tus servidores o servicios en la nube y dónde se guardan los respaldos?",
                 "Indica el proveedor y el país si lo sabes (por ejemplo, nube en Estados Unidos).",
                 ("Todo en la nube de un proveedor en Estados Unidos", "Tenemos un servidor en la oficina y respaldos en un disco externo")),
        Pregunta("ti.seguridad",
                 "¿Qué medidas de seguridad usan? Por ejemplo, contraseñas con doble factor, cifrado, perfiles de "
                 "acceso o registro de accesos.",
                 "Esto ayuda a calcular el riesgo de cada actividad.",
                 ("Doble factor y respaldos diarios", "Solo contraseñas")),
    )),
    Area("ia", "Uso de IA", "Herramientas de inteligencia artificial que usan datos personales.", (
        Pregunta("ia.herramientas",
                 "¿Usan herramientas de inteligencia artificial (chatbots, asistentes de redacción, análisis de "
                 "currículums, scoring)? ¿Qué datos les entregan?",
                 "Incluye las que usa cada equipo por su cuenta, como asistentes de chat en el navegador.",
                 ("Usamos un chatbot de atención con IA", "El equipo usa un asistente de chat para redactar correos")),
        Pregunta("ia.decisiones",
                 "¿Alguna herramienta toma decisiones o arma perfiles de personas de forma automática? Por ejemplo, "
                 "aprobar créditos, filtrar postulantes o segmentar clientes.",
                 "Si es así, cuenta si una persona revisa la decisión antes de aplicarla.",
                 ("No, solo apoyan el trabajo", "Sí, filtramos postulantes con un sistema automático")),
    )),
)

AREAS_POR_CODIGO: dict[str, Area] = {a.codigo: a for a in AREAS}
ORDEN_AREAS: tuple[str, ...] = tuple(a.codigo for a in AREAS)
PREGUNTAS_POR_CODIGO: dict[str, Pregunta] = {p.codigo: p for a in AREAS for p in a.preguntas}


def area(codigo: str) -> Area:
    return AREAS_POR_CODIGO[codigo]


def pregunta(area_codigo: str, paso: int) -> Pregunta | None:
    a = AREAS_POR_CODIGO.get(area_codigo)
    if a is None or not 0 <= paso < len(a.preguntas):
        return None
    return a.preguntas[paso]


def siguiente(area_codigo: str, paso: int, completadas: list[str]) -> tuple[str, int, list[str]]:
    """
    (área, paso, áreas completadas) después de responder la pregunta `paso` de `area_codigo`. Al terminar
    un área se pasa a la primera área no completada (en el orden del banco). Si todas están completas,
    el paso queda fuera de rango (la entrevista terminó: queda la revisión final).
    """
    a = AREAS_POR_CODIGO[area_codigo]
    if paso + 1 < len(a.preguntas):
        return area_codigo, paso + 1, list(completadas)
    hechas = list(dict.fromkeys([*completadas, area_codigo]))
    pendiente = next((c for c in ORDEN_AREAS if c not in hechas), None)
    if pendiente is None:
        return area_codigo, len(a.preguntas), hechas
    return pendiente, 0, hechas


def terminada(area_codigo: str, paso: int, completadas: list[str]) -> bool:
    return set(ORDEN_AREAS) <= set(completadas) and pregunta(area_codigo, paso) is None


def resumen_areas(area_actual: str, completadas: list[str]) -> list[dict]:
    return [{**a.como_dict(), "completada": a.codigo in completadas, "actual": a.codigo == area_actual}
            for a in AREAS]

"""
HU-34 criterio 4 · Sugerencias del mapa de datos a partir de la evaluación de la empresa.

Las respuestas del filtro de aplicabilidad (F1–F7) dicen cómo usa la IA la empresa. Si, por
ejemplo, declaró usar un modelo de lenguaje (LLM) externo, el mapa debería tener el flujo hacia
ese proveedor (una transferencia internacional, casi siempre). Este módulo convierte esas
respuestas en propuestas concretas de elementos y flujos que la empresa acepta o descarta.

Reglas:
  - Una sugerencia desaparece si ya se aplicó (su elemento principal está en el mapa, por
    clave) o si la empresa la descartó.
  - Si el mapa ya tiene un elemento que cumple el papel (por ejemplo, un "Sistema con IA"), el
    flujo sugerido sale de ese elemento en vez de crear uno nuevo; al aceptar, la empresa puede
    elegir otro elemento de origen (conector).
  - Todo lo que se agrega queda "por confirmar" y con el origen "evaluacion".
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.application.mapa_datos.plantillas import ElementoPlantilla
from app.domain.mapa_datos.modelo import Elemento

E = ElementoPlantilla


@dataclass(frozen=True)
class FlujoSugerido:
    origen: str            # "nuevo:<clave>" o "id:<id existente>"
    destino: str
    finalidad: str
    datos: tuple[str, ...] = ()
    titulares: tuple[str, ...] = ()
    frecuencia: str | None = None
    medio: str | None = None
    nna: bool = False


@dataclass
class Sugerencia:
    clave: str
    titulo: str
    motivo: str
    descripcion: str
    principal: str                        # clave del elemento que identifica la sugerencia aplicada
    elementos: list[ElementoPlantilla] = field(default_factory=list)
    flujos: list[FlujoSugerido] = field(default_factory=list)
    conector: str | None = None           # clave de un elemento nuevo que se puede reemplazar por uno existente
    candidatos: list[int] = field(default_factory=list)
    usa_existente: int | None = None      # id del elemento existente que ya cumple el papel del conector

    def como_dict(self, nombres: dict[int, str]) -> dict:
        def extremo(ref: str) -> dict:
            tipo, _, valor = ref.partition(":")
            if tipo == "id":
                return {"existente": True, "id": int(valor), "nombre": nombres.get(int(valor), "?")}
            el = next((e for e in self.elementos if e.clave == valor), None)
            return {"existente": False, "clave": valor, "nombre": el.nombre if el else valor}

        return {
            "clave": self.clave, "titulo": self.titulo, "motivo": self.motivo, "descripcion": self.descripcion,
            "elementos": [{"clave": e.clave, "tipo": e.tipo, "subtipo": e.subtipo, "nombre": e.nombre,
                           "descripcion": e.descripcion, "pais": e.pais, "categorias_datos": list(e.datos),
                           "categorias_titulares": list(e.titulares), "rol_tercero": e.rol}
                          for e in self.elementos
                          if not (self.usa_existente and e.clave == self.conector)],
            "flujos": [{"origen": extremo(f.origen), "destino": extremo(f.destino), "finalidad": f.finalidad,
                        "categorias_datos": list(f.datos)} for f in self.flujos],
            "conector": self.conector,
            "candidatos": [{"id": i, "nombre": nombres.get(i, "?")} for i in self.candidatos],
            "usa_existente": self.usa_existente,
        }


_PREGUNTAS = {
    "F2": "procesa datos sensibles (salud, biométricos o perfilamiento)",
    "F3": "usa servicios o plataformas de IA de terceros o en la nube internacional",
    "F4": "usa modelos de lenguaje (LLM), IA generativa o bases vectoriales (RAG)",
    "F5": "usa IA que ejecuta acciones conectada a otros sistemas de la empresa",
    "F6": "usa IA que toma decisiones que afectan a personas",
    "F7": "desarrolla o entrena sus propios modelos de IA",
}


def _motivo(*codigos: str) -> str:
    partes = [_PREGUNTAS[c] for c in codigos if c in _PREGUNTAS]
    if not partes:
        return "Según tu evaluación."
    texto = partes[0] if len(partes) == 1 else ", ".join(partes[:-1]) + " y " + partes[-1]
    return f"En tu evaluación indicaste que tu empresa {texto}."


def _buscar(elementos: list[Elemento], *, tipo: str | None = None, subtipos: tuple[str, ...] = ()) -> list[Elemento]:
    return sorted((e for e in elementos if (tipo is None or e.tipo == tipo)
                   and (not subtipos or e.subtipo in subtipos)), key=lambda e: e.id or 0)


def _con_conector(s: Sugerencia, existentes: list[Elemento], candidatos: list[Elemento]) -> Sugerencia:
    """Si ya hay un elemento que cumple el papel del conector, los flujos salen de él."""
    s.candidatos = [e.id for e in candidatos if e.id is not None]
    if existentes and s.conector:
        uso = existentes[0].id
        s.usa_existente = uso
        s.flujos = [FlujoSugerido(f"id:{uso}" if f.origen == f"nuevo:{s.conector}" else f.origen,
                                  f"id:{uso}" if f.destino == f"nuevo:{s.conector}" else f.destino,
                                  f.finalidad, f.datos, f.titulares, f.frecuencia, f.medio, f.nna)
                    for f in s.flujos]
    return s


def calcular(respuestas: dict[str, bool], elementos: list[Elemento], descartadas: set[str] | None = None) -> list[Sugerencia]:
    """Sugerencias vigentes para las respuestas del filtro y el mapa actual."""
    descartadas = descartadas or set()
    si = {k for k, v in respuestas.items() if v}
    if "F1" in respuestas and not respuestas["F1"]:
        return []                                   # declaró no usar IA: nada que sugerir desde la evaluación
    claves = {e.clave for e in elementos if e.clave}
    sistemas_ia = _buscar(elementos, tipo="sistema", subtipos=("sistema_ia",))
    sistemas = _buscar(elementos, tipo="sistema")
    internos = [e for e in elementos if not e.es_tercero]
    salida: list[Sugerencia] = []

    def asistente() -> ElementoPlantilla:
        return E("sug_asistente_ia", "sistema", "sistema_ia", "Asistente o aplicación con IA generativa",
                 "Chatbot, copiloto o funcionalidad que usa un modelo de lenguaje.", "CL", None,
                 ("comunicaciones", "identificacion"), ("clientes", "trabajadores"))

    # ---------------------------------------------------- F4: proveedor de LLM externo (+ F3)
    if "F4" in si:
        s = Sugerencia(
            "llm_externo", "Flujo hacia tu proveedor de modelos de lenguaje",
            _motivo("F4", "F3") if "F3" in si else _motivo("F4"),
            "Lo que tus usuarios escriben al asistente (instrucciones y contexto) viaja al proveedor del modelo. "
            "Suele ser una transferencia internacional: registra su garantía y qué datos se envían.",
            "sug_llm_proveedor",
            [asistente(),
             E("sug_llm_proveedor", "tercero", "proveedor_ia", "Proveedor de modelos de lenguaje (LLM)",
               "Servicio externo que procesa las instrucciones y devuelve las respuestas del modelo.", "US",
               datos=("comunicaciones", "identificacion"), titulares=("clientes", "trabajadores"), rol="encargado")],
            [FlujoSugerido("nuevo:sug_asistente_ia", "nuevo:sug_llm_proveedor",
                           "Enviar instrucciones (prompts) y contexto al modelo para generar respuestas",
                           ("comunicaciones", "identificacion"), ("clientes", "trabajadores"), "tiempo_real", "api")],
            conector="sug_asistente_ia")
        salida.append(_con_conector(s, sistemas_ia, sistemas))

        s = Sugerencia(
            "base_vectorial", "Base de conocimiento para respuestas con contexto (RAG)", _motivo("F4"),
            "Si el asistente responde con documentos de tu empresa, esos documentos (y los datos personales que "
            "contengan) quedan en una base vectorial. Regístrala y define qué documentos entran.",
            "sug_base_vectorial",
            [asistente(),
             E("sug_base_vectorial", "base_datos", "vectorial", "Base vectorial de documentos (RAG)",
               "Fragmentos de documentos internos que el asistente usa como contexto.", None, None,
               ("identificacion", "contacto", "comunicaciones"), ("clientes", "trabajadores"))],
            [FlujoSugerido("nuevo:sug_base_vectorial", "nuevo:sug_asistente_ia",
                           "Recuperar documentos relevantes para responder", ("identificacion", "comunicaciones"),
                           ("clientes", "trabajadores"), "tiempo_real", "api")],
            conector="sug_asistente_ia")
        salida.append(_con_conector(s, sistemas_ia, sistemas))

    # ---------------------------------------------------- F3 sin F4: servicio de IA de un tercero en la nube
    if "F3" in si and "F4" not in si:
        s = Sugerencia(
            "ia_nube", "Flujo hacia tu servicio de IA en la nube", _motivo("F3"),
            "Los datos que procesa el servicio de IA salen hacia la infraestructura del proveedor, normalmente "
            "fuera de Chile. Registra el país y la garantía de la transferencia.",
            "sug_ia_nube",
            [E("sug_sistema_ia", "sistema", "sistema_ia", "Sistema que usa un servicio de IA",
               "Aplicación de la empresa que envía datos a un servicio de IA externo.", "CL", None,
               ("identificacion",), ("clientes",)),
             E("sug_ia_nube", "tercero", "proveedor_ia", "Servicio de IA en la nube",
               "Plataforma, API o SaaS de IA operado por un tercero.", "US",
               datos=("identificacion",), titulares=("clientes",), rol="encargado")],
            [FlujoSugerido("nuevo:sug_sistema_ia", "nuevo:sug_ia_nube", "Procesar datos con el servicio de IA",
                           ("identificacion",), ("clientes",), "tiempo_real", "api")],
            conector="sug_sistema_ia")
        salida.append(_con_conector(s, sistemas_ia, sistemas))

    # ---------------------------------------------------- F2: datos sensibles
    if "F2" in si:
        s = Sugerencia(
            "datos_sensibles", "Repositorio con datos sensibles", _motivo("F2"),
            "Los datos sensibles exigen un resguardo reforzado. Identifica dónde se guardan y qué sistemas los "
            "usan; luego marca esas categorías en cada elemento y flujo.",
            "sug_repositorio_sensibles",
            [E("sug_repositorio_sensibles", "base_datos", "relacional", "Repositorio de datos sensibles",
               "Base donde se guardan datos de salud, biométricos o de perfilamiento.", "CL", None,
               ("salud", "biometricos", "perfilamiento"), ("clientes",))],
            [])
        if sistemas_ia:
            s.flujos = [FlujoSugerido("nuevo:sug_repositorio_sensibles", f"id:{sistemas_ia[0].id}",
                                      "Usar datos sensibles en el sistema con IA", ("salud", "biometricos"),
                                      ("clientes",), "bajo_demanda", "api")]
        salida.append(s)

    # ---------------------------------------------------- F5: agente con acceso a sistemas corporativos
    if "F5" in si:
        corporativos = _buscar(elementos, tipo="sistema", subtipos=("erp", "crm"))
        nuevos = [E("sug_agente_ia", "sistema", "sistema_ia", "Agente de IA conectado a sistemas de la empresa",
                    "Agente que consulta o modifica datos de otros sistemas por sí mismo.", "CL", None,
                    ("identificacion", "contacto", "comerciales"), ("clientes",))]
        flujos: list[FlujoSugerido] = []
        if corporativos:
            for c in corporativos[:3]:
                flujos.append(FlujoSugerido(f"id:{c.id}", "nuevo:sug_agente_ia", "Consultar y actualizar datos "
                                            "del sistema por medio del agente", ("identificacion", "comerciales"),
                                            ("clientes",), "tiempo_real", "api"))
        else:
            nuevos.append(E("sug_sistemas_corporativos", "sistema", "erp", "Sistemas corporativos conectados",
                            "ERP, CRM u otros sistemas a los que accede el agente.", "CL", None,
                            ("identificacion", "contacto", "comerciales"), ("clientes",)))
            flujos.append(FlujoSugerido("nuevo:sug_sistemas_corporativos", "nuevo:sug_agente_ia",
                                        "Consultar y actualizar datos por medio del agente",
                                        ("identificacion", "comerciales"), ("clientes",), "tiempo_real", "api"))
        salida.append(Sugerencia(
            "agente_ia", "Agente de IA con acceso a tus sistemas", _motivo("F5"),
            "Un agente que actúa sobre otros sistemas multiplica los datos a los que accede. Registra a qué "
            "sistemas se conecta y limita sus permisos al mínimo necesario.",
            "sug_agente_ia", nuevos, flujos))

    # ---------------------------------------------------- F6: decisiones automatizadas
    if "F6" in si:
        fuentes = [e for e in internos if e.tipo == "base_datos"][:1]
        s = Sugerencia(
            "decisiones_automatizadas", "Motor de decisiones automatizadas", _motivo("F6"),
            "Las decisiones automatizadas sobre personas (crédito, contratación, beneficios) requieren explicar "
            "la lógica y permitir revisión humana. Regístralo con los datos que usa para decidir.",
            "sug_motor_decisiones",
            [E("sug_motor_decisiones", "sistema", "sistema_ia", "Motor de decisiones automatizadas",
               "Modelo que evalúa, clasifica o prioriza a personas.", "CL", None,
               ("identificacion", "perfilamiento", "solvencia"), ("clientes", "postulantes"))],
            [FlujoSugerido(f"id:{fuentes[0].id}", "nuevo:sug_motor_decisiones", "Evaluar o clasificar a personas",
                           ("identificacion", "perfilamiento"), ("clientes", "postulantes"), "bajo_demanda", "api")]
            if fuentes else [])
        salida.append(s)

    # ---------------------------------------------------- F7: entrenamiento de modelos propios
    if "F7" in si:
        salida.append(Sugerencia(
            "entrenamiento", "Datos de entrenamiento de modelos propios", _motivo("F7"),
            "Entrenar modelos con datos personales es un tratamiento en sí mismo: registra de dónde salen los "
            "datos, si se anonimizan y dónde se entrena.",
            "sug_datos_entrenamiento",
            [E("sug_datos_entrenamiento", "base_datos", "analitica", "Conjunto de datos de entrenamiento",
               "Datos históricos usados para entrenar y evaluar modelos.", "CL", None,
               ("identificacion", "comerciales", "perfilamiento"), ("clientes",)),
             E("sug_plataforma_ml", "sistema", "sistema_ia", "Plataforma de entrenamiento de modelos",
               "Entorno donde se entrenan, prueban y versionan los modelos.", None, None,
               ("identificacion", "perfilamiento"), ("clientes",))],
            [FlujoSugerido("nuevo:sug_datos_entrenamiento", "nuevo:sug_plataforma_ml",
                           "Entrenar y evaluar modelos", ("identificacion", "perfilamiento"), ("clientes",),
                           "puntual", "archivo")]))

    return [s for s in salida if s.principal not in claves and s.clave not in descartadas]


def sugerencia(respuestas: dict[str, bool], elementos: list[Elemento], clave: str,
               descartadas: set[str] | None = None) -> Sugerencia | None:
    return next((s for s in calcular(respuestas, elementos, descartadas) if s.clave == clave), None)

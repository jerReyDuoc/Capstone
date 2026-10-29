"""
HU-18 · Filtro de entrada del Agente IA (reglas locales, sin servicios externos).

Capa propia del agente que se SUMA a `seguridad.py` (copiado del repo
ComplianceAI-Prompt-Injection, que no se modifica aquí). Decisión del equipo (28-oct):
solo reglas locales, sin clasificador ML externo, por presupuesto.

Orden de evaluación (la primera categoría que calza es la que se audita):

  1. codificado      instrucciones ocultas: base64/hex/base32 que al decodificarse son un
                     ataque, caracteres de control, bidi o "tag" invisibles.
  2. delimitadores   etiquetas del prompt del tutor (</mensaje_usuario>, <historial>...),
                     roles falsos ("system:", "asistente:") o los separadores del prompt.
  3. fuga_prompt     pedir el system prompt, las reglas, las instrucciones o el contexto
                     "en bruto", "textual", "lo que te dieron", "el texto de arriba"...
  4. jailbreak       cambio de rol o de personalidad, "sin restricciones/filtros", "modo
                     desarrollador", DAN, "a partir de ahora eres/ignora"...
  5. uso_indebido    pedir ayuda para falsificar evidencia, ocultar una filtración o un
                     incidente, borrar registros sin rastro o engañar a la fiscalización.
  6. inyeccion       todo lo demás que detecta seguridad.detectar_inyeccion().

Cada regla se prueba sobre varias versiones normalizadas del texto (sin tildes, homoglifos,
"i g n o r a", leetspeak, ROT13, al revés) y, si el mensaje nuevo está limpio, también
sobre el mensaje unido a los anteriores del mismo usuario (ataque repartido en turnos).

El resultado lleva la categoría y el identificador de la regla, NUNCA el texto.
"""
from __future__ import annotations

import re
import unicodedata

from app.domain.ports.filtro_agente_port import CategoriaAtaque, FiltroAgentePort, ResultadoFiltro
from app.domain.ports.prompt_guard_port import PromptGuardPort
from app.infrastructure.security import seguridad

C = CategoriaAtaque

# ------------------------------------------------------------------ reglas (texto sin tildes, minúsculas)
_V_FUGA = (r"(recita\w*|cuentame|cuenta\w*|copia\w*|repite\w*|repiteme|reproduc\w*|imprim\w*|muestra\w*|muestrame|ensename|revela\w*|escribe\w*|"
           r"resume\w*|resumeme|traduc\w*|lista\w*|enumera\w*|dime|di|cuales son|cual es|que dice\w*|comparte\w*|"
           r"pega\w*|devuelve\w*|exporta\w*|transcrib\w*|entrega\w*|envia\w*|mandame)")
_O_FUGA = (r"(instrucciones|reglas|normas|indicaciones|directrices|lineamientos|prompt|system prompt|configuracion|programacion|"
           r"contexto|mensaje (del|de) sistema|politicas internas|texto (de |que esta )?(arriba|anterior|previo))")
_Q_FUGA = (r"(tus|te (dieron|entregaron|pasaron|configuraron|dijeron|programaron)|del sistema|internas?|iniciales?|"
           r"ocult[oa]s|originales?|secret[oa]s|de arriba|anteriores|en bruto|textual\w*|literal\w*|"
           r"palabra por palabra|al pie de la letra|complet[oa]s?|exact[oa]s?|sin resumir|que recibiste|que tienes)")

_REGLAS: list[tuple[CategoriaAtaque, str, re.Pattern]] = [
    # ---------------------------------------------------------- delimitadores / roles falsos
    (C.DELIMITADORES, "etiqueta_prompt", re.compile(
        r"<\s*/?\s*(mensaje_usuario|historial|antecedentes_empresa|contexto|system|sistema|instrucciones|"
        r"assistant|asistente|user|developer)\s*>")),
    (C.DELIMITADORES, "rol_falso", re.compile(
        r"(^|\n)\s*\[?(sistema|system|assistant|asistente|developer|desarrollador|tutor|ia)\]?\s*:\s*\S")),
    (C.DELIMITADORES, "separador_prompt", re.compile(
        r"(═{5,}|contexto de la empresa \(datos del sistema|reglas de seguridad \(prioridad|mensaje nuevo del usuario)")),
    # ---------------------------------------------------------- inyección directa (complementa seguridad.py)
    (C.INYECCION, "ignorar_instrucciones", re.compile(
        r"\b(ignora|ignores|ignoren|ignorame|ignorar|olvida|olvidate|olvides|olvidar|descarta|descartes|descartar|omite|"
        r"omitas|omitir|desatiende|anula|anules|anular|haz caso omiso|no hagas caso|deja de lado|pasa por alto|saltate|"
        r"saltar|no tomes en cuenta|no sigas|no obedezcas|no respetes)\b.{0,40}\b(instruccion\w*|indicacion\w*|regla\w*|"
        r"directri\w*|orden\w*|restriccion\w*|lo anterior|lo de arriba|lo que te (dijeron|indicaron|pidieron|dieron|"
        r"configuraron)|tu (rol|proposito|funcion|papel|programacion)|la gobernanza|el sistema|anteriores|previas)\b")),
    (C.INYECCION, "ignorar_ingles", re.compile(
        r"\b(disregard|override|bypass|ignore|forget)\b.{0,30}\b(above|previous|prior|instructions|rules|safety|system|"
        r"guidelines|everything)\b|\bsystem override\b")),
    (C.INYECCION, "reglas_sin_efecto", re.compile(
        r"\b(las |tus |esas )?(reglas|instrucciones|restricciones|indicaciones)\b.{0,25}\b(ya )?no (aplican|valen|importan|"
        r"rigen|cuentan|existen|corren)\b|\bobedeceme\b|\bobedece (solo )?(a mi|mis ordenes)\b|\bhaz (solo )?lo que (yo )?te diga\b")),
    # ---------------------------------------------------------- fuga del system prompt
    (C.FUGA_PROMPT, "pedir_reglas", re.compile(
        rf"\b{_V_FUGA}\b.{{0,40}}\b{_O_FUGA}\b.{{0,40}}\b{_Q_FUGA}\b|\b{_V_FUGA}\b.{{0,25}}\b{_Q_FUGA}\b.{{0,25}}\b{_O_FUGA}\b")),
    (C.FUGA_PROMPT, "reglas_recibidas", re.compile(
        r"\b(instrucciones|reglas|indicaciones|directrices|prompt|configuracion|contexto)\b\s*(que\s+)?"
        r"(te (dieron|entregaron|pasaron|configuraron|dijeron|programaron)|recibiste|tienes (cargad|configurad|programad)\w*)")),
    (C.FUGA_PROMPT, "system_prompt", re.compile(
        r"\b(system ?prompt|prompt (del|de) sistema|prompt inicial|prompt original|tu prompt|tus instrucciones|"
        r"tus reglas (internas|ocultas|secretas)|mensaje de sistema|instrucciones de sistema)\b")),
    (C.FUGA_PROMPT, "texto_de_arriba", re.compile(
        r"\b(todo )?(el |lo )?(texto|que esta|escrito|anterior) (de )?(arriba|encima|antes) de (este|mi) mensaje\b"
        r"|\btodo lo que (esta|aparece|hay) (arriba|antes)\b")),
    (C.FUGA_PROMPT, "fuga_ingles", re.compile(
        r"\b(repeat|print|show|reveal|output|translate|summari[sz]e|copy|dump|leak)\b.{0,40}"
        r"\b(above|previous|prior|system|initial|hidden|your)\b.{0,30}\b(text|message|instructions|prompt|rules|context)\b"
        r"|\byour (system )?(prompt|instructions|rules)\b")),
    (C.FUGA_PROMPT, "como_te_configuraron", re.compile(
        r"\bcomo te (configuraron|programaron|entrenaron|instruyeron|prepararon|crearon|armaron)\b"
        r"|\bque te (dijeron|indicaron|pidieron|prohibieron|ordenaron|ensenaron|instruyeron)\b"
        r"|\b(were you|you were|have you been) (told|instructed|given|configured|programmed)\b")),
    (C.FUGA_PROMPT, "lo_prohibido", re.compile(
        r"\b(que|lo que) (tienes|te tienen) (prohibido|vetado|restringido)\b|\bque no (puedes|debes|te dejan) "
        r"(decir|contestar|responder|hablar|mostrar|revelar)\b|\b(primera|ultima|primeras|ultimas) (frase|linea|palabra|"
        r"oracion|mensaje)s? (que te|de tu|del sistema)\b|\b(mensaje|texto|frase)s? (anterior|previo|previa)s? al? (mio|"
        r"primero)\b|\b(etiquetas|delimitadores|marcadores|separadores)\b.{0,40}\b(delimitan|usas|contenido|entre|mis "
        r"mensajes|del prompt)\b|\b(en|de) tu (sistema|memoria|configuracion) (interna|oculta)?\b.{0,20}\b(dice|decia|hay|"
        r"guardad\w*)\b")),
    (C.FUGA_PROMPT, "tus_secretos", re.compile(
        r"\b(tus|tu) (secretos|normas|programacion|configuracion|system message|mensaje de sistema)\b"
        r"|\b(texto|contenido|redaccion) (exacto|exacta|literal|original|completo) de (tus|tu|las|la)\b"
        r"|\bwhat is your (system )?(message|prompt|instructions)\b|\bsystem message\b")),
    (C.FUGA_PROMPT, "tal_cual", re.compile(
        r"\b(tal cual|tal como (esta|viene|lo recibiste)|sin cambios|en bruto|textual\w*|literal\w*|palabra por palabra)\b"
        r".{0,40}\b(bloque|contexto|prompt|instrucciones|reglas|mensaje (del )?sistema|indicaciones)\b"
        r"|\b(bloque|contexto|prompt|instrucciones|reglas|indicaciones)\b.{0,40}\b(tal cual|tal como (esta|viene)|en bruto|"
        r"textual\w*|literal\w*|palabra por palabra)\b|\bbloque (de |del )?contexto\b")),
    # ---------------------------------------------------------- jailbreak
    (C.JAILBREAK, "juego_de_rol", re.compile(
        r"\b(juguemos|hagamos|vamos a jugar|jugar)\b.{0,20}\b(un |a un |al |a )?(rol|roleplay|juego de rol|personaje|simulacion)\b")),
    (C.JAILBREAK, "fingir_identidad", re.compile(
        r"\b(finge|fingir|simula|pretende|imagina|supon)\b.{0,25}\b(que eres|ser un|ser otro|que no tienes|que no hay|"
        r"que ya no eres|que estas libre)\b")),
    (C.JAILBREAK, "sin_restricciones", re.compile(
        r"\b(responde|respondes|respondas|responderas|contesta|contestas|contestes|contestaras|habla|hablas|hables|actua|"
        r"actuas|actues|actuaras|eres|seras|estas|funciona|funcionas|funciones|opera|operas|operes|modo)\b.{0,25}"
        r"\bsin (ningun[ao]? |tus |las |los )?(restriccion(es)?|filtros?|censura|limites?|reglas?|politicas?|barreras?)\b")),
    (C.JAILBREAK, "modo_especial", re.compile(
        r"\bmodo (desarrollador|developer|dios|god|dan|sin filtros?|libre|jailbreak|administrador|admin|root|debug|"
        r"depuracion|sin censura|mantenimiento)\b")),
    (C.JAILBREAK, "dan", re.compile(r"\beres dan\b|\b(como|modo|soy) dan\b|\bdo anything now\b|\bjailbreak\w*\b|\bdeveloper mode\b")),
    (C.JAILBREAK, "desde_ahora", re.compile(
        r"\b(a partir de ahora|desde ahora|de ahora en adelante|desde este momento)\b.{0,40}\b(eres|seras|respondes|"
        r"responderas|responde|contesta|contestaras|ignora|ignoras|olvida|actua|actuaras|no sigas|no obedezcas|"
        r"no apliques|tu nombre es|te llamas)\b")),
    (C.JAILBREAK, "cambio_de_rol", re.compile(
        r"\bya no eres\b|\bcambia(r)? (tu|de) (rol|personalidad|identidad|proposito|funcion)\b"
        r"|\b(nuevo|otro) (rol|personaje|proposito) (para ti|que tendras)\b|\bdeja de ser (el |un )?tutor\b")),
    (C.JAILBREAK, "quitar_tus_limites", re.compile(
        r"\b(saltar\w*|desactiv\w*|apag\w*|quit\w*|romp\w*|levant\w*|suspend\w*|deshabilit\w*|liber\w*|elimin\w*|"
        r"anul\w*|desbloque\w*|relaj\w*|olvid\w*|ignor\w*)\b.{0,20}\b(tus|tu|sus)\b.{0,10}\b(limites|restricciones|"
        r"filtros|reglas|directrices|politicas|protecciones|modo seguro|seguridad|censura|candados|barreras|guardarrailes)\b"
        r"|\b(te autorizo|tienes permiso|te doy permiso|te permito)\b.{0,40}\b(saltar|ignorar|romper|olvidar|desactivar|"
        r"no seguir|responder todo|cualquier)\b")),
    (C.JAILBREAK, "nueva_identidad", re.compile(
        r"\beres un (asistente|bot|chatbot|modelo|ia|programa) (generico|general|cualquiera|normal|libre|diferente|"
        r"distint\w*|sin)\b|\btu nombre (sera|es ahora|ahora es)\b|\bte llamaras\b|\bharas (todo )?lo que (te )?"
        r"(pida|diga|ordene)\b|\b(comportate|te comportes|comportarte|comportandote) como\b|\b(quiero|necesito) que "
        r"(seas|actues|hables|respondas|te comportes|funciones)\b.{0,40}\bsin (limites|restricciones|filtros|reglas|censura)\b")),
    (C.JAILBREAK, "rol_ficticio", re.compile(
        r"\bhaz (como|de cuenta) que (eres|fueras|no)\b|\b(en esta|para esta|durante esta) (sesion|conversacion|charla)\b"
        r".{0,20}\b(eres|seras|te llamas|actuas|actuaras)\b|\b(deja|dejes|dejar) (de lado )?(tus|las) (normas|reglas|"
        r"restricciones|instrucciones|politicas)\b|\b(esta permitido|puedes|se permite) (romper|saltar|ignorar|olvidar) "
        r"(las|tus) (reglas|normas|restricciones|instrucciones)\b|\bdesactiva\w* (la|el|los|las) (seguridad|filtros?|"
        r"proteccion\w*|modo seguro|restricciones)\b|\bact like\b|\b(different|another|other) (ai|assistant|model)\b")),
    (C.JAILBREAK, "nueva_tarea", re.compile(
        r"\btu (nueva |verdadera |unica )?(tarea|funcion|mision|rol|proposito|identidad|trabajo) (ahora )?(es|sera)\b"
        r"|\b(interpreta|haz|asume|adopta|toma) (el |un )?(papel|rol|personaje|identidad)\b|\bconviertete en\b"
        r"|\b(habla|responde|contesta|escribe|actua) como si (fueras|tu fueras|no tuvieras)\b"
        r"|\b(no|ya no) como (el |un )?tutor\b|\bse (un|una) (asistente|ia|chatbot|bot|modelo) (general|normal|libre|"
        r"diferente|distint\w*|cualquiera|sin)\b|\bolvidate de (la gobernanza|tu rol|tu papel|ser tutor)\b")),
    (C.JAILBREAK, "jailbreak_ingles", re.compile(
        r"\b(pretend (to be|you are)|act as (if|an? )|roleplay|you are now|from now on you|"
        r"without (any )?(restrictions|filters|rules|limits)|no longer (bound|restricted))\b")),
    # ---------------------------------------------------------- uso indebido (fraude / ocultamiento)
    (C.USO_INDEBIDO, "evidencia_falsa", re.compile(
        r"\b(redact\w*|hac\w*|hazme|crea\w*|creame|genera\w*|escrib\w*|inventa\w*|dame|necesito|consigue\w*|prepara\w*|"
        r"arma\w*|elabora\w*|fabrica\w*|quiero|ayudame)\b.{0,50}\b(evidencias?|pruebas?|documentos?|actas?|registros?|informes?|"
        r"certificados?|firmas?|politicas?|constancias?)\b.{0,15}\b(falsa|falso|falsas|falsos|ficticia|ficticio|ficticias|"
        r"trucha|truchas|inventada|inventado|inventadas|adulterad[oa]s?|de mentira)\b"
        r"|\b(falsific\w*|adulter\w*|maquill\w*)\b.{0,40}\b(evidencia|prueba|documento|acta|registro|informe|certificado|"
        r"firma|resultado|cumplimiento|inventario)s?\b"
        r"|\b(parezca|parezcan|parecer|aparente|aparenten) (real|reales|autentic\w*|legitim\w*|antigu\w*|valid\w*|"
        r"ciert\w*|verdader\w*|oficial\w*)\b"
        r"|\b(fecha (anterior|retroactiva|atrasada|falsa)|antedat\w*|retrofech\w*)\b"
        r"|\b(inventa|inventame|inventar|inventen|invente|fabrica|fabricame|fabricar|fabriquen)\b.{0,30}\b(evidencias?|"
        r"pruebas?|documentos?|actas?|registros?|informes?|certificados?|firmas?|constancias?|resultados?)\b")),
    (C.USO_INDEBIDO, "aparentar_cumplimiento", re.compile(
        r"\b(diga|digan|decir|aparentar|parezca|parecer|simular)\b.{0,30}\b(que )?(cumplimos|cumple|cumplen|estamos cumpliendo)\b"
        r".{0,30}\b(aunque|sin|pero) (no|que no)\b|\baunque no (cumplamos|lo hagamos|sea verdad|sea cierto)\b")),
    (C.USO_INDEBIDO, "ocultar_incidente", re.compile(
        r"\b(ocult\w*|escond\w*|encubr\w*|tapar\w*|no (notificar|reportar|informar|avisar)\w*|"
        r"evit\w* (notific|report|inform|avis|declar)\w*|sin (notificar|reportar|avisar|informar)\w*|"
        r"que no se (entere|sepa|enteren))\b.{0,60}"
        r"\b(filtracion|brecha de seguridad|incidente|vulneracion|fuga de datos|agencia|autoridad|titulares|regulador|"
        r"fiscalizador|auditor\w*)\b")),
    (C.USO_INDEBIDO, "borrar_rastro", re.compile(
        r"\b(borr\w*|elimin\w*|destru\w*|alter\w*|modific\w*|limpi\w*)\b.{0,40}\b(registros?|logs?|bitacoras?|evidencias?|"
        r"auditorias?|historial|rastros?|huellas?)\b.{0,40}\b(sin (dejar )?rastro|sin que (se note|nadie|lo sepan|se entere)|"
        r"antes de (la |una )?(auditoria|fiscalizacion|inspeccion)|para (ocultar|que no)|que no se (note|vea|sepa|detecte))\b")),
    (C.USO_INDEBIDO, "evadir_control", re.compile(
        r"\b(engan(ar|amos|emos|arlo|arla)|burl(ar|amos|emos)|evad(ir|imos|amos)|elud(ir|imos|amos)|trampe(ar|amos|emos|o)|"
        r"hacer trampa|hackear)\b.{0,30}\b(al sistema|el sistema|la plataforma|la evaluacion|la auditoria|a la auditoria|"
        r"la fiscalizacion|la ley|a la agencia|la agencia|el control|el puntaje|al auditor|los auditores|al regulador)\b"
        r"|\b(puntaje|nota|resultado|calificacion) (suba|subir|mejore|mejorar|aumente)\b.{0,20}\bsin (hacer|cumplir|"
        r"evidencia|trabajar)\b")),
    (C.USO_INDEBIDO, "ocultar_al_fiscalizador", re.compile(
        r"\bque (el |la |los |las )?(auditor\w*|agencia|fiscalizador\w*|regulador\w*|inspector\w*|titulares|autoridad\w*) "
        r"no (encuentre|encuentren|vea|vean|detecte|detecten|note|noten|se entere|se enteren|descubra|descubran|sepa|sepan)\b"
        r"|\balgo que (nunca|no) (hicimos|hemos hecho|existe|existio|paso|ocurrio|tenemos)\b"
        r"|\b(genera\w*|haz|hac\w*|crea\w*|falsific\w*|imita\w*|copia\w*|pon\w*)\b.{0,25}\bfirma (del|de la|de)\b"
        r"|\b(haz|hazme|crea\w*|genera\w*|escrib\w*|redact\w*|prepar\w*|arma\w*|elabor\w*|llena\w*|completa\w*)\b.{0,40}"
        r"\b(cifras|datos|numeros|resultados|metricas|porcentajes)\b.{0,10}\b(inventad\w*|falsos|falsas|ficticios|"
        r"maquillad\w*|truchas?)\b"
        r"|\b(elimin\w*|borr\w*|destru\w*|desaparec\w*)\b.{0,25}\b(evidencias?|pruebas?|rastros?|huellas?)\b.{0,10}"
        r"\b(del|de la|de los) (incidente|filtracion|brecha|fuga|ataque|acceso)\b")),
    (C.USO_INDEBIDO, "falsear_registros", re.compile(
        r"\b(asistentes|participantes|personas|firmantes) que no (vinieron|asistieron|participaron|firmaron|estuvieron)\b"
        r"|\b(diciendo|que diga|indicando|afirmando|declarando) que\b.{0,50}\b(aunque|pero|cuando) (no|en realidad no)\b"
        r"|\b(para )?que no (revise|revisen|audite|auditen|fiscalice|fiscalicen|inspeccione|inspeccionen)\b"
        r"|\b(cambia\w*|modific\w*|alter\w*|edita\w*)\b.{0,25}\bfecha\b.{0,30}\bpara que parezca\b"
        r"|\b(mentir\w*|mienta\w*|mentirle|engan\w*) (a la|al|a los|a) (agencia|auditor\w*|regulador\w*|titulares|"
        r"autoridad\w*|fiscalizador\w*|clientes)\b")),
    (C.USO_INDEBIDO, "datos_de_terceros", re.compile(
        r"\b(empresas|clientes|organizaciones|usuarios)\b.{0,15}\b(que usan|de la plataforma|registrad\w*|de complianceia|"
        r"de therion)\b|\b(datos|evaluaciones|brechas|resultados|puntajes|conversaciones) (de|tienen|guardados de|que tienen) "
        r"(las |los )?otr[oa]s (empresas|organizaciones|clientes)\b|\botr[oa]s (empresas|organizaciones|clientes)\b.{0,20}"
        r"\b(evaluaciones|brechas|resultados|puntajes|datos)\b|\bque (evaluaciones|brechas|resultados|puntajes|datos) "
        r"tienen otr[oa]s (empresas|organizaciones|clientes)\b")),
    (C.USO_INDEBIDO, "negar_incidente", re.compile(
        r"\bconvencer a (la agencia|los titulares|el regulador|la autoridad|el auditor|los clientes)\b.{0,30}\bque no\b"
        r"|\bque no (hubo|existio|ocurrio|paso) (ninguna |ningun |nada)?(filtracion|incidente|brecha|vulneracion|fuga)?\b"
        r".{0,40}\b(cuando|aunque|pero) (si|en realidad)\b"
        r"|\bque no (hubo|existio|ocurrio) (ninguna |ningun )?(filtracion|incidente|brecha|vulneracion|fuga)\b")),
    (C.USO_INDEBIDO, "cumplimiento_de_fachada", re.compile(
        r"\b(solo|nada mas) (sea |es |para )?(para )?(mostrar|aparentar|la foto|el papel|la auditoria)\b.{0,30}\b(no la|no lo|"
        r"no se) (vamos a|van a)? ?(aplicar|usar|cumplir)\b|\bde fachada\b|\bno la vamos a aplicar\b")),
]

# Vocabulario normal de gobernanza que seguridad.py marca porque, en una JUSTIFICACIÓN, suele
# ser una orden al LLM ("apruébame"). En el chat del tutor es frecuente y legítimo ("el
# directorio aprueba la política"): se neutraliza solo para la revisión de seguridad.py.
_BENIGNAS_CHAT = [(re.compile(r"\b(a|A)prueb(a|as|an|e|en)\b"), "autoriza")]

_CONTROLES_INVISIBLES = re.compile(r"[​-‏⁠-⁤﻿]")


def _benigno(texto: str) -> str:
    for rx, reemplazo in _BENIGNAS_CHAT:
        texto = rx.sub(reemplazo, texto)
    return texto


def _sin_tildes(texto: str) -> str:
    t = unicodedata.normalize("NFD", texto)
    return "".join(c for c in t if unicodedata.category(c) != "Mn").lower()


def _variantes(texto: str) -> list[str]:
    """Versiones normalizadas: la de seguridad.py (incluye leetspeak, ROT13, al revés...) y la base."""
    try:
        vs = seguridad._variantes(texto)  # noqa: SLF001 (mismo paquete de seguridad)
    except Exception:  # noqa: BLE001
        vs = []
    base = re.sub(r"\s+", " ", _sin_tildes(seguridad.normalizar(texto)))
    guiones = re.sub(r"\s+", " ", re.sub(r"[_*~|]+", " ", base))        # "ignora_las_instrucciones"
    return list(dict.fromkeys([base, guiones, *vs]))


def _reglas(texto: str) -> ResultadoFiltro:
    for v in _variantes(texto):
        for categoria, nombre, rx in _REGLAS:
            if rx.search(v):
                return ResultadoFiltro(True, categoria, nombre)
    return ResultadoFiltro.limpio()


def _decodificados(texto: str) -> list[str]:
    """Contenido oculto en base64/base32/hex (con las mismas reglas de decodificación de seguridad.py)."""
    n = seguridad.normalizar(texto)
    salida = []
    for rx, dec in ((seguridad._RE_HEX, seguridad._dec_hex), (seguridad._RE_B32, seguridad._dec_b32),  # noqa: SLF001
                    (seguridad._RE_B64, seguridad._dec_b64)):  # noqa: SLF001
        for m in rx.finditer(n):
            try:
                oculto = dec(m.group(0))
            except Exception:  # noqa: BLE001
                oculto = None
            if oculto and seguridad._imprimible(oculto):  # noqa: SLF001
                salida.append(oculto)
    return salida


class FiltroAgente(FiltroAgentePort):
    """Reglas del agente + `seguridad.py` (vía PromptGuardPort) para todo lo demás."""

    def __init__(self, guard: PromptGuardPort, max_previos: int = 2):
        self.guard = guard
        self.max_previos = max_previos

    def _evaluar_uno(self, texto: str) -> ResultadoFiltro:
        if not texto or not texto.strip():
            return ResultadoFiltro.limpio()
        # 1. codificado: señales de caracteres o instrucciones dentro de base64/hex
        if seguridad._controles_sospechosos(texto) or len(_CONTROLES_INVISIBLES.findall(texto)) >= 3:  # noqa: SLF001
            return ResultadoFiltro(True, C.CODIFICADO, "caracteres_ocultos")
        for oculto in _decodificados(texto):
            r = _reglas(oculto)
            if r.bloquear or self.guard.detectar_inyeccion(oculto):
                return ResultadoFiltro(True, C.CODIFICADO, f"decodificado:{r.regla or 'inyeccion'}")
        # 2-5. reglas propias del agente
        r = _reglas(texto)
        if r.bloquear:
            return r
        # 6. todo lo que ya detectaba la capa de seguridad del proyecto
        if self.guard.detectar_inyeccion(_benigno(texto)):
            return ResultadoFiltro(True, C.INYECCION, "seguridad")
        return ResultadoFiltro.limpio()

    def evaluar(self, texto: str, previos: list[str] | None = None) -> ResultadoFiltro:
        r = self._evaluar_uno(texto)
        if r.bloquear:
            return r
        previos = [p for p in (previos or []) if p and p.strip()][-self.max_previos:]
        if previos:
            # Ataque repartido: "recuerda: ignora las" + "instrucciones anteriores"
            unido = " ".join([*previos, texto])
            ru = _reglas(unido)
            if not ru.bloquear and self.guard.detectar_inyeccion(_benigno(unido)):
                ru = ResultadoFiltro(True, C.INYECCION, "seguridad")
            if ru.bloquear:
                return ResultadoFiltro(True, ru.categoria, f"multiturno:{ru.regla}")
        return ResultadoFiltro.limpio()

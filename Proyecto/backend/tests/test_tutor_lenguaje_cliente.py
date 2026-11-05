"""
Correcciones 05-11 · El tutor no muestra códigos internos al cliente (prompt tutor/1.3.0 +
humanizar_codigos en la salida del agente).
"""
from app.application.ai.agente.salida import humanizar_codigos, nombre_legible, sin_vocativos_anonimizados
from app.application.ai.prompts import tutor as prompt_tutor

NOMBRES = {"GOB-001": nombre_legible("No existe una política de uso de IA aprobada."),
           "BR-005": nombre_legible("No existe una política de uso de IA aprobada.")}


def test_reemplaza_codigos_conocidos_por_el_nombre_de_la_brecha():
    t = humanizar_codigos("Parte por [GOB-001] y luego revisa BR-005.", NOMBRES)
    assert "GOB-001" not in t and "BR-005" not in t
    assert "«no existe una política de uso de IA aprobada»" in t


def test_codigos_desconocidos_y_estados_del_sistema_quedan_en_lenguaje_simple():
    t = humanizar_codigos("La brecha DAT-999 está no_cumplido (ERR-GOB-003).", NOMBRES)
    assert t == "Esta brecha está no cumplido."


def test_no_toca_normas_ni_numeros_de_ley():
    texto = "La Ley 21.719, ISO/IEC 42001 y NIST AI RMF 100-1 lo exigen."
    assert humanizar_codigos(texto, NOMBRES) == texto


def test_prompt_pide_conversacion_simple_y_sin_codigos():
    assert prompt_tutor.PROMPT_VERSION == "tutor/1.4.1"
    assert "LENGUAJE CON EL USUARIO" in prompt_tutor.SYSTEM
    assert "NUNCA escribas códigos internos" in prompt_tutor.SYSTEM
    assert "GOB-003" not in prompt_tutor.SYSTEM


def test_prompt_responde_saludos_como_charla_simple():
    s = prompt_tutor.SYSTEM
    assert "CHARLA SIMPLE" in s and "Máximo 2 frases" in s
    # el saludo ya no pide resumir el estado de la empresa
    assert "resume en dos frases el estado de la empresa" not in s


def test_sin_etiquetas_usadas_como_vocativo():
    assert sin_vocativos_anonimizados("[NOMBRE_ANON], recuerda que puedes volver cuando quieras.") == \
        "Recuerda que puedes volver cuando quieras."
    assert sin_vocativos_anonimizados("¡Hola, [NOMBRE_ANON]! ¿Con qué partimos?") == "¡Hola! ¿Con qué partimos?"
    assert sin_vocativos_anonimizados("Hola [NOMBRE_ANON], te ayudo.") == "Hola, te ayudo."
    # una etiqueta que es parte del contenido se conserva
    assert sin_vocativos_anonimizados("El RUT [RUT_ANON] no debe ir en la política.") == \
        "El RUT [RUT_ANON] no debe ir en la política."
    assert sin_vocativos_anonimizados(None) is None

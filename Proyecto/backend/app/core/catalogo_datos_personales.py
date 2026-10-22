"""
T-06 — Inventario de datos personales del modelo de base de datos (minimización).

Cada columna de cada tabla del modelo está aquí, con su categoría y, si contiene datos
personales, su finalidad, base de licitud (Ley 21.719), plazo de conservación y
tratamiento. Es la "matriz de minimización" en forma de código:

  - tests/test_t06_minimizacion.py falla si alguien agrega una columna al modelo sin
    clasificarla aquí (o deja aquí una columna que ya no existe). Así la auditoría no
    queda obsoleta con la primera migración nueva.
  - scripts/auditoria_minimizacion.py la cruza con el esquema REAL de PostgreSQL,
    genera el DER y la matriz en CSV y revisa el contenido de las columnas.

Principios aplicados (Ley 21.719, art. 3): finalidad, proporcionalidad (solo los datos
necesarios y por el tiempo necesario), calidad, responsabilidad, seguridad y
confidencialidad.

Las evaluaciones describen a la ORGANIZACIÓN (su gobernanza de IA), no a una persona
natural: puntajes, respuestas SI/NO y clasificaciones se tratan como datos no
personales. Lo personal es quién responde (contacto, credenciales, consentimiento) y
lo que pueda venir escrito en los textos libres y en las evidencias.
"""
from __future__ import annotations

from dataclasses import dataclass

# --------------------------------------------------------------------- categorías
SIN_DP = "sin_datos_personales"      # catálogo, métrica, estado o clave técnica
CONTACTO = "contacto"                # email: identifica directamente a una persona
CREDENCIAL = "credencial"            # secreto de autenticación (solo su hash)
METADATO = "metadato_titular"        # fechas, consentimiento y actores ligados a un titular
TEXTO_LIBRE = "texto_libre"          # lo escribe el titular: puede traer PII
DERIVADO_IA = "derivado_ia"          # salida del LLM sobre texto ya anonimizado
SEUDONIMO = "seudonimo"              # hash/HMAC/código aleatorio ligado a un titular

CATEGORIAS = (SIN_DP, CONTACTO, CREDENCIAL, METADATO, TEXTO_LIBRE, DERIVADO_IA, SEUDONIMO)
CON_DATOS_PERSONALES = frozenset(CATEGORIAS) - {SIN_DP}

# --------------------------------------------------------------------- tratamiento
EN_CLARO = "en_claro"
ANONIMIZADO = "anonimizado"          # etiquetas fijas [RUT_ANON]... antes de persistir (HU-06)
CIFRADO = "cifrado"                  # TextoCifrado, prefijo enc:v1: (excepción ARCOP, HU-06)
HASH = "hash"                        # SHA-256 / PBKDF2: no reversible
HMAC = "hmac"                        # seudónimo con clave (ENTITY_MAP_KEY)
NO_SE_GUARDA = "no_se_guarda"        # la columna existe pero debe quedar NULL

# --------------------------------------------------------------------- bases de licitud
B_CONSENTIMIENTO = "Consentimiento (aviso legal aceptado, HU-04/HU-19)"
B_OBLIGACION_ARCOP = "Obligación legal: atender los derechos del titular (Ley 21.719)"
B_RESPONSABILIDAD = "Obligación legal: principio de responsabilidad, poder demostrar el cumplimiento (Ley 21.719, art. 3)"
B_SEGURIDAD = "Interés legítimo: seguridad del sistema y control de acceso"
B_CONTRATO = "Relación contractual/laboral con el administrador"

# --------------------------------------------------------------------- plazos (config)
C_TITULAR = "Hasta la supresión ARCOP o RETENCION_DATOS_TITULAR_DIAS después de vencer el acceso"
C_ARCOP = "RETENCION_ARCOP_CERRADAS_DIAS después del cierre de la solicitud (luego solo metadatos)"
C_EVENTOS = "RETENCION_EVENTOS_SEGURIDAD_DIAS después de revisado el evento"
C_ADMIN = "Mientras la cuenta esté activa"
C_PRUEBA = "Mientras exista el registro (prueba del consentimiento o de la atención del derecho)"


@dataclass(frozen=True)
class Dato:
    categoria: str
    tratamiento: str = EN_CLARO
    finalidad: str = ""
    base: str = ""
    conservacion: str = ""
    # Qué revisa scripts/auditoria_minimizacion.py en el CONTENIDO de la columna:
    #   "pii"     -> no debe haber RUT, correos ni teléfonos en claro
    #   "cifrado" -> todo valor no nulo debe llevar el prefijo enc:v1:
    #   "nulo"    -> todo valor debe ser NULL
    #   ""        -> no se revisa el contenido
    escaneo: str = ""

    @property
    def es_personal(self) -> bool:
        return self.categoria in CON_DATOS_PERSONALES


_N = Dato(SIN_DP)  # atajo para columnas sin datos personales


def _sin_dp(*columnas: str) -> dict[str, Dato]:
    return {c: _N for c in columnas}


CATALOGO: dict[str, dict[str, Dato]] = {
    # ------------------------------------------------------------ catálogos y agregados
    "dominio": _sin_dp("id", "nombre_dominio"),
    "rubro": _sin_dp("id", "nombre_rubro"),
    "ruta_formativa": _sin_dp(
        "id", "nombre", "dominio_id", "nivel", "objetivo", "objetivos_especificos", "contenidos",
        "horas", "modalidad", "publico_objetivo",
    ),
    "preguntas_filtro": _sin_dp("id_pregunta", "codigo", "orden", "pregunta", "descripcion", "activa"),
    "catalogo_brechas": _sin_dp(
        "id_brecha", "codigo_brecha", "categoria", "comportamiento_detectado", "criticidad",
        "accion_sistema", "ruta_formativa_id",
    ),
    "matriz_controles": _sin_dp(
        "id_control", "codigo_control", "framework_fuente", "articulo_referencia", "tipo_fuente",
        "obligacion", "pregunta_evaluacion", "aplicabilidad", "evidencia_esperada", "criticidad",
        "recomendacion", "test_asociado", "dominio_id", "catalogo_brechas_id_brecha",
    ),
    "benchmark": _sin_dp(
        "id_benchmark", "promedio_puntaje", "mediana_puntaje", "puntaje_maximo", "puntaje_minimo",
        "total_evaluaciones", "Rubro_id", "dominio_id",
    ),
    "resumen": _sin_dp(
        "id_resumen", "puntaje_obtenido", "nivel_madurez", "total_controles_evaluados",
        "Evaluacion_id", "dominio_id",
    ),
    # ------------------------------------------------------------ titulares
    "usuario_temporal": {
        "id": _N,
        "Rubro_id": _N,
        "email": Dato(
            CONTACTO, EN_CLARO,
            finalidad="Invitado: credencial de acceso del titular a sus derechos ARCOP. "
                      "Encuestado público: opcional, para retomar o recibir el informe",
            base=B_CONSENTIMIENTO, conservacion=C_TITULAR,
        ),
        "fecha_expiracion": Dato(
            METADATO, finalidad="Limitar el acceso temporal y calcular la conservación",
            base=B_SEGURIDAD, conservacion=C_TITULAR,
        ),
        "validacion_invitacion": Dato(
            METADATO, finalidad="Saber si la invitación fue validada (habilita el token del titular)",
            base=B_SEGURIDAD, conservacion=C_TITULAR,
        ),
        "fecha_anonimizacion": Dato(
            METADATO, finalidad="Prueba de que se ejecutó la supresión o la conservación vencida",
            base=B_RESPONSABILIDAD, conservacion=C_PRUEBA,
        ),
        "aviso_legal_version": Dato(
            METADATO, finalidad="Prueba de qué aviso legal aceptó el titular",
            base=B_RESPONSABILIDAD, conservacion=C_PRUEBA,
        ),
        "fecha_aceptacion_aviso": Dato(
            METADATO, finalidad="Prueba de cuándo aceptó el aviso legal",
            base=B_RESPONSABILIDAD, conservacion=C_PRUEBA,
        ),
    },
    "usuarios_admin": {
        "id_admin": _N,
        "activo": _N,
        "email": Dato(
            CONTACTO, EN_CLARO, finalidad="Usuario de inicio de sesión del administrador",
            base=B_CONTRATO, conservacion=C_ADMIN,
        ),
        "password_hash": Dato(
            CREDENCIAL, HASH, finalidad="Verificar la contraseña (PBKDF2-SHA256, nunca en claro)",
            base=B_SEGURIDAD, conservacion=C_ADMIN,
        ),
        "fecha_creacion": Dato(
            METADATO, finalidad="Trazabilidad de la cuenta", base=B_SEGURIDAD, conservacion=C_ADMIN,
        ),
        "ultimo_acceso": Dato(
            METADATO, finalidad="Detectar cuentas inactivas o accesos indebidos",
            base=B_SEGURIDAD, conservacion=C_ADMIN,
        ),
    },
    # ------------------------------------------------------------ evaluación
    "evaluacion": {
        **_sin_dp("id", "fecha_inicio", "estado_progreso", "Usuario_temporal_id",
                  "filtro_completado", "fecha_filtro", "origen", "es_prueba"),
        "clave_acceso_hash": Dato(
            CREDENCIAL, HASH,
            finalidad="Que el encuestado anónimo retome su evaluación y ejerza sus derechos",
            base=B_SEGURIDAD, conservacion=C_TITULAR,
        ),
    },
    "respuestas_filtro": _sin_dp("id_respuesta_filtro", "Evaluacion_id", "pregunta_id", "respuesta",
                                 "fecha_respuesta"),
    "respuestas": {
        **_sin_dp("id_respuesta", "estado_clasificacion", "Matriz_controles_id_control",
                  "Catalogo_brechas_id_brecha", "Evaluacion_id", "estado_clasificacion_final",
                  "fuente_clasificacion", "confianza_clasificacion", "fecha_validacion",
                  "clasificacion_revisada", "fecha_revision"),
        "justificacion_usuario": Dato(
            TEXTO_LIBRE, ANONIMIZADO,
            finalidad="Sustentar la clasificación del control (HU-02); la PII se reemplaza por etiquetas",
            base=B_CONSENTIMIENTO, conservacion=C_TITULAR, escaneo="pii",
        ),
    },
    "evidencias": {
        **_sin_dp("id_evidencia", "mime_type", "estado_validacion", "clasificacion_llm", "confianza",
                  "fecha_subida", "fecha_procesada", "Respuestas_id_respuesta"),
        "storage_path": _N,  # HU-06: nombre en disco = UUID, sin el nombre original
        "nombre_archivo": Dato(
            TEXTO_LIBRE, ANONIMIZADO, finalidad="Que el usuario reconozca qué archivo subió",
            base=B_CONSENTIMIENTO, conservacion=C_TITULAR, escaneo="pii",
        ),
        "hash_archivo": Dato(
            SEUDONIMO, HASH, finalidad="Detectar evidencias duplicadas (SHA-256 del original)",
            base=B_SEGURIDAD, conservacion=C_TITULAR,
        ),
        "justificacion_llm": Dato(
            DERIVADO_IA, ANONIMIZADO, finalidad="Explicar la clasificación propuesta por el LLM",
            base=B_CONSENTIMIENTO, conservacion=C_TITULAR, escaneo="pii",
        ),
        "datos_extraidos": Dato(
            DERIVADO_IA, NO_SE_GUARDA,
            finalidad="T-06: sin finalidad ni consumidor definidos; ya no se persiste",
            conservacion="No se conserva", escaneo="nulo",
        ),
        "errores_validacion": Dato(
            DERIVADO_IA, ANONIMIZADO, finalidad="Informar al usuario por qué no se validó la evidencia",
            base=B_CONSENTIMIENTO, conservacion=C_TITULAR, escaneo="pii",
        ),
    },
    # ------------------------------------------------------------ capa de IA y seguridad
    "llamadas_llm": {
        **_sin_dp("id_llamada", "traza_id", "fecha", "tarea", "proveedor", "modelo", "prompt_version",
                  "exito", "tipo_error", "tokens_entrada", "tokens_salida", "costo_estimado_usd",
                  "latencia_ms", "sanitizado", "entidades_anonimizadas", "clasificacion", "confianza",
                  "Evaluacion_id", "Respuestas_id_respuesta", "Evidencias_id_evidencia"),
        # Mensajes técnicos del proveedor; no deben traer texto del usuario
        "detalle_error": Dato(SIN_DP, escaneo="pii"),
        "advertencias": Dato(SIN_DP, escaneo="pii"),
    },
    "sanitizaciones": {
        **_sin_dp("id_sanitizacion", "traza_id", "fecha", "campo", "motor", "duracion_ms", "truncado",
                  "total_entidades", "Evaluacion_id", "Respuestas_id_respuesta",
                  "Evidencias_id_evidencia"),
        "conteo_por_tipo": Dato(SIN_DP, escaneo="pii"),  # solo {tipo: cantidad}
        "entidades": Dato(
            SEUDONIMO, HMAC,
            finalidad="Auditoría de la anonimización y respuesta a un ARCOP de acceso por huella",
            base=B_OBLIGACION_ARCOP, conservacion=C_TITULAR, escaneo="pii",
        ),
        "mapa_cifrado": Dato(
            TEXTO_LIBRE, NO_SE_GUARDA,
            finalidad="HU-06: mapa reversible desactivado; prohibido en producción (T-06)",
            conservacion="No se conserva", escaneo="nulo",
        ),
    },
    "eventos_seguridad": {
        **_sin_dp("id_evento", "fecha", "tipo", "origen", "Evaluacion_id", "Matriz_controles_id_control",
                  "Respuestas_id_respuesta", "Evidencias_id_evidencia", "revisado"),
        "extracto": Dato(
            TEXTO_LIBRE, ANONIMIZADO,
            finalidad="Que el Oficial de Cumplimiento revise el intento de prompt injection",
            base=B_SEGURIDAD, conservacion=C_EVENTOS, escaneo="pii",
        ),
        "hash_texto": Dato(
            SEUDONIMO, HASH, finalidad="Agrupar intentos repetidos sin guardar el texto",
            base=B_SEGURIDAD, conservacion=C_EVENTOS,
        ),
    },
    # ------------------------------------------------------------ derechos ARCOP
    "solicitudes_arcop": {
        **_sin_dp("id_solicitud", "tipo", "estado", "Usuario_temporal_id", "Evaluacion_id",
                  "fecha_creacion", "fecha_actualizacion", "fecha_cierre", "fecha_limite_respuesta",
                  "fecha_limite_informacion", "fecha_prorroga"),
        "codigo_seguimiento": Dato(
            SEUDONIMO, EN_CLARO, finalidad="Que el titular siga su solicitud sin identificarse",
            base=B_OBLIGACION_ARCOP, conservacion=C_PRUEBA,
        ),
        "descripcion": Dato(
            TEXTO_LIBRE, CIFRADO, finalidad="Atender el derecho solicitado (excepción HU-06)",
            base=B_OBLIGACION_ARCOP, conservacion=C_ARCOP, escaneo="cifrado",
        ),
        "respuesta": Dato(
            TEXTO_LIBRE, CIFRADO, finalidad="Comunicar la resolución al titular",
            base=B_OBLIGACION_ARCOP, conservacion=C_ARCOP, escaneo="cifrado",
        ),
    },
    "eventos_solicitud_arcop": {
        **_sin_dp("id_evento", "Solicitudes_arcop_id_solicitud", "fecha", "tipo_evento",
                  "estado_anterior", "estado_nuevo", "actor_rol"),
        "actor_id": Dato(
            METADATO, finalidad="Trazabilidad: quién hizo cada cambio de la solicitud",
            base=B_RESPONSABILIDAD, conservacion=C_PRUEBA,
        ),
        "comentario": Dato(
            TEXTO_LIBRE, CIFRADO, finalidad="Comunicación entre titular y responsable",
            base=B_OBLIGACION_ARCOP, conservacion=C_ARCOP, escaneo="cifrado",
        ),
    },
}


def columnas_personales() -> list[tuple[str, str, Dato]]:
    """[(tabla, columna, dato)] de las columnas con datos personales, en orden estable."""
    return [(t, c, d) for t, cols in CATALOGO.items() for c, d in cols.items() if d.es_personal]

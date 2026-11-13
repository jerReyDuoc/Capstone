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
B_CONTRATO_CLIENTE = "Ejecución del contrato del servicio pagado con la empresa cliente (HU-27)"
B_CONSENTIMIENTO_CONTRATACION = "Consentimiento: el usuario temporal pidió ser contactado para contratar (HU-31)"

# --------------------------------------------------------------------- plazos (config)
C_TITULAR = ("Hasta la supresión ARCOP o el plazo de retención de titulares después de vencer el acceso "
             "(HU-25: lo fija el Oficial de Privacidad en /admin/retencion; por defecto RETENCION_DATOS_TITULAR_DIAS)")
C_ARCOP = "RETENCION_ARCOP_CERRADAS_DIAS después del cierre de la solicitud (luego solo metadatos)"
C_EVENTOS = "RETENCION_EVENTOS_SEGURIDAD_DIAS después de revisado el evento"
C_ADMIN = "Mientras la cuenta esté activa"
C_PRUEBA = "Mientras exista el registro (prueba del consentimiento o de la atención del derecho)"
C_CLIENTE = ("Mientras dure el contrato de la empresa y CONTRATO_GRACIA_DIAS después de su término "
             "(HU-30); luego, las reglas de retención (HU-25)")
C_CONTRATACION = "Hasta migrar la evaluación (se borra al pasar a la empresa) o descartar la solicitud"
C_SESION = "Mientras la cuenta exista (el PO fija una depuración de sesiones y enlaces vencidos, HU-28)"
C_TUTOR = ("TUTOR_RETENCION_DIAS (30) días sin actividad en la conversación, o hasta la supresión ARCOP "
           "del usuario definitivo (HU-15); el usuario también la puede borrar")
B_TUTOR = "Ejecución del contrato del servicio pagado: Agente IA Tutor del panel de formación (HU-15)"
# HU-09: el log es inmutable (no se puede suprimir una fila ni su IP). Una purga solo sería
# por lote sellado y exportado, con un procedimiento del dueño de la BD: plazo pendiente del PO.
C_AUDITORIA = ("Mientras exista el registro del audit_log (inmutable, HU-09). Plazo de conservación "
               "y purga por lote sellado: pendiente de definir por el PO")
C_AUDITOR = "Mientras la cuenta del auditor exista (vence sola; el admin puede desactivarla)"


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
        "activo",  # HU-24
    ),
    "preguntas_filtro": _sin_dp("id_pregunta", "codigo", "orden", "pregunta", "descripcion", "activa",
                                "es_compuerta"),  # HU-24
    "catalogo_brechas": _sin_dp(
        "id_brecha", "codigo_brecha", "categoria", "comportamiento_detectado", "criticidad",
        "accion_sistema", "ruta_formativa_id",
        "activo",  # HU-24
    ),
    "matriz_controles": _sin_dp(
        "id_control", "codigo_control", "framework_fuente", "articulo_referencia", "tipo_fuente",
        "obligacion", "pregunta_evaluacion", "aplicabilidad", "evidencia_esperada", "criticidad",
        "recomendacion", "test_asociado", "dominio_id", "catalogo_brechas_id_brecha",
        "activo",  # HU-24
    ),
    # HU-24: versiones de la matriz normativa (contenido del catálogo, sin datos personales) y
    # el árbol de aplicabilidad vigente. El contenido JSON y la nota los escribe el admin: se
    # revisan igual por si alguien pegó un correo o un RUT.
    "matriz_version": {
        **_sin_dp("id", "etiqueta", "estado", "huella", "version_texto", "base_version_id", "revision",
                  "creado_por_admin_id", "publicado_por_admin_id", "fecha_creacion", "fecha_actualizacion",
                  "fecha_publicacion"),
        "contenido": Dato(SIN_DP, escaneo="pii"),
        "nota_cambio": Dato(SIN_DP, escaneo="pii"),
    },
    "regla_aplicabilidad": _sin_dp("id", "control_id", "pregunta_filtro_id"),
    "benchmark": _sin_dp(
        "id_benchmark", "promedio_puntaje", "mediana_puntaje", "puntaje_maximo", "puntaje_minimo",
        "total_evaluaciones", "Rubro_id", "dominio_id",
        "total_empresas", "percentil_25", "percentil_75",  # HU-10
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
                  "filtro_completado", "fecha_filtro", "origen", "es_prueba",
                  "empresa_id", "fecha_migracion",  # HU-27
                  "fecha_completado",  # HU-29
                  "version_matriz",  # HU-21: "<etiqueta>+<huella>" de la matriz, sin datos personales
                  "matriz_version_id"),  # HU-24: versión de la matriz con la que se respondió
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
                  "clasificacion_revisada", "fecha_revision",
                  "decision_revision", "revisor_admin_id"),  # HU-22
        # HU-22: lo escribe el Oficial de Cumplimiento; se anonimiza igual por si cita a alguien
        "comentario_revision": Dato(SIN_DP, ANONIMIZADO, escaneo="pii"),
        "justificacion_usuario": Dato(
            TEXTO_LIBRE, ANONIMIZADO,
            finalidad="Sustentar la clasificación del control (HU-02); la PII se reemplaza por etiquetas",
            base=B_CONSENTIMIENTO, conservacion=C_TITULAR, escaneo="pii",
        ),
    },
    "evidencias": {
        **_sin_dp("id_evidencia", "mime_type", "estado_validacion", "clasificacion_llm", "confianza",
                  "fecha_subida", "fecha_procesada", "Respuestas_id_respuesta",
                  # HU-17: remediación (estados de la matriz y origen de la evidencia)
                  "origen", "estado_declarado", "estado_previo", "estado_resultante",
                  "puntaje_previo", "puntaje_resultante",
                  "fecha_eliminacion"),  # HU-29: el archivo se borró desde "Mis documentos"
        # HU-17: palabras del CATÁLOGO del control encontradas en el texto (no copia el texto)
        "terminos_control": Dato(SIN_DP, escaneo="pii"),
        "justificacion_remediacion": Dato(
            TEXTO_LIBRE, ANONIMIZADO,
            finalidad="Que la empresa explique al LLM cómo cumple ahora el control (HU-17)",
            base=B_CONTRATO_CLIENTE, conservacion=C_CLIENTE, escaneo="pii",
        ),
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
                  "Evaluacion_id", "Respuestas_id_respuesta", "Evidencias_id_evidencia",
                  "conversacion_tutor_id"),
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
                  "Respuestas_id_respuesta", "Evidencias_id_evidencia", "revisado",
                  "resolucion", "fecha_revision", "revisor_admin_id",  # HU-22
                  "regla"),  # HU-33: identificador de la regla del detector (sin texto)
        "comentario_revision": Dato(SIN_DP, ANONIMIZADO, escaneo="pii"),  # HU-22: nota del oficial
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
        **_sin_dp("id_solicitud", "tipo", "estado", "Usuario_temporal_id", "Evaluacion_id", "Usuario_definitivo_id",
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
    # ------------------------------------------------------------ HU-27: clientes del servicio pagado
    # La empresa es una persona JURÍDICA: razón social y RUT de la empresa no son datos personales.
    "empresa": _sin_dp(
        "id", "razon_social", "rut", "rubro_id", "fecha_inicio_contrato", "fecha_termino_contrato",
        "fecha_creacion", "creada_por_admin_id",
        # HU-30: estado del contrato (motivos de una lista cerrada, sin texto libre)
        "estado_contrato", "fecha_suspension", "motivo_suspension", "fecha_terminacion",
        "motivo_terminacion", "fecha_actualizacion_contrato",
    ),
    "usuario_definitivo": {
        **_sin_dp("id", "empresa_id", "rol", "estado"),
        "nombre": Dato(
            CONTACTO, EN_CLARO, finalidad="Identificar al usuario de la empresa cliente en el servicio pagado",
            base=B_CONTRATO_CLIENTE, conservacion=C_CLIENTE,
        ),
        "email": Dato(
            CONTACTO, EN_CLARO,
            finalidad="Usuario de inicio de sesión y destino del enlace de activación (HU-27)",
            base=B_CONTRATO_CLIENTE, conservacion=C_CLIENTE,
        ),
        "password_hash": Dato(
            CREDENCIAL, HASH, finalidad="Verificar la contraseña (PBKDF2-SHA256, nunca en claro ni por correo)",
            base=B_SEGURIDAD, conservacion=C_CLIENTE,
        ),
        "fecha_creacion": Dato(
            METADATO, finalidad="Trazabilidad de la cuenta", base=B_SEGURIDAD, conservacion=C_CLIENTE,
        ),
        "fecha_activacion": Dato(
            METADATO, finalidad="Prueba de que el propio usuario definió su contraseña",
            base=B_RESPONSABILIDAD, conservacion=C_CLIENTE,
        ),
        "ultimo_acceso": Dato(
            METADATO, finalidad="Detectar cuentas inactivas o accesos indebidos",
            base=B_SEGURIDAD, conservacion=C_CLIENTE,
        ),
    },
    "token_activacion": {
        **_sin_dp("id", "usuario_definitivo_id", "fecha_creacion", "fecha_expiracion", "fecha_uso",
                  "fecha_revocacion", "creado_por_admin_id"),
        "token_hash": Dato(
            CREDENCIAL, HASH, finalidad="Validar el enlace de activación de un solo uso (solo su SHA-256)",
            base=B_SEGURIDAD, conservacion=C_CLIENTE,
        ),
    },
    "solicitud_contratacion": {
        **_sin_dp("id", "evaluacion_id", "razon_social_declarada", "estado", "empresa_id",
                  "fecha_creacion", "fecha_actualizacion", "fecha_migracion"),
        "nombre_contacto": Dato(
            CONTACTO, EN_CLARO, finalidad="Que Therion Labs contacte a quien pidió contratar (HU-31)",
            base=B_CONSENTIMIENTO_CONTRATACION, conservacion=C_CONTRATACION,
        ),
        "cargo_contacto": Dato(
            CONTACTO, EN_CLARO, finalidad="Que Therion Labs sepa con quién habla al contactar (HU-31)",
            base=B_CONSENTIMIENTO_CONTRATACION, conservacion=C_CONTRATACION,
        ),
        "email_contacto": Dato(
            CONTACTO, EN_CLARO, finalidad="Que Therion Labs contacte a quien pidió contratar (HU-31)",
            base=B_CONSENTIMIENTO_CONTRATACION, conservacion=C_CONTRATACION,
        ),
        "telefono_contacto": Dato(
            CONTACTO, EN_CLARO, finalidad="Que Therion Labs contacte a quien pidió contratar (HU-31)",
            base=B_CONSENTIMIENTO_CONTRATACION, conservacion=C_CONTRATACION,
        ),
        "autoriza_migracion": Dato(
            METADATO, finalidad="Prueba de la autorización para traspasar la evaluación a la empresa",
            base=B_RESPONSABILIDAD, conservacion=C_PRUEBA,
        ),
        "consentimiento_version": Dato(
            METADATO, finalidad="Prueba de qué texto de autorización aceptó",
            base=B_RESPONSABILIDAD, conservacion=C_PRUEBA,
        ),
        "fecha_autorizacion": Dato(
            METADATO, finalidad="Prueba de cuándo autorizó el traspaso",
            base=B_RESPONSABILIDAD, conservacion=C_PRUEBA,
        ),
        "consentimiento_contacto_version": Dato(
            METADATO, finalidad="Prueba de qué texto de contacto comercial aceptó (HU-31)",
            base=B_RESPONSABILIDAD, conservacion=C_PRUEBA,
        ),
        "fecha_consentimiento_contacto": Dato(
            METADATO, finalidad="Prueba de cuándo aceptó ser contactado (HU-31)",
            base=B_RESPONSABILIDAD, conservacion=C_PRUEBA,
        ),
    },
    # ------------------------------------------------------------ HU-28: sesiones y recuperación
    # Una fila por inicio de sesión de un admin o de un usuario definitivo. Del identificador
    # de sesión solo queda su SHA-256; actor_id liga la fila a la persona.
    "sesion_usuario": {
        **_sin_dp("id", "actor_rol", "fecha_expiracion", "motivo_cierre"),
        "sid_hash": Dato(
            CREDENCIAL, HASH, finalidad="Validar y revocar la sesión del token (solo su SHA-256, HU-28)",
            base=B_SEGURIDAD, conservacion=C_SESION,
        ),
        "actor_id": Dato(
            METADATO, finalidad="Saber de quién es la sesión para cerrarla (cerrar sesión, cambio de contraseña)",
            base=B_SEGURIDAD, conservacion=C_SESION,
        ),
        "fecha_inicio": Dato(
            METADATO, finalidad="Detectar accesos indebidos", base=B_SEGURIDAD, conservacion=C_SESION,
        ),
        "fecha_cierre": Dato(
            METADATO, finalidad="Revocar el token al cerrar sesión", base=B_SEGURIDAD, conservacion=C_SESION,
        ),
    },
    "token_recuperacion": {
        **_sin_dp("id", "actor_rol", "fecha_creacion", "fecha_expiracion", "fecha_uso", "fecha_revocacion"),
        "actor_id": Dato(
            METADATO, finalidad="Saber a qué cuenta pertenece el enlace de recuperación (HU-28)",
            base=B_SEGURIDAD, conservacion=C_SESION,
        ),
        "token_hash": Dato(
            CREDENCIAL, HASH, finalidad="Validar el enlace de recuperación de un solo uso (solo su SHA-256)",
            base=B_SEGURIDAD, conservacion=C_SESION,
        ),
    },
    # ------------------------------------------------------------ HU-26: formación de la empresa
    # Contenido del catálogo formativo (placeholders) y avance de la EMPRESA (persona jurídica).
    # Los textos/JSON del catálogo los escanea igual la auditoría (no deberían traer PII).
    "leccion_formativa": {
        **_sin_dp("id", "ruta_formativa_id", "orden", "titulo", "duracion_min"),
        **{c: Dato(SIN_DP, escaneo="pii") for c in ("resumen", "contenido", "material_apoyo")},
    },
    "pregunta_verificacion": {
        **_sin_dp("id", "ruta_formativa_id", "orden", "correcta"),
        **{c: Dato(SIN_DP, escaneo="pii") for c in ("enunciado", "opciones", "explicacion")},
    },
    "avance_formativo": {
        "lecciones_vistas": Dato(SIN_DP, escaneo="pii"),  # lista de números de lección
        **_sin_dp("id", "empresa_id", "ruta_formativa_id", "evaluacion_id", "estado",
                  "intentos", "ultimo_puntaje", "mejor_puntaje", "fecha_inicio", "fecha_ultima_actividad",
                  "fecha_completado", "codigo_constancia",
                  "fecha_eliminacion_constancia"),  # HU-29
        "usuario_definitivo_id": Dato(
            METADATO, finalidad="Saber quién registró el avance de la empresa (constancia, HU-26)",
            base=B_CONTRATO_CLIENTE, conservacion=C_CLIENTE,
        ),
    },
    # ------------------------------------------------------------ HU-29: "Mis documentos"
    # Archivos que el sistema genera para la empresa (informes PDF, borradores HU-16). El
    # nombre lo arma el sistema; el archivo está cifrado en STORAGE_DIR (nombre UUID).
    "documento_empresa": {
        **_sin_dp("id", "empresa_id", "evaluacion_id", "tipo", "storage_path", "mime_type",
                  "tamano_bytes", "hash_contenido", "fecha_creacion"),
        "nombre": Dato(SIN_DP, escaneo="pii"),
        "creado_por_usuario_id": Dato(
            METADATO, finalidad="Saber qué usuario de la empresa generó el documento (HU-29)",
            base=B_CONTRATO_CLIENTE, conservacion=C_CLIENTE,
        ),
    },
    # ------------------------------------------------------------ HU-16: borradores de cumplimiento
    # Borrador en revisión de un documento de la EMPRESA (política, aviso de privacidad, PIA).
    # El contenido lo edita la empresa y necesita datos de contacto reales (p. ej. el canal del
    # Encargado de Protección de Datos): se guarda CIFRADO (excepción documentada, como ARCOP).
    # Las instrucciones dadas al Agente IA no se guardan.
    "borrador_documento": {
        **_sin_dp("id", "empresa_id", "evaluacion_id", "tipo", "titulo", "estado", "version", "adaptado_ia",
                  "prompt_version", "traza_id", "version_plantillas", "huella_contexto", "fecha_creacion",
                  "fecha_actualizacion", "fecha_consolidacion", "documento_id"),
        "usuario_definitivo_id": Dato(
            METADATO, finalidad="Saber qué usuario de la empresa generó el borrador (HU-16)",
            base=B_CONTRATO_CLIENTE, conservacion=C_CLIENTE,
        ),
        "contenido": Dato(
            TEXTO_LIBRE, CIFRADO,
            finalidad="Documento de cumplimiento que la empresa revisa y edita antes de consolidarlo (HU-16)",
            base=B_CONTRATO_CLIENTE, conservacion=C_CLIENTE, escaneo="cifrado",
        ),
        "notas": Dato(
            DERIVADO_IA, ANONIMIZADO, finalidad="Puntos que el Agente IA sugiere revisar en el borrador",
            base=B_CONTRATO_CLIENTE, conservacion=C_CLIENTE, escaneo="pii",
        ),
        "advertencias": Dato(SIN_DP, escaneo="pii"),
    },
    # ------------------------------------------------------------ HU-15: Agente IA Tutor
    # Conversación de la EMPRESA con el tutor. Los textos se guardan ANONIMIZADOS (el del
    # usuario es el que vio el LLM tras el NER; el del tutor se re-anonimiza). Un mensaje
    # bloqueado por prompt injection no guarda su texto.
    "conversacion_tutor": {
        **_sin_dp("id", "empresa_id", "evaluacion_id", "ruta_formativa_id", "nivel", "huella_contexto",
                  "mensajes_total", "fecha_creacion"),
        "usuario_definitivo_id": Dato(
            METADATO, finalidad="Saber qué usuario de la empresa abrió la conversación (supresión ARCOP)",
            base=B_TUTOR, conservacion=C_TUTOR,
        ),
        "titulo": Dato(
            TEXTO_LIBRE, ANONIMIZADO, finalidad="Reconocer la conversación en la lista (inicio del primer mensaje)",
            base=B_TUTOR, conservacion=C_TUTOR, escaneo="pii",
        ),
        "fecha_ultimo_mensaje": Dato(
            METADATO, finalidad="Calcular la conservación de la conversación (retención R4)",
            base=B_TUTOR, conservacion=C_TUTOR,
        ),
    },
    "mensaje_tutor": {
        **_sin_dp("id", "conversacion_tutor_id", "rol", "tipo", "nivel", "bloqueado", "motivo_bloqueo",
                  "traza_id", "prompt_version", "huella_contexto", "fecha"),
        "contenido": Dato(
            TEXTO_LIBRE, ANONIMIZADO,
            finalidad="Historial de la conversación con el tutor (y contexto de los mensajes siguientes)",
            base=B_TUTOR, conservacion=C_TUTOR, escaneo="pii",
        ),
        "datos": Dato(
            DERIVADO_IA, ANONIMIZADO, finalidad="Pasos, brechas y referencias de la respuesta del tutor",
            base=B_TUTOR, conservacion=C_TUTOR, escaneo="pii",
        ),
        "advertencias": Dato(SIN_DP, escaneo="pii"),
    },
    # HU-09: audit_log (antes bitacora_auditoria). El detalle lleva solo ids, conteos y códigos
    # (se escanea). La IP es la ÚNICA excepción de minimización de la tabla: la exige el
    # criterio 2 de HU-09 para demostrar la trazabilidad (art. 14 ter).
    "audit_log": {
        **_sin_dp("id", "fecha", "actor_rol", "accion", "entidad", "entidad_id", "resultado",
                  "hash_anterior", "hash"),  # HU-18: cadena de HMAC (no contiene datos)
        "actor_id": Dato(
            METADATO, finalidad="Trazabilidad: quién ejecutó cada acción (HU-09)",
            base=B_RESPONSABILIDAD, conservacion=C_AUDITORIA,
        ),
        "ip": Dato(
            METADATO, finalidad="Trazabilidad: desde dónde se ejecutó cada acción (HU-09, art. 14 ter)",
            base=B_RESPONSABILIDAD, conservacion=C_AUDITORIA,
        ),
        "detalle": Dato(SIN_DP, escaneo="pii"),
    },
    # HU-09: sellos SHA-256 por lote del audit_log (solo hashes, ids y conteos)
    "audit_log_sello": _sin_dp("id", "desde_id", "hasta_id", "cantidad", "hash_lote", "sello_anterior",
                               "sello", "firma", "algoritmo", "fecha"),
    # HU-09: cuentas del Auditor Externo (la organización es la firma auditora, no una persona)
    "usuario_auditor": {
        **_sin_dp("id", "organizacion", "activo", "creado_por_admin_id"),
        "email": Dato(
            CONTACTO, EN_CLARO, finalidad="Usuario de inicio de sesión del Auditor Externo (HU-09)",
            base=B_RESPONSABILIDAD, conservacion=C_AUDITOR,
        ),
        "password_hash": Dato(
            CREDENCIAL, HASH, finalidad="Verificar la contraseña (PBKDF2-SHA256, nunca en claro)",
            base=B_SEGURIDAD, conservacion=C_AUDITOR,
        ),
        "fecha_creacion": Dato(METADATO, finalidad="Trazabilidad de la cuenta", base=B_SEGURIDAD, conservacion=C_AUDITOR),
        "fecha_expiracion": Dato(METADATO, finalidad="Vencimiento del acceso del auditor",
                                 base=B_SEGURIDAD, conservacion=C_AUDITOR),
        "ultimo_acceso": Dato(METADATO, finalidad="Detectar accesos indebidos", base=B_SEGURIDAD, conservacion=C_AUDITOR),
    },
    # HU-25: plazo de retención configurable (fila única). Quién lo cambió va al audit_log.
    "configuracion_retencion": _sin_dp("id", "fuente_plazo", "plazo_titular_dias", "fecha_actualizacion",
                                       "ejecucion_desde"),
    # ------------------------------------------------------------ HU-34: mapa de datos personales
    # Describe los sistemas, bases de datos, terceros y flujos de la ORGANIZACIÓN: no guarda datos
    # de titulares (solo CATEGORÍAS del catálogo común). El responsable interno es un cargo o un
    # área; los textos libres se rechazan al guardar si traen correos, RUT o teléfonos
    # (app/domain/mapa_datos/modelo.py) y la auditoría de contenido los vuelve a revisar ("pii").
    "mapa_datos": {
        **_sin_dp("id", "empresa_id", "version", "plantilla_inicial", "fecha_creacion", "fecha_actualizacion"),
        "sugerencias_descartadas": Dato(SIN_DP, escaneo="pii"),
        "usuario_definitivo_id": Dato(
            METADATO, finalidad="Saber qué usuario de la empresa cambió el mapa por última vez (HU-34)",
            base=B_CONTRATO_CLIENTE, conservacion=C_CLIENTE,
        ),
    },
    "mapa_elemento": {
        **_sin_dp("id", "mapa_id", "tipo", "subtipo", "pais", "nna_declarado", "rol_tercero", "contrato_firmado",
                  "origen", "clave", "pendiente_revision", "fecha_creacion", "fecha_actualizacion",
                  "propuesta_ia_id"),  # HU-39
        **{c: Dato(SIN_DP, escaneo="pii") for c in ("nombre", "descripcion", "proveedor", "responsable",
                                                     "categorias_datos", "categorias_titulares")},
    },
    "mapa_flujo": {
        **_sin_dp("id", "mapa_id", "origen_id", "destino_id", "nna_declarado", "frecuencia", "medio", "cifrado",
                  "garantia", "origen", "clave", "pendiente_revision", "fecha_creacion", "fecha_actualizacion",
                  "propuesta_ia_id"),  # HU-39
        **{c: Dato(SIN_DP, escaneo="pii") for c in ("finalidad", "categorias_datos", "categorias_titulares")},
    },
    # Versiones de solo inserción (criterio 5): la instantánea repite los textos del mapa.
    "mapa_datos_version": {
        **_sin_dp("id", "mapa_id", "empresa_id", "numero", "fecha", "accion", "huella", "elementos", "flujos"),
        **{c: Dato(SIN_DP, escaneo="pii") for c in ("resumen", "cambios", "contenido")},
        "usuario_definitivo_id": Dato(
            METADATO, finalidad="Trazabilidad: qué usuario de la empresa hizo cada cambio del mapa (HU-34)",
            base=B_CONTRATO_CLIENTE, conservacion=C_CLIENTE,
        ),
    },
    # ------------------------------------------------------------ HU-35: registro de actividades (RAT)
    # Describe ACTIVIDADES de la organización con categorías del catálogo común y los ids de lo
    # elegido del mapa: no guarda datos de titulares. Los textos libres (nombre, finalidades,
    # interés legítimo, lógica de decisiones…) se rechazan al guardar si traen correos, RUT o
    # teléfonos (app/domain/rat/modelo.py) y la auditoría de contenido los vuelve a revisar ("pii").
    "rat_actividad": {
        **_sin_dp("id", "empresa_id", "estado", "estado_previo", "revision", "completitud", "version_vigente",
                  "fecha_creacion", "fecha_actualizacion", "fecha_vigencia", "fecha_archivo",
                  "origen", "propuesta_ia_id"),  # HU-39
        **{c: Dato(SIN_DP, escaneo="pii") for c in ("nombre", "contenido", "motivos_revision")},
        "usuario_definitivo_id": Dato(
            METADATO, finalidad="Saber qué usuario de la empresa creó la actividad (HU-35)",
            base=B_CONTRATO_CLIENTE, conservacion=C_CLIENTE,
        ),
    },
    # Versiones vigentes, inmutables (criterio 4): la instantánea repite los textos de la actividad.
    "rat_actividad_version": {
        **_sin_dp("id", "actividad_id", "empresa_id", "numero", "fecha", "huella", "version_mapa"),
        **{c: Dato(SIN_DP, escaneo="pii") for c in ("resumen", "cambios", "contenido")},
        "usuario_definitivo_id": Dato(
            METADATO, finalidad="Trazabilidad: qué usuario de la empresa dejó vigente cada versión (HU-35)",
            base=B_CONTRATO_CLIENTE, conservacion=C_CLIENTE,
        ),
    },
    # ------------------------------------------------------------ HU-36: informe del RAT
    # Cada emisión del informe (PDF y XLSX en "Mis documentos"): código verificable, versión del RAT,
    # huella y cifras del resumen. Sin datos de titulares; los textos (motivos del borrador y el
    # resumen con nombres de categorías) se revisan igual en la auditoría de contenido ("pii").
    "rat_informe": {
        **_sin_dp("id", "empresa_id", "codigo", "version_rat", "huella", "borrador", "actividades",
                  "aviso_version", "fecha", "documento_pdf_id", "documento_xlsx_id"),
        **{c: Dato(SIN_DP, escaneo="pii") for c in ("motivos_borrador", "resumen", "versiones")},
        "usuario_definitivo_id": Dato(
            METADATO, finalidad="Trazabilidad: qué usuario de la empresa emitió cada informe del registro (HU-36)",
            base=B_CONTRATO_CLIENTE, conservacion=C_CLIENTE,
        ),
    },
    # ------------------------------------------------------------ HU-37: informe RoPA
    # Datos que el RoPA pide y el registro no tiene. Son canales de contacto de ORGANIZACIONES (la empresa y
    # las organizaciones por cuenta de las cuales actúa como encargada): la ayuda pide correos genéricos y,
    # para el delegado, el cargo o el área, no el nombre de una persona. Aun así un correo puede identificar
    # a alguien: se clasifican como contacto, van cifrados en reposo (misma excepción que los borradores,
    # HU-16, con su propia subclave) y nunca se copian a la bitácora de auditoría.
    "ropa_datos": {
        **_sin_dp("id", "empresa_id", "fecha_actualizacion"),
        "contenido": Dato(
            CONTACTO, CIFRADO,
            finalidad="Datos de contacto que exige el formato RoPA (responsable o encargado, su delegado de "
                      "protección de datos y las organizaciones por cuenta de las cuales actúa), informados por "
                      "la empresa para sus informes (HU-37)",
            base=B_CONTRATO_CLIENTE, conservacion=C_CLIENTE, escaneo="cifrado",
        ),
        "actualizado_por_usuario_id": Dato(
            METADATO, finalidad="Trazabilidad: qué usuario de la empresa actualizó los datos del RoPA (HU-37)",
            base=B_CONTRATO_CLIENTE, conservacion=C_CLIENTE,
        ),
    },
    # Cada emisión del informe RoPA (PDF y XLSX en "Mis documentos"): código, versión, huella, partes y
    # conteos. Sin datos de titulares.
    "ropa_informe": {
        **_sin_dp("id", "empresa_id", "codigo", "version", "huella", "actividades", "aviso_version", "fecha",
                  "documento_pdf_id", "documento_xlsx_id"),
        **{c: Dato(SIN_DP, escaneo="pii") for c in ("partes", "resumen", "versiones")},
        "usuario_definitivo_id": Dato(
            METADATO, finalidad="Trazabilidad: qué usuario de la empresa emitió cada informe RoPA (HU-37)",
            base=B_CONTRATO_CLIENTE, conservacion=C_CLIENTE,
        ),
    },
    # ------------------------------------------------------------ HU-39: asistente de IA del mapa y del RAT
    # La entrevista describe PROCESOS de la empresa, no personas. Lo que escribe el usuario se guarda
    # anonimizado (el mismo texto que vio el LLM) y las propuestas pasan por el NER antes de guardarse.
    # Los documentos subidos NO se guardan: solo su huella y sus metadatos.
    "asistente_sesion": {
        **_sin_dp("id", "empresa_id", "area_actual", "paso", "estado", "fecha_creacion", "fecha_actualizacion"),
        "areas_completadas": Dato(SIN_DP, escaneo="pii"),   # lista de códigos de área
        "usuario_definitivo_id": Dato(
            METADATO, finalidad="Saber qué usuario de la empresa hizo la entrevista del asistente (HU-39)",
            base=B_CONTRATO_CLIENTE, conservacion=C_CLIENTE,
        ),
    },
    "asistente_mensaje": {
        **_sin_dp("id", "sesion_id", "rol", "area", "pregunta_codigo", "bloqueado", "motivo_bloqueo", "motivo_sin_ia",
                  "traza_id", "prompt_version", "fecha"),
        "contenido": Dato(
            TEXTO_LIBRE, ANONIMIZADO, finalidad="Respuestas de la entrevista con que el asistente propuso el registro",
            base=B_CONTRATO_CLIENTE, conservacion=C_CLIENTE, escaneo="pii",
        ),
    },
    "asistente_documento": {
        **_sin_dp("id", "empresa_id", "sesion_id", "tipo_archivo", "tipo_documento", "huella_sha256", "estado",
                  "regla_detector", "lineas_omitidas", "pasajes_total", "pasajes_usados", "entidades_anonimizadas",
                  "motivo_sin_ia", "traza_id", "fecha"),
        "nombre_archivo": Dato(
            TEXTO_LIBRE, ANONIMIZADO, finalidad="Reconocer el documento analizado en la lista (HU-39)",
            base=B_CONTRATO_CLIENTE, conservacion=C_CLIENTE, escaneo="pii",
        ),
        "usuario_definitivo_id": Dato(
            METADATO, finalidad="Saber qué usuario de la empresa subió el documento (HU-39)",
            base=B_CONTRATO_CLIENTE, conservacion=C_CLIENTE,
        ),
    },
    "asistente_propuesta": {
        "campos_editados": Dato(SIN_DP, escaneo="pii"),     # lista de nombres de campos
        **_sin_dp("id", "empresa_id", "sesion_id", "documento_id", "origen", "area", "tipo", "clave", "estado",
                  "riesgo_nivel", "confianza", "modelo", "prompt_version", "traza_id",
                  "version_mapa_base", "entidad_destino", "entidad_destino_id", "fecha_decision", "motivo_descarte",
                  "fecha_creacion"),
        **{c: Dato(DERIVADO_IA, ANONIMIZADO, finalidad="Propuesta del asistente y lo que confirmó el usuario (HU-39)",
                   base=B_CONTRATO_CLIENTE, conservacion=C_CLIENTE, escaneo="pii")
           for c in ("payload_propuesto", "payload_final", "explicaciones", "inconsistencias")},
        "decidido_por": Dato(
            METADATO, finalidad="Human-in-the-Loop: qué usuario aceptó, editó o descartó la propuesta (HU-39)",
            base=B_CONTRATO_CLIENTE, conservacion=C_CLIENTE,
        ),
    },
}


def columnas_personales() -> list[tuple[str, str, Dato]]:
    """[(tabla, columna, dato)] de las columnas con datos personales, en orden estable."""
    return [(t, c, d) for t, cols in CATALOGO.items() for c, d in cols.items() if d.es_personal]

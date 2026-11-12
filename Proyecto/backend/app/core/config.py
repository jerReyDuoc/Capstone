import re
from pathlib import Path
from typing import Literal
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Un solo .env para todo el proyecto: Proyecto/.env (junto al docker-compose.yml). En Docker
# no existe dentro de la imagen: compose lo entrega como variables (env_file), que tienen
# prioridad sobre el archivo. Fuera de Docker (pytest/uvicorn locales) se lee directo.
ENV_PROYECTO = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    DATABASE_URL: str
    DATABASE_URL_SYNC: str
    REDIS_URL: str
    # Obligatoria con LLM_PROVIDER=groq (con un modelo local, HU-07, puede quedar vacía)
    GROQ_API_KEY: str = ""
    # openai/gpt-oss-20b y gpt-oss-120b admiten salida ESTRICTA en Groq (el JSON siempre
    # cumple el schema). gpt-oss-safeguard-20b solo "best effort": falla más seguido.
    LLM_MODEL: str = "openai/gpt-oss-20b"
    UMBRAL_CONFIANZA: float = 0.8
    STORAGE_DIR: str = "./storage"
    # Caracteres de la evidencia que se analizan y se envían al LLM
    MAX_CHARS_EVIDENCIA_LLM: int = 8000
    # HU-02: largo mínimo (caracteres, sin contar espacios repetidos ni de los
    # extremos) de la justificación obligatoria en 'parcialmente_cumplido' y
    # 'requiere_revision'.
    JUSTIFICACION_MIN_CARACTERES: int = 20
    # Correcciones 05-11 (pedido del equipo): la justificación es OPCIONAL en todos los
    # estados. Con true vuelve la regla original de la HU-02 (obligatoria en parcial y
    # requiere revisión, con el largo mínimo de arriba).
    JUSTIFICACION_OBLIGATORIA: bool = False
    # Correcciones 05-11: para completar la evaluación, cada pregunta declarada "cumplido"
    # necesita al menos una evidencia (igual que "requiere revisión"). Con false se permite
    # completar sin ella (útil para poblar datos de prueba).
    EVIDENCIA_OBLIGATORIA_CUMPLIDO: bool = True
    # OBSOLETO: lo reemplaza SANITIZER_ENABLED (con el sanitizador activo el NER es
    # siempre obligatorio). Se mantiene para no romper archivos .env existentes.
    REQUIERE_NER: bool = False
    # Qué hacer si la EVIDENCIA parece contener prompt injection:
    #   "bloquear" -> no se envía al LLM; la respuesta queda en requiere_revision
    #   "marcar"   -> se envía (anonimizada y delimitada), se registra el evento y,
    #                 si el LLM no está seguro, queda en requiere_revision (sin fallback al usuario)
    MODO_SEGURIDAD_EVIDENCIA: Literal["bloquear", "marcar"] = "bloquear"
    # HU-07: qué hacer si la SALIDA del modelo tiene un hallazgo grave (dato inventado, fuga de
    # datos personales o del system prompt, señal de inyección o formato inválido):
    #   "bloquear" -> no se aplica la propuesta; la pregunta queda en requiere_revision (en la
    #                 remediación el control no cambia) y se registra la alerta
    #   "marcar"   -> se registra la alerta y la propuesta se aplica como siempre
    MODO_VERIFICACION_SALIDA: Literal["bloquear", "marcar"] = "bloquear"

    # ------------------------------------------------ Capa de Políticas e IA
    APP_ENV: Literal["development", "test", "production"] = "development"
    # Proveedor del LLM (cambiarlo no toca la lógica de negocio)
    # HU-07: "ollama" = modelo local (el texto no sale del servidor); ver OLLAMA_URL
    LLM_PROVIDER: Literal["groq", "ollama"] = "groq"
    # HU-07: dirección del servidor Ollama (servicio "ollama" del compose, perfil modelo-local)
    OLLAMA_URL: str = "http://ollama:11434"
    LLM_TIMEOUT_S: float = 60.0
    LLM_MAX_REINTENTOS: int = 2
    # Incluye los tokens de razonamiento de gpt-oss: con muy pocos el JSON queda cortado.
    LLM_MAX_TOKENS_SALIDA: int = 4096
    # Esfuerzo de razonamiento (solo gpt-oss-20b/120b): low | medium | high
    LLM_REASONING_EFFORT: Literal["low", "medium", "high"] = "low"
    # Reintentos cuando el modelo devuelve una salida inválida (JSON cortado / fuera del schema)
    LLM_REINTENTOS_SALIDA: int = 1
    MAX_CHARS_JUSTIFICACION_LLM: int = 4000
    # Precio del modelo en USD por millón de tokens, para estimar costo en las
    # métricas. Tómalos de la página de precios del proveedor para LLM_MODEL.
    LLM_PRECIO_ENTRADA_USD_1M: float = 0.0
    LLM_PRECIO_SALIDA_USD_1M: float = 0.0
    # true  -> el motor NER anonimiza todo antes del LLM (obligatorio en producción)
    # false -> SOLO DEBUG: el texto va en claro al LLM. Prohibido si APP_ENV=production.
    SANITIZER_ENABLED: bool = True
    # Clave maestra Fernet de los datos personales (ver app/infrastructure/security/cifrado.py).
    # De ella se derivan: las huellas HMAC del mapa de entidades, el cifrado de los
    # archivos de evidencia hasta que se anonimizan y el de los textos ARCOP (HU-06).
    # Generar con:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    ENTITY_MAP_KEY: str | None = None
    # HU-06 (decisión del PO, 16-oct): la anonimización es IRREVERSIBLE. En la tabla
    # sanitizaciones quedan solo conteos y huellas HMAC, no los valores originales.
    # true reactiva el mapa cifrado (reversible) y debe documentarse como excepción.
    GUARDAR_MAPA_ENTIDADES_CIFRADO: bool = False
    # ------------------------------------------------ Autenticación de la API
    # Secreto HMAC para firmar/verificar los tokens bearer (app/core/autenticacion.py).
    AUTH_SECRET: str | None = None
    AUTH_TOKEN_TTL_MIN: int = 480
    # ------------------------------------------------ Plazos de solicitudes ARCOP
    # Ley 21.719 (art. 11 de la Ley 19.628 reemplazado): el responsable responde en
    # 30 días CORRIDOS desde que recibe la solicitud, prorrogables UNA vez por hasta
    # 30 días más; el bloqueo temporal se responde en 2 días HÁBILES.
    ARCOP_PLAZO_RESPUESTA_DIAS: int = 30
    ARCOP_PLAZO_PRORROGA_DIAS: int = 30
    ARCOP_PLAZO_BLOQUEO_DIAS_HABILES: int = 2
    # Días que tiene el titular para aportar antecedentes pedidos. La ley no lo fija:
    # vacío = sin plazo (decisión del equipo).
    ARCOP_PLAZO_INFORMACION_DIAS: int | None = None

    # ------------------------------------------------ HU-19: encuesta pública (landing)
    # Versión vigente del aviso legal (HU-04). El frontend envía la versión que mostró;
    # si no coincide se rechaza (409 AVISO_DESACTUALIZADO) y debe volver a aceptarlo.
    AVISO_LEGAL_VERSION: str = "2026-10-v1"
    # Días que el usuario temporal anónimo puede retomar su evaluación.
    ENCUESTA_DIAS_VIGENCIA: int = 30
    # Cloudflare Turnstile (CAPTCHA al iniciar). Vacío solo en development/test: se omite
    # la verificación con un aviso en el log. Claves de prueba de Cloudflare:
    #   secreto que siempre aprueba 1x0000000000000000000000000000000AA
    TURNSTILE_SECRET_KEY: str | None = None
    TURNSTILE_VERIFY_URL: str = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
    # Secreto compartido con el BFF de Next.js (frontend-next). Solo con él la API
    # confía en la IP del cliente que el BFF reenvía en X-Cliente-IP; sin él, la IP
    # sería la del contenedor web y todos compartirían el mismo límite.
    BFF_SHARED_SECRET: str | None = None
    # Límites contra abuso (solo evaluaciones de la encuesta pública, origen='publica')
    ENCUESTA_INTENTOS_IP_10MIN: int = 10          # intentos de iniciar (también fallidos)
    ENCUESTA_EVALUACIONES_IP_DIA: int = 10        # evaluaciones creadas por IP y día
    ENCUESTA_MAX_EVIDENCIAS_EVALUACION: int = 30  # evidencias en toda la evaluación
    ENCUESTA_MAX_EVIDENCIAS_IP_DIA: int = 100     # evidencias por IP y día
    # Cuota diaria de validaciones con IA (1 evidencia subida = 1 validación). Se
    # reinicia a medianoche de ZONA_HORARIA_CUOTAS. 0 = sin límite.
    LLM_CUOTA_DIARIA_EVALUACION: int = 40
    LLM_CUOTA_DIARIA_GLOBAL: int = 2000
    ZONA_HORARIA_CUOTAS: str = "America/Santiago"
    # HU-20: las rutas de evaluaciones, respuestas, evidencias y reportes exigen el token
    # del encuestado/referente o de un admin (true, por defecto). false = SOLO DESARROLLO:
    # deja abiertas sin token las evaluaciones POR INVITACIÓN (p. ej. el modo interno del
    # panel prototipo). Las de la encuesta pública lo exigen siempre. Prohibido en production.
    EXIGIR_TOKEN_EVALUACIONES: bool = True

    # ------------------------------------------------ Comparativa e informes (HU-12/HU-13)
    # "Lo que debería cumplir": puntaje de referencia por dimensión que se muestra junto al
    # resultado. 75 = techo de "gestionado" (controles definidos, documentados y con dueño).
    META_CUMPLIMIENTO_PUNTAJE: float = 75.0
    # HU-21: etiqueta de la versión de la matriz de controles que se imprime en el informe.
    # El informe la acompaña de una huella del contenido ("2026.1+3fa9c2d1"), así un cambio en
    # la matriz se nota aunque nadie suba la etiqueta. Súbela al publicar una matriz nueva.
    MATRIZ_VERSION: str = "2026.1"
    # HU-10 · k-anonimato de la comparativa sectorial. Las métricas de un rubro (promedio,
    # diferencia, posición) solo se publican si la cohorte tiene al menos K_ANONIMATO_MINIMO
    # EMPRESAS distintas (no evaluaciones: una empresa que se reevalúa cuenta una vez). Con
    # menos se suprimen, sin revelar cuántas hay, y la interfaz muestra una advertencia.
    # En production no puede bajar de 5 (criterio de aceptación). Reemplaza a
    # COMPARATIVA_MIN_MUESTRAS (HU-12), que contaba evaluaciones y valía 3.
    K_ANONIMATO_MINIMO: int = 5
    # Mediana y percentiles 25/75 exigen una cohorte mayor: con pocas empresas un percentil
    # coincide con el puntaje exacto de una de ellas. Debe ser >= K_ANONIMATO_MINIMO.
    K_ANONIMATO_DISTRIBUCION: int = 10
    # Recalcular el benchmark al completar cada evaluación (además del cron diario de las
    # 02:00 UTC). Sin esto la comparativa no aparece hasta el día siguiente.
    BENCHMARK_AL_COMPLETAR: bool = True

    # ------------------------------------------------ Envío del informe por correo
    #   smtp       -> se envía por SMTP_* (producción)
    #   archivo    -> se guarda el .eml en STORAGE_DIR/correos (desarrollo, sin servidor de correo)
    #   desactivado-> el endpoint responde 503 CORREO_NO_DISPONIBLE
    CORREO_MODO: Literal["smtp", "archivo", "desactivado"] = "archivo"
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USUARIO: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_STARTTLS: bool = True           # 587 + STARTTLS; con SMTP_SSL=true usa 465 directo
    SMTP_SSL: bool = False
    SMTP_TIMEOUT_S: float = 20.0
    CORREO_REMITENTE: str = "ComplianceIA <no-responder@complianceia.cl>"
    # Envíos del informe por evaluación y por IP en el día (contra abuso del correo).
    INFORME_CORREOS_DIA_EVALUACION: int = 3
    INFORME_CORREOS_DIA_IP: int = 10

    # ------------------------------------------------ T-06: plazos de conservación
    # Ley 21.719 (principio de proporcionalidad): los datos personales se conservan
    # solo el tiempo necesario para su finalidad. Vencido el plazo, el worker
    # (cron diario) los anonimiza con las mismas reglas que una supresión ARCOP:
    # se borran correos, textos, archivos y huellas y se conservan los puntajes.
    # Vacío = regla desactivada (el PO debe fijar los valores; ver Extras/Cambios/backend/CAMBIOS_T06.md).
    #   Titulares: días DESPUÉS de vencer el acceso (usuario_temporal.fecha_expiracion).
    RETENCION_DATOS_TITULAR_DIAS: int | None = None
    #   Solicitudes ARCOP: días después del cierre; quedan tipo, estados, fechas e historial.
    RETENCION_ARCOP_CERRADAS_DIAS: int | None = None
    #   Eventos de seguridad: días después del evento, solo si ya fue revisado.
    RETENCION_EVENTOS_SEGURIDAD_DIAS: int | None = None
    # ------------------------------------------------ HU-25: retención de usuarios temporales
    # El Oficial de Privacidad cambia el plazo de RETENCION_DATOS_TITULAR_DIAS desde el panel
    # interno (/admin/retencion). Lo que fije allí queda en la tabla configuracion_retencion y
    # manda sobre la variable de entorno; la variable es el valor inicial y el de respaldo.
    # Límites del plazo que acepta el panel (días). El mínimo evita que un error de tipeo
    # ("1" en vez de "100") anonimice de un día para otro a todos los titulares vencidos.
    RETENCION_TITULAR_MIN_DIAS: int = 30
    RETENCION_TITULAR_MAX_DIAS: int = 3650
    # Hora UTC (0-23) del cron diario de retención (03:00 UTC = 00:00 en Chile en verano).
    RETENCION_HORA_UTC: int = 3
    # Tiempo máximo de una ejecución en el worker (segundos). El resto de las tareas usa 300.
    RETENCION_TIMEOUT_S: int = 3600
    # Una ejecución marca "en curso" en la BD para que otra (cron y manual a la vez) no se
    # cruce. Si el worker muere a mitad de camino, la marca se considera abandonada pasados
    # estos minutos. Debe ser mayor que RETENCION_TIMEOUT_S.
    RETENCION_BLOQUEO_MAX_MIN: int = 120

    # ------------------------------------------------ HU-27: empresa cliente y usuario definitivo
    # Horas de validez del enlace de activación (un solo uso). Vencido, un admin lo reenvía.
    ACTIVACION_TTL_HORAS: int = 72
    # Página del frontend que recibe el enlace. El token va en el FRAGMENTO (#token=...):
    # el navegador no lo envía al servidor ni queda en logs de acceso ni en el Referer.
    # En production debe ser https:// (se comprueba al emitir el enlace, antes de guardar nada).
    ACTIVACION_URL_BASE: str = "http://localhost:3000/activar"
    # Largo mínimo de la contraseña del usuario definitivo (además: letras y números).
    CLIENTE_PASSWORD_MIN: int = 12
    # Versión vigente del texto con que el usuario temporal autoriza el traspaso de su
    # evaluación al pedir contratar (HU-31; el PO aún debe aprobar el texto definitivo).
    # HU-31 subió la versión porque reescribió el texto (sigue provisorio hasta que lo apruebe el PO).
    CONSENTIMIENTO_CONTRATACION_VERSION: str = "2026-10-v2"

    # ------------------------------------------------ HU-31: solicitud de contratación
    # Versión vigente del texto del consentimiento de CONTACTO COMERCIAL (separado del de
    # traspaso). Si el PO cambia el texto, se sube la versión: el envío con otra versión
    # se rechaza (409 CONSENTIMIENTO_DESACTUALIZADO) y el formulario muestra el nuevo.
    CONSENTIMIENTO_CONTACTO_VERSION: str = "2026-10-v1"
    # Bandeja del equipo comercial de Therion Labs que recibe el aviso de cada solicitud
    # nueva. Vacío = sin aviso (queda en la bitácora como omitido). El aviso NO lleva
    # nombre, correo ni teléfono de la persona: solo el número, la empresa y el enlace.
    CONTRATACION_AVISO_EMAIL: str | None = None
    # Página de la bandeja del administrador que se enlaza en el aviso.
    CONTRATACION_BANDEJA_URL: str = "http://localhost:3000/admin/clientes"
    # Límite contra abuso (HU-31 criterio 3: el mismo que la encuesta pública, HU-19):
    # intentos por IP en 10 min (ENCUESTA_INTENTOS_IP_10MIN), CAPTCHA y un máximo por IP y
    # día. Vacío = el mismo valor de ENCUESTA_EVALUACIONES_IP_DIA.
    CONTRATACION_SOLICITUDES_IP_DIA: int | None = None

    # ------------------------------------------------ HU-28: inicio/cierre de sesión y recuperación
    # Intentos FALLIDOS de inicio de sesión (admin y cliente). Se cuentan por cuenta (huella del
    # correo, exista o no, para no revelar cuáles existen) y por IP en una ventana fija; al
    # llegar al máximo se rechaza con 429 hasta que la ventana termine. Entrar bien reinicia el
    # contador de la cuenta.
    LOGIN_MAX_FALLOS_CUENTA: int = 5
    LOGIN_MAX_FALLOS_IP: int = 20
    LOGIN_VENTANA_FALLOS_MIN: int = 15
    # Recuperación de contraseña: enlace de un solo uso por correo (token en el fragmento #token=,
    # como la activación de HU-27). En production con SMTP debe ser https:// (se comprueba al arrancar).
    RECUPERACION_URL_BASE: str = "http://localhost:3000/restablecer"
    RECUPERACION_TTL_MIN: int = 30
    # Correos de recuperación por cuenta y hora (pasado el límite se responde igual, sin enviar)
    # y peticiones por IP y hora (pasado el límite, 429).
    RECUPERACION_CORREOS_CUENTA_HORA: int = 3
    RECUPERACION_SOLICITUDES_IP_HORA: int = 10

    # ------------------------------------------------ HU-26: recorrido de módulos formativos
    # Nota mínima (0-100) para aprobar la actividad de verificación y completar el módulo.
    FORMACION_UMBRAL_APROBACION: float = 70.0
    # Intentos de la actividad por empresa, módulo y día (corta adivinar las respuestas).
    FORMACION_INTENTOS_DIA: int = 5

    # ------------------------------------------------ HU-17: evidencias (cuestionario y remediación)
    # Tamaño máximo de una evidencia. Tipos admitidos: PDF, DOCX y TXT (por contenido, no solo
    # por extensión; app/application/evidencias/archivos.py). El BFF corta en 12 MB.
    EVIDENCIA_MAX_MB: int = 10
    # Evidencias de remediación por empresa y día (cada una consume una llamada al LLM).
    REMEDIACION_EVIDENCIAS_DIA: int = 20
    # Mínimo de caracteres legibles para enviar una evidencia al LLM (un PDF escaneado sin
    # texto se rechaza antes, sin gastar cuota, y se le pide al usuario un PDF con texto).
    EVIDENCIA_MIN_CARACTERES: int = 40

    # ------------------------------------------------ HU-30: vigencia del contrato
    # Días que el usuario definitivo puede seguir descargando sus documentos después de que
    # el contrato vence o el admin lo termina. Pasado el plazo, los datos quedan para las
    # reglas de retención (HU-25). 0 = sin plazo de gracia. Valor provisorio hasta que lo fije el PO.
    CONTRATO_GRACIA_DIAS: int = 30

    # ------------------------------------------------ HU-29: "Mis documentos"
    # Informes PDF archivados por evaluación (cada uno es una foto del informe al generarlo).
    DOCUMENTOS_INFORMES_POR_EVALUACION: int = 5
    # Al completar una reevaluación de la empresa se archiva su informe PDF automáticamente.
    DOCUMENTOS_ARCHIVAR_AL_COMPLETAR: bool = True

    # ------------------------------------------------ HU-15: Agente IA Tutor
    # Mensajes al tutor por empresa y día (se reinicia a medianoche de ZONA_HORARIA_CUOTAS).
    # Cada mensaje es una llamada al LLM. 0 = sin límite. Decisión del PO (28-oct): 60.
    TUTOR_MENSAJES_DIA_EMPRESA: int = 60
    # Ráfaga: mensajes por empresa en 60 s (corta scripts y doble clic). 0 = sin límite.
    TUTOR_MENSAJES_MINUTO_EMPRESA: int = 6
    # Largo máximo del mensaje del usuario (caracteres).
    TUTOR_MAX_CHARS_MENSAJE: int = 2000
    # Mensajes previos (ya anonimizados) que se envían como historial al LLM.
    TUTOR_HISTORIAL_MENSAJES: int = 6
    # Brechas que entran al prompt, por prioridad (acota tokens; el resto se resume).
    TUTOR_MAX_BRECHAS_CONTEXTO: int = 40
    # Conversaciones por empresa (las viejas se borran por retención o a mano).
    TUTOR_MAX_CONVERSACIONES: int = 50
    # Modelo del tutor. Vacío = LLM_MODEL.
    TUTOR_MODELO: str | None = None
    TUTOR_MAX_TOKENS_SALIDA: int = 4096
    TUTOR_TIMEOUT_S: float = 45.0
    TUTOR_TEMPERATURA: float = 0.3
    # Conservación (decisión del PO, 28-oct): las conversaciones sin actividad por más de N
    # días se BORRAN en el cron diario de retención (además de borrarse con la supresión
    # ARCOP del usuario definitivo). Vacío = regla desactivada.
    TUTOR_RETENCION_DIAS: int | None = 30
    # HU-18: abuso reiterado. Desde el N-ésimo mensaje bloqueado de una empresa dentro de la
    # ventana se muestra una advertencia y se alerta al Oficial de Cumplimiento (evento de
    # seguridad). NO bloquea el tutor (decisión del equipo, 28-oct). 0 = sin advertencia.
    TUTOR_BLOQUEOS_ADVERTENCIA: int = 3
    # HU-18: clave del HMAC que encadena la bitácora de auditoría. Vacía = se deriva de
    # AUTH_SECRET. Si se cambia, las filas anteriores dejan de verificar con la clave nueva:
    # fíjenla una vez y no la roten sin guardar el ancla de la cadena.
    BITACORA_CLAVE_HASH: str | None = None
    TUTOR_VENTANA_BLOQUEOS_MIN: int = 10

    # ------------------------------------------------ HU-16: borradores de cumplimiento
    # Borradores adaptados por el Agente IA por empresa y día (cada uno es una llamada al LLM;
    # sin IA, o si la cuota se agotó, el borrador se arma igual con la plantilla). 0 = sin límite.
    BORRADORES_IA_DIA_EMPRESA: int = 10
    # Borradores EN REVISIÓN por empresa (los consolidados no cuentan).
    BORRADORES_MAX_EN_REVISION: int = 20
    # Largo máximo del Markdown editado (el BFF acepta hasta 64 KB de JSON).
    BORRADORES_MAX_CHARS_CONTENIDO: int = 30000
    # Largo máximo de las instrucciones de redacción que la empresa da al Agente IA.
    BORRADORES_MAX_CHARS_INSTRUCCIONES: int = 1500
    # false = los borradores se arman solo con la plantilla (sin llamar al LLM).
    BORRADORES_IA_HABILITADA: bool = True
    # Modelo del redactor. Vacío = LLM_MODEL.
    BORRADOR_MODELO: str | None = None
    BORRADOR_MAX_TOKENS_SALIDA: int = 6000
    BORRADOR_TIMEOUT_S: float = 60.0
    BORRADOR_TEMPERATURA: float = 0.2

    # ------------------------------------------------ HU-39: asistente de IA del mapa y del RAT
    # false = la entrevista sigue sin IA (preguntas del banco y sugerencias de la evaluación) y los
    # documentos no se analizan con el LLM. Todo se puede completar a mano igual (degradación HU-16).
    ASISTENTE_IA_HABILITADA: bool = True
    # Respuestas de la entrevista analizadas con IA por empresa y día, y ráfaga por minuto. 0 = sin límite.
    ASISTENTE_RESPUESTAS_DIA_EMPRESA: int = 60
    ASISTENTE_RESPUESTAS_MINUTO_EMPRESA: int = 6
    # Documentos analizados con IA por empresa y día (cada uno es una llamada al LLM)
    ASISTENTE_DOCUMENTOS_DIA_EMPRESA: int = 10
    ASISTENTE_MAX_CHARS_RESPUESTA: int = 2000
    # Lo que se envía al LLM de un documento (pasajes BM25 más relevantes, HU-17)
    ASISTENTE_MAX_CHARS_DOCUMENTO_LLM: int = 12000
    ASISTENTE_DOCUMENTO_MAX_MB: int = 5
    # Entidades personales (NER) por cada 1.000 caracteres sobre las que un documento se rechaza:
    # parece una planilla o listado de personas, no una política, un contrato ni un aviso.
    ASISTENTE_MAX_DENSIDAD_PII: float = 8.0
    # Propuestas pendientes de revisar por empresa (las decididas no cuentan)
    ASISTENTE_MAX_PENDIENTES: int = 60
    ASISTENTE_MODELO: str | None = None   # vacío = LLM_MODEL
    ASISTENTE_MAX_TOKENS_SALIDA: int = 6000
    ASISTENTE_TIMEOUT_S: float = 60.0
    ASISTENTE_TEMPERATURA: float = 0.1

    # ------------------------------------------------ HU-34: mapa de datos personales
    # Tamaño máximo del mapa de una empresa (elementos y flujos). El mapa completo viaja en cada
    # respuesta del panel y se dibuja en el navegador: con esto se mantiene ágil.
    MAPA_MAX_ELEMENTOS: int = 300
    MAPA_MAX_FLUJOS: int = 800
    # Envíos del informe del mapa por correo por empresa y día.
    MAPA_CORREOS_DIA_EMPRESA: int = 5

    # ------------------------------------------------ HU-36: informe del registro de actividades
    # Emisiones nuevas del informe (PDF + XLSX, guardados en "Mis documentos") por empresa y día.
    # Si el registro no cambió, se reutiliza la última emisión y no cuenta.
    RAT_INFORMES_DIA_EMPRESA: int = 20
    # Envíos del informe por correo por empresa y día.
    RAT_CORREOS_DIA_EMPRESA: int = 5

    # HU-09: log inmutable (audit_log) para el Auditor Externo (Ley 21.719, art. 14 ter)
    # Filas por lote sellado. Cada lote recibe un hash SHA-256 que un tercero puede
    # recalcular con el archivo exportado (verificación de integridad por hash en lote).
    AUDIT_LOTE_TAMANO: int = 500
    # Cada cuántos minutos el worker sella las filas pendientes (1-60).
    AUDIT_SELLO_CADA_MIN: int = 15
    # Tope de filas de una exportación (si se supera, se pide acotar el rango de fechas).
    AUDIT_EXPORT_MAX_FILAS: int = 200_000
    # Vigencia máxima (días) de una cuenta de auditor externo: la auditoría es acotada.
    AUDITOR_VIGENCIA_MAX_DIAS: int = 90
    AUDITOR_PASSWORD_MIN: int = 12
    # Rol de PostgreSQL con el que se conectan la API y el worker. NO es dueño de las tablas:
    # en audit_log y audit_log_sello solo tiene SELECT e INSERT (sin UPDATE, DELETE ni
    # TRUNCATE). Lo crea la migración de HU-09 (que corre con el dueño, POSTGRES_USER).
    DB_APP_USER: str = "complianceia_app"
    DB_APP_PASSWORD: str = "complianceia_app_dev"

    @property
    def contratacion_solicitudes_ip_dia(self) -> int:
        valor = self.CONTRATACION_SOLICITUDES_IP_DIA
        return self.ENCUESTA_EVALUACIONES_IP_DIA if valor is None else valor

    # extra="ignore": el .env único también trae variables del compose y del frontend
    # (puertos, POSTGRES_*, API_URL, TURNSTILE_SITE_KEY...) que no son de la API.
    model_config = SettingsConfigDict(env_file=ENV_PROYECTO, env_file_encoding="utf-8", extra="ignore")

    @model_validator(mode="after")
    def _validar_capa_ia(self):
        if self.LLM_PROVIDER == "groq" and not self.GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY es obligatoria con LLM_PROVIDER=groq (o usa LLM_PROVIDER=ollama).")
        if self.APP_ENV == "production" and not self.SANITIZER_ENABLED:
            raise ValueError(
                "SANITIZER_ENABLED=false está prohibido con APP_ENV=production "
                "(enviaría datos personales en claro al LLM)."
            )
        if self.APP_ENV == "production" and self.GUARDAR_MAPA_ENTIDADES_CIFRADO:
            raise ValueError(
                "GUARDAR_MAPA_ENTIDADES_CIFRADO=true está prohibido con APP_ENV=production "
                "(T-06: la anonimización es irreversible por decisión del PO en HU-06)."
            )
        for nombre in ("RETENCION_DATOS_TITULAR_DIAS", "RETENCION_ARCOP_CERRADAS_DIAS",
                       "RETENCION_EVENTOS_SEGURIDAD_DIAS", "TUTOR_RETENCION_DIAS"):
            valor = getattr(self, nombre)
            if valor is not None and valor < 1:
                raise ValueError(f"{nombre} debe ser un número de días mayor que 0 (o vacío).")
        # HU-25
        if not 1 <= self.RETENCION_TITULAR_MIN_DIAS <= self.RETENCION_TITULAR_MAX_DIAS:
            raise ValueError("RETENCION_TITULAR_MIN_DIAS debe ser >= 1 y <= RETENCION_TITULAR_MAX_DIAS.")
        if not 0 <= self.RETENCION_HORA_UTC <= 23:
            raise ValueError("RETENCION_HORA_UTC debe ser una hora entre 0 y 23.")
        if self.RETENCION_TIMEOUT_S < 60 or self.RETENCION_BLOQUEO_MAX_MIN * 60 <= self.RETENCION_TIMEOUT_S:
            raise ValueError("RETENCION_TIMEOUT_S debe ser >= 60 y menor que RETENCION_BLOQUEO_MAX_MIN (en segundos).")
        if self.APP_ENV == "production" and not self.ENTITY_MAP_KEY:
            raise ValueError("ENTITY_MAP_KEY es obligatoria con APP_ENV=production.")
        if self.APP_ENV == "production" and (not self.AUTH_SECRET or len(self.AUTH_SECRET) < 32):
            raise ValueError("AUTH_SECRET (mínimo 32 caracteres) es obligatorio con APP_ENV=production.")
        if self.APP_ENV == "production" and not self.TURNSTILE_SECRET_KEY:
            raise ValueError("TURNSTILE_SECRET_KEY es obligatoria con APP_ENV=production (HU-19).")
        if self.APP_ENV == "production" and (not self.BFF_SHARED_SECRET or len(self.BFF_SHARED_SECRET) < 32):
            raise ValueError("BFF_SHARED_SECRET (mínimo 32 caracteres) es obligatorio con APP_ENV=production (HU-19).")
        if self.APP_ENV == "production" and not self.EXIGIR_TOKEN_EVALUACIONES:
            raise ValueError(
                "EXIGIR_TOKEN_EVALUACIONES=false está prohibido con APP_ENV=production "
                "(HU-20: las respuestas, evidencias y reportes son confidenciales)."
            )
        if self.APP_ENV == "production" and self.CORREO_MODO == "archivo":
            raise ValueError("CORREO_MODO=archivo es solo para desarrollo: usa smtp o desactivado en producción.")
        if self.CORREO_MODO == "smtp" and not self.SMTP_HOST:
            raise ValueError("CORREO_MODO=smtp requiere SMTP_HOST.")
        if self.ACTIVACION_TTL_HORAS < 1:
            raise ValueError("ACTIVACION_TTL_HORAS debe ser mayor que 0.")
        if self.CLIENTE_PASSWORD_MIN < 10:
            raise ValueError("CLIENTE_PASSWORD_MIN no puede ser menor que 10 (HU-27).")
        if self.K_ANONIMATO_MINIMO < 1:
            raise ValueError("K_ANONIMATO_MINIMO debe ser mayor que 0 (HU-10).")
        if self.APP_ENV == "production" and self.K_ANONIMATO_MINIMO < 5:
            raise ValueError("K_ANONIMATO_MINIMO no puede ser menor que 5 con APP_ENV=production (HU-10).")
        if self.K_ANONIMATO_DISTRIBUCION < self.K_ANONIMATO_MINIMO:
            raise ValueError("K_ANONIMATO_DISTRIBUCION debe ser mayor o igual que K_ANONIMATO_MINIMO (HU-10).")
        if not 0 <= self.CONTRATO_GRACIA_DIAS <= 365:
            raise ValueError("CONTRATO_GRACIA_DIAS debe estar entre 0 y 365 (HU-30).")
        if self.CONTRATACION_AVISO_EMAIL and "@" not in self.CONTRATACION_AVISO_EMAIL:
            raise ValueError("CONTRATACION_AVISO_EMAIL debe ser un correo válido (o vacío).")
        if self.CONTRATACION_SOLICITUDES_IP_DIA is not None and self.CONTRATACION_SOLICITUDES_IP_DIA < 1:
            raise ValueError("CONTRATACION_SOLICITUDES_IP_DIA debe ser mayor que 0 (o vacío).")
        for nombre in ("LOGIN_MAX_FALLOS_CUENTA", "LOGIN_MAX_FALLOS_IP", "LOGIN_VENTANA_FALLOS_MIN",
                       "RECUPERACION_TTL_MIN", "RECUPERACION_CORREOS_CUENTA_HORA",
                       "RECUPERACION_SOLICITUDES_IP_HORA"):
            if getattr(self, nombre) < 1:
                raise ValueError(f"{nombre} debe ser mayor que 0 (HU-28).")
        for nombre in ("TUTOR_MENSAJES_DIA_EMPRESA", "TUTOR_MENSAJES_MINUTO_EMPRESA"):
            if getattr(self, nombre) < 0:
                raise ValueError(f"{nombre} no puede ser negativo (HU-15; 0 = sin límite).")
        for nombre in ("TUTOR_MAX_CHARS_MENSAJE", "TUTOR_MAX_BRECHAS_CONTEXTO", "TUTOR_MAX_CONVERSACIONES",
                       "TUTOR_MAX_TOKENS_SALIDA"):
            if getattr(self, nombre) < 1:
                raise ValueError(f"{nombre} debe ser mayor que 0 (HU-15).")
        if not 0 <= self.TUTOR_HISTORIAL_MENSAJES <= 30:
            raise ValueError("TUTOR_HISTORIAL_MENSAJES debe estar entre 0 y 30 (HU-15).")
        if self.TUTOR_BLOQUEOS_ADVERTENCIA < 0 or self.TUTOR_VENTANA_BLOQUEOS_MIN < 1:
            raise ValueError("TUTOR_BLOQUEOS_ADVERTENCIA no puede ser negativo y TUTOR_VENTANA_BLOQUEOS_MIN debe ser > 0 (HU-18).")
        if not 0 <= self.TUTOR_TEMPERATURA <= 1:
            raise ValueError("TUTOR_TEMPERATURA debe estar entre 0 y 1 (HU-15).")
        if not 10 <= self.AUDIT_LOTE_TAMANO <= 10_000:
            raise ValueError("AUDIT_LOTE_TAMANO debe estar entre 10 y 10000 (HU-09).")
        if not 1 <= self.AUDIT_SELLO_CADA_MIN <= 60:
            raise ValueError("AUDIT_SELLO_CADA_MIN debe estar entre 1 y 60 (HU-09).")
        if self.AUDIT_EXPORT_MAX_FILAS < 1 or not 1 <= self.AUDITOR_VIGENCIA_MAX_DIAS <= 365:
            raise ValueError("AUDIT_EXPORT_MAX_FILAS debe ser > 0 y AUDITOR_VIGENCIA_MAX_DIAS estar entre 1 y 365 (HU-09).")
        if self.AUDITOR_PASSWORD_MIN < 12:
            raise ValueError("AUDITOR_PASSWORD_MIN no puede ser menor que 12 (HU-09).")
        if not re.fullmatch(r"[a-z_][a-z0-9_]{2,62}", self.DB_APP_USER or ""):
            raise ValueError("DB_APP_USER debe ser un nombre de rol simple (minúsculas, dígitos y _) (HU-09).")
        if self.APP_ENV == "production" and (self.DB_APP_PASSWORD == "complianceia_app_dev"
                                             or len(self.DB_APP_PASSWORD) < 16):
            raise ValueError("DB_APP_PASSWORD (mínimo 16 caracteres, distinta de la de desarrollo) "
                             "es obligatoria con APP_ENV=production (HU-09).")
        if (self.APP_ENV == "production" and self.CORREO_MODO == "smtp"
                and not self.RECUPERACION_URL_BASE.startswith("https://")):
            # Al arrancar y no al enviar: un error solo cuando el correo existe revelaría cuáles existen
            raise ValueError("RECUPERACION_URL_BASE debe usar https:// con APP_ENV=production (HU-28).")
        if not 0 < self.FORMACION_UMBRAL_APROBACION <= 100:
            raise ValueError("FORMACION_UMBRAL_APROBACION debe estar entre 1 y 100 (HU-26).")
        for nombre in ("FORMACION_INTENTOS_DIA", "EVIDENCIA_MAX_MB", "REMEDIACION_EVIDENCIAS_DIA",
                       "DOCUMENTOS_INFORMES_POR_EVALUACION"):
            if getattr(self, nombre) < 1:
                raise ValueError(f"{nombre} debe ser mayor que 0 (HU-26/HU-17/HU-29).")
        if not 0 < self.META_CUMPLIMIENTO_PUNTAJE <= 100:
            raise ValueError("META_CUMPLIMIENTO_PUNTAJE debe estar entre 1 y 100.")
        if self.BORRADORES_IA_DIA_EMPRESA < 0:
            raise ValueError("BORRADORES_IA_DIA_EMPRESA no puede ser negativo (HU-16).")
        if not 1 <= self.BORRADORES_MAX_EN_REVISION <= 200:
            raise ValueError("BORRADORES_MAX_EN_REVISION debe estar entre 1 y 200 (HU-16).")
        if not 2000 <= self.BORRADORES_MAX_CHARS_CONTENIDO <= 50000:
            raise ValueError("BORRADORES_MAX_CHARS_CONTENIDO debe estar entre 2000 y 50000 (el BFF acepta 64 KB, HU-16).")
        if not 100 <= self.BORRADORES_MAX_CHARS_INSTRUCCIONES <= 4000:
            raise ValueError("BORRADORES_MAX_CHARS_INSTRUCCIONES debe estar entre 100 y 4000 (HU-16).")
        if not 0 <= self.BORRADOR_TEMPERATURA <= 1:
            raise ValueError("BORRADOR_TEMPERATURA debe estar entre 0 y 1 (HU-16).")
        if not 1 <= self.MAPA_MAX_ELEMENTOS <= 2000 or not 1 <= self.MAPA_MAX_FLUJOS <= 5000:
            raise ValueError("MAPA_MAX_ELEMENTOS (1-2000) y MAPA_MAX_FLUJOS (1-5000) fuera de rango (HU-34).")
        if self.MAPA_CORREOS_DIA_EMPRESA < 1:
            raise ValueError("MAPA_CORREOS_DIA_EMPRESA debe ser mayor que 0 (HU-34).")
        if not 1 <= self.RAT_INFORMES_DIA_EMPRESA <= 500 or self.RAT_CORREOS_DIA_EMPRESA < 1:
            raise ValueError("RAT_INFORMES_DIA_EMPRESA (1-500) y RAT_CORREOS_DIA_EMPRESA (1 o más) fuera de rango (HU-36).")
        for nombre in ("ASISTENTE_RESPUESTAS_DIA_EMPRESA", "ASISTENTE_RESPUESTAS_MINUTO_EMPRESA",
                       "ASISTENTE_DOCUMENTOS_DIA_EMPRESA"):
            if getattr(self, nombre) < 0:
                raise ValueError(f"{nombre} no puede ser negativo (HU-39).")
        if not 200 <= self.ASISTENTE_MAX_CHARS_RESPUESTA <= 4000:
            raise ValueError("ASISTENTE_MAX_CHARS_RESPUESTA debe estar entre 200 y 4000 (HU-39).")
        if not 1000 <= self.ASISTENTE_MAX_CHARS_DOCUMENTO_LLM <= 40000 or not 1 <= self.ASISTENTE_DOCUMENTO_MAX_MB <= 20:
            raise ValueError("ASISTENTE_MAX_CHARS_DOCUMENTO_LLM (1000-40000) o ASISTENTE_DOCUMENTO_MAX_MB (1-20) fuera de rango (HU-39).")
        if not 0 < self.ASISTENTE_MAX_DENSIDAD_PII <= 100 or not 1 <= self.ASISTENTE_MAX_PENDIENTES <= 500:
            raise ValueError("ASISTENTE_MAX_DENSIDAD_PII (0-100) o ASISTENTE_MAX_PENDIENTES (1-500) fuera de rango (HU-39).")
        if not 0 <= self.ASISTENTE_TEMPERATURA <= 1:
            raise ValueError("ASISTENTE_TEMPERATURA debe estar entre 0 y 1 (HU-39).")
        if not 0 < len(self.MATRIZ_VERSION.strip()) <= 30:
            raise ValueError("MATRIZ_VERSION debe tener entre 1 y 30 caracteres (HU-21).")
        # En desarrollo la falta de clave se detecta al crear el gateway (worker),
        # para no bloquear alembic ni la API, que no la necesitan.
        return self

settings = Settings()

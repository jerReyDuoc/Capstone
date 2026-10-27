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
    GROQ_API_KEY: str
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
    # OBSOLETO: lo reemplaza SANITIZER_ENABLED (con el sanitizador activo el NER es
    # siempre obligatorio). Se mantiene para no romper archivos .env existentes.
    REQUIERE_NER: bool = False
    # Qué hacer si la EVIDENCIA parece contener prompt injection:
    #   "bloquear" -> no se envía al LLM; la respuesta queda en requiere_revision
    #   "marcar"   -> se envía (anonimizada y delimitada), se registra el evento y,
    #                 si el LLM no está seguro, queda en requiere_revision (sin fallback al usuario)
    MODO_SEGURIDAD_EVIDENCIA: Literal["bloquear", "marcar"] = "bloquear"

    # ------------------------------------------------ Capa de Políticas e IA
    APP_ENV: Literal["development", "test", "production"] = "development"
    # Proveedor del LLM (cambiarlo no toca la lógica de negocio)
    LLM_PROVIDER: Literal["groq"] = "groq"
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
    # El promedio del rubro solo se muestra desde N evaluaciones completadas (incluida la
    # propia): con 1 o 2 la "industria" sería casi tu propio puntaje. 1 = mostrar siempre.
    COMPARATIVA_MIN_MUESTRAS: int = 3
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

    @property
    def contratacion_solicitudes_ip_dia(self) -> int:
        valor = self.CONTRATACION_SOLICITUDES_IP_DIA
        return self.ENCUESTA_EVALUACIONES_IP_DIA if valor is None else valor

    # extra="ignore": el .env único también trae variables del compose y del frontend
    # (puertos, POSTGRES_*, API_URL, TURNSTILE_SITE_KEY...) que no son de la API.
    model_config = SettingsConfigDict(env_file=ENV_PROYECTO, env_file_encoding="utf-8", extra="ignore")

    @model_validator(mode="after")
    def _validar_capa_ia(self):
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
                       "RETENCION_EVENTOS_SEGURIDAD_DIAS"):
            valor = getattr(self, nombre)
            if valor is not None and valor < 1:
                raise ValueError(f"{nombre} debe ser un número de días mayor que 0 (o vacío).")
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
        if self.CONTRATACION_AVISO_EMAIL and "@" not in self.CONTRATACION_AVISO_EMAIL:
            raise ValueError("CONTRATACION_AVISO_EMAIL debe ser un correo válido (o vacío).")
        if self.CONTRATACION_SOLICITUDES_IP_DIA is not None and self.CONTRATACION_SOLICITUDES_IP_DIA < 1:
            raise ValueError("CONTRATACION_SOLICITUDES_IP_DIA debe ser mayor que 0 (o vacío).")
        if not 0 < self.META_CUMPLIMIENTO_PUNTAJE <= 100:
            raise ValueError("META_CUMPLIMIENTO_PUNTAJE debe estar entre 1 y 100.")
        # En desarrollo la falta de clave se detecta al crear el gateway (worker),
        # para no bloquear alembic ni la API, que no la necesitan.
        return self

settings = Settings()

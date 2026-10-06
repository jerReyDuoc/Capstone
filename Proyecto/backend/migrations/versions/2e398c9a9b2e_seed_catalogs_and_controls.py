"""seed catalogs and controls

Revision ID: <auto>
Revises: <auto>
Create Date: 2026-10-06

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '2e398c9a9b2e'
down_revision: Union[str, None] = 'b54cdc747a36'
branch_labels = None
depends_on = None


# ============================================================
# DATOS
# ============================================================

DOMINIOS = [
    "Protección de Datos",
    "Gobernanza de IA",
    "Gestión de Riesgos",
    "Uso Responsable",
]

RUBROS = [
    "Banca y Finanzas",
    "Salud",
    "Retail y E-commerce",
    "Telecomunicaciones",
    "Educación",
    "Tecnología/SaaS",
    "Manufactura",
    "Servicios/Otros",
]

RUTAS_FORMATIVAS = [
    "Protección de Datos - Inicial",
    "Protección de Datos - Intermedio",
    "Protección de Datos - Avanzado",
    "Gobernanza de IA - Inicial",
    "Gobernanza de IA - Intermedio",
    "Gobernanza de IA - Avanzado",
    "Gestión de Riesgos - Inicial",
    "Gestión de Riesgos - Intermedio",
    "Gestión de Riesgos - Avanzado",
    "Uso Responsable - Inicial",
    "Uso Responsable - Intermedio",
    "Uso Responsable - Avanzado",
]

# (codigo, categoria, comportamiento_detectado, criticidad, accion_sistema, ruta_formativa)
BRECHAS = [
    ("ERR-DAT-001", "Protección de Datos", "Ingresar datos a la IA sin validar ni documentar el consentimiento previo.", "Alta", "Bloqueo preventivo / Alerta", "Protección de Datos - Inicial"),
    ("ERR-DAT-002", "Protección de Datos", "Desplegar un proyecto de IA con datos sensibles sin ejecutar una EIPD.", "Alta", "Detención del pase a producción", "Gestión de Riesgos - Intermedio"),
    ("ERR-DAT-003", "Protección de Datos", "Procesar datos en IA para fines distintos a los autorizados originalmente.", "Alta", "Alerta a Cumplimiento", "Protección de Datos - Inicial"),
    ("ERR-DAT-004", "Protección de Datos", "Omitir o rechazar injustificadamente una solicitud de eliminación (ARCOP).", "Alta", "Escalamiento a DPO", "Protección de Datos - Intermedio"),
    ("ERR-DAT-005", "Protección de Datos", "Integrar una nueva herramienta de IA sin registrarla en el RAT corporativo.", "Media", "Notificación de inventario", "Protección de Datos - Inicial"),
    ("ERR-DAT-006", "Protección de Datos", "Omitir el reporte inmediato tras detectar una filtración de datos en la IA.", "Alta", "Bloqueo de cuenta temporal", "Gestión de Riesgos - Intermedio"),
    ("ERR-DAT-007", "Protección de Datos", "Conectar una API de IA externa sin firmar el Anexo de Tratamiento (DPA).", "Alta", "Bloqueo de token API", "Protección de Datos - Intermedio"),
    ("ERR-DAT-008", "Protección de Datos", "Enviar bases de datos a servidores en el extranjero sin cláusulas tipo.", "Media", "Bloqueo de transferencia", "Protección de Datos - Avanzado"),
    ("ERR-DAT-009", "Protección de Datos", "Subir datos biométricos o de menores sin activar el cifrado reforzado.", "Alta", "Rechazo de carga (DLP)", "Protección de Datos - Avanzado"),
    ("ERR-DAT-010", "Protección de Datos", "Lanzar un chatbot sin incluir el aviso de privacidad de uso de IA.", "Media", "Suspensión de interfaz", "Protección de Datos - Inicial"),
    ("ERR-GOB-001", "Gobernanza de IA", "Utilizar IA fuera de los lineamientos aprobados por la Política Corporativa.", "Media", "Advertencia en pantalla", "Gobernanza de IA - Inicial"),
    ("ERR-GOB-002", "Gobernanza de IA", "Eludir o no designar responsables de supervisión en un proyecto de IA.", "Media", "Rechazo de proyecto", "Gobernanza de IA - Inicial"),
    ("ERR-GOB-003", "Gobernanza de IA", "Instalar o usar herramientas de 'Shadow AI' no contabilizadas por TI.", "Alta", "Bloqueo de URL/App", "Gobernanza de IA - Inicial"),
    ("ERR-GOB-004", "Gobernanza de IA", "No asistir o reprobar las capacitaciones obligatorias de ética en IA.", "Baja", "Recordatorio automatizado", "Gobernanza de IA - Inicial"),
    ("ERR-GOB-005", "Gobernanza de IA", "Adquirir software de IA sin justificación de negocio ni análisis de riesgos.", "Media", "Bloqueo de orden de compra", "Gobernanza de IA - Intermedio"),
    ("ERR-GOB-006", "Gobernanza de IA", "Saltar controles de seguridad en el ciclo de vida de desarrollo de IA (SDLC).", "Media", "Bloqueo en pipeline CI/CD", "Gobernanza de IA - Intermedio"),
    ("ERR-GOB-007", "Gobernanza de IA", "No presentar el informe anual de riesgos de IA a la alta dirección.", "Media", "Alerta a Gerencia", "Gobernanza de IA - Avanzado"),
    ("ERR-GOB-008", "Gobernanza de IA", "Contratar a un proveedor de IA que reprobó el checklist de homologación.", "Alta", "Bloqueo de integración", "Gobernanza de IA - Intermedio"),
    ("ERR-GOB-009", "Gobernanza de IA", "Pegar código fuente o datos confidenciales en ChatGPT / Gemini.", "Alta", "Bloqueo perimetral (Proxy)", "Gobernanza de IA - Inicial"),
    ("ERR-GOB-010", "Gobernanza de IA", "Ignorar reportes de 'alucinaciones' sistemáticas sin aplicar correcciones.", "Baja", "Registro de reincidencia", "Gobernanza de IA - Avanzado"),
    ("ERR-RIE-001", "Gestión de Riesgos", "Operar un modelo sin haber documentado sus amenazas en la Matriz.", "Alta", "Alerta a Riesgos TI", "Gestión de Riesgos - Inicial"),
    ("ERR-RIE-002", "Gestión de Riesgos", "Utilizar salidas generadas por IA en informes sin verificar su precisión.", "Alta", "Marca de agua de revisión", "Gestión de Riesgos - Intermedio"),
    ("ERR-RIE-003", "Gestión de Riesgos", "Mantener un riesgo de IA en nivel 'Crítico' sin un plan de mitigación.", "Alta", "Escalamiento ejecutivo", "Gestión de Riesgos - Intermedio"),
    ("ERR-RIE-004", "Gestión de Riesgos", "Omitir el monitoreo periódico, ignorando la degradación del modelo.", "Media", "Alerta de desactualización", "Gestión de Riesgos - Avanzado"),
    ("ERR-RIE-005", "Gestión de Riesgos", "Aprobar un modelo que presenta sesgos discriminatorios hacia usuarios.", "Alta", "Bloqueo de despliegue", "Gestión de Riesgos - Avanzado"),
    ("ERR-RIE-006", "Gestión de Riesgos", "Tomar decisiones sobre clientes usando IA de 'caja negra' inexplicable.", "Media", "Auditoría forzada", "Gestión de Riesgos - Avanzado"),
    ("ERR-RIE-007", "Gestión de Riesgos", "Lanzar un agente conversacional sin someterlo a pruebas de Red Teaming.", "Media", "Suspensión de lanzamiento", "Gestión de Riesgos - Avanzado"),
    ("ERR-RIE-008", "Gestión de Riesgos", "Depender de una API de IA sin configurar un flujo manual de contingencia.", "Media", "Advertencia de arquitectura", "Gestión de Riesgos - Inicial"),
    ("ERR-RIE-009", "Gestión de Riesgos", "Otorgar a la IA capacidad de enviar correos/pagos sin límite de aprobación.", "Alta", "Revocación de permisos", "Gestión de Riesgos - Intermedio"),
    ("ERR-RIE-010", "Gestión de Riesgos", "Desactivar los logs de auditoría de las interacciones con el modelo.", "Media", "Reactivación forzada", "Gestión de Riesgos - Inicial"),
    ("ERR-SEG-001", "Uso Responsable", "Enviar instrucciones maliciosas o inyecciones de prompt al sistema.", "Alta", "Cierre de sesión y Log", "Uso Responsable - Avanzado"),
    ("ERR-SEG-002", "Uso Responsable", "Extraer involuntariamente contraseñas o PII en las respuestas del LLM.", "Alta", "Censura de salida (DLP)", "Uso Responsable - Avanzado"),
    ("ERR-SEG-003", "Uso Responsable", "Asignar privilegios de administrador a un componente de IA conectada.", "Alta", "Downgrade de permisos", "Uso Responsable - Avanzado"),
    ("ERR-SEG-004", "Uso Responsable", "Ejecutar código o consultas SQL generadas por IA sin sanitizarlas.", "Alta", "Bloqueo de compilación", "Uso Responsable - Avanzado"),
    ("ERR-SEG-005", "Uso Responsable", "Subir archivos no verificados a la base de conocimiento (RAG Poisoning).", "Media", "Cuarentena de archivo", "Uso Responsable - Intermedio"),
    ("ERR-SEG-006", "Uso Responsable", "Transmitir prompts o vectores de conocimiento a través de red no cifrada.", "Alta", "Rechazo de conexión", "Uso Responsable - Intermedio"),
    ("ERR-SEG-007", "Uso Responsable", "Almacenar historiales de chat empresariales en bases de datos sin cifrar.", "Alta", "Alerta de vulnerabilidad", "Uso Responsable - Avanzado"),
    ("ERR-SEG-008", "Uso Responsable", "Enviar RUTs o nombres a APIs públicas sin pasar por el motor NER.", "Alta", "Enmascaramiento forzado", "Uso Responsable - Intermedio"),
    ("ERR-SEG-009", "Uso Responsable", "Realizar consultas abusivas a la API agotando la cuota mensual (DoS).", "Baja", "Rate Limiting (Pausa)", "Uso Responsable - Inicial"),
    ("ERR-SEG-010", "Uso Responsable", "Aprobar automáticamente una decisión crítica sin validación humana.", "Alta", "Reversión de la acción", "Uso Responsable - Inicial"),
]

# (codigo, framework, articulo, tipo_fuente, obligacion, pregunta, aplicabilidad, evidencia_esperada, criticidad, recomendacion, test_asociado, dominio, codigo_brecha)
CONTROLES = [
    ("DAT-001", "Ley N.º 21.719", "Art. 3 N°5, Art. 12 y Art. 13", "Obligación Legal", "Demostrar base de licitud para los datos ingresados en IA", "¿Cuenta con bases de licitud documentadas (ej. consentimiento explícito, contrato firmado) para autorizar los datos procesados en sus sistemas de IA?", "Siempre", "Registro de consentimiento / Cláusulas de privacidad", "Alta", "Formalizar registros de consentimiento y bases de licitud según Ley 21.719", "test_evaluar_dat_001_licitud", "Protección de Datos", "ERR-DAT-001"),
    ("DAT-002", "Ley N.º 21.719", "Art. 15 ter", "Obligación Legal", "Ejecutar una EIPD antes de procesar datos de alto riesgo en IA", "¿Se ejecutó una Evaluación de Impacto en Protección de Datos (EIPD) para los sistemas de IA que procesan datos sensibles o realizan perfilamiento de usuarios?", "Condicional (Datos sensibles o perfilamiento)", "Informe formal de EIPD firmado", "Alta", "Implementar la metodología EIPD previa al despliegue", "test_evaluar_dat_002_eipd", "Protección de Datos", "ERR-DAT-002"),
    ("DAT-003", "Ley N.º 21.719", "Art. 3 N°2 y Art. 15 bis", "Obligación Legal", "Limitar el uso de datos en IA exclusivamente a los fines informados", "¿Los datos ingresados a modelos de IA se utilizan únicamente para la finalidad explícita informada al titular?", "Siempre", "Política de tratamiento de datos / Términos de uso", "Alta", "Restringir el uso de datos en IA solo a las finalidades autorizadas", "test_evaluar_dat_003_finalidad", "Protección de Datos", "ERR-DAT-003"),
    ("DAT-004", "Ley N.º 21.719", "Arts. 4 a 9 (ARCOP)", "Obligación Legal", "Garantizar ejercicio de derechos ARCOP en datos procesados por IA", "¿Existen canales y procedimientos para que los usuarios ejerzan sus derechos ARCOP (Acceso, Rectificación, Cancelación, Oposición y Portabilidad) sobre sus datos procesados por IA?", "Siempre", "Procedimiento operativo de atención de solicitudes ARCOP", "Alta", "Diseñar flujo operativo para eliminación o rectificación en IA", "test_evaluar_dat_004_arcop", "Protección de Datos", "ERR-DAT-004"),
    ("DAT-005", "Ley N.º 21.719", "Art. 14 ter y Art.3 N°5", "Obligación Legal", "Mantener un Registro de Actividades de Tratamiento (RAT) actualizado", "¿Mantiene un Registro de Actividades de Tratamiento (RAT) o inventario que identifique explícitamente los datos personales procesados por sus herramientas de IA?", "Siempre", "Documento o plataforma del RAT actualizado", "Media", "Construir e integrar el RAT con foco en componentes de IA", "test_evaluar_dat_005_rat", "Protección de Datos", "ERR-DAT-005"),
    ("DAT-006", "Ley N.º 21.719", "Art. 14 quinquies y 14 sixies", "Obligación Legal", "Notificar incidentes de seguridad que afecten datos personales", "¿Cuenta con un protocolo para detectar y notificar incidentes o brechas de seguridad (ej. filtraciones o accesos no autorizados) que involucren datos procesados en sus sistemas de IA?", "Siempre", "Plan de respuesta a incidentes de privacidad", "Alta", "Establecer procedimiento de reporte de incidentes según la Ley", "test_evaluar_dat_006_incidentes", "Protección de Datos", "ERR-DAT-006"),
    ("DAT-007", "Ley N.º 21.719", "Art. 15 bis", "Obligación Legal", "Regular mediante contrato a los proveedores de IA que actúan como encargados", "¿Los contratos con sus proveedores de IA (ej. ChatGPT, servicios en la nube, APIs) incluyen cláusulas de privacidad o un Anexo de Tratamiento de Datos (DPA) que los regule legalmente como encargados?", "Condicional (Si usa IA de terceros)", "Contratos o DPA (Data Processing Agreements) firmados", "Alta", "Exigir firmar un Anexo de Tratamiento de Datos (DPA) con proveedores", "test_evaluar_dat_007_encargados", "Protección de Datos", "ERR-DAT-007"),
    ("DAT-008", "Ley N.º 21.719", "Arts. 26 a 31", "Obligación Legal", "Validar licitud de transferencias internacionales al enviar datos a servidores externos", "¿Se verifica que los proveedores o APIs de IA ubicados fuera de Chile cumplan con los estándares legales exigidos para la transferencia internacional de datos personales?", "Condicional (Si usa IA en la nube internacional)", "Cláusulas tipo / Certificación del proveedor de nube", "Media", "Evaluar la ubicación de los servidores y aplicar cláusulas contractuales tipo", "test_evaluar_dat_008_transferencia", "Protección de Datos", "ERR-DAT-008"),
    ("DAT-009", "Ley N.º 21.719", "Arts. 16 y 17", "Obligación Legal", "Proteger con medidas reforzadas datos sensibles, biométricos o de menores", "¿Se aplican medidas de seguridad reforzadas cuando la IA procesa datos sensibles (ej. salud, origen étnico), datos biométricos (ej. reconocimiento facial, huellas) o datos de menores de edad?", "Condicional (Si procesa datos sensibles/menores)", "Política de protección de datos sensibles y consentimientos explícitos", "Alta", "Implementar controles de cifrado y consentimiento expreso reforzado", "test_evaluar_dat_009_sensibles", "Protección de Datos", "ERR-DAT-009"),
    ("DAT-010", "Ley N.º 21.719", "Art. 14 ter y Art. 3 N°7", "Obligación Legal", "Informar de forma clara y transparente el uso de IA al titular de los datos", "¿Se informa de manera clara a los usuarios y clientes (ej. mediante avisos de privacidad) cuando sus datos personales son analizados o procesados por algoritmos de Inteligencia Artificial?", "Siempre", "Avisos de privacidad en interfaces / Términos de uso", "Media", "Publicar avisos de privacidad claros sobre el uso de sistemas de IA", "test_evaluar_dat_010_transparencia", "Protección de Datos", "ERR-DAT-010"),
    ("GOB-001", "ISO/IEC 42001", "Cláusula 5.2", "Estándar Normativo", "Formalizar una Política Corporativa de Uso y Gobernanza de IA", "¿Existe una Política de Uso de Inteligencia Artificial aprobada formalmente por la gerencia y comunicada a todos los colaboradores de la empresa?", "Siempre", "Documento de Política de IA / Acta de aprobación directiva", "Media", "Redactar y oficializar una política marco de gobernanza de IA", "test_evaluar_gob_001_politica", "Gobernanza de IA", "ERR-GOB-001"),
    ("GOB-002", "ISO/IEC 42001", "Cláusula 5.3", "Estándar Normativo", "Asignar roles y responsabilidades claras en la gestión de IA", "¿Se ha asignado a una persona o equipo (ej. responsable de TI, gerencia, o un líder designado) la responsabilidad formal de supervisar el uso seguro de la IA en la organización?", "Siempre", "Matriz RACI / Definición de roles en la organización", "Media", "Asignar formalmente responsabilidades de supervisión de IA", "test_evaluar_gob_002_roles", "Gobernanza de IA", "ERR-GOB-002"),
    ("GOB-003", "ISO/IEC 42001", "Cláusula 4.3, 7.5, 8.1", "Estándar Normativo", "Mantener un inventario centralizado de todos los sistemas de IA en uso", "¿Cuenta la organización con un inventario actualizado de todas las herramientas y modelos de IA que utiliza su personal (incluyendo software de pago y plataformas gratuitas)?", "Siempre", "Inventario de Sistemas de IA (software, API, modelos)", "Alta", "Crear y mantener un catálogo oficial de aplicaciones de IA", "test_evaluar_gob_003_inventario", "Gobernanza de IA", "ERR-GOB-003"),
    ("GOB-004", "ISO/IEC 42001", "Cláusula 7.2", "Estándar Normativo", "Capacitar continuamente al personal en uso seguro y ético de la IA", "¿Se realizan capacitaciones periódicas a los colaboradores sobre los riesgos y buenas prácticas en el uso de herramientas de IA?", "Siempre", "Registro de asistencia y programa de capacitación corporativo", "Baja", "Implementar itinerarios formativos continuos para los equipos", "test_evaluar_gob_004_capacitacion", "Gobernanza de IA", "ERR-GOB-004"),
    ("GOB-005", "ISO/IEC 42001", "Cláusula 4.1", "Estándar Normativo", "Evaluar la alineación ética y estratégica de los proyectos de IA", "Antes de comprar, desarrollar o permitir el uso de una nueva herramienta de IA, ¿se evalúa formalmente si realmente aporta valor al negocio y si los riesgos que introduce (legales, privacidad, reputación) son aceptables?", "Siempre", "Análisis FODA y Análisis PESTEL", "Media", "Implementar un checklist o filtro de aprobación obligatoria (Business Case) antes de adoptar nuevas herramientas de IA", "test_evaluar_gob_005_alineacion", "Gobernanza de IA", "ERR-GOB-005"),
    ("GOB-006", "ISO/IEC 42001", "Cláusula 8.1", "Estándar Normativo", "Establecer controles operativos para todo el ciclo de vida de la IA", "¿Existen procedimientos formales para gestionar de forma segura el diseño, las pruebas, la puesta en marcha y la desactivación (baja) de los sistemas de IA propios?", "Condicional (Si desarrolla o integra IA propia)", "Manual de ciclo de vida de desarrollo de software con IA", "Media", "Formalizar un procedimiento de control del ciclo de vida de IA", "test_evaluar_gob_006_ciclo_vida", "Gobernanza de IA", "ERR-GOB-006"),
    ("GOB-007", "ISO/IEC 42001", "Cláusula 9.3", "Estándar Normativo", "Efectuar revisiones periódicas del sistema de gestión de IA por la dirección", "¿La gerencia o dirección general revisa periódicamente (ej. anualmente) el desempeño, los riesgos y los resultados de las herramientas de IA utilizadas en la empresa?", "Siempre", "Minuta o acta de reunión de revisión por la dirección", "Media", "Programar revisiones ejecutivas semestrales o anuales sobre IA", "test_evaluar_gob_007_revision_direccion", "Gobernanza de IA", "ERR-GOB-007"),
    ("GOB-008", "ISO/IEC 42001", "Cláusula 8.1", "Estándar Normativo", "Aplicar homologación rigurosa de proveedores de soluciones de IA", "¿Se evalúan los estándares de seguridad, privacidad y ética de los proveedores antes de adquirir o contratar un nuevo software o servicio de IA?", "Condicional (Si contrata IA a terceros)", "Checklist de homologación de proveedores de IA completado", "Alta", "Integrar criterios de gobernanza de IA en la gestión de compras", "test_evaluar_gob_008_proveedores", "Gobernanza de IA", "ERR-GOB-008"),
    ("GOB-009", "ISO/IEC 42001", "Cláusula 7.2, 8.1", "Estándar Normativo", "Establecer guía de uso aceptable de IA Generativa en el puesto de trabajo", "¿Se han definido y comunicado reglas claras a los empleados sobre qué información confidencial o privada NO se debe ingresar a herramientas de IA públicas (ej. ChatGPT, Gemini)?", "Siempre", "Guía de uso aceptable de IA Generativa publicada", "Alta", "Publicar norma de uso aceptable de IA pública para empleados", "test_evaluar_gob_009_uso_aceptable", "Gobernanza de IA", "ERR-GOB-009"),
    ("GOB-010", "ISO/IEC 42001", "Cláusula 10.1", "Estándar Normativo", "Implementar mecanismos de mejora continua ante fallas en sistemas de IA", "¿Existen procesos establecidos para reportar y corregir fallos, respuestas incorrectas (alucinaciones) o comportamientos indeseados detectados en las herramientas de IA?", "Siempre", "Registro de no conformidades y acciones correctivas aplicadas", "Baja", "Establecer un canal de reporte interno de fallos en IA", "test_evaluar_gob_010_mejora_continua", "Gobernanza de IA", "ERR-GOB-010"),
    ("RIE-001", "NIST AI RMF 100-1", "MAP 1.1, 1.2", "Estándar Normativo", "Identificar y catalogar riesgos específicos de los sistemas de IA", "¿Cuenta la empresa con un registro o matriz donde se identifiquen y evalúen los posibles riesgos, problemas o amenazas específicas de usar Inteligencia Artificial?", "Siempre", "Matriz de Riesgos de IA con escala de impacto y probabilidad", "Alta", "Implementar la función MAP de NIST AI RMF para catalogar riesgos", "test_evaluar_rie_001_map", "Gestión de Riesgos", "ERR-RIE-001"),
    ("RIE-002", "NIST AI RMF 100-1", "MEASURE 2.1", "Estándar Normativo", "Medir métricas de precisión, confiabilidad y tasa de error de los modelos", "¿Se revisa o evalúa periódicamente la precisión de las respuestas de la IA para detectar errores o inventos de información (alucinaciones)?", "Condicional (Si usa o desarrolla modelos/LLM)", "Reporte de métricas de desempeño y calidad del modelo", "Alta", "Establecer métricas de evaluación continua de calidad del modelo", "test_evaluar_rie_002_measure", "Gestión de Riesgos", "ERR-RIE-002"),
    ("RIE-003", "NIST AI RMF 100-1", "MANAGE 1.1, 1.2", "Estándar Normativo", "Implementar planes de tratamiento y mitigación para riesgos identificados", "¿Existen medidas o planes de acción concretos para controlar los riesgos de Inteligencia Artificial que se consideren críticos o altos para su negocio?", "Siempre", "Plan de Tratamiento de Riesgos con responsables y plazos", "Alta", "Asignar acciones de control a cada riesgo de nivel alto o crítico", "test_evaluar_rie_003_manage", "Gestión de Riesgos", "ERR-RIE-003"),
    ("RIE-004", "ISO/IEC 42001", "Cláusula 9.1", "Estándar Normativo", "Monitorear continuamente el entorno para detectar riesgos emergentes de IA", "¿Se monitorean periódicamente las herramientas de IA que ya se están utilizando en la empresa para detectar nuevos riesgos, cambios o comportamientos inesperados?", "Siempre", "Minutas de revisión del perfil de riesgos de IA", "Media", "Establecer revisiones trimestrales de la matriz de riesgos de IA", "test_evaluar_rie_004_monitoreo", "Gestión de Riesgos", "ERR-RIE-004"),
    ("RIE-005", "NIST AI RMF 100-1", "MEASURE 2.1, 2.2, 2.3", "Estándar Normativo", "Detectar y mitigar sesgos discriminatorios en las decisiones de la IA", "¿Se realizan pruebas para asegurar que las decisiones o respuestas de la IA no generen discriminación, tratos injustos o sesgos hacia las personas?", "Condicional (Si usa IA para decisiones que afectan personas)", "Reporte de evaluación de sesgo o equidad (Fairness test)", "Alta", "Ejecutar pruebas de equidad y corregir datos de entrenamiento/prompts", "test_evaluar_rie_005_sesgos", "Gestión de Riesgos", "ERR-RIE-005"),
    ("RIE-006", "NIST AI RMF 100-1", "MEASURE 2.9", "Estándar Normativo", "Evaluar la explicabilidad de las decisiones automatizadas", "Cuando la IA toma decisiones clave que afectan a personas, ¿es posible explicar de manera clara y sencilla cómo el sistema llegó a esa conclusión?", "Condicional (Si toma decisiones automatizadas sobre personas)", "Documentación de explicabilidad o arquitectura del modelo", "Media", "Incorporar técnicas de explicabilidad (ej. LIME/SHAP) o árboles", "test_evaluar_rie_006_explicabilidad", "Gestión de Riesgos", "ERR-RIE-006"),
    ("RIE-007", "NIST AI RMF 100-1", "MEASURE 2.5, 2.6", "Estándar Normativo", "Realizar pruebas de adversario y red teaming sobre modelos sensibles", "¿Se realizan pruebas de seguridad intencionales (ej. intentar engañar a la IA o 'Red Teaming') para descubrir fallos o vulnerabilidades antes de usarla oficialmente?", "Condicional (Si desarrolla o despliega agentes/LLM propios)", "Informe de pruebas de penetración o Red Teaming en IA", "Media", "Programar sesiones de Red Teaming antes de lanzamientos clave", "test_evaluar_rie_007_red_teaming", "Gestión de Riesgos", "ERR-RIE-007"),
    ("RIE-008", "NIST AI RMF 100-1", "MANAGE 2.4", "Estándar Normativo", "Definir un plan de contingencia ante caída o indisponibilidad de la IA", "¿Existe un plan o procedimiento alternativo (ej. volver a un proceso manual) en caso de que la herramienta de IA falle, cometa errores graves o quede fuera de servicio?", "Siempre", "Plan de Continuidad Operativa con alternativa manual", "Media", "Diseñar flujos alternativos de trabajo en caso de caída del servicio", "test_evaluar_rie_008_contingencia", "Gestión de Riesgos", "ERR-RIE-008"),
    ("RIE-009", "NIST AI RMF 100-1", "GOVERN 4.2 / MANAGE 1.3, 2.3", "Estándar Normativo", "Establecer límites de autonomía para agentes de IA que ejecutan acciones", "Si utiliza sistemas de IA que actúan por sí solos, ¿tienen límites para evitar que ejecuten acciones críticas (ej. enviar correos a clientes o hacer pagos) sin supervisión o aprobación humana?", "Condicional (Si utiliza agentes autónomos de IA)", "Configuración de permisos y arquitectura de llamadas a API", "Alta", "Implementar límites de aprobación para acciones críticas de la IA", "test_evaluar_rie_009_autonomia", "Gestión de Riesgos", "ERR-RIE-009"),
    ("RIE-010", "NIST AI RMF 100-1", "GOVERN 1.5", "Estándar Normativo", "Mantener registros de auditoría (logs) de las interacciones con IA", "¿Se guardan registros históricos (logs) de la información ingresada (preguntas/datos) y las respuestas entregadas por los sistemas de IA corporativos, para futuras revisiones?", "Siempre", "Logs de auditoría almacenados de forma segura", "Media", "Activar y resguardar logs de auditoría de interacciones de IA", "test_evaluar_rie_010_logs", "Gestión de Riesgos", "ERR-RIE-010"),
    ("SEG-001", "OWASP LLM", "LLM01", "Seguridad Técnica", "Implementar sanitización e inspección de prompts para evitar inyecciones", "¿Existen filtros o barreras de seguridad (Guardrails) para prevenir que usuarios malintencionados manipulen o engañen a la IA mediante instrucciones falsas (inyección de prompts)?", "Condicional (Si utiliza LLM o IA Generativa)", "Configuración técnica de Guardrails / Pruebas de entrada", "Alta", "Integrar capas intermedias de sanitización e inspección de prompts", "test_evaluar_seg_001_prompt_injection", "Uso Responsable", "ERR-SEG-001"),
    ("SEG-002", "OWASP LLM", "LLM02", "Seguridad Técnica", "Prevenir la divulgación o fuga involuntaria de información sensible en salidas", "¿Se aplican filtros o reglas de seguridad para evitar que la IA revele accidentalmente datos confidenciales, contraseñas o información sensible en sus respuestas?", "Condicional (Si utiliza LLM o IA Generativa)", "Filtros DLP (Data Loss Prevention) o reglas en respuesta de API", "Alta", "Desplegar filtros de prevención de fuga de datos en la salida", "test_evaluar_seg_002_fuga_informacion", "Uso Responsable", "ERR-SEG-002"),
    ("SEG-003", "OWASP LLM", "LLM03", "Seguridad Técnica", "Restringir el nivel de acceso y permisos de las funciones de la IA (Exceso de Agencia)", "Si la IA está conectada a otros sistemas de la empresa, ¿opera con permisos restringidos (principio de menor privilegio) para evitar que lea, modifique o borre información no autorizada?", "Condicional (Si la IA ejecuta acciones en otros sistemas)", "Configuración de permisos RBAC y API scopes acotados", "Alta", "Restringir permisos de escritura y eliminación de la IA a lo mínimo", "test_evaluar_seg_003_exceso_agencia", "Uso Responsable", "ERR-SEG-003"),
    ("SEG-004", "OWASP LLM", "LLM02", "Seguridad Técnica", "Validar las respuestas antes de ejecutarlas en el backend (Insecure Output Handling)", "¿Se revisan y validan técnicamente las respuestas de la IA antes de que interactúen automáticamente con otros sistemas (ej. antes de ejecutar código o consultar bases de datos)?", "Condicional (Si la IA genera código o consultas SQL/HTML)", "Sanitización de salida (Escapado de código, validación de esquemas)", "Alta", "Validar y tipar sintácticamente cualquier salida previa a su ejecución", "test_evaluar_seg_004_output_inseguro", "Uso Responsable", "ERR-SEG-004"),
    ("SEG-005", "OWASP LLM", "LLM05", "Seguridad Técnica", "Asegurar la integridad de las fuentes de datos utilizadas en arquitecturas RAG", "Si la IA utiliza documentos internos de la empresa para responder (arquitectura RAG), ¿existen controles para asegurar que esos archivos sean seguros y no contengan código malicioso o información falsa?", "Condicional (Si utiliza arquitecturas RAG o bases vectoriales)", "Procedimiento de validación y control de acceso a documentos RAG", "Media", "Implementar firma y control de acceso a la base de conocimiento RAG", "test_evaluar_seg_005_rag_poisoning", "Uso Responsable", "ERR-SEG-005"),
    ("SEG-006", "NIST 600-1", "Sec. 2.9", "Seguridad Técnica", "Cifrar las comunicaciones y almacenamiento de vectores, prompts y resultados", "¿Se utilizan medidas de seguridad como el cifrado (ej. conexiones seguras TLS, AES) para proteger la información mientras se almacena o se envía a los sistemas de IA?", "Siempre", "Certificados SSL/TLS activos y políticas de cifrado en reposo", "Alta", "Configurar cifrado extremo a extremo en todas las llamadas a API", "test_evaluar_seg_006_cifrado", "Uso Responsable", "ERR-SEG-006"),
    ("SEG-007", "NIST 600-1", "Sec. 2.9", "Decisión de Diseño", "Cifrar las comunicaciones y almacenamiento de vectores, prompts y resultados", "¿Se aplican medidas de cifrado para proteger estrictamente el historial de conversaciones (prompts) y los documentos internos guardados en la base de datos de la IA, evitando que sean robados o interceptados?", "Siempre", "Configuración de cifrado activa en la base de datos de vectores y canales de comunicación del LLM", "Alta", "Implementar controles criptográficos en todas las capas del sistema (tránsito y almacenamiento)", "test_evaluar_seg_007_cifrado", "Uso Responsable", "ERR-SEG-007"),
    ("SEG-008", "Ley N.º 21.719", "Art. 14 Letra H", "Decisión de Diseño", "Anonimizar o seudonimizar PII antes de enviarla a modelos externos", "Si utiliza IA de proveedores externos, ¿se aplican herramientas (como motores NER) para enmascarar u ocultar datos personales (ej. RUT, nombres, teléfonos) antes de enviarlos a la plataforma externa?", "Condicional (Si utiliza API de IA de terceros)", "Funciones de seudonimización comprobadas en el backend", "Alta", "Integrar módulo NER de enmascaramiento previo al envío de prompts", "test_evaluar_seg_008_ner_anonimizacion", "Uso Responsable", "ERR-SEG-008"),
    ("SEG-009", "OWASP LLM", "LLM10", "Seguridad Técnica", "Proteger el sistema contra ataques de denegación de servicio por consultas masivas", "¿Se aplican límites de uso y cuotas (Rate Limiting) para evitar que consultas masivas bloqueen el sistema (ej. Ataque DoS) o generen sobrecostos inesperados en los servicios de IA?", "Siempre", "Configuración de Rate Limiting y alertas de presupuesto en API", "Baja", "Configurar límites de peticiones por minuto y alertas de consumo", "test_evaluar_seg_009_rate_limiting", "Uso Responsable", "ERR-SEG-009"),
    ("SEG-010", "Ley N.º 21.719", "Art. 8 bis", "Decisión de Diseño", "Requerir intervención humana obligatoria en decisiones de alto impacto", "Cuando la IA toma decisiones importantes que afectan a personas (ej. contrataciones, evaluación crediticia), ¿se exige la validación o revisión de un operador humano antes de aplicar definitivamente esa decisión?", "Condicional (Si la IA afecta derechos o contrataciones)", "Procedimiento formal de supervisión 'Human-in-the-Loop'", "Alta", "Implementar una interfaz de aprobación humana previa a la ejecución", "test_evaluar_seg_010_human_in_loop", "Uso Responsable", "ERR-SEG-010"),
]


def upgrade() -> None:
    conn = op.get_bind()

    # --- 1. Dominios ---
    dominio_map = {}
    for idx, nombre in enumerate(DOMINIOS, start=1):
        conn.execute(
            sa.text("INSERT INTO dominio (id, nombre_dominio) VALUES (:id, :nombre)"),
            {"id": idx, "nombre": nombre},
        )
        dominio_map[nombre] = idx

    # --- 2. Rubros ---
    for idx, nombre in enumerate(RUBROS, start=1):
        conn.execute(
            sa.text("INSERT INTO rubro (id, nombre_rubro) VALUES (:id, :nombre)"),
            {"id": idx, "nombre": nombre},
        )

    # --- 3. Rutas formativas ---
    ruta_map = {}
    for idx, nombre in enumerate(RUTAS_FORMATIVAS, start=1):
        conn.execute(
            sa.text("INSERT INTO ruta_formativa (id, nombre) VALUES (:id, :nombre)"),
            {"id": idx, "nombre": nombre},
        )
        ruta_map[nombre] = idx

    # --- 4. Catálogo de brechas ---
    brecha_map = {}
    for idx, (codigo, categoria, comportamiento, criticidad, accion, ruta) in enumerate(BRECHAS, start=1):
        conn.execute(
            sa.text("""
                INSERT INTO catalogo_brechas
                    (id_brecha, codigo_brecha, categoria, comportamiento_detectado,
                     criticidad, accion_sistema, ruta_formativa_id)
                VALUES
                    (:id, :codigo, :categoria, :comportamiento,
                     :criticidad, :accion, :ruta_id)
            """),
            {
                "id": idx,
                "codigo": codigo,
                "categoria": categoria,
                "comportamiento": comportamiento,
                "criticidad": criticidad,
                "accion": accion,
                "ruta_id": ruta_map[ruta],
            },
        )
        brecha_map[codigo] = idx

    # --- 5. Matriz de controles ---
    for idx, (codigo, fw, art, tipo, oblig, preg, aplic, ev, crit, rec, test, dom, brecha_cod) in enumerate(CONTROLES, start=1):
        conn.execute(
            sa.text("""
                INSERT INTO matriz_controles
                    (id_control, codigo_control, framework_fuente, articulo_referencia,
                     tipo_fuente, obligacion, pregunta_evaluacion, aplicabilidad,
                     evidencia_esperada, criticidad, recomendacion, test_asociado,
                     dominio_id, catalogo_brechas_id_brecha)
                VALUES
                    (:id, :cod, :fw, :art,
                     :tipo, :oblig, :preg, :aplic,
                     :ev, :crit, :rec, :test,
                     :dom_id, :brecha_id)
            """),
            {
                "id": idx,
                "cod": codigo,
                "fw": fw,
                "art": art,
                "tipo": tipo,
                "oblig": oblig,
                "preg": preg,
                "aplic": aplic,
                "ev": ev,
                "crit": crit,
                "rec": rec,
                "test": test,
                "dom_id": dominio_map[dom],
                "brecha_id": brecha_map[brecha_cod],
            },
        )


def downgrade() -> None:
    conn = op.get_bind()
    # Borrar en orden inverso por las FKs
    conn.execute(sa.text("DELETE FROM matriz_controles"))
    conn.execute(sa.text("DELETE FROM catalogo_brechas"))
    conn.execute(sa.text("DELETE FROM ruta_formativa"))
    conn.execute(sa.text("DELETE FROM rubro"))
    conn.execute(sa.text("DELETE FROM dominio"))
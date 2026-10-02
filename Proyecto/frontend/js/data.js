// ============================================================================
// Datos de ejemplo generados a partir de la matriz de controles y el árbol
// de aplicabilidad REALES del proyecto Therion Labs. No hay backend: todo lo
// que ves aquí vive en este archivo y en localStorage del navegador.
// ============================================================================
window.Therion = window.Therion || {};
Therion.data = {
  CONTROLES: [
  {
    "id": 1,
    "control_id": "DAT-001",
    "version": 1,
    "framework_fuente": "Ley N.º 21.719",
    "articulo_referencia": "Art. 3 N°5, Art. 12 y Art. 13",
    "dominio": "Protección de Datos",
    "tipo_fuente": "Obligación Legal",
    "obligacion": "Demostrar base de licitud para los datos ingresados en IA",
    "pregunta": "¿Cuenta con bases de licitud documentadas (ej. consentimiento explícito, contrato firmado) para autorizar los datos procesados en sus sistemas de IA?",
    "aplicabilidad": "Siempre",
    "evidencia_esperada": "Registro de consentimiento / Cláusulas de privacidad",
    "criticidad": "Alta",
    "brecha_asociada": "Ausencia de licitud en tratamiento de datos en IA",
    "recomendacion": "Formalizar registros de consentimiento y bases de licitud según Ley 21.719",
    "ruta_formativa": "Protección de Datos - Inicial",
    "test_asociado": "test_evaluar_dat_001_licitud"
  },
  {
    "id": 2,
    "control_id": "DAT-002",
    "version": 1,
    "framework_fuente": "Ley N.º 21.719",
    "articulo_referencia": "Art. 15 ter",
    "dominio": "Protección de Datos",
    "tipo_fuente": "Obligación Legal",
    "obligacion": "Ejecutar una EIPD antes de procesar datos de alto riesgo en IA",
    "pregunta": "¿Se ejecutó una Evaluación de Impacto en Protección de Datos (EIPD) para los sistemas de IA que procesan datos sensibles o realizan perfilamiento de usuarios?",
    "aplicabilidad": "Condicional (Datos sensibles o perfilamiento)",
    "evidencia_esperada": "Informe formal de EIPD firmado",
    "criticidad": "Alta",
    "brecha_asociada": "Inexistencia de EIPD en proyectos de IA de alto riesgo",
    "recomendacion": "Implementar la metodología EIPD previa al despliegue",
    "ruta_formativa": "Gestión de Riesgos - Intermedio",
    "test_asociado": "test_evaluar_dat_002_eipd"
  },
  {
    "id": 3,
    "control_id": "DAT-003",
    "version": 1,
    "framework_fuente": "Ley N.º 21.719",
    "articulo_referencia": "Art. 3 N°2 y Art. 15 bis",
    "dominio": "Protección de Datos",
    "tipo_fuente": "Obligación Legal",
    "obligacion": "Limitar el uso de datos en IA exclusivamente a los fines informados",
    "pregunta": "¿Los datos ingresados a modelos de IA se utilizan únicamente para la finalidad explícita informada al titular?",
    "aplicabilidad": "Siempre",
    "evidencia_esperada": "Política de tratamiento de datos / Términos de uso",
    "criticidad": "Alta",
    "brecha_asociada": "Desviación de la finalidad original en el procesamiento con IA",
    "recomendacion": "Restringir el uso de datos en IA solo a las finalidades autorizadas",
    "ruta_formativa": "Protección de Datos - Inicial",
    "test_asociado": "test_evaluar_dat_003_finalidad"
  },
  {
    "id": 4,
    "control_id": "DAT-004",
    "version": 1,
    "framework_fuente": "Ley N.º 21.719",
    "articulo_referencia": "Arts. 4 a 9 (ARCOP)",
    "dominio": "Protección de Datos",
    "tipo_fuente": "Obligación Legal",
    "obligacion": "Garantizar ejercicio de derechos ARCOP en datos procesados por IA",
    "pregunta": "¿Existen canales y procedimientos para que los usuarios ejerzan sus derechos ARCOP (Acceso, Rectificación, Cancelación, Oposición y Portabilidad) sobre sus datos procesados por IA?",
    "aplicabilidad": "Siempre",
    "evidencia_esperada": "Procedimiento operativo de atención de solicitudes ARCOP",
    "criticidad": "Alta",
    "brecha_asociada": "Imposibilidad de atender derechos ARCOP en flujos con IA",
    "recomendacion": "Diseñar flujo operativo para eliminación o rectificación en IA",
    "ruta_formativa": "Protección de Datos - Intermedio",
    "test_asociado": "test_evaluar_dat_004_arcop"
  },
  {
    "id": 5,
    "control_id": "DAT-005",
    "version": 1,
    "framework_fuente": "Ley N.º 21.719",
    "articulo_referencia": "Art. 14 ter y Art.3 N°5",
    "dominio": "Protección de Datos",
    "tipo_fuente": "Obligación Legal",
    "obligacion": "Mantener un Registro de Actividades de Tratamiento (RAT) actualizado",
    "pregunta": "¿Mantiene un Registro de Actividades de Tratamiento (RAT) o inventario que identifique explícitamente los datos personales procesados por sus herramientas de IA?",
    "aplicabilidad": "Siempre",
    "evidencia_esperada": "Documento o plataforma del RAT actualizado",
    "criticidad": "Media",
    "brecha_asociada": "Inexistencia de inventario de flujos de datos en IA",
    "recomendacion": "Construir e integrar el RAT con foco en componentes de IA",
    "ruta_formativa": "Protección de Datos - Inicial",
    "test_asociado": "test_evaluar_dat_005_rat"
  },
  {
    "id": 6,
    "control_id": "DAT-006",
    "version": 1,
    "framework_fuente": "Ley N.º 21.719",
    "articulo_referencia": "Art. 14 quinquies y 14 sixies",
    "dominio": "Protección de Datos",
    "tipo_fuente": "Obligación Legal",
    "obligacion": "Notificar incidentes de seguridad que afecten datos personales",
    "pregunta": "¿Cuenta con un protocolo para detectar y notificar incidentes o brechas de seguridad (ej. filtraciones o accesos no autorizados) que involucren datos procesados en sus sistemas de IA?",
    "aplicabilidad": "Siempre",
    "evidencia_esperada": "Plan de respuesta a incidentes de privacidad",
    "criticidad": "Alta",
    "brecha_asociada": "Ausencia de protocolo de notificación de brechas de datos",
    "recomendacion": "Establecer procedimiento de reporte de incidentes según la Ley",
    "ruta_formativa": "Gestión de Riesgos - Intermedio",
    "test_asociado": "test_evaluar_dat_006_incidentes"
  },
  {
    "id": 7,
    "control_id": "DAT-007",
    "version": 1,
    "framework_fuente": "Ley N.º 21.719",
    "articulo_referencia": "Art. 15 bis",
    "dominio": "Protección de Datos",
    "tipo_fuente": "Obligación Legal",
    "obligacion": "Regular mediante contrato a los proveedores de IA que actúan como encargados",
    "pregunta": "¿Los contratos con sus proveedores de IA (ej. ChatGPT, servicios en la nube, APIs) incluyen cláusulas de privacidad o un Anexo de Tratamiento de Datos (DPA) que los regule legalmente como encargados?",
    "aplicabilidad": "Condicional (Si usa IA de terceros)",
    "evidencia_esperada": "Contratos o DPA (Data Processing Agreements) firmados",
    "criticidad": "Alta",
    "brecha_asociada": "Contratación de servicios de IA sin garantías legales de privacidad",
    "recomendacion": "Exigir firmar un Anexo de Tratamiento de Datos (DPA) con proveedores",
    "ruta_formativa": "Protección de Datos - Intermedio",
    "test_asociado": "test_evaluar_dat_007_encargados"
  },
  {
    "id": 8,
    "control_id": "DAT-008",
    "version": 1,
    "framework_fuente": "Ley N.º 21.719",
    "articulo_referencia": "Arts. 26 a 31",
    "dominio": "Protección de Datos",
    "tipo_fuente": "Obligación Legal",
    "obligacion": "Validar licitud de transferencias internacionales al enviar datos a servidores externos",
    "pregunta": "¿Se verifica que los proveedores o APIs de IA ubicados fuera de Chile cumplan con los estándares legales exigidos para la transferencia internacional de datos personales?",
    "aplicabilidad": "Condicional (Si usa IA en la nube internacional)",
    "evidencia_esperada": "Cláusulas tipo / Certificación del proveedor de nube",
    "criticidad": "Media",
    "brecha_asociada": "Transferencia internacional de datos no regulada",
    "recomendacion": "Evaluar la ubicación de los servidores y aplicar cláusulas contractuales tipo",
    "ruta_formativa": "Protección de Datos - Avanzado",
    "test_asociado": "test_evaluar_dat_008_transferencia"
  },
  {
    "id": 9,
    "control_id": "DAT-009",
    "version": 1,
    "framework_fuente": "Ley N.º 21.719",
    "articulo_referencia": "Arts. 16 y 17",
    "dominio": "Protección de Datos",
    "tipo_fuente": "Obligación Legal",
    "obligacion": "Proteger con medidas reforzadas datos sensibles, biométricos o de menores",
    "pregunta": "¿Se aplican medidas de seguridad reforzadas cuando la IA procesa datos sensibles (ej. salud, origen étnico), datos biométricos (ej. reconocimiento facial, huellas) o datos de menores de edad?",
    "aplicabilidad": "Condicional (Si procesa datos sensibles/menores)",
    "evidencia_esperada": "Política de protección de datos sensibles y consentimientos explícitos",
    "criticidad": "Alta",
    "brecha_asociada": "Tratamiento no autorizado de datos de categoría especial",
    "recomendacion": "Implementar controles de cifrado y consentimiento expreso reforzado",
    "ruta_formativa": "Protección de Datos - Avanzado",
    "test_asociado": "test_evaluar_dat_009_sensibles"
  },
  {
    "id": 10,
    "control_id": "DAT-010",
    "version": 1,
    "framework_fuente": "Ley N.º 21.719",
    "articulo_referencia": "Art. 14 ter y Art. 3 N°7",
    "dominio": "Protección de Datos",
    "tipo_fuente": "Obligación Legal",
    "obligacion": "Informar de forma clara y transparente el uso de IA al titular de los datos",
    "pregunta": "¿Se informa de manera clara a los usuarios y clientes (ej. mediante avisos de privacidad) cuando sus datos personales son analizados o procesados por algoritmos de Inteligencia Artificial?",
    "aplicabilidad": "Siempre",
    "evidencia_esperada": "Avisos de privacidad en interfaces / Términos de uso",
    "criticidad": "Media",
    "brecha_asociada": "Opacidad en la recolección y procesamiento con IA",
    "recomendacion": "Publicar avisos de privacidad claros sobre el uso de sistemas de IA",
    "ruta_formativa": "Protección de Datos - Inicial",
    "test_asociado": "test_evaluar_dat_010_transparencia"
  },
  {
    "id": 11,
    "control_id": "GOB-001",
    "version": 1,
    "framework_fuente": "ISO/IEC 42001",
    "articulo_referencia": "Cláusula 5.2",
    "dominio": "Gobernanza de IA",
    "tipo_fuente": "Estándar Normativo",
    "obligacion": "Formalizar una Política Corporativa de Uso y Gobernanza de IA",
    "pregunta": "¿Existe una Política de Uso de Inteligencia Artificial aprobada formalmente por la gerencia y comunicada a todos los colaboradores de la empresa?",
    "aplicabilidad": "Siempre",
    "evidencia_esperada": "Documento de Política de IA / Acta de aprobación directiva",
    "criticidad": "Media",
    "brecha_asociada": "Inexistencia de directrices institucionales sobre IA",
    "recomendacion": "Redactar y oficializar una política marco de gobernanza de IA",
    "ruta_formativa": "Gobernanza de IA - Inicial",
    "test_asociado": "test_evaluar_gob_001_politica"
  },
  {
    "id": 12,
    "control_id": "GOB-002",
    "version": 1,
    "framework_fuente": "ISO/IEC 42001",
    "articulo_referencia": "Cláusula 5.3",
    "dominio": "Gobernanza de IA",
    "tipo_fuente": "Estándar Normativo",
    "obligacion": "Asignar roles y responsabilidades claras en la gestión de IA",
    "pregunta": "¿Se ha asignado a una persona o equipo (ej. responsable de TI, gerencia, o un líder designado) la responsabilidad formal de supervisar el uso seguro de la IA en la organización?",
    "aplicabilidad": "Siempre",
    "evidencia_esperada": "Matriz RACI / Definición de roles en la organización",
    "criticidad": "Media",
    "brecha_asociada": "Falta de un responsable formal de la gobernanza de IA",
    "recomendacion": "Asignar formalmente responsabilidades de supervisión de IA",
    "ruta_formativa": "Gobernanza de IA - Inicial",
    "test_asociado": "test_evaluar_gob_002_roles"
  },
  {
    "id": 13,
    "control_id": "GOB-003",
    "version": 1,
    "framework_fuente": "ISO/IEC 42001",
    "articulo_referencia": "Cláusula 4.3, 7.5, 8.1",
    "dominio": "Gobernanza de IA",
    "tipo_fuente": "Estándar Normativo",
    "obligacion": "Mantener un inventario centralizado de todos los sistemas de IA en uso",
    "pregunta": "¿Cuenta la organización con un inventario actualizado de todas las herramientas y modelos de IA que utiliza su personal (incluyendo software de pago y plataformas gratuitas)?",
    "aplicabilidad": "Siempre",
    "evidencia_esperada": "Inventario de Sistemas de IA (software, API, modelos)",
    "criticidad": "Alta",
    "brecha_asociada": "Uso de 'Shadow AI' o herramientas no contabilizadas",
    "recomendacion": "Crear y mantener un catálogo oficial de aplicaciones de IA",
    "ruta_formativa": "Gobernanza de IA - Inicial",
    "test_asociado": "test_evaluar_gob_003_inventario"
  },
  {
    "id": 14,
    "control_id": "GOB-004",
    "version": 1,
    "framework_fuente": "ISO/IEC 42001",
    "articulo_referencia": "Cláusula 7.2",
    "dominio": "Gobernanza de IA",
    "tipo_fuente": "Estándar Normativo",
    "obligacion": "Capacitar continuamente al personal en uso seguro y ético de la IA",
    "pregunta": "¿Se realizan capacitaciones periódicas a los colaboradores sobre los riesgos y buenas prácticas en el uso de herramientas de IA?",
    "aplicabilidad": "Siempre",
    "evidencia_esperada": "Registro de asistencia y programa de capacitación corporativo",
    "criticidad": "Baja",
    "brecha_asociada": "Falta de alfabetización y cultura sobre riesgos de IA",
    "recomendacion": "Implementar itinerarios formativos continuos para los equipos",
    "ruta_formativa": "Gobernanza de IA - Inicial",
    "test_asociado": "test_evaluar_gob_004_capacitacion"
  },
  {
    "id": 15,
    "control_id": "GOB-005",
    "version": 1,
    "framework_fuente": "ISO/IEC 42001",
    "articulo_referencia": "Cláusula 4.1",
    "dominio": "Gobernanza de IA",
    "tipo_fuente": "Estándar Normativo",
    "obligacion": "Evaluar la alineación ética y estratégica de los proyectos de IA",
    "pregunta": "Antes de comprar, desarrollar o permitir el uso de una nueva herramienta de IA, ¿se evalúa formalmente si realmente aporta valor al negocio y si los riesgos que introduce (legales, privacidad, reputación) son aceptables?",
    "aplicabilidad": "Siempre",
    "evidencia_esperada": "Análisis FODA y Análisis PESTEL",
    "criticidad": "Media",
    "brecha_asociada": "Adopción de herramientas de IA por moda o en las sombras, sin control de riesgos ni justificación de negocio",
    "recomendacion": "Definir un filtro de evaluación de proyectos de IA previo a la compra (checklist / business case)",
    "ruta_formativa": "Gobernanza de IA - Inicial",
    "test_asociado": "test_evaluar_gob_005_alineacion"
  },
  {
    "id": 16,
    "control_id": "GOB-006",
    "version": 1,
    "framework_fuente": "ISO/IEC 42001",
    "articulo_referencia": "Cláusula 8.1",
    "dominio": "Gobernanza de IA",
    "tipo_fuente": "Estándar Normativo",
    "obligacion": "Establecer controles operativos para todo el ciclo de vida de la IA",
    "pregunta": "¿Existen procedimientos formales para gestionar de forma segura el diseño, las pruebas, la puesta en marcha y la desactivación (baja) de los sistemas de IA propios?",
    "aplicabilidad": "Condicional (Si desarrolla o integra IA propia)",
    "evidencia_esperada": "Manual de ciclo de vida de desarrollo de software con IA",
    "criticidad": "Media",
    "brecha_asociada": "Despliegue de IA sin controles en las etapas del ciclo de vida",
    "recomendacion": "Formalizar un procedimiento de control del ciclo de vida de IA",
    "ruta_formativa": "Gobernanza de IA - Intermedio",
    "test_asociado": "test_evaluar_gob_006_ciclo_vida"
  },
  {
    "id": 17,
    "control_id": "GOB-007",
    "version": 1,
    "framework_fuente": "ISO/IEC 42001",
    "articulo_referencia": "Cláusula 9.3",
    "dominio": "Gobernanza de IA",
    "tipo_fuente": "Estándar Normativo",
    "obligacion": "Efectuar revisiones periódicas del sistema de gestión de IA por la dirección",
    "pregunta": "¿La gerencia o dirección general revisa periódicamente (ej. anualmente) el desempeño, los riesgos y los resultados de las herramientas de IA utilizadas en la empresa?",
    "aplicabilidad": "Siempre",
    "evidencia_esperada": "Minuta o acta de reunión de revisión por la dirección",
    "criticidad": "Media",
    "brecha_asociada": "Desconexión directiva de los riesgos operacionales de la IA",
    "recomendacion": "Programar revisiones ejecutivas semestrales o anuales sobre IA",
    "ruta_formativa": "Gobernanza de IA - Avanzado",
    "test_asociado": "test_evaluar_gob_007_revision_direccion"
  },
  {
    "id": 18,
    "control_id": "GOB-008",
    "version": 1,
    "framework_fuente": "ISO/IEC 42001",
    "articulo_referencia": "Cláusula 8.1",
    "dominio": "Gobernanza de IA",
    "tipo_fuente": "Estándar Normativo",
    "obligacion": "Aplicar homologación rigurosa de proveedores de soluciones de IA",
    "pregunta": "¿Se evalúan los estándares de seguridad, privacidad y ética de los proveedores antes de adquirir o contratar un nuevo software o servicio de IA?",
    "aplicabilidad": "Condicional (Si contrata IA a terceros)",
    "evidencia_esperada": "Checklist de homologación de proveedores de IA completado",
    "criticidad": "Alta",
    "brecha_asociada": "Adquisición de IA de terceros sin estándares de seguridad",
    "recomendacion": "Integrar criterios de gobernanza de IA en la gestión de compras",
    "ruta_formativa": "Gobernanza de IA - Intermedio",
    "test_asociado": "test_evaluar_gob_008_proveedores"
  },
  {
    "id": 19,
    "control_id": "GOB-009",
    "version": 1,
    "framework_fuente": "ISO/IEC 42001",
    "articulo_referencia": "Cláusula 7.2, 8.1",
    "dominio": "Gobernanza de IA",
    "tipo_fuente": "Estándar Normativo",
    "obligacion": "Establecer guía de uso aceptable de IA Generativa en el puesto de trabajo",
    "pregunta": "¿Se han definido y comunicado reglas claras a los empleados sobre qué información confidencial o privada NO se debe ingresar a herramientas de IA públicas (ej. ChatGPT, Gemini)?",
    "aplicabilidad": "Siempre",
    "evidencia_esperada": "Guía de uso aceptable de IA Generativa publicada",
    "criticidad": "Alta",
    "brecha_asociada": "Exposición de secretos comerciales o datos en chatbots públicos",
    "recomendacion": "Publicar norma de uso aceptable de IA pública para empleados",
    "ruta_formativa": "Gobernanza de IA - Inicial",
    "test_asociado": "test_evaluar_gob_009_uso_aceptable"
  },
  {
    "id": 20,
    "control_id": "GOB-010",
    "version": 1,
    "framework_fuente": "ISO/IEC 42001",
    "articulo_referencia": "Cláusula 10.1",
    "dominio": "Gobernanza de IA",
    "tipo_fuente": "Estándar Normativo",
    "obligacion": "Implementar mecanismos de mejora continua ante fallas en sistemas de IA",
    "pregunta": "¿Existen procesos establecidos para reportar y corregir fallos, respuestas incorrectas (alucinaciones) o comportamientos indeseados detectados en las herramientas de IA?",
    "aplicabilidad": "Siempre",
    "evidencia_esperada": "Registro de no conformidades y acciones correctivas aplicadas",
    "criticidad": "Baja",
    "brecha_asociada": "Reincidencia en errores operacionales o éticos de los modelos",
    "recomendacion": "Establecer un canal de reporte interno de fallos en IA",
    "ruta_formativa": "Gobernanza de IA - Avanzado",
    "test_asociado": "test_evaluar_gob_010_mejora_continua"
  },
  {
    "id": 21,
    "control_id": "RIE-001",
    "version": 1,
    "framework_fuente": "NIST AI RMF 100-1",
    "articulo_referencia": "MAP 1.1, 1.2",
    "dominio": "Gestión de Riesgos",
    "tipo_fuente": "Estándar Normativo",
    "obligacion": "Identificar y catalogar riesgos específicos de los sistemas de IA",
    "pregunta": "¿Cuenta la empresa con un registro o matriz donde se identifiquen y evalúen los posibles riesgos, problemas o amenazas específicas de usar Inteligencia Artificial?",
    "aplicabilidad": "Siempre",
    "evidencia_esperada": "Matriz de Riesgos de IA con escala de impacto y probabilidad",
    "criticidad": "Alta",
    "brecha_asociada": "Inexistencia de catalogación de riesgos propios de la IA",
    "recomendacion": "Implementar la función MAP de NIST AI RMF para catalogar riesgos",
    "ruta_formativa": "Gestión de Riesgos - Inicial",
    "test_asociado": "test_evaluar_rie_001_map"
  },
  {
    "id": 22,
    "control_id": "RIE-002",
    "version": 1,
    "framework_fuente": "NIST AI RMF 100-1",
    "articulo_referencia": "MEASURE 2.1",
    "dominio": "Gestión de Riesgos",
    "tipo_fuente": "Estándar Normativo",
    "obligacion": "Medir métricas de precisión, confiabilidad y tasa de error de los modelos",
    "pregunta": "¿Se revisa o evalúa periódicamente la precisión de las respuestas de la IA para detectar errores o inventos de información (alucinaciones)?",
    "aplicabilidad": "Condicional (Si usa o desarrolla modelos/LLM)",
    "evidencia_esperada": "Reporte de métricas de desempeño y calidad del modelo",
    "criticidad": "Alta",
    "brecha_asociada": "Falta de medición de fallas y alucinaciones en respuestas",
    "recomendacion": "Establecer métricas de evaluación continua de calidad del modelo",
    "ruta_formativa": "Gestión de Riesgos - Intermedio",
    "test_asociado": "test_evaluar_rie_002_measure"
  },
  {
    "id": 23,
    "control_id": "RIE-003",
    "version": 1,
    "framework_fuente": "NIST AI RMF 100-1",
    "articulo_referencia": "MANAGE 1.1, 1.2",
    "dominio": "Gestión de Riesgos",
    "tipo_fuente": "Estándar Normativo",
    "obligacion": "Implementar planes de tratamiento y mitigación para riesgos identificados",
    "pregunta": "¿Existen medidas o planes de acción concretos para controlar los riesgos de Inteligencia Artificial que se consideren críticos o altos para su negocio?",
    "aplicabilidad": "Siempre",
    "evidencia_esperada": "Plan de Tratamiento de Riesgos con responsables y plazos",
    "criticidad": "Alta",
    "brecha_asociada": "Identificación de riesgos sin planes concretos de mitigación",
    "recomendacion": "Asignar acciones de control a cada riesgo de nivel alto o crítico",
    "ruta_formativa": "Gestión de Riesgos - Intermedio",
    "test_asociado": "test_evaluar_rie_003_manage"
  },
  {
    "id": 24,
    "control_id": "RIE-004",
    "version": 1,
    "framework_fuente": "ISO/IEC 42001",
    "articulo_referencia": "Cláusula 9.1",
    "dominio": "Gestión de Riesgos",
    "tipo_fuente": "Estándar Normativo",
    "obligacion": "Monitorear continuamente el entorno para detectar riesgos emergentes de IA",
    "pregunta": "¿Se monitorean periódicamente las herramientas de IA que ya se están utilizando en la empresa para detectar nuevos riesgos, cambios o comportamientos inesperados?",
    "aplicabilidad": "Siempre",
    "evidencia_esperada": "Minutas de revisión del perfil de riesgos de IA",
    "criticidad": "Media",
    "brecha_asociada": "Monitoreo estático que ignora la evolución de los modelos",
    "recomendacion": "Establecer revisiones trimestrales de la matriz de riesgos de IA",
    "ruta_formativa": "Gestión de Riesgos - Avanzado",
    "test_asociado": "test_evaluar_rie_004_monitoreo"
  },
  {
    "id": 25,
    "control_id": "RIE-005",
    "version": 1,
    "framework_fuente": "NIST AI RMF 100-1",
    "articulo_referencia": "MEASURE 2.1, 2.2, 2.3",
    "dominio": "Gestión de Riesgos",
    "tipo_fuente": "Estándar Normativo",
    "obligacion": "Detectar y mitigar sesgos discriminatorios en las decisiones de la IA",
    "pregunta": "¿Se realizan pruebas para asegurar que las decisiones o respuestas de la IA no generen discriminación, tratos injustos o sesgos hacia las personas?",
    "aplicabilidad": "Condicional (Si usa IA para decisiones que afectan personas)",
    "evidencia_esperada": "Reporte de evaluación de sesgo o equidad (Fairness test)",
    "criticidad": "Alta",
    "brecha_asociada": "Respuestas o decisiones algorítmicas discriminatorias",
    "recomendacion": "Ejecutar pruebas de equidad y corregir datos de entrenamiento/prompts",
    "ruta_formativa": "Gestión de Riesgos - Avanzado",
    "test_asociado": "test_evaluar_rie_005_sesgos"
  },
  {
    "id": 26,
    "control_id": "RIE-006",
    "version": 1,
    "framework_fuente": "NIST AI RMF 100-1",
    "articulo_referencia": "MEASURE 2.9",
    "dominio": "Gestión de Riesgos",
    "tipo_fuente": "Estándar Normativo",
    "obligacion": "Evaluar la explicabilidad de las decisiones automatizadas",
    "pregunta": "Cuando la IA toma decisiones clave que afectan a personas, ¿es posible explicar de manera clara y sencilla cómo el sistema llegó a esa conclusión?",
    "aplicabilidad": "Condicional (Si toma decisiones automatizadas sobre personas)",
    "evidencia_esperada": "Documentación de explicabilidad o arquitectura del modelo",
    "criticidad": "Media",
    "brecha_asociada": "Decisiones en formato caja negra imposibles de auditar",
    "recomendacion": "Incorporar técnicas de explicabilidad (ej. LIME/SHAP) o árboles",
    "ruta_formativa": "Gestión de Riesgos - Avanzado",
    "test_asociado": "test_evaluar_rie_006_explicabilidad"
  },
  {
    "id": 27,
    "control_id": "RIE-007",
    "version": 1,
    "framework_fuente": "NIST AI RMF 100-1",
    "articulo_referencia": "MEASURE 2.5, 2.6",
    "dominio": "Gestión de Riesgos",
    "tipo_fuente": "Estándar Normativo",
    "obligacion": "Realizar pruebas de adversario y red teaming sobre modelos sensibles",
    "pregunta": "¿Se realizan pruebas de seguridad intencionales (ej. intentar engañar a la IA o Red Teaming) para descubrir fallos o vulnerabilidades antes de usarla oficialmente?",
    "aplicabilidad": "Condicional (Si desarrolla o despliega agentes/LLM propios)",
    "evidencia_esperada": "Informe de pruebas de penetración o Red Teaming en IA",
    "criticidad": "Media",
    "brecha_asociada": "Vulnerabilidad del sistema ante entradas maliciosas o complejas",
    "recomendacion": "Programar sesiones de Red Teaming antes de lanzamientos clave",
    "ruta_formativa": "Gestión de Riesgos - Avanzado",
    "test_asociado": "test_evaluar_rie_007_red_teaming"
  },
  {
    "id": 28,
    "control_id": "RIE-008",
    "version": 1,
    "framework_fuente": "NIST AI RMF 100-1",
    "articulo_referencia": "MANAGE 2.4",
    "dominio": "Gestión de Riesgos",
    "tipo_fuente": "Estándar Normativo",
    "obligacion": "Definir un plan de contingencia ante caída o indisponibilidad de la IA",
    "pregunta": "¿Existe un plan o procedimiento alternativo (ej. volver a un proceso manual) en caso de que la herramienta de IA falle, cometa errores graves o quede fuera de servicio?",
    "aplicabilidad": "Siempre",
    "evidencia_esperada": "Plan de Continuidad Operativa con alternativa manual",
    "criticidad": "Media",
    "brecha_asociada": "Interrupción del negocio por caída de las API de IA de terceros",
    "recomendacion": "Diseñar flujos alternativos de trabajo en caso de caída del servicio",
    "ruta_formativa": "Gestión de Riesgos - Inicial",
    "test_asociado": "test_evaluar_rie_008_contingencia"
  },
  {
    "id": 29,
    "control_id": "RIE-009",
    "version": 1,
    "framework_fuente": "NIST AI RMF 100-1",
    "articulo_referencia": "GOVERN 4.2 / MANAGE 1.3, 2.3",
    "dominio": "Gestión de Riesgos",
    "tipo_fuente": "Estándar Normativo",
    "obligacion": "Establecer límites de autonomía para agentes de IA que ejecutan acciones",
    "pregunta": "Si utiliza sistemas de IA que actúan por sí solos, ¿tienen límites para evitar que ejecuten acciones críticas (ej. enviar correos a clientes o hacer pagos) sin supervisión o aprobación humana?",
    "aplicabilidad": "Condicional (Si utiliza agentes autónomos de IA)",
    "evidencia_esperada": "Configuración de permisos y arquitectura de llamadas a API",
    "criticidad": "Alta",
    "brecha_asociada": "Acciones ejecutadas por IA sin control o revisión intermedia",
    "recomendacion": "Implementar límites de aprobación para acciones críticas de la IA",
    "ruta_formativa": "Gestión de Riesgos - Intermedio",
    "test_asociado": "test_evaluar_rie_009_autonomia"
  },
  {
    "id": 30,
    "control_id": "RIE-010",
    "version": 1,
    "framework_fuente": "NIST AI RMF 100-1",
    "articulo_referencia": "GOVERN 1.5",
    "dominio": "Gestión de Riesgos",
    "tipo_fuente": "Estándar Normativo",
    "obligacion": "Mantener registros de auditoría (logs) de las interacciones con IA",
    "pregunta": "¿Se guardan registros históricos (logs) de la información ingresada (preguntas/datos) y las respuestas entregadas por los sistemas de IA corporativos, para futuras revisiones?",
    "aplicabilidad": "Siempre",
    "evidencia_esperada": "Logs de auditoría almacenados de forma segura",
    "criticidad": "Media",
    "brecha_asociada": "Ausencia de trazabilidad en caso de investigaciones o litigios",
    "recomendacion": "Activar y resguardar logs de auditoría de interacciones de IA",
    "ruta_formativa": "Gestión de Riesgos - Inicial",
    "test_asociado": "test_evaluar_rie_010_logs"
  },
  {
    "id": 31,
    "control_id": "SEG-001",
    "version": 1,
    "framework_fuente": "OWASP LLM",
    "articulo_referencia": "LLM01",
    "dominio": "Uso Responsable",
    "tipo_fuente": "Seguridad Técnica",
    "obligacion": "Implementar sanitización e inspección de prompts para evitar inyecciones",
    "pregunta": "¿Existen filtros o barreras de seguridad (Guardrails) para prevenir que usuarios malintencionados manipulen o engañen a la IA mediante instrucciones falsas (inyección de prompts)?",
    "aplicabilidad": "Condicional (Si utiliza LLM o IA Generativa)",
    "evidencia_esperada": "Configuración técnica de Guardrails / Pruebas de entrada",
    "criticidad": "Alta",
    "brecha_asociada": "Vulnerabilidad a inyección de instrucciones no autorizadas",
    "recomendacion": "Integrar capas intermedias de sanitización e inspección de prompts",
    "ruta_formativa": "Uso Responsable - Avanzado",
    "test_asociado": "test_evaluar_seg_001_prompt_injection"
  },
  {
    "id": 32,
    "control_id": "SEG-002",
    "version": 1,
    "framework_fuente": "OWASP LLM",
    "articulo_referencia": "LLM02",
    "dominio": "Uso Responsable",
    "tipo_fuente": "Seguridad Técnica",
    "obligacion": "Prevenir la divulgación o fuga involuntaria de información sensible en salidas",
    "pregunta": "¿Se aplican filtros o reglas de seguridad para evitar que la IA revele accidentalmente datos confidenciales, contraseñas o información sensible en sus respuestas?",
    "aplicabilidad": "Condicional (Si utiliza LLM o IA Generativa)",
    "evidencia_esperada": "Filtros DLP (Data Loss Prevention) o reglas en respuesta de API",
    "criticidad": "Alta",
    "brecha_asociada": "Exposición de secretos o datos personales en las respuestas",
    "recomendacion": "Desplegar filtros de prevención de fuga de datos en la salida",
    "ruta_formativa": "Uso Responsable - Avanzado",
    "test_asociado": "test_evaluar_seg_002_fuga_informacion"
  },
  {
    "id": 33,
    "control_id": "SEG-003",
    "version": 1,
    "framework_fuente": "OWASP LLM",
    "articulo_referencia": "LLM03",
    "dominio": "Uso Responsable",
    "tipo_fuente": "Seguridad Técnica",
    "obligacion": "Restringir el nivel de acceso y permisos de las funciones de la IA (Exceso de Agencia)",
    "pregunta": "Si la IA está conectada a otros sistemas de la empresa, ¿opera con permisos restringidos (principio de menor privilegio) para evitar que lea, modifique o borre información no autorizada?",
    "aplicabilidad": "Condicional (Si la IA ejecuta acciones en otros sistemas)",
    "evidencia_esperada": "Configuración de permisos RBAC y API scopes acotados",
    "criticidad": "Alta",
    "brecha_asociada": "Exceso de privilegios otorgados a componentes de IA",
    "recomendacion": "Restringir permisos de escritura y eliminación de la IA a lo mínimo",
    "ruta_formativa": "Uso Responsable - Avanzado",
    "test_asociado": "test_evaluar_seg_003_exceso_agencia"
  },
  {
    "id": 34,
    "control_id": "SEG-004",
    "version": 1,
    "framework_fuente": "OWASP LLM",
    "articulo_referencia": "LLM02 (Insecure Output Handling)",
    "dominio": "Uso Responsable",
    "tipo_fuente": "Seguridad Técnica",
    "obligacion": "Validar las respuestas antes de ejecutarlas en el backend",
    "pregunta": "¿Se revisan y validan técnicamente las respuestas de la IA antes de que interactúen automáticamente con otros sistemas (ej. antes de ejecutar código o consultar bases de datos)?",
    "aplicabilidad": "Condicional (Si la IA genera código o consultas SQL/HTML)",
    "evidencia_esperada": "Sanitización de salida (Escapado de código, validación de esquemas)",
    "criticidad": "Alta",
    "brecha_asociada": "Procesamiento inseguro de respuestas que genera XSS o SQLi",
    "recomendacion": "Validar y tipar sintácticamente cualquier salida previa a su ejecución",
    "ruta_formativa": "Uso Responsable - Avanzado",
    "test_asociado": "test_evaluar_seg_004_output_inseguro"
  },
  {
    "id": 35,
    "control_id": "SEG-005",
    "version": 1,
    "framework_fuente": "OWASP LLM",
    "articulo_referencia": "LLM05",
    "dominio": "Uso Responsable",
    "tipo_fuente": "Seguridad Técnica",
    "obligacion": "Asegurar la integridad de las fuentes de datos utilizadas en arquitecturas RAG",
    "pregunta": "Si la IA utiliza documentos internos de la empresa para responder (arquitectura RAG), ¿existen controles para asegurar que esos archivos sean seguros y no contengan código malicioso o información falsa?",
    "aplicabilidad": "Condicional (Si utiliza arquitecturas RAG o bases vectoriales)",
    "evidencia_esperada": "Procedimiento de validación y control de acceso a documentos RAG",
    "criticidad": "Media",
    "brecha_asociada": "Envenenamiento de fuentes de conocimiento de la IA",
    "recomendacion": "Implementar firma y control de acceso a la base de conocimiento RAG",
    "ruta_formativa": "Uso Responsable - Intermedio",
    "test_asociado": "test_evaluar_seg_005_rag_poisoning"
  },
  {
    "id": 36,
    "control_id": "SEG-006",
    "version": 1,
    "framework_fuente": "NIST 600-1",
    "articulo_referencia": "Sec. 2.9",
    "dominio": "Uso Responsable",
    "tipo_fuente": "Seguridad Técnica",
    "obligacion": "Cifrar las comunicaciones y almacenamiento de vectores, prompts y resultados",
    "pregunta": "¿Se utilizan medidas de seguridad como el cifrado (ej. conexiones seguras TLS, AES) para proteger la información mientras se almacena o se envía a los sistemas de IA?",
    "aplicabilidad": "Siempre",
    "evidencia_esperada": "Certificados SSL/TLS activos y políticas de cifrado en reposo",
    "criticidad": "Alta",
    "brecha_asociada": "Tránsito o almacenamiento de interacciones de IA en texto plano",
    "recomendacion": "Configurar cifrado extremo a extremo en todas las llamadas a API",
    "ruta_formativa": "Uso Responsable - Intermedio",
    "test_asociado": "test_evaluar_seg_006_cifrado"
  },
  {
    "id": 37,
    "control_id": "SEG-007",
    "version": 1,
    "framework_fuente": "NIST 600-1",
    "articulo_referencia": "Sec. 2.9",
    "dominio": "Protección de Datos",
    "tipo_fuente": "Decisión de Diseño",
    "obligacion": "Cifrar las comunicaciones y almacenamiento de vectores, prompts y resultados",
    "pregunta": "¿Se aplican medidas de cifrado para proteger estrictamente el historial de conversaciones (prompts) y los documentos internos guardados en la base de datos de la IA, evitando que sean robados o interceptados?",
    "aplicabilidad": "Siempre",
    "evidencia_esperada": "Configuración de cifrado activa en la base de datos de vectores y canales del LLM",
    "criticidad": "Alta",
    "brecha_asociada": "Compromiso de la confidencialidad de los datos o intercepción de sesiones",
    "recomendacion": "Implementar controles criptográficos en todas las capas del sistema (tránsito y almacenamiento)",
    "ruta_formativa": "Uso Responsable - Avanzado",
    "test_asociado": "test_evaluar_seg_007_cifrado"
  },
  {
    "id": 38,
    "control_id": "SEG-008",
    "version": 1,
    "framework_fuente": "Ley N.º 21.719",
    "articulo_referencia": "Art. 14 Letra H",
    "dominio": "Protección de Datos",
    "tipo_fuente": "Decisión de Diseño",
    "obligacion": "Anonimizar o seudonimizar PII antes de enviarla a modelos externos",
    "pregunta": "Si utiliza IA de proveedores externos, ¿se aplican herramientas (como motores NER) para enmascarar u ocultar datos personales (ej. RUT, nombres, teléfonos) antes de enviarlos a la plataforma externa?",
    "aplicabilidad": "Condicional (Si utiliza API de IA de terceros)",
    "evidencia_esperada": "Funciones de seudonimización comprobadas en el backend",
    "criticidad": "Alta",
    "brecha_asociada": "Envío de datos identificables a servidores de proveedores de IA",
    "recomendacion": "Integrar módulo NER de enmascaramiento previo al envío de prompts",
    "ruta_formativa": "Uso Responsable - Intermedio",
    "test_asociado": "test_evaluar_seg_008_ner_anonimizacion"
  },
  {
    "id": 39,
    "control_id": "SEG-009",
    "version": 1,
    "framework_fuente": "OWASP LLM",
    "articulo_referencia": "LLM10",
    "dominio": "Uso Responsable",
    "tipo_fuente": "Seguridad Técnica",
    "obligacion": "Proteger el sistema contra ataques de denegación de servicio por consultas masivas",
    "pregunta": "¿Se aplican límites de uso y cuotas (Rate Limiting) para evitar que consultas masivas bloqueen el sistema (ej. Ataque DoS) o generen sobrecostos inesperados en los servicios de IA?",
    "aplicabilidad": "Siempre",
    "evidencia_esperada": "Configuración de Rate Limiting y alertas de presupuesto en API",
    "criticidad": "Baja",
    "brecha_asociada": "Agotamiento de recursos o sobrecostos por uso desmedido de la API",
    "recomendacion": "Configurar límites de peticiones por minuto y alertas de consumo",
    "ruta_formativa": "Uso Responsable - Inicial",
    "test_asociado": "test_evaluar_seg_009_rate_limiting"
  },
  {
    "id": 40,
    "control_id": "SEG-010",
    "version": 1,
    "framework_fuente": "Ley N.º 21.719",
    "articulo_referencia": "Art. 8 bis",
    "dominio": "Uso Responsable",
    "tipo_fuente": "Decisión de Diseño",
    "obligacion": "Requerir intervención humana obligatoria en decisiones de alto impacto",
    "pregunta": "Cuando la IA toma decisiones importantes que afectan a personas (ej. contrataciones, evaluación crediticia), ¿se exige la validación o revisión de un operador humano antes de aplicar definitivamente esa decisión?",
    "aplicabilidad": "Condicional (Si la IA afecta derechos o contrataciones)",
    "evidencia_esperada": "Procedimiento formal de supervisión Human-in-the-Loop",
    "criticidad": "Alta",
    "brecha_asociada": "Tomar decisiones críticas de forma automatizada sin supervisión",
    "recomendacion": "Implementar una interfaz de aprobación humana previa a la ejecución",
    "ruta_formativa": "Uso Responsable - Inicial",
    "test_asociado": "test_evaluar_seg_010_human_in_loop"
  }
],
  GATES: [
  {
    "id": 1,
    "orden": 0,
    "pregunta": "¿La organización utiliza, desarrolla o integra algún sistema, modelo o herramienta de IA?",
    "es_raiz": true,
    "controles_si": [
      "DAT-001",
      "DAT-003",
      "DAT-004",
      "DAT-005",
      "DAT-006",
      "DAT-010",
      "GOB-001",
      "GOB-002",
      "GOB-003",
      "GOB-004",
      "GOB-005",
      "GOB-007",
      "GOB-009",
      "GOB-010",
      "RIE-001",
      "RIE-003",
      "RIE-004",
      "RIE-008",
      "RIE-010",
      "SEG-006",
      "SEG-007",
      "SEG-009"
    ]
  },
  {
    "id": 2,
    "orden": 1,
    "pregunta": "¿Procesa datos sensibles (salud, biométricos) o realiza perfilamiento de personas/menores?",
    "es_raiz": false,
    "controles_si": [
      "DAT-002",
      "DAT-009"
    ]
  },
  {
    "id": 3,
    "orden": 2,
    "pregunta": "¿Utiliza servicios, APIs, SaaS o plataformas de IA provistas por terceros/nube internacional?",
    "es_raiz": false,
    "controles_si": [
      "DAT-007",
      "GOB-008",
      "DAT-008",
      "SEG-008"
    ]
  },
  {
    "id": 4,
    "orden": 3,
    "pregunta": "¿Utiliza modelos de lenguaje (LLM), IA Generativa o arquitecturas RAG / bases vectoriales?",
    "es_raiz": false,
    "controles_si": [
      "RIE-002",
      "SEG-001",
      "SEG-002",
      "SEG-005"
    ]
  },
  {
    "id": 5,
    "orden": 4,
    "pregunta": "¿La IA genera código/SQL/HTML o ejecuta acciones/agentes conectados a otros sistemas corporativos?",
    "es_raiz": false,
    "controles_si": [
      "RIE-009",
      "SEG-003",
      "SEG-004"
    ]
  },
  {
    "id": 6,
    "orden": 5,
    "pregunta": "¿La IA toma decisiones o genera resultados que afectan directamente derechos, personas, crédito o contrataciones?",
    "es_raiz": false,
    "controles_si": [
      "RIE-005",
      "RIE-006",
      "SEG-010"
    ]
  },
  {
    "id": 7,
    "orden": 6,
    "pregunta": "¿La empresa desarrolla, entrena o adapta internamente sus propios modelos o agentes de IA?",
    "es_raiz": false,
    "controles_si": [
      "RIE-007",
      "GOB-006"
    ]
  }
],
  MODULOS: [
  {
    "id": 1,
    "dimension": "Gestión de Riesgos",
    "nivel": "Inicial",
    "titulo": "Gestión de Riesgos — Nivel Inicial",
    "contenido": "Módulo formativo de nivel Inicial para la dimensión 'Gestión de Riesgos'. Cubre 3 control(es) de la matriz relacionados con las brechas detectadas en esta dimensión durante el autodiagnóstico. (Contenido de ejemplo para la versión estática de demostración.)",
    "controles": [
      "RIE-001",
      "RIE-008",
      "RIE-010"
    ]
  },
  {
    "id": 2,
    "dimension": "Gestión de Riesgos",
    "nivel": "Intermedio",
    "titulo": "Gestión de Riesgos — Nivel Intermedio",
    "contenido": "Módulo formativo de nivel Intermedio para la dimensión 'Gestión de Riesgos'. Cubre 5 control(es) de la matriz relacionados con las brechas detectadas en esta dimensión durante el autodiagnóstico. (Contenido de ejemplo para la versión estática de demostración.)",
    "controles": [
      "DAT-002",
      "DAT-006",
      "RIE-002",
      "RIE-003",
      "RIE-009"
    ]
  },
  {
    "id": 3,
    "dimension": "Gestión de Riesgos",
    "nivel": "Avanzado",
    "titulo": "Gestión de Riesgos — Nivel Avanzado",
    "contenido": "Módulo formativo de nivel Avanzado para la dimensión 'Gestión de Riesgos'. Cubre 4 control(es) de la matriz relacionados con las brechas detectadas en esta dimensión durante el autodiagnóstico. (Contenido de ejemplo para la versión estática de demostración.)",
    "controles": [
      "RIE-004",
      "RIE-005",
      "RIE-006",
      "RIE-007"
    ]
  },
  {
    "id": 4,
    "dimension": "Gobernanza de IA",
    "nivel": "Inicial",
    "titulo": "Gobernanza de IA — Nivel Inicial",
    "contenido": "Módulo formativo de nivel Inicial para la dimensión 'Gobernanza de IA'. Cubre 6 control(es) de la matriz relacionados con las brechas detectadas en esta dimensión durante el autodiagnóstico. (Contenido de ejemplo para la versión estática de demostración.)",
    "controles": [
      "GOB-001",
      "GOB-002",
      "GOB-003",
      "GOB-004",
      "GOB-005",
      "GOB-009"
    ]
  },
  {
    "id": 5,
    "dimension": "Gobernanza de IA",
    "nivel": "Intermedio",
    "titulo": "Gobernanza de IA — Nivel Intermedio",
    "contenido": "Módulo formativo de nivel Intermedio para la dimensión 'Gobernanza de IA'. Cubre 2 control(es) de la matriz relacionados con las brechas detectadas en esta dimensión durante el autodiagnóstico. (Contenido de ejemplo para la versión estática de demostración.)",
    "controles": [
      "GOB-006",
      "GOB-008"
    ]
  },
  {
    "id": 6,
    "dimension": "Gobernanza de IA",
    "nivel": "Avanzado",
    "titulo": "Gobernanza de IA — Nivel Avanzado",
    "contenido": "Módulo formativo de nivel Avanzado para la dimensión 'Gobernanza de IA'. Cubre 2 control(es) de la matriz relacionados con las brechas detectadas en esta dimensión durante el autodiagnóstico. (Contenido de ejemplo para la versión estática de demostración.)",
    "controles": [
      "GOB-007",
      "GOB-010"
    ]
  },
  {
    "id": 7,
    "dimension": "Protección de Datos",
    "nivel": "Inicial",
    "titulo": "Protección de Datos — Nivel Inicial",
    "contenido": "Módulo formativo de nivel Inicial para la dimensión 'Protección de Datos'. Cubre 4 control(es) de la matriz relacionados con las brechas detectadas en esta dimensión durante el autodiagnóstico. (Contenido de ejemplo para la versión estática de demostración.)",
    "controles": [
      "DAT-001",
      "DAT-003",
      "DAT-005",
      "DAT-010"
    ]
  },
  {
    "id": 8,
    "dimension": "Protección de Datos",
    "nivel": "Intermedio",
    "titulo": "Protección de Datos — Nivel Intermedio",
    "contenido": "Módulo formativo de nivel Intermedio para la dimensión 'Protección de Datos'. Cubre 2 control(es) de la matriz relacionados con las brechas detectadas en esta dimensión durante el autodiagnóstico. (Contenido de ejemplo para la versión estática de demostración.)",
    "controles": [
      "DAT-004",
      "DAT-007"
    ]
  },
  {
    "id": 9,
    "dimension": "Protección de Datos",
    "nivel": "Avanzado",
    "titulo": "Protección de Datos — Nivel Avanzado",
    "contenido": "Módulo formativo de nivel Avanzado para la dimensión 'Protección de Datos'. Cubre 2 control(es) de la matriz relacionados con las brechas detectadas en esta dimensión durante el autodiagnóstico. (Contenido de ejemplo para la versión estática de demostración.)",
    "controles": [
      "DAT-008",
      "DAT-009"
    ]
  },
  {
    "id": 10,
    "dimension": "Uso Responsable",
    "nivel": "Inicial",
    "titulo": "Uso Responsable — Nivel Inicial",
    "contenido": "Módulo formativo de nivel Inicial para la dimensión 'Uso Responsable'. Cubre 2 control(es) de la matriz relacionados con las brechas detectadas en esta dimensión durante el autodiagnóstico. (Contenido de ejemplo para la versión estática de demostración.)",
    "controles": [
      "SEG-009",
      "SEG-010"
    ]
  },
  {
    "id": 11,
    "dimension": "Uso Responsable",
    "nivel": "Intermedio",
    "titulo": "Uso Responsable — Nivel Intermedio",
    "contenido": "Módulo formativo de nivel Intermedio para la dimensión 'Uso Responsable'. Cubre 3 control(es) de la matriz relacionados con las brechas detectadas en esta dimensión durante el autodiagnóstico. (Contenido de ejemplo para la versión estática de demostración.)",
    "controles": [
      "SEG-005",
      "SEG-006",
      "SEG-008"
    ]
  },
  {
    "id": 12,
    "dimension": "Uso Responsable",
    "nivel": "Avanzado",
    "titulo": "Uso Responsable — Nivel Avanzado",
    "contenido": "Módulo formativo de nivel Avanzado para la dimensión 'Uso Responsable'. Cubre 5 control(es) de la matriz relacionados con las brechas detectadas en esta dimensión durante el autodiagnóstico. (Contenido de ejemplo para la versión estática de demostración.)",
    "controles": [
      "SEG-001",
      "SEG-002",
      "SEG-003",
      "SEG-004",
      "SEG-007"
    ]
  }
],
  EVALUACIONES_PRECARGADAS: [
  {
    "control_id": "DAT-001",
    "estado": "cumplido",
    "evidencia_texto": "Evidencia de ejemplo (modo demo): documento PDF cargado que respalda el control DAT-001 dentro de la dimensión 'Protección de Datos'."
  },
  {
    "control_id": "DAT-002",
    "estado": "parcial",
    "evidencia_texto": "Evidencia de ejemplo (modo demo): documento PDF cargado que respalda el control DAT-002 dentro de la dimensión 'Protección de Datos'."
  },
  {
    "control_id": "DAT-003",
    "estado": "no",
    "evidencia_texto": null
  },
  {
    "control_id": "DAT-004",
    "estado": "revision",
    "evidencia_texto": null
  },
  {
    "control_id": "DAT-005",
    "estado": "cumplido",
    "evidencia_texto": "Evidencia de ejemplo (modo demo): documento PDF cargado que respalda el control DAT-005 dentro de la dimensión 'Protección de Datos'."
  },
  {
    "control_id": "DAT-006",
    "estado": "parcial",
    "evidencia_texto": "Evidencia de ejemplo (modo demo): documento PDF cargado que respalda el control DAT-006 dentro de la dimensión 'Protección de Datos'."
  },
  {
    "control_id": "DAT-007",
    "estado": "no",
    "evidencia_texto": null
  },
  {
    "control_id": "DAT-008",
    "estado": "revision",
    "evidencia_texto": null
  },
  {
    "control_id": "DAT-009",
    "estado": "cumplido",
    "evidencia_texto": "Evidencia de ejemplo (modo demo): documento PDF cargado que respalda el control DAT-009 dentro de la dimensión 'Protección de Datos'."
  },
  {
    "control_id": "DAT-010",
    "estado": "parcial",
    "evidencia_texto": "Evidencia de ejemplo (modo demo): documento PDF cargado que respalda el control DAT-010 dentro de la dimensión 'Protección de Datos'."
  },
  {
    "control_id": "GOB-001",
    "estado": "no",
    "evidencia_texto": null
  },
  {
    "control_id": "GOB-002",
    "estado": "revision",
    "evidencia_texto": null
  },
  {
    "control_id": "GOB-003",
    "estado": "cumplido",
    "evidencia_texto": "Evidencia de ejemplo (modo demo): documento PDF cargado que respalda el control GOB-003 dentro de la dimensión 'Gobernanza de IA'."
  },
  {
    "control_id": "GOB-004",
    "estado": "parcial",
    "evidencia_texto": "Evidencia de ejemplo (modo demo): documento PDF cargado que respalda el control GOB-004 dentro de la dimensión 'Gobernanza de IA'."
  },
  {
    "control_id": "GOB-005",
    "estado": "no",
    "evidencia_texto": null
  },
  {
    "control_id": "GOB-006",
    "estado": "revision",
    "evidencia_texto": null
  },
  {
    "control_id": "GOB-007",
    "estado": "cumplido",
    "evidencia_texto": "Evidencia de ejemplo (modo demo): documento PDF cargado que respalda el control GOB-007 dentro de la dimensión 'Gobernanza de IA'."
  },
  {
    "control_id": "GOB-008",
    "estado": "parcial",
    "evidencia_texto": "Evidencia de ejemplo (modo demo): documento PDF cargado que respalda el control GOB-008 dentro de la dimensión 'Gobernanza de IA'."
  },
  {
    "control_id": "GOB-009",
    "estado": "no",
    "evidencia_texto": null
  },
  {
    "control_id": "GOB-010",
    "estado": "revision",
    "evidencia_texto": null
  },
  {
    "control_id": "RIE-001",
    "estado": "cumplido",
    "evidencia_texto": "Evidencia de ejemplo (modo demo): documento PDF cargado que respalda el control RIE-001 dentro de la dimensión 'Gestión de Riesgos'."
  },
  {
    "control_id": "RIE-002",
    "estado": "parcial",
    "evidencia_texto": "Evidencia de ejemplo (modo demo): documento PDF cargado que respalda el control RIE-002 dentro de la dimensión 'Gestión de Riesgos'."
  },
  {
    "control_id": "RIE-003",
    "estado": "no",
    "evidencia_texto": null
  },
  {
    "control_id": "RIE-004",
    "estado": "revision",
    "evidencia_texto": null
  },
  {
    "control_id": "RIE-005",
    "estado": "cumplido",
    "evidencia_texto": "Evidencia de ejemplo (modo demo): documento PDF cargado que respalda el control RIE-005 dentro de la dimensión 'Gestión de Riesgos'."
  },
  {
    "control_id": "RIE-006",
    "estado": "parcial",
    "evidencia_texto": "Evidencia de ejemplo (modo demo): documento PDF cargado que respalda el control RIE-006 dentro de la dimensión 'Gestión de Riesgos'."
  },
  {
    "control_id": "RIE-007",
    "estado": "no",
    "evidencia_texto": null
  },
  {
    "control_id": "RIE-008",
    "estado": "revision",
    "evidencia_texto": null
  },
  {
    "control_id": "RIE-009",
    "estado": "cumplido",
    "evidencia_texto": "Evidencia de ejemplo (modo demo): documento PDF cargado que respalda el control RIE-009 dentro de la dimensión 'Gestión de Riesgos'."
  },
  {
    "control_id": "RIE-010",
    "estado": "parcial",
    "evidencia_texto": "Evidencia de ejemplo (modo demo): documento PDF cargado que respalda el control RIE-010 dentro de la dimensión 'Gestión de Riesgos'."
  },
  {
    "control_id": "SEG-001",
    "estado": "no",
    "evidencia_texto": null
  },
  {
    "control_id": "SEG-002",
    "estado": "revision",
    "evidencia_texto": null
  },
  {
    "control_id": "SEG-003",
    "estado": "cumplido",
    "evidencia_texto": "Evidencia de ejemplo (modo demo): documento PDF cargado que respalda el control SEG-003 dentro de la dimensión 'Uso Responsable'."
  },
  {
    "control_id": "SEG-004",
    "estado": "parcial",
    "evidencia_texto": "Evidencia de ejemplo (modo demo): documento PDF cargado que respalda el control SEG-004 dentro de la dimensión 'Uso Responsable'."
  },
  {
    "control_id": "SEG-005",
    "estado": "no",
    "evidencia_texto": null
  },
  {
    "control_id": "SEG-006",
    "estado": "revision",
    "evidencia_texto": null
  },
  {
    "control_id": "SEG-007",
    "estado": "cumplido",
    "evidencia_texto": "Evidencia de ejemplo (modo demo): documento PDF cargado que respalda el control SEG-007 dentro de la dimensión 'Protección de Datos'."
  },
  {
    "control_id": "SEG-008",
    "estado": "parcial",
    "evidencia_texto": "Evidencia de ejemplo (modo demo): documento PDF cargado que respalda el control SEG-008 dentro de la dimensión 'Protección de Datos'."
  },
  {
    "control_id": "SEG-009",
    "estado": "no",
    "evidencia_texto": null
  },
  {
    "control_id": "SEG-010",
    "estado": "revision",
    "evidencia_texto": null
  }
],
  PANEL_SECTORIAL: [
  {
    "dimension": "Gobernanza de IA",
    "rubro_id": "manufactura",
    "promedio": 62.5,
    "n_organizaciones": 14
  },
  {
    "dimension": "Gestión de Riesgos",
    "rubro_id": "manufactura",
    "promedio": 48.0,
    "n_organizaciones": 14
  },
  {
    "dimension": "Protección de Datos",
    "rubro_id": "manufactura",
    "promedio": 70.0,
    "n_organizaciones": 14
  },
  {
    "dimension": "Uso Responsable",
    "rubro_id": "manufactura",
    "promedio": 55.5,
    "n_organizaciones": 14
  },
  {
    "dimension": "Gobernanza de IA",
    "rubro_id": "retail",
    "promedio": 58.0,
    "n_organizaciones": 9
  },
  {
    "dimension": "Gestión de Riesgos",
    "rubro_id": "retail",
    "promedio": 41.5,
    "n_organizaciones": 9
  },
  {
    "dimension": "Protección de Datos",
    "rubro_id": "retail",
    "promedio": 66.0,
    "n_organizaciones": 9
  },
  {
    "dimension": "Uso Responsable",
    "rubro_id": "retail",
    "promedio": 50.0,
    "n_organizaciones": 9
  },
  {
    "dimension": "Gobernanza de IA",
    "rubro_id": "servicios_financieros",
    "promedio": 81.0,
    "n_organizaciones": 22
  },
  {
    "dimension": "Gestión de Riesgos",
    "rubro_id": "servicios_financieros",
    "promedio": 76.5,
    "n_organizaciones": 22
  },
  {
    "dimension": "Protección de Datos",
    "rubro_id": "servicios_financieros",
    "promedio": 88.0,
    "n_organizaciones": 22
  },
  {
    "dimension": "Uso Responsable",
    "rubro_id": "servicios_financieros",
    "promedio": 79.0,
    "n_organizaciones": 22
  },
  {
    "dimension": "Gobernanza de IA",
    "rubro_id": "tecnologia",
    "promedio": 69.5,
    "n_organizaciones": 11
  },
  {
    "dimension": "Gestión de Riesgos",
    "rubro_id": "tecnologia",
    "promedio": 52.0,
    "n_organizaciones": 11
  },
  {
    "dimension": "Protección de Datos",
    "rubro_id": "tecnologia",
    "promedio": 74.0,
    "n_organizaciones": 11
  },
  {
    "dimension": "Uso Responsable",
    "rubro_id": "tecnologia",
    "promedio": 60.5,
    "n_organizaciones": 11
  }
]
};

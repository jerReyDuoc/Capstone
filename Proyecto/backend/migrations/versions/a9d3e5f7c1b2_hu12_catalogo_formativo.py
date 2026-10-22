"""HU-12: catálogo formativo con dimensión, nivel y objetivos

La tabla ruta_formativa solo tenía el nombre ("Protección de Datos - Inicial"…). Para
recomendar planes de estudio por dimensión normativa y nivel, cada ruta suma:

  dominio_id             dimensión normativa (FK dominio)
  nivel                  Inicial | Intermedio | Avanzado
  objetivo               objetivo general del módulo
  objetivos_especificos  uno por línea
  contenidos             uno por línea
  horas, modalidad, publico_objetivo

Las 12 rutas de la semilla (2e398c9a9b2e) se completan por nombre. Si una ruta no está,
no se crea: el plan formativo deduce dimensión y nivel del nombre (analisis.py).

Revision ID: a9d3e5f7c1b2
Revises: e2b7c9d4f8a1
Create Date: 2026-10-22 15:30:00

Si tu head no es e2b7c9d4f8a1 (`alembic heads`), cambia down_revision por el tuyo.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a9d3e5f7c1b2'
down_revision: Union[str, None] = 'e2b7c9d4f8a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (nombre, dominio, nivel, horas, modalidad, público, objetivo, [objetivos], [contenidos])
CATALOGO = [
    # ------------------------------------------------------------ Protección de Datos
    ("Protección de Datos - Inicial", "Protección de Datos", "Inicial", 4, "E-learning autoguiado",
     "Todo el personal que usa herramientas de IA",
     "Reconocer qué es un dato personal y qué exige la Ley 21.719 antes de ingresar información a una herramienta de IA.",
     ["Identificar datos personales y datos sensibles en el trabajo diario.",
      "Explicar las bases de licitud y cuándo se necesita consentimiento.",
      "Aplicar la regla de minimización antes de usar una IA."],
     ["Conceptos clave de la Ley 21.719: titular, responsable y encargado",
      "Datos sensibles, de menores y biométricos",
      "Consentimiento, finalidad y minimización",
      "Avisos de privacidad en servicios con IA"]),
    ("Protección de Datos - Intermedio", "Protección de Datos", "Intermedio", 8, "Taller práctico",
     "Encargados de área, TI y equipos que contratan o integran IA",
     "Operar los procesos de protección de datos que rodean a la IA: derechos ARCOP, contratos con proveedores y registro de actividades.",
     ["Gestionar solicitudes ARCOP dentro de los plazos legales.",
      "Revisar un acuerdo de tratamiento de datos (DPA) con un proveedor de IA.",
      "Mantener el registro de actividades de tratamiento (RAT) al día."],
     ["Derechos de acceso, rectificación, supresión, oposición, portabilidad y bloqueo",
      "Plazos de respuesta y evidencia de cumplimiento",
      "Encargados de tratamiento y cláusulas mínimas del DPA",
      "Inventario de herramientas de IA en el RAT"]),
    ("Protección de Datos - Avanzado", "Protección de Datos", "Avanzado", 12, "Taller con casos",
     "DPO, cumplimiento, seguridad de la información y arquitectura",
     "Diseñar tratamientos de alto riesgo con IA cumpliendo privacidad desde el diseño, transferencias internacionales y cifrado reforzado.",
     ["Aplicar privacidad desde el diseño y por defecto en un proyecto de IA.",
      "Evaluar transferencias internacionales y sus garantías.",
      "Definir controles técnicos para datos sensibles (cifrado, seudonimización, DLP)."],
     ["Privacidad desde el diseño en el ciclo de vida del modelo",
      "Transferencias internacionales y cláusulas tipo",
      "Seudonimización, anonimización y cifrado",
      "Gestión de brechas de seguridad y notificación a la Agencia"]),
    # ------------------------------------------------------------ Gobernanza de IA
    ("Gobernanza de IA - Inicial", "Gobernanza de IA", "Inicial", 3, "E-learning autoguiado",
     "Todo el personal",
     "Conocer la política corporativa de IA y los usos permitidos y prohibidos, incluido el uso de herramientas no autorizadas (shadow AI).",
     ["Distinguir herramientas de IA aprobadas de las no autorizadas.",
      "Explicar qué información nunca se ingresa a una IA pública.",
      "Saber a quién reportar un uso dudoso."],
     ["Política corporativa de IA y roles responsables",
      "Shadow AI: riesgos y cómo evitarla",
      "Información confidencial y código fuente en IA generativa",
      "Canal de consultas y reporte"]),
    ("Gobernanza de IA - Intermedio", "Gobernanza de IA", "Intermedio", 8, "Taller práctico",
     "Líderes de proyecto, compras, TI y desarrollo",
     "Integrar la gobernanza en la adquisición y el desarrollo de sistemas de IA: justificación de negocio, homologación de proveedores y SDLC seguro.",
     ["Aplicar el checklist de homologación a un proveedor de IA.",
      "Documentar la justificación y el análisis de riesgo de una compra de IA.",
      "Incorporar controles de gobernanza en el ciclo de desarrollo."],
     ["Comité de IA, responsables y supervisión humana",
      "Homologación de proveedores y contratos",
      "Ciclo de vida seguro de sistemas de IA (SDLC)",
      "Inventario y clasificación de sistemas de IA"]),
    ("Gobernanza de IA - Avanzado", "Gobernanza de IA", "Avanzado", 10, "Taller con casos",
     "Alta dirección, comité de IA y auditoría interna",
     "Dirigir la gobernanza de IA con indicadores, reporte a la alta dirección y gestión de incidentes como alucinaciones sistemáticas.",
     ["Definir indicadores de desempeño y riesgo de la IA.",
      "Preparar el informe anual de riesgos de IA para el directorio.",
      "Gestionar incidentes y correcciones de modelos en producción."],
     ["Marcos de referencia (ISO/IEC 42001, NIST AI RMF)",
      "Indicadores y tablero de gobernanza",
      "Reporte a la alta dirección",
      "Gestión de incidentes y mejora continua"]),
    # ------------------------------------------------------------ Gestión de Riesgos
    ("Gestión de Riesgos - Inicial", "Gestión de Riesgos", "Inicial", 4, "E-learning autoguiado",
     "Equipos que operan o usan modelos de IA",
     "Identificar los riesgos básicos de un sistema de IA y registrarlos en la matriz de riesgos antes de operarlo.",
     ["Reconocer amenazas típicas de la IA (sesgo, filtración, error, abuso).",
      "Registrar un riesgo en la matriz con su dueño.",
      "Distinguir cuándo un riesgo requiere escalamiento."],
     ["Tipos de riesgo en IA",
      "Matriz de riesgos: probabilidad, impacto y dueño",
      "Criterios de escalamiento",
      "Rol de cada persona en la gestión de riesgos"]),
    ("Gestión de Riesgos - Intermedio", "Gestión de Riesgos", "Intermedio", 8, "Taller práctico",
     "Riesgo, cumplimiento, TI y dueños de proceso",
     "Evaluar y mitigar riesgos de IA: EIPD, verificación de resultados, planes de mitigación y respuesta a incidentes de datos.",
     ["Ejecutar una evaluación de impacto en protección de datos (EIPD).",
      "Diseñar un plan de mitigación para un riesgo crítico.",
      "Aplicar el protocolo de reporte de incidentes."],
     ["Evaluación de impacto (EIPD) paso a paso",
      "Verificación humana de salidas de IA",
      "Planes de mitigación y seguimiento",
      "Respuesta a incidentes y filtraciones"]),
    ("Gestión de Riesgos - Avanzado", "Gestión de Riesgos", "Avanzado", 12, "Taller con casos",
     "Ciencia de datos, riesgo y auditoría",
     "Monitorear modelos en producción y gestionar riesgos complejos: sesgo, degradación y decisiones automatizadas.",
     ["Medir sesgo y equidad en un modelo.",
      "Definir el monitoreo de degradación (drift) con umbrales.",
      "Auditar decisiones automatizadas con impacto en personas."],
     ["Métricas de sesgo y equidad",
      "Monitoreo continuo y degradación del modelo",
      "Decisiones automatizadas y explicabilidad",
      "Auditoría de modelos"]),
    # ------------------------------------------------------------ Uso Responsable
    ("Uso Responsable - Inicial", "Uso Responsable", "Inicial", 3, "E-learning autoguiado",
     "Todo el personal",
     "Usar la IA de forma responsable en el día a día: transparencia, verificación y respeto por las personas.",
     ["Informar cuándo un contenido o atención fue generado con IA.",
      "Verificar la información antes de usarla.",
      "Reconocer usos que pueden discriminar o engañar."],
     ["Principios de uso ético de la IA",
      "Transparencia con clientes y colegas",
      "Verificación de contenidos generados",
      "Casos de uso permitidos y no permitidos"]),
    ("Uso Responsable - Intermedio", "Uso Responsable", "Intermedio", 6, "Taller práctico",
     "Equipos que diseñan servicios o contenidos con IA",
     "Diseñar servicios con IA que respeten la supervisión humana, la explicabilidad y la inclusión.",
     ["Incorporar supervisión humana en un flujo con IA.",
      "Redactar avisos de uso de IA claros para el usuario.",
      "Evaluar la accesibilidad e inclusión de un servicio con IA."],
     ["Supervisión humana significativa",
      "Explicabilidad para usuarios no técnicos",
      "Diseño inclusivo y accesible",
      "Gestión de reclamos sobre IA"]),
    ("Uso Responsable - Avanzado", "Uso Responsable", "Avanzado", 8, "Taller con casos",
     "Comité de ética, producto y alta dirección",
     "Liderar una cultura de IA responsable con evaluación ética de casos complejos y rendición de cuentas.",
     ["Conducir una evaluación ética de un caso de uso de alto impacto.",
      "Definir criterios de rendición de cuentas.",
      "Medir la adopción responsable en la organización."],
     ["Evaluación ética de casos de alto impacto",
      "Rendición de cuentas y comunicación pública",
      "Cultura organizacional y formación continua",
      "Indicadores de uso responsable"]),
]

_COLUMNAS = [
    sa.Column("dominio_id", sa.Integer(), sa.ForeignKey("dominio.id"), nullable=True),
    sa.Column("nivel", sa.String(15), nullable=True),
    sa.Column("objetivo", sa.Text(), nullable=True),
    sa.Column("objetivos_especificos", sa.Text(), nullable=True),
    sa.Column("contenidos", sa.Text(), nullable=True),
    sa.Column("horas", sa.Integer(), nullable=True),
    sa.Column("modalidad", sa.String(50), nullable=True),
    sa.Column("publico_objetivo", sa.String(150), nullable=True),
]


def upgrade() -> None:
    for columna in _COLUMNAS:
        op.add_column("ruta_formativa", columna)

    conn = op.get_bind()
    for nombre, dominio, nivel, horas, modalidad, publico, objetivo, objetivos, contenidos in CATALOGO:
        conn.execute(
            sa.text(
                "UPDATE ruta_formativa SET "
                "dominio_id = (SELECT id FROM dominio WHERE nombre_dominio = :dominio LIMIT 1), "
                "nivel = :nivel, objetivo = :objetivo, objetivos_especificos = :objetivos, "
                "contenidos = :contenidos, horas = :horas, modalidad = :modalidad, "
                "publico_objetivo = :publico "
                "WHERE nombre = :nombre"
            ),
            {
                "dominio": dominio, "nivel": nivel, "objetivo": objetivo,
                "objetivos": "\n".join(objetivos), "contenidos": "\n".join(contenidos),
                "horas": horas, "modalidad": modalidad, "publico": publico, "nombre": nombre,
            },
        )


def downgrade() -> None:
    for columna in reversed(_COLUMNAS):
        op.drop_column("ruta_formativa", columna.name)

"""HU-26 y HU-17: recorrido de módulos formativos, avance de la empresa y remediación

HU-26 (registrar el avance de los módulos formativos):
  - leccion_formativa       lecciones de cada ruta del catálogo, en orden. Se crean a partir
                            de `ruta_formativa.contenidos` (una lección por línea) con texto y
                            material de apoyo PLACEHOLDER (decisión del PO del 26-oct).
  - pregunta_verificacion   actividad de verificación del final de cada ruta (3 preguntas de
                            selección única por ruta de la semilla; la correcta no sale por la API).
  - avance_formativo        avance de la EMPRESA en cada módulo (en curso / completado, lecciones
                            vistas, intentos, puntaje, fecha y código de la constancia).

HU-17 (re-evaluar un control con evidencia nueva):
  - evidencias.origen                    cuestionario | remediacion
  - evidencias.estado_declarado          estado que la empresa dice haber alcanzado
  - evidencias.justificacion_remediacion su justificación, ya anonimizada (HU-06)
  - evidencias.estado_previo / estado_resultante   antes y después de procesarla
  - evidencias.terminos_control          términos del control encontrados en el texto

Si tu head no es f3a8d1c6e4b2 (`alembic heads`), cambia down_revision por el tuyo.

Revision ID: d6e1a4c8f2b5
Revises: f3a8d1c6e4b2
Create Date: 2026-10-27 23:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd6e1a4c8f2b5'
down_revision: Union[str, None] = 'f3a8d1c6e4b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Material de apoyo de cada lección: placeholders hasta que Therion Labs cargue el real.
MATERIAL_PLACEHOLDER = [
    {"tipo": "guia", "titulo": "Guía de la lección (PDF)",
     "descripcion": "Resumen descargable con los conceptos y ejemplos de la lección."},
    {"tipo": "video", "titulo": "Video explicativo",
     "descripcion": "Cápsula de 5 a 8 minutos con un caso práctico."},
    {"tipo": "plantilla", "titulo": "Plantilla de trabajo",
     "descripcion": "Formato editable para aplicar la lección en tu organización."},
]

# Actividad de verificación: (enunciado, [opciones], índice correcto, explicación)
PREGUNTAS = {
    "Protección de Datos - Inicial": [
        ("¿Cuál de estos datos es un dato personal sensible?",
         ["El cargo de una persona en la empresa", "Un diagnóstico de salud de un trabajador",
          "El RUT de la empresa", "El nombre de un producto"], 1,
         "Los datos de salud son sensibles: exigen una base de licitud reforzada y más resguardo."),
        ("Antes de pegar información en una herramienta de IA, ¿qué exige el principio de minimización?",
         ["Usar solo los datos necesarios para la finalidad", "Copiar toda la ficha para dar contexto",
          "Pedir permiso al proveedor de la IA", "Cifrar el archivo antes de pegarlo"], 0,
         "Minimizar es tratar solo los datos indispensables para la finalidad declarada."),
        ("¿Quién es el titular de los datos personales?",
         ["La empresa que los almacena", "El proveedor de la nube",
          "La persona natural a quien se refieren", "La Agencia de Protección de Datos"], 2,
         "El titular es la persona a quien se refieren los datos; responsable y encargado los tratan."),
    ],
    "Protección de Datos - Intermedio": [
        ("Un cliente pide saber qué datos suyos usa el chatbot de la empresa. ¿Qué derecho ejerce?",
         ["Portabilidad", "Acceso", "Oposición", "Bloqueo"], 1,
         "El derecho de acceso permite conocer qué datos se tratan, con qué finalidad y origen."),
        ("¿Qué debe incluir el contrato con un proveedor de IA que trata datos por cuenta de la empresa?",
         ["Solo el precio y el plazo", "Las instrucciones, la finalidad y las medidas de seguridad del tratamiento",
          "Una cláusula de exclusividad", "La lista de empleados que usan la herramienta"], 1,
         "El encargado solo puede tratar los datos según las instrucciones y con las medidas pactadas."),
        ("¿Para qué sirve el registro de actividades de tratamiento (RAT)?",
         ["Para medir la productividad del equipo", "Para documentar qué datos se tratan, para qué y con qué herramientas",
          "Para guardar las contraseñas de los sistemas", "Para publicar la política de cookies"], 1,
         "El RAT permite demostrar el cumplimiento: qué se trata, con qué finalidad, base y sistemas."),
    ],
    "Protección de Datos - Avanzado": [
        ("Privacidad desde el diseño significa…",
         ["Revisar la privacidad cuando el sistema ya está en producción",
          "Incorporar las medidas de protección desde la concepción del proyecto",
          "Delegar la privacidad en el proveedor", "Agregar un aviso legal al final"], 1,
         "Las medidas se definen desde el diseño y quedan activas por defecto."),
        ("¿Qué técnica reduce el riesgo de reidentificar a las personas en un conjunto de entrenamiento?",
         ["Duplicar los registros", "Seudonimizar o anonimizar los identificadores",
          "Guardar los datos en una planilla compartida", "Aumentar el tamaño del modelo"], 1,
         "La seudonimización y la anonimización disminuyen la exposición de los titulares."),
        ("Ante una brecha de seguridad con datos personales, lo primero es…",
         ["Esperar a que el proveedor la detecte", "Contenerla, evaluar el riesgo y activar el protocolo de notificación",
          "Borrar los registros de acceso", "Informar solo si un cliente reclama"], 1,
         "El protocolo exige contener, evaluar y notificar cuando corresponde."),
    ],
    "Gobernanza de IA - Inicial": [
        ("¿Qué es la shadow AI?",
         ["Una IA que funciona sin conexión", "El uso de herramientas de IA no autorizadas por la organización",
          "Un modelo de IA de código abierto", "Una auditoría secreta de IA"], 1,
         "Shadow AI es usar herramientas de IA fuera de las aprobadas y de su control."),
        ("¿Qué información nunca debe ingresarse a una IA pública?",
         ["Una pregunta general sobre la Ley 21.719", "Información confidencial o código fuente de la empresa",
          "Un texto ya publicado en la web de la empresa", "Una fórmula de planilla genérica"], 1,
         "La información confidencial puede quedar fuera del control de la empresa."),
        ("Si tienes dudas sobre si un uso de IA está permitido, debes…",
         ["Usarla igual y preguntar después", "Consultar en el canal definido por la política de IA",
          "Pedir a un colega que la use por ti", "Desactivar el antivirus"], 1,
         "La política define responsables y un canal de consultas y reporte."),
    ],
    "Gobernanza de IA - Intermedio": [
        ("¿Qué revisa la homologación de un proveedor de IA?",
         ["Solo su precio", "Seguridad, tratamiento de datos, contratos y riesgos del servicio",
          "La cantidad de seguidores en redes", "El color de su interfaz"], 1,
         "Homologar es verificar que el proveedor cumple los requisitos antes de contratarlo."),
        ("¿Por qué mantener un inventario de sistemas de IA?",
         ["Para saber qué sistemas existen, quién responde por ellos y su nivel de riesgo",
          "Para reemplazar el registro de proveedores", "Para calcular sueldos", "No es necesario"], 0,
         "Sin inventario no se puede gobernar ni clasificar el riesgo de cada sistema."),
        ("La supervisión humana en un sistema de IA busca…",
         ["Que una persona pueda entender, corregir o detener sus decisiones",
          "Que una persona vigile a los usuarios", "Reemplazar la IA por personas", "Aumentar la velocidad del modelo"], 0,
         "Supervisar es poder intervenir en las decisiones del sistema cuando hace falta."),
    ],
    "Gobernanza de IA - Avanzado": [
        ("¿Qué marco de referencia se enfoca en sistemas de gestión de IA?",
         ["ISO/IEC 42001", "ISO 9001 para alimentos", "PCI DSS", "ITIL v2"], 0,
         "ISO/IEC 42001 define requisitos para un sistema de gestión de la IA."),
        ("Un buen indicador de gobernanza de IA es…",
         ["El número de reuniones del comité", "El porcentaje de sistemas de IA con evaluación de riesgo vigente",
          "La cantidad de licencias compradas", "El tamaño del equipo de TI"], 1,
         "Los indicadores deben medir el control efectivo del riesgo, no la actividad."),
        ("Ante alucinaciones sistemáticas de un modelo en producción, se debe…",
         ["Ignorarlas si son pocas", "Gestionarlas como incidente: registrar, corregir y comunicar",
          "Apagar todos los sistemas de la empresa", "Cambiar el nombre del modelo"], 1,
         "La gestión de incidentes incluye registro, corrección del modelo y mejora continua."),
    ],
    "Gestión de Riesgos - Inicial": [
        ("¿Cuál es un riesgo típico de un sistema de IA?",
         ["Sesgo en sus resultados", "Que tenga una interfaz oscura", "Que use poca memoria", "Que tenga un nombre largo"], 0,
         "Sesgo, filtración de datos, error y abuso son riesgos típicos de la IA."),
        ("Al registrar un riesgo en la matriz, ¿qué no puede faltar?",
         ["Su dueño, probabilidad e impacto", "El nombre del proveedor del correo", "Una foto del equipo", "El precio del sistema"], 0,
         "Cada riesgo necesita un responsable y una valoración para priorizarlo."),
        ("¿Cuándo se escala un riesgo?",
         ["Nunca", "Cuando supera el umbral definido por la organización", "Solo a fin de año", "Cuando lo pide un cliente"], 1,
         "Los criterios de escalamiento definen cuándo un riesgo sube a otro nivel de decisión."),
    ],
    "Gestión de Riesgos - Intermedio": [
        ("¿Cuándo se necesita una evaluación de impacto en protección de datos (EIPD)?",
         ["Para cualquier planilla", "Cuando el tratamiento puede implicar un alto riesgo para los titulares",
          "Solo si lo pide el proveedor", "Al cambiar de computador"], 1,
         "La EIPD se exige ante tratamientos de alto riesgo, como decisiones automatizadas a gran escala."),
        ("Verificar humanamente la salida de una IA sirve para…",
         ["Detectar errores antes de que afecten a personas o decisiones", "Aumentar el costo", "Evitar documentar", "Ocultar el uso de IA"], 0,
         "La verificación humana reduce el impacto de errores y alucinaciones."),
        ("Un plan de mitigación debe tener…",
         ["Acciones, responsables y plazos medibles", "Solo una declaración de intenciones", "Un logo", "La firma de un cliente"], 0,
         "Sin responsables ni plazos no hay forma de hacer seguimiento a la mitigación."),
    ],
    "Gestión de Riesgos - Avanzado": [
        ("¿Qué mide una métrica de equidad en un modelo?",
         ["La velocidad de respuesta", "Si los resultados difieren injustificadamente entre grupos",
          "El consumo de energía", "La cantidad de usuarios"], 1,
         "Las métricas de equidad comparan resultados entre grupos para detectar sesgo."),
        ("La degradación (drift) de un modelo se gestiona con…",
         ["Monitoreo continuo y umbrales que gatillan revisión", "Una revisión única al lanzarlo",
          "Más publicidad", "Cambiar la contraseña del servidor"], 0,
         "El monitoreo continuo detecta cuando el modelo deja de comportarse como se validó."),
        ("Auditar decisiones automatizadas con impacto en personas exige…",
         ["Poder explicarlas y revisar su trazabilidad", "Borrar los registros", "Confiar en el proveedor", "Nada especial"], 0,
         "La explicabilidad y la trazabilidad permiten revisar y corregir decisiones automatizadas."),
    ],
    "Uso Responsable - Inicial": [
        ("Si un texto para clientes fue generado con IA, lo responsable es…",
         ["Informarlo cuando corresponda y revisarlo antes de enviarlo", "Ocultarlo siempre",
          "Enviarlo sin leer", "Firmarlo como si fuera de un experto"], 0,
         "Transparencia y verificación son la base del uso responsable."),
        ("Antes de usar un dato entregado por una IA debes…",
         ["Verificarlo con una fuente confiable", "Asumir que es correcto", "Compartirlo de inmediato", "Traducirlo"], 0,
         "Las IA generativas pueden equivocarse o inventar información."),
        ("¿Cuál es un uso no permitido de la IA?",
         ["Resumir un documento interno autorizado", "Generar contenido que discrimine o engañe a las personas",
          "Mejorar la redacción de un correo", "Buscar ideas para una presentación"], 1,
         "Los usos que discriminan o engañan contradicen los principios de uso ético."),
    ],
    "Uso Responsable - Intermedio": [
        ("Una supervisión humana significativa implica que la persona…",
         ["Solo aprueba lo que la IA propone", "Tiene información y autoridad para cambiar la decisión",
          "Revisa una vez al año", "No conoce el sistema"], 1,
         "Supervisar de verdad requiere poder entender y modificar la decisión."),
        ("Un buen aviso de uso de IA para el usuario es…",
         ["Claro, breve y dice qué hace la IA y cómo pedir ayuda humana", "Un texto legal extenso",
          "Una nota en letra pequeña al final", "Innecesario"], 0,
         "El aviso debe ser comprensible y ofrecer una vía de atención humana."),
        ("Diseñar un servicio con IA de forma inclusiva significa…",
         ["Considerar la accesibilidad y a usuarios con distintas necesidades", "Usar solo inglés",
          "Diseñar para el usuario promedio", "Agregar más colores"], 0,
         "La inclusión evita que el servicio excluya a personas con distintas capacidades."),
    ],
    "Uso Responsable - Avanzado": [
        ("Una evaluación ética de un caso de alto impacto revisa…",
         ["Beneficios, riesgos y afectados, con alternativas y salvaguardas", "Solo el retorno económico",
          "La opinión de un solo área", "El nombre del proyecto"], 0,
         "La evaluación ética pondera beneficios y riesgos para todos los afectados."),
        ("La rendición de cuentas en IA exige…",
         ["Responsables identificados y decisiones documentadas", "Que nadie sea responsable",
          "Culpar al proveedor", "Evitar los registros"], 0,
         "Sin responsables y documentación no se puede responder por las decisiones."),
        ("Un indicador de uso responsable de IA puede ser…",
         ["El porcentaje del personal formado en la política de IA", "La cantidad de prompts escritos",
          "La velocidad del internet", "El número de pantallas"], 0,
         "Medir la formación y adopción de la política muestra la cultura de uso responsable."),
    ],
}


def _contenido_placeholder(titulo: str, objetivo: str | None) -> str:
    parrafos = [
        f"Esta lección trabaja «{titulo}».",
        "Contenido en preparación por Therion Labs: aquí irá el desarrollo de la lección con "
        "ejemplos aplicados a empresas chilenas y a la Ley 21.719.",
    ]
    if objetivo:
        parrafos.append(f"Se conecta con el objetivo del módulo: {objetivo}")
    parrafos.append("Al terminar, revisa el material de apoyo y marca la lección como vista para seguir.")
    return "\n".join(parrafos)


def upgrade() -> None:
    op.create_table(
        'leccion_formativa',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ruta_formativa_id', sa.Integer(), sa.ForeignKey('ruta_formativa.id'), nullable=False),
        sa.Column('orden', sa.Integer(), nullable=False),
        sa.Column('titulo', sa.String(length=200), nullable=False),
        sa.Column('resumen', sa.Text(), nullable=True),
        sa.Column('contenido', sa.Text(), nullable=True),
        sa.Column('material_apoyo', sa.JSON(), nullable=True),
        sa.Column('duracion_min', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('ruta_formativa_id', 'orden', name='uq_leccion_ruta_orden'),
    )
    op.create_index('ix_leccion_formativa_ruta_formativa_id', 'leccion_formativa', ['ruta_formativa_id'])

    op.create_table(
        'pregunta_verificacion',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ruta_formativa_id', sa.Integer(), sa.ForeignKey('ruta_formativa.id'), nullable=False),
        sa.Column('orden', sa.Integer(), nullable=False),
        sa.Column('enunciado', sa.Text(), nullable=False),
        sa.Column('opciones', sa.JSON(), nullable=False),
        sa.Column('correcta', sa.Integer(), nullable=False),
        sa.Column('explicacion', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('ruta_formativa_id', 'orden', name='uq_pregunta_ruta_orden'),
    )
    op.create_index('ix_pregunta_verificacion_ruta_formativa_id', 'pregunta_verificacion', ['ruta_formativa_id'])

    op.create_table(
        'avance_formativo',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('empresa_id', sa.Integer(), sa.ForeignKey('empresa.id'), nullable=False),
        sa.Column('ruta_formativa_id', sa.Integer(), sa.ForeignKey('ruta_formativa.id'), nullable=False),
        sa.Column('evaluacion_id', sa.Integer(), sa.ForeignKey('evaluacion.id'), nullable=True),
        sa.Column('usuario_definitivo_id', sa.Integer(), sa.ForeignKey('usuario_definitivo.id'), nullable=True),
        sa.Column('estado', sa.String(length=15), nullable=False),
        sa.Column('lecciones_vistas', sa.JSON(), nullable=True),
        sa.Column('intentos', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('ultimo_puntaje', sa.Float(), nullable=True),
        sa.Column('mejor_puntaje', sa.Float(), nullable=True),
        sa.Column('fecha_inicio', sa.DateTime(), nullable=False),
        sa.Column('fecha_ultima_actividad', sa.DateTime(), nullable=False),
        sa.Column('fecha_completado', sa.DateTime(), nullable=True),
        sa.Column('codigo_constancia', sa.String(length=20), nullable=True),
        sa.CheckConstraint("estado IN ('en_curso', 'completado')", name='ck_avance_formativo_estado'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('empresa_id', 'ruta_formativa_id', name='uq_avance_empresa_ruta'),
        sa.UniqueConstraint('codigo_constancia'),
    )
    op.create_index('ix_avance_formativo_empresa_id', 'avance_formativo', ['empresa_id'])

    # HU-17: evidencias de remediación
    with op.batch_alter_table('evidencias') as t:
        t.add_column(sa.Column('origen', sa.String(length=15), nullable=False, server_default='cuestionario'))
        t.add_column(sa.Column('estado_declarado', sa.String(length=25), nullable=True))
        t.add_column(sa.Column('justificacion_remediacion', sa.Text(), nullable=True))
        t.add_column(sa.Column('estado_previo', sa.String(length=25), nullable=True))
        t.add_column(sa.Column('estado_resultante', sa.String(length=25), nullable=True))
        t.add_column(sa.Column('terminos_control', sa.JSON(), nullable=True))

    # ------------------------------------------------------------ contenido semilla
    conn = op.get_bind()
    lecciones = sa.table(
        'leccion_formativa', sa.column('ruta_formativa_id', sa.Integer), sa.column('orden', sa.Integer),
        sa.column('titulo', sa.String), sa.column('resumen', sa.Text), sa.column('contenido', sa.Text),
        sa.column('material_apoyo', sa.JSON), sa.column('duracion_min', sa.Integer),
    )
    preguntas = sa.table(
        'pregunta_verificacion', sa.column('ruta_formativa_id', sa.Integer), sa.column('orden', sa.Integer),
        sa.column('enunciado', sa.Text), sa.column('opciones', sa.JSON), sa.column('correcta', sa.Integer),
        sa.column('explicacion', sa.Text),
    )
    rutas = conn.execute(sa.text("SELECT id, nombre, objetivo, contenidos, horas FROM ruta_formativa")).fetchall()
    filas_l, filas_p = [], []
    for ruta_id, nombre, objetivo, contenidos, horas in rutas:
        titulos = [t.strip() for t in (contenidos or "").splitlines() if t.strip()]
        minutos = max(10, round((horas or 1) * 60 / max(1, len(titulos)))) if titulos else None
        for orden, titulo in enumerate(titulos, start=1):
            filas_l.append({
                "ruta_formativa_id": ruta_id, "orden": orden, "titulo": titulo[:200],
                "resumen": f"Lección {orden} de {len(titulos)} del módulo {nombre}.",
                "contenido": _contenido_placeholder(titulo, objetivo),
                "material_apoyo": MATERIAL_PLACEHOLDER, "duracion_min": minutos,
            })
        for orden, (enunciado, opciones, correcta, explicacion) in enumerate(PREGUNTAS.get(nombre, []), start=1):
            filas_p.append({
                "ruta_formativa_id": ruta_id, "orden": orden, "enunciado": enunciado,
                "opciones": opciones, "correcta": correcta, "explicacion": explicacion,
            })
    if filas_l:
        op.bulk_insert(lecciones, filas_l)
    if filas_p:
        op.bulk_insert(preguntas, filas_p)


def downgrade() -> None:
    with op.batch_alter_table('evidencias') as t:
        for columna in ('terminos_control', 'estado_resultante', 'estado_previo', 'justificacion_remediacion',
                        'estado_declarado', 'origen'):
            t.drop_column(columna)
    op.drop_index('ix_avance_formativo_empresa_id', table_name='avance_formativo')
    op.drop_table('avance_formativo')
    op.drop_index('ix_pregunta_verificacion_ruta_formativa_id', table_name='pregunta_verificacion')
    op.drop_table('pregunta_verificacion')
    op.drop_index('ix_leccion_formativa_ruta_formativa_id', table_name='leccion_formativa')
    op.drop_table('leccion_formativa')

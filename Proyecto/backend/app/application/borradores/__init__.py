"""
HU-16 · Borradores adaptados de documentos de cumplimiento.

Como Gestor de Riesgos e IA, quiero que el Agente IA genere borradores adaptados de
políticas, avisos y procedimientos normativos, para acelerar la creación de la
documentación legal e institucional requerida para mitigar las no-conformidades.

  plantillas.py   biblioteca de cláusulas (Ley N.º 21.719 e ISO/IEC 42001 / NIST AI RMF /
                  OWASP LLM) de las tres plantillas: Política de uso de LLM, Aviso de
                  privacidad y Evaluación de impacto (PIA/EIPD). Cada cláusula está atada a
                  una dimensión del modelo de madurez y a los controles de la matriz que ayuda
                  a cerrar. Datos puros, sin BD.
  generador.py    arma el Markdown del borrador a partir del contexto de la evaluación de la
                  empresa (brechas y puntajes por dimensión) y, si las hay, de las secciones
                  que adaptó el Agente IA (ya validadas). Lógica pura: se prueba sin BD.
  salida_ia.py    reglas deterministas sobre lo que devolvió el modelo (anclaje a las
                  cláusulas pedidas, artículos verificados, sin código ni enlaces).
  pdf_borrador.py Markdown -> PDF (reportlab), para la descarga previa y la consolidación.

El LLM nunca toca la BD ni ve la razón social, el RUT ni datos de contacto: recibe las
cláusulas base y datos de catálogo; la identidad de la empresa la escribe el backend.
"""

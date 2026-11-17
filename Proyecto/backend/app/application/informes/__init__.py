"""
Informes de la evaluación (HU-11 exportación, HU-12 plan formativo, informe por correo).

  analisis.py      lógica PURA (sin BD ni red): severidad, brechas priorizadas,
                   filtros y plan formativo. Se prueba sin SQLAlchemy.
  carga.py         lee de la BD y arma las entradas de analisis.py.
  ficha.py         HU-21: código de evaluación, versión de la matriz, 5 puntajes,
                   huella y aviso legal del informe (lógica pura).
  informe_evaluacion.py HU-21: armado único del informe (descarga, correo, archivo y ficha).
  datos_informe.py DTO y nombre del PDF del informe; el dibujo (reportlab) está en
                   infrastructure/documentos/pdf/informe_evaluacion.py.
  correo.py        validación/enmascarado de destinos y cuerpo del correo; el envío SMTP o .eml está en
                   infrastructure/correo/smtp.py (CorreoPort).
"""

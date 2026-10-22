"""
Informes de la evaluación (HU-11 exportación, HU-12 plan formativo, informe por correo).

  analisis.py      lógica PURA (sin BD ni red): severidad, brechas priorizadas,
                   filtros y plan formativo. Se prueba sin SQLAlchemy.
  carga.py         lee de la BD y arma las entradas de analisis.py.
  pdf_informe.py   arma el PDF del informe (reportlab).
  correo.py        envía el informe por SMTP o lo deja en un archivo .eml (desarrollo).
"""

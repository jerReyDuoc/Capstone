"""
HU-37 · Informe RoPA del registro de actividades de tratamiento.

  informe_ropa armado (lógica pura): toma las actividades VIGENTES del informe del registro
              (app/application/rat/armado_informe_rat.py) y traduce cada campo a los del RoPA, en dos partes según
              el rol marcado en cada actividad (como responsable / como encargado). También la huella, el
              código verificable, el aviso legal y la vista previa para el panel.
  PDF y XLSX: app/infrastructure/documentos (pdf/ropa_pdf.py con el motor pdf/motor.py, xlsx/ropa_xlsx.py), tras GeneradorDocumentosPort.
"""

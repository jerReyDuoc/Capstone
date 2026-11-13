"""
HU-37 · Informe RoPA del registro de actividades de tratamiento.

  informe     armado (lógica pura): toma las actividades VIGENTES del informe del registro
              (app/application/rat/informe.py) y traduce cada campo a los del RoPA, en dos partes según
              el rol marcado en cada actividad (como responsable / como encargado). También la huella, el
              código verificable, el aviso legal y la vista previa para el panel.
  pdf_ropa    PDF con el motor de informes (app/application/informes/motor_pdf.py).
  xlsx_ropa   la misma información en una planilla Excel.
"""

"""
HU-37 · Informe RoPA (registro de actividades de tratamiento en formato RoPA) desde el RAT.

  datos     los datos que el RoPA pide y el registro no tiene (contacto de la empresa, delegado de
            protección de datos y contacto de cada organización por cuenta de la cual la empresa actúa
            como encargada): validación, normalización y lo que falta para generar.

Sin dependencias de la base de datos ni de FastAPI: lo importan los casos de uso, la API y las pruebas.
El armado del informe (traducción de cada actividad a los campos del RoPA) vive en
app/application/ropa/informe.py, porque parte del informe del RAT (app/application/rat/informe.py).
"""

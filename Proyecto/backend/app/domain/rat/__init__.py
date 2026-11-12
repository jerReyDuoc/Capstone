"""
HU-35 · Registro de Actividades de Tratamiento (RAT) de la empresa cliente.

  catalogo     bases de licitud, medidas de seguridad, fuentes, plazos, estados y los textos de
               ayuda de cada campo (PROPUESTA pendiente de validación por asesoría legal).
  modelo       validación y normalización de lo que escribe la empresa.
  analisis     lo que la actividad toma del mapa de datos (HU-34) y la completitud.
  estados      borrador → en revisión → vigente → archivada (y las transiciones permitidas).
  versiones    instantánea, huella y diferencias de las versiones vigentes (inmutables).

Sin dependencias de la base de datos ni de FastAPI: lo importan los casos de uso, la API y las pruebas.
"""

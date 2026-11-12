"""
HU-39 · Asistente de IA que guía a la empresa para armar su mapa de datos, su RAT y sus informes.

  banco.py            entrevista guiada por áreas (preguntas fijas, en lenguaje simple)
  contexto.py         lo que ve el LLM: catálogos (confiables) y el mapa de la empresa (no confiable)
  documento.py        tipo de documento, control de densidad de datos personales y pasajes (HU-17)
  salida_ia.py        revisión de la salida del modelo (canario, fuga del prompt, código, enlaces: HU-18)
  anclaje.py          propuestas del modelo -> propuestas válidas contra los catálogos y el mapa
  inconsistencias.py  inconsistencias y riesgo calculados por el backend (no por el modelo)

Todo es lógica pura (sin BD ni LLM): el caso de uso es app/application/use_cases/asistente_rat.py.
"""

"""
HU-16 · Borradores adaptados de documentos de cumplimiento.

Como Gestor de Riesgos e IA, quiero que el Agente IA genere borradores adaptados de
políticas, avisos y procedimientos normativos, para acelerar la creación de la
documentación legal e institucional requerida para mitigar las no-conformidades.

  C1  Plantillas editables en Markdown/PDF: Política de uso de LLM, Aviso de privacidad y
      PIA/EIPD (app/application/borradores/plantillas_borrador.py). El borrador se guarda en Markdown
      y se descarga en Markdown o PDF.
  C2  Cláusulas ajustadas a la Ley N.º 21.719 y a las dimensiones del modelo: cada cláusula
      está atada a una dimensión y a los controles de la matriz; las que tratan una brecha
      abierta de la evaluación más reciente de la empresa llevan su "Medida prioritaria", su
      fundamento es el artículo real de la matriz y el Anexo A cruza el documento con los
      puntajes por dimensión. El Agente IA (skill "borrador" de LangGraph) adapta las
      cláusulas al rubro, a las brechas y a las instrucciones de la empresa.
  C3  Revisión, edición y descarga previa a la consolidación: el borrador queda EN REVISIÓN,
      se edita (con control de versión), se descarga en Markdown o PDF (con marca de agua
      "BORRADOR") y solo al CONSOLIDARLO queda de solo lectura y su PDF se guarda en
      "Mis documentos" (HU-29). Consolidar con campos [COMPLETAR: ...] pendientes exige
      confirmarlo.

Reglas:
  - Solo el usuario definitivo con contrato VIGENTE (la ruta usa empresa_con_servicio, HU-30).
  - El LLM no toca la BD ni ve la razón social, el RUT ni datos de contacto: recibe la
    plantilla, datos de catálogo y las instrucciones de la empresa, que pasan por el filtro
    del agente (HU-18: un ataque bloquea sin llamar al NER ni al LLM) y por el NER del gateway.
  - La salida del modelo se valida y se ancla (salida_borrador.py). Si el LLM falla, no está
    habilitado o se agotó la cuota, el borrador se arma igual con la plantilla y se avisa.
  - Cuota de borradores con IA por empresa y día (BORRADORES_IA_DIA_EMPRESA) + cuota global
    del LLM. Si el servicio de IA falla, la cuota se devuelve.
  - Todo queda en la bitácora inmutable (HU-09) sin el texto del borrador ni de las
    instrucciones (solo su huella HMAC).

HU-38 C2: la PIA se pre-llena con las actividades de alto riesgo del registro de actividades (o las que
elija la empresa) y el aviso de privacidad toma sus finalidades y bases de licitud
(app/application/borradores/registro_borrador.py). El registro se lee igual que el informe del RAT (versión
vigente de cada actividad) y nunca pasa por el LLM.
"""
from app.application.borradores.casos_uso.generar_borradores.casos import Borradores
from app.application.borradores.casos_uso.generar_borradores.comun import (
    AVISOS, MAX_PENDIENTES_LISTA, MENSAJE_BLOQUEO, MENSAJE_ETICA, MIME_MD, MIME_PDF, ZONA, BorradorError, _ahora, _iso,
    borrador_a_dict, logger,
)

__all__ = [
    "AVISOS", "Borradores", "BorradorError", "MAX_PENDIENTES_LISTA", "MENSAJE_BLOQUEO", "MENSAJE_ETICA", "MIME_MD",
    "MIME_PDF", "ZONA", "_ahora", "_iso", "borrador_a_dict", "logger",
]

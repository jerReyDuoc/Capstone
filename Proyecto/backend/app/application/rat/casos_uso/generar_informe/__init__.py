"""
HU-36 · Informe del Registro de Actividades de Tratamiento (RAT) de la empresa cliente.

Como Usuario Definitivo (cliente), quiero descargar el informe RAT de mi empresa, para presentarlo ante
la Agencia de Protección de Datos, el certificador de mi modelo de prevención de infracciones o mi
directorio.

  C1  PDF armado en el servidor desde la versión vigente del RAT, con el motor de informes de HU-21:
      portada, resumen (actividades, datos sensibles, transferencias internacionales, decisiones
      automatizadas), detalle por actividad y matriz de riesgos (base de HU-38).
      → app/application/rat/armado_informe_rat.py (armado) y infrastructure/documentos/pdf/rat_pdf.py (PDF).
  C2  Fecha, versión del RAT, código verificable y el aviso legal (la plataforma apoya, no reemplaza la
      asesoría legal). → rat_informe (versión y código) y AVISO_RAT.
  C3  También en XLSX (infrastructure/documentos/xlsx/rat_xlsx.py); ambos quedan en "Mis documentos" (documento_empresa, HU-29) y cada
      emisión, descarga, envío y verificación queda en el audit_log (HU-09).
  C4  Con actividades incompletas o en revisión, el informe sale como borrador con marca de agua y lo
      indica en la portada.

Emitir genera los dos formatos con el MISMO código. Si el registro no cambió desde la última emisión (misma
huella y mismo estado) y sus archivos siguen en "Mis documentos", se reutiliza esa emisión (no se llena
"Mis documentos" de copias iguales); con `forzar` se emite una nueva igual. Solo con contrato vigente.
"""
from app.application.rat.casos_uso.generar_informe.casos import InformeRatCasos
from app.application.rat.casos_uso.generar_informe.comun import (
    FORMATOS, MAX_HISTORIAL, InformeRatError, _ahora, _fecha_txt, _iso, _naive, marca_de_revision,
)

__all__ = [
    "FORMATOS", "MAX_HISTORIAL", "InformeRatCasos", "InformeRatError", "_ahora", "_fecha_txt", "_iso", "_naive",
    "marca_de_revision",
]

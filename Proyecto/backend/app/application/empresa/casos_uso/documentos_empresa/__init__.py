"""
HU-29 criterio 3 · "Mis documentos" de la empresa cliente.

Reúne en un solo lugar lo que la empresa tiene guardado en la plataforma:

  informes      informes PDF archivados (documento_empresa, tipo informe_pdf). Se archivan al
                completar una reevaluación (DOCUMENTOS_ARCHIVAR_AL_COMPLETAR) o cuando el
                usuario lo pide desde "Mis evaluaciones". Son una foto del informe al generarlo.
  borradores    borradores de cumplimiento de HU-16 (documento_empresa, tipo borrador). HU-16
                los guarda con guardar_documento() y aparecen aquí sin cambiar nada más.
  evidencias    las de sus evaluaciones (cuestionario y remediación). Tras la validación en el
                disco solo queda su texto ANONIMIZADO (HU-06): eso es lo que se descarga.
  constancias   las de los módulos formativos completados (HU-26).
  registro_actividades   HU-36: informes del Registro de Actividades de Tratamiento (PDF y XLSX de
                cada emisión, con su código verificable). Los guarda app/application/rat/casos_uso/generar_informe.py
                con guardar_documento().

Cada descarga y cada eliminación queda en la bitácora de auditoría (HU-09) con el tipo y
los ids, nunca con el contenido ni el nombre que subió el usuario.

Qué borra "eliminar":
  informe / borrador   la fila y el archivo cifrado.
  evidencia            el archivo y lo que se extrajo de él (datos_extraidos). Se conservan los
                       metadatos de la validación (clasificación, estados, puntajes) para que
                       el historial de madurez siga explicable: borrar un archivo no cambia
                       ningún puntaje (HU-26: el puntaje solo cambia con evidencia NUEVA).
  constancia           anula su código (ya no se descarga ni se puede verificar). El módulo
                       sigue completado: el avance formativo de la empresa no se pierde.
"""
from app.application.empresa.casos_uso.documentos_empresa.casos import DocumentosEmpresa
from app.application.empresa.casos_uso.documentos_empresa.comun import (
    NOMBRE_SEGURO, DocumentoError, _doc_dict,
)
from app.application.empresa.casos_uso.documentos_empresa.guardado_documentos import (
    archivar_informe, guardar_documento, tras_completar,
)

__all__ = [
    "NOMBRE_SEGURO", "DocumentoError", "DocumentosEmpresa", "_doc_dict", "archivar_informe",
    "guardar_documento", "tras_completar",
]

"""
HU-34 · Mapa de datos personales del cliente (base del RAT y del RoPA).

Como Usuario Definitivo (cliente), quiero mapear los sistemas, bases de datos y flujos donde mi
empresa trata datos personales, para saber qué datos tengo, de quién, dónde están y con quién los
comparto, y usarlo como base del RAT y del RoPA.

  C1  Sistemas y bases de datos (nombre, tipo, proveedor, país de alojamiento y responsable
      interno), terceros y los flujos entre ellos; las transferencias internacionales se
      calculan con el país de cada extremo (app/domain/mapa_datos/analisis_mapa.py).
  C2  Cada elemento y flujo lleva categorías de datos (sensibles marcadas) y de titulares (con
      NNA) del catálogo común con el RAT (app/domain/catalogos/catalogo_tratamiento.py).
  C3  La vista navegable y sus filtros viven en el panel; aquí se entregan el mapa completo, sus
      hallazgos y el informe PDF con los mismos filtros (además de su envío por correo).
  C4  Se inicia desde una plantilla por rubro (app/application/mapa_datos/plantillas_mapa.py) o desde
      las respuestas de la evaluación (app/application/mapa_datos/sugerencias.py).
  C5  Cada cambio crea una versión con la instantánea completa (mapa_datos_version, inalterable)
      y queda en el audit_log (HU-09) en la MISMA transacción. Solo con contrato vigente (la ruta
      usa empresa_con_servicio, HU-30).

Concurrencia: toda edición manda la versión que vio el usuario. Si otra pestaña guardó antes,
responde 409 MAPA_DESACTUALIZADO (nada se pisa). La fila del mapa se bloquea (SELECT … FOR
UPDATE) mientras se aplica el cambio.

Nota: los datos de la empresa y del usuario se copian a variables simples al construir el caso
de uso, porque un rollback expira los objetos de la sesión y en modo asíncrono no se pueden
recargar de forma implícita.
"""
from app.application.mapa_datos.casos_uso.casos import MapaDatosCasos
from app.application.mapa_datos.casos_uso.comun import (
    MAX_CAMBIOS_GUARDADOS, TAMANO_PAGINA_VERSIONES, MapaDatosError, elemento_de_fila, flujo_de_fila,
)

__all__ = [
    "MAX_CAMBIOS_GUARDADOS", "TAMANO_PAGINA_VERSIONES", "MapaDatosCasos", "MapaDatosError", "elemento_de_fila",
    "flujo_de_fila",
]

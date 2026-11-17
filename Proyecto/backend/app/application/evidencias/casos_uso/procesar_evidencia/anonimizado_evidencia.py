"""Conserva solo el texto anonimizado de la evidencia (HU-06)."""
from app.application.fabricas import fabricas
from app.domain.models.evidencia import Evidencia
from app.domain.ports.extractor_texto_port import ArchivoIlegibleError
from app.application.evidencias.casos_uso.procesar_evidencia.comun import logger, NOMBRE_TEXTO_ANONIMIZADO


class AnonimizadoMixin:
    """Conserva solo el texto anonimizado de la evidencia (HU-06)."""

    async def _conservar_solo_anonimizado(self, evidencia: Evidencia) -> None:
        """
        HU-06: reemplaza el archivo (cifrado) por su texto anonimizado y borra el original.
        Nunca rompe el flujo: si algo falla, el archivo queda cifrado y se registra en el log
        (sin contenido), para reintentarlo con scripts/migraciones_datos/migrar_pii_hu06.py.
        """
        anterior = evidencia.storage_path
        if self.anonimizador is None or not self.anonimizador.habilitado or not anterior:
            return
        try:
            original = await self.storage.get(anterior)
            # HU-17: el texto real del PDF/DOCX (antes se guardaba el binario decodificado como texto)
            try:
                texto = fabricas().extractor_texto.extraer_texto(original)
            except ArchivoIlegibleError:
                texto = ""
            anonimo = await self.anonimizador.anonimizar(texto) or ""
            guardar = getattr(self.storage, "save_plano", self.storage.save)
            nueva = await guardar(anonimo.encode("utf-8"), NOMBRE_TEXTO_ANONIMIZADO)
        except Exception as e:  # noqa: BLE001
            logger.error("HU-06: no se pudo anonimizar el archivo de la evidencia %s (%s); "
                         "queda cifrado", evidencia.id_evidencia, type(e).__name__)
            return
        try:
            evidencia.storage_path = nueva
            if self.auditar_supresion is not None:
                self.auditar_supresion(evidencia)
            await self.evidencia_repo.update(evidencia)
        except Exception as e:  # noqa: BLE001
            logger.error("HU-06: no se pudo registrar el archivo anonimizado de la evidencia %s (%s)",
                         evidencia.id_evidencia, type(e).__name__)
            await self._borrar(nueva)
            return
        await self._borrar(anterior)

    async def _borrar(self, ruta: str) -> None:
        try:
            await self.storage.delete(ruta)
        except Exception as e:  # noqa: BLE001
            logger.error("HU-06: no se pudo borrar un archivo de evidencia (%s)", type(e).__name__)

"""
HU-06 — Archivos de evidencia cifrados en reposo (decisión del PO, 16-oct).

Ciclo de vida de un archivo de evidencia:
  1. API (upload):  se guarda CIFRADO (Fernet, subclave "evidencias" de ENTITY_MAP_KEY).
                    El texto original nunca toca el disco en claro.
  2. Worker:        lo descifra en memoria, la capa de seguridad revisa el ORIGINAL
                    (prompt injection, también en datos codificados) y la capa de IA
                    lo anonimiza antes del LLM.
  3. Worker (fin):  reemplaza el archivo cifrado por SOLO el texto anonimizado y borra
                    el cifrado (ProcessEvidenceUseCase._conservar_solo_anonimizado).

Decorador de cualquier FileStoragePort: hoy envuelve LocalFileStorage. Lee también
archivos sin cifrar (anteriores a HU-06 o ya reemplazados por el texto anonimizado).
"""
from app.domain.ports.file_storage_port import FileStoragePort
from app.infrastructure.security.cifrado import CifradorDatos


class ArchivoCifradoStorage(FileStoragePort):
    def __init__(self, interno: FileStoragePort, cifrador: CifradorDatos):
        self.interno = interno
        self.cifrador = cifrador

    async def save(self, content: bytes, filename: str) -> str:
        return await self.interno.save(self.cifrador.cifrar_bytes(content), filename)

    async def save_plano(self, content: bytes, filename: str) -> str:
        """Solo para contenido YA anonimizado (el texto que queda tras validar)."""
        return await self.interno.save(content, filename)

    async def get(self, storage_path: str) -> bytes:
        return self.cifrador.descifrar_bytes(await self.interno.get(storage_path))

    async def delete(self, storage_path: str) -> None:
        await self.interno.delete(storage_path)

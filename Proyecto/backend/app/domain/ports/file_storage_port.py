from abc import ABC, abstractmethod

class FileStoragePort(ABC):
    @abstractmethod
    async def save(self, content: bytes, filename: str) -> str:
        """Guarda el archivo y devuelve la ruta de almacenamiento."""
        ...

    @abstractmethod
    async def get(self, storage_path: str) -> bytes:
        """Recupera el contenido de un archivo."""
        ...

    @abstractmethod
    async def delete(self, storage_path: str) -> None:
        """Elimina un archivo."""
        ...
import aiofiles
import os
import uuid
from app.core.config import settings
from app.domain.ports.file_storage_port import FileStoragePort

class LocalFileStorage(FileStoragePort):
    def __init__(self):
        os.makedirs(settings.STORAGE_DIR, exist_ok=True)

    async def save(self, content: bytes, filename: str) -> str:
        unique_name = f"{uuid.uuid4()}_{filename}"
        path = os.path.join(settings.STORAGE_DIR, unique_name)
        async with aiofiles.open(path, "wb") as f:
            await f.write(content)
        return path

    async def get(self, storage_path: str) -> bytes:
        async with aiofiles.open(storage_path, "rb") as f:
            return await f.read()

    async def delete(self, storage_path: str) -> None:
        if os.path.exists(storage_path):
            os.remove(storage_path)
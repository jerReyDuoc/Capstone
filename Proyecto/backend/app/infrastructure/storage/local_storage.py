import os
import re
import uuid

import aiofiles

from app.core.config import settings
from app.domain.ports.file_storage_port import FileStoragePort

_EXTENSION_SEGURA = re.compile(r"^\.[A-Za-z0-9]{1,10}$")


class LocalFileStorage(FileStoragePort):
    def __init__(self):
        os.makedirs(settings.STORAGE_DIR, exist_ok=True)

    async def save(self, content: bytes, filename: str) -> str:
        # HU-06: el nombre en disco es solo un UUID (+ extensión). El nombre original
        # puede traer datos personales ("CV_Juan_Perez.pdf") y no debe quedar en la ruta.
        ext = os.path.splitext(filename or "")[1]
        unique_name = f"{uuid.uuid4().hex}{ext.lower() if _EXTENSION_SEGURA.match(ext) else ''}"
        path = os.path.join(settings.STORAGE_DIR, unique_name)
        async with aiofiles.open(path, "wb") as f:
            await f.write(content)
        return path

    async def get(self, storage_path: str) -> bytes:
        async with aiofiles.open(storage_path, "rb") as f:
            return await f.read()

    async def delete(self, storage_path: str) -> None:
        if storage_path and os.path.exists(storage_path):
            os.remove(storage_path)

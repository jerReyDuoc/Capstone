from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_size=10,
    pool_pre_ping=True,      # ← verifica la conexión antes de usarla
    pool_recycle=3600,       # ← recicla conexiones cada hora
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

class Base(DeclarativeBase):
    pass

async def get_db():
    """Dependencia de FastAPI para inyectar la sesión de BD."""
    async with AsyncSessionLocal() as session:
        yield session
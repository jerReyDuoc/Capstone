from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

# --- Importar la app y los modelos ---
from app.core.config import settings
from app.core.database import Base
from app.domain.models import evaluacion, respuesta, matriz_control, evidencia

# Importar TODOS los modelos para que Alembic los detecte al autogenerar.
# El noqa evita que linters se quejen de imports "no usados".
from app.domain.models import (  # noqa: F401
    evaluacion,
    respuesta,
    matriz_control,
    evidencia,
)

# Objeto de configuración de Alembic
config = context.config

# Sobrescribir la URL desde .env (usa la versión SÍNCRONA, no la asyncpg)
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL_SYNC)

# Configurar logging desde alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Metadata de los modelos para que Alembic detecte cambios
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Ejecuta migraciones en modo 'offline' (genera SQL sin conectarse)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Ejecuta migraciones conectándose realmente a la BD."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,          # detecta cambios de tipo
            compare_server_default=True # detecta cambios de default
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.schema import MetaData

from app.core.config import get_settings


NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base class for SQLAlchemy ORM models."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


settings = get_settings()

engine: AsyncEngine | None = None
SessionLocal: async_sessionmaker[AsyncSession] | None = None

if settings.database_url:
    engine = create_async_engine(
        settings.database_url,
        echo=settings.database_echo,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
    )
    SessionLocal = async_sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured.")

    async with SessionLocal() as session:
        yield session


async def check_database_connection() -> dict[str, object]:
    if engine is None:
        return {
            "ok": False,
            "configured": False,
            "message": "DATABASE_URL is not configured.",
        }

    try:
        async with engine.connect() as connection:
            result = await connection.execute(text("select 1 as health_check"))
            value = result.scalar_one()
    except Exception as exc:
        return {
            "ok": False,
            "configured": True,
            "message": str(exc),
        }

    return {
        "ok": value == 1,
        "configured": True,
        "message": "Database connection succeeded.",
    }


async def close_database_connection() -> None:
    if engine is not None:
        await engine.dispose()

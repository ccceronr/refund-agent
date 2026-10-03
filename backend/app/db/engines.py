"""Database engines. `app_rw` serves the API services; `agent_ro` arrives with the tools (P1/P2)."""

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import Settings


def create_rw_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        settings.database_url_rw.get_secret_value(),
        pool_pre_ping=True,
        # asyncpg waits 60 s by default; never hang a request that long on connect.
        connect_args={"timeout": settings.db_connect_timeout_seconds},
    )

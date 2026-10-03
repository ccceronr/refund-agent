"""Database engines and sessions (design §3.3, R-31).

`app_rw` serves the API services, the only code that writes. `agent_ro` serves the agent
tools: it can only SELECT the tables the tools need.
"""

from pydantic import SecretStr
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings


def create_rw_engine(settings: Settings) -> AsyncEngine:
    return _engine(settings.database_url_rw, settings)


def create_ro_engine(settings: Settings) -> AsyncEngine:
    if settings.database_url_ro is None:
        raise ValueError("DATABASE_URL_RO is not set: the agent tools need the read-only role")
    return _engine(settings.database_url_ro, settings)


def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    # expire_on_commit=False: loaded rows stay readable after commit (async can't lazy-load).
    return async_sessionmaker(engine, expire_on_commit=False)


def _engine(url: SecretStr, settings: Settings) -> AsyncEngine:
    return create_async_engine(
        url.get_secret_value(),
        pool_pre_ping=True,
        # asyncpg waits 60 s by default; never hang a request that long on connect.
        connect_args={"timeout": settings.db_connect_timeout_seconds},
    )

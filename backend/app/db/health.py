"""Database reachability check for GET /api/health."""

import asyncio

import structlog
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

log = structlog.get_logger(__name__)


async def database_is_reachable(engine: AsyncEngine, timeout_seconds: float) -> bool:
    try:
        async with asyncio.timeout(timeout_seconds), engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except (SQLAlchemyError, OSError, TimeoutError) as error:
        # Only the error type: driver messages can contain host names or user names.
        log.warning("database_unreachable", error=type(error).__name__)
        return False
    return True

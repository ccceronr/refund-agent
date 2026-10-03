"""Two engines: app_rw for services, agent_ro for the agent tools (design §3.3, R-31)."""

from collections.abc import Callable

import pytest
from sqlalchemy import text

from app.core.config import Settings
from app.db.engines import create_ro_engine, create_rw_engine


@pytest.mark.parametrize(
    ("create", "role"), [(create_rw_engine, "app_rw"), (create_ro_engine, "agent_ro")]
)
async def test_each_engine_connects_as_its_own_role(
    make_settings: Callable[..., Settings], create, role: str
) -> None:
    engine = create(make_settings())
    try:
        async with engine.connect() as connection:
            current_user = await connection.scalar(text("SELECT current_user"))
    finally:
        await engine.dispose()

    assert current_user == role


def test_the_read_only_engine_needs_its_own_url(make_settings: Callable[..., Settings]) -> None:
    with pytest.raises(ValueError, match="DATABASE_URL_RO"):
        create_ro_engine(make_settings(database_url_ro=None))

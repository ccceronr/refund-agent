"""The one-time production demo reset (seed/reset_demo.py; P9): confirmed by domain and
date, used once, keeps the audit log, never touches anything when refused."""

from collections.abc import Callable
from datetime import date

import asyncpg
import pytest
from pydantic import SecretStr
from seed.reset_demo import ResetRefused, ResetRequest, reset_demo
from seed.seed import StaffPasswords

from app.core.config import Settings

DOMAIN = "app-production-6228.up.railway.app"
TODAY = date(2026, 10, 4)
CONFIRMED = ResetRequest(demo_reset=f"{DOMAIN}@2026-10-04", railway_public_domain=DOMAIN)


@pytest.fixture
async def db(
    fresh_db: None, seeded_db: dict[str, str], connect_as, backend_cli
) -> asyncpg.Connection:
    async with connect_as("app_rw") as connection:
        # Demo activity to be wiped, and an audit entry that must survive.
        await connection.execute(
            "UPDATE cases SET status = 'resolved' WHERE conversation_id = 5012"
        )
        await connection.execute(
            "INSERT INTO audit_log (actor_id, event, details) VALUES ('S14', 'reset_test_kept', '{}')"
        )
        yield connection
    # The reset keeps audit rows on purpose: start the next test from a clean seed.
    backend_cli(seeded_db, "-m", "seed.seed", "--reset")


@pytest.fixture
def run(make_settings: Callable[..., Settings], staff_passwords: dict[str, str]):
    passwords = StaffPasswords(
        seed_password_luis=SecretStr(staff_passwords["luis"]),
        seed_password_marta=SecretStr(staff_passwords["marta"]),
    )

    async def _run(request: ResetRequest, today: date = TODAY) -> str:
        return await reset_demo(make_settings(app_env="production"), passwords, request, today)

    return _run


async def test_a_normal_deploy_changes_nothing(db: asyncpg.Connection, run) -> None:
    outcome = await run(ResetRequest(railway_public_domain=DOMAIN))

    assert outcome == "not_requested"
    assert await db.fetchval("SELECT status FROM cases WHERE conversation_id = 5012") == "resolved"


@pytest.mark.parametrize(
    ("confirmation", "today"),
    [
        (f"{DOMAIN}@2026-10-04", date(2026, 10, 5)),  # yesterday's value left in place
        ("other-app.up.railway.app@2026-10-04", TODAY),  # another deployment
        ("yes", TODAY),
    ],
    ids=["stale-date", "other-domain", "not-a-confirmation"],
)
async def test_anything_but_the_exact_confirmation_is_refused_and_deletes_nothing(
    db: asyncpg.Connection, run, confirmation: str, today: date
) -> None:
    with pytest.raises(ResetRefused):
        await run(ResetRequest(demo_reset=confirmation, railway_public_domain=DOMAIN), today)

    assert await db.fetchval("SELECT status FROM cases WHERE conversation_id = 5012") == "resolved"


async def test_the_confirmed_reset_reloads_the_demo_and_keeps_the_audit_log(
    db: asyncpg.Connection, run, staff_passwords: dict[str, str]
) -> None:
    outcome = await run(CONFIRMED)

    assert outcome == "reset"
    assert await db.fetchval("SELECT count(*) FROM cases WHERE status = 'new'") == 22
    assert await db.fetchval("SELECT count(*) FROM audit_log WHERE event = 'reset_test_kept'") == 1
    assert (
        await db.fetchval(
            "SELECT details->>'confirmation' FROM audit_log WHERE event = 'demo_reset'"
        )
        == CONFIRMED.demo_reset
    )
    assert await db.fetchval("SELECT password_hash IS NOT NULL FROM staff WHERE username = 'luis'")


async def test_a_redeploy_with_the_same_confirmation_does_not_reset_again(
    db: asyncpg.Connection, run
) -> None:
    await run(CONFIRMED)
    await db.execute("UPDATE cases SET status = 'resolved' WHERE conversation_id = 5013")

    outcome = await run(CONFIRMED)

    assert outcome == "already_done"
    assert await db.fetchval("SELECT status FROM cases WHERE conversation_id = 5013") == "resolved"


def test_a_refused_reset_stops_the_pre_deploy(seeded_db: dict[str, str], backend_cli) -> None:
    env = {**seeded_db, "DEMO_RESET": "yes", "RAILWAY_PUBLIC_DOMAIN": DOMAIN}

    result = backend_cli(env, "-m", "seed.reset_demo")

    assert result.returncode == 2
    assert "demo_reset_refused" in result.stdout + result.stderr

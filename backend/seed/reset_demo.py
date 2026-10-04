"""One-time reset of the demo data in production, confirmed by domain and date.

    railway variable set DEMO_RESET=<RAILWAY_PUBLIC_DOMAIN>@<today, YYYY-MM-DD UTC> --service app
    then Deploy: the pre-deploy runs `python -m seed.reset_demo` as app_rw, inside Railway.

- DEMO_RESET unset: nothing happens (every normal deploy).
- Any other value (another domain, another day, a typo): refused, the pre-deploy fails and
  the deploy stops; nothing is deleted.
- Used once: the confirmation is recorded in audit_log (`demo_reset`), so a redeploy with
  the variable still set does nothing.
Everything is reloaded from the seed except audit_log, which keeps its history (A09).
No admin URL, no public database endpoint, no endpoint or button in the app.
"""

import asyncio
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Literal

import structlog
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.config import Settings
from app.core.logging import configure_logging
from app.db.engines import create_rw_engine
from app.db.models import AuditLog
from app.services import audit
from seed.seed import StaffPasswords, reload_demo_data

RESET_EVENT = "demo_reset"
Outcome = Literal["not_requested", "already_done", "reset"]

log = structlog.get_logger(__name__)


class ResetRefused(RuntimeError):
    pass


class ResetRequest(BaseSettings):
    model_config = SettingsConfigDict(env_ignore_empty=True)

    demo_reset: str | None = None
    railway_public_domain: str | None = None  # set by Railway on every service


@dataclass(frozen=True)
class Confirmation:
    value: str
    domain: str | None
    today: date

    def check(self) -> None:
        expected = f"{self.domain}@{self.today.isoformat()}" if self.domain else None
        if self.value != expected:
            raise ResetRefused("DEMO_RESET must be <RAILWAY_PUBLIC_DOMAIN>@<today in UTC>")


async def reset_demo(
    settings: Settings, passwords: StaffPasswords, request: ResetRequest, today: date
) -> Outcome:
    if not request.demo_reset:
        return "not_requested"
    confirmation = Confirmation(request.demo_reset, request.railway_public_domain, today)
    confirmation.check()
    engine = create_rw_engine(settings)
    try:
        async with engine.begin() as connection:
            if await _already_done(connection, confirmation.value):
                return "already_done"
            await reload_demo_data(connection, passwords)
            await audit.record(
                connection,
                event=RESET_EVENT,
                actor_id=None,
                case_id=None,
                details={"confirmation": confirmation.value},
            )
    finally:
        await engine.dispose()
    return "reset"


async def _already_done(connection: AsyncConnection, confirmation: str) -> bool:
    done = await connection.scalar(
        select(
            exists().where(
                AuditLog.event == RESET_EVENT,
                AuditLog.details["confirmation"].astext == confirmation,
            )
        )
    )
    return bool(done)


def main() -> int:
    configure_logging()
    today = datetime.now(UTC).date()
    try:
        outcome = asyncio.run(reset_demo(Settings(), StaffPasswords(), ResetRequest(), today))
    except ResetRefused as refused:
        log.error("demo_reset_refused", reason=str(refused))
        return 2
    log.info(RESET_EVENT, outcome=outcome)
    return 0


if __name__ == "__main__":
    sys.exit(main())

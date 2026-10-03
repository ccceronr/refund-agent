"""Staff sign-in (design §4.0; OWASP A07): argon2id passwords, throttling, audit events."""

import asyncio
import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import ColumnElement, select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.passwords import verify_password
from app.db.models import Staff
from app.rules.model import Role
from app.services import audit
from app.services.errors import TooManyAttempts, WrongCredentials


@dataclass(frozen=True)
class StaffMember:
    staff_id: str
    first_name: str
    role: Role


@dataclass(frozen=True)
class _Account:
    member: StaffMember
    password_hash: str | None


_ACCOUNT_COLUMNS = (Staff.id, Staff.first_name, Staff.role, Staff.password_hash)


class LoginThrottle:
    """Locks a username after `max_failures` failed sign-ins within `window_seconds`.

    In memory: the app runs as one process; a restart clears it (acceptable for the demo).
    """

    def __init__(
        self,
        max_failures: int,
        window_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max_failures = max_failures
        self._window = window_seconds
        self._clock = clock
        self._failures: defaultdict[str, deque[float]] = defaultdict(deque)

    def is_locked(self, username: str) -> bool:
        return len(self._recent(username)) >= self._max_failures

    def record_failure(self, username: str) -> None:
        self._recent(username).append(self._clock())

    def clear(self, username: str) -> None:
        self._failures.pop(username, None)

    def _recent(self, username: str) -> deque[float]:
        failures = self._failures[username]
        while failures and self._clock() - failures[0] > self._window:
            failures.popleft()
        return failures


class AuthService:
    def __init__(self, engine: AsyncEngine, throttle: LoginThrottle) -> None:
        self._engine = engine
        self._throttle = throttle

    async def sign_in(self, username: str, password: str) -> StaffMember:
        key = username.strip().lower()
        if self._throttle.is_locked(key):
            await self._audit("login_throttled", None)
            raise TooManyAttempts
        account = await self._account(Staff.username == key)
        # Verified even for unknown usernames (decoy hash), so timing reveals nothing.
        # argon2 is CPU-bound: run it off the event loop.
        stored_hash = account.password_hash if account else None
        valid = await asyncio.to_thread(verify_password, stored_hash, password)
        if account is None or not valid:
            self._throttle.record_failure(key)
            await self._audit("login_failed", account.member.staff_id if account else None)
            raise WrongCredentials
        self._throttle.clear(key)
        await self._audit("login_succeeded", account.member.staff_id)
        return account.member

    async def signed_in_staff(self, staff_id: str) -> StaffMember | None:
        """The staff member behind a session, if that account can still sign in."""
        account = await self._account(Staff.id == staff_id)
        if account is None or account.password_hash is None:
            return None
        return account.member

    async def sign_out(self, staff: StaffMember) -> None:
        await self._audit("logout", staff.staff_id)

    async def _account(self, where: ColumnElement[bool]) -> _Account | None:
        async with self._engine.connect() as connection:
            row = (await connection.execute(select(*_ACCOUNT_COLUMNS).where(where))).first()
        if row is None:
            return None
        return _Account(StaffMember(row.id, row.first_name, Role(row.role)), row.password_hash)

    async def _audit(self, event: str, actor_id: str | None) -> None:
        # OWASP A09; never the username or password (a password typed as a username would leak).
        async with self._engine.begin() as connection:
            await audit.record(connection, event=event, actor_id=actor_id, case_id=None, details={})

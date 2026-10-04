"""A fresh copy of the seeded demo data for every eval run (refunds_eval), so results never
depend on what was done in the local demo database."""

import asyncio
import os
import sys
from pathlib import Path

from sqlalchemy.engine import make_url

from app.db.bootstrap_roles import RolePasswords, bootstrap_roles, create_database_if_missing

BACKEND = Path(__file__).resolve().parents[1] / "backend"


def role_url(admin_url: str, role: str, password: str) -> str:
    url = make_url(admin_url).set(drivername="postgresql+asyncpg", username=role, password=password)
    return url.render_as_string(hide_password=False)


async def prepare(admin_url: str, passwords: RolePasswords) -> tuple[str, str]:
    """Creates refunds_eval if needed, migrates it and reloads the seed. Returns the app_rw
    and agent_ro URLs."""
    await create_database_if_missing(admin_url)
    await bootstrap_roles(admin_url, passwords)
    rw = role_url(admin_url, "app_rw", passwords.app_rw)
    ro = role_url(admin_url, "agent_ro", passwords.agent_ro)
    env = {**os.environ, "APP_ENV": "local", "DATABASE_URL_RW": rw}
    # The same commands compose and Railway run (design §11).
    for args in (("alembic", "upgrade", "head"), ("seed.seed", "--reset")):
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", *args, cwd=BACKEND, env=env,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
        )  # fmt: skip
        _, errors = await process.communicate()
        if process.returncode != 0:
            raise RuntimeError(f"{' '.join(args)} failed: {errors.decode()[-500:]}")
    return rw, ro

"""Append-only audit trail: who, when, what, why (R-35, OWASP A09).

Details hold ids, codes and amounts only: never names, messages or account numbers.
"""

from typing import Any

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncConnection

from app.db.models import AuditLog


async def record(
    connection: AsyncConnection,
    *,
    event: str,
    actor_id: str | None,
    case_id: int | None,
    details: dict[str, Any],
) -> None:
    await connection.execute(
        insert(AuditLog).values(event=event, actor_id=actor_id, case_id=case_id, details=details)
    )

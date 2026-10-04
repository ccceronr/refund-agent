"""POST /api/cases/prepare-new: every new case, one after another, on the server (R-03;
design §4, §4.4). Models are faked."""

import json
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI
from httpx import AsyncClient

REQUESTED_WITH = {"X-Requested-With": "refund-app"}
SignIn = Callable[[AsyncClient, str], Awaitable[None]]


def events_of(body: str) -> list[tuple[str, dict[str, Any]]]:
    events = []
    for block in body.strip().split("\n\n"):
        name, data = block.split("\n")
        events.append((name.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return events


async def rows(connect_as, sql: str) -> list[tuple[Any, ...]]:
    async with connect_as("app_rw") as db:
        return [tuple(r) for r in await db.fetch(sql)]


async def test_every_new_case_is_prepared_and_the_auto_tier_refunds(
    api: AsyncClient, sign_in: SignIn, connect_as
) -> None:
    await sign_in(api, "luis")
    new_cases = await rows(connect_as, "SELECT count(*) FROM cases WHERE status = 'new'")

    response = await api.post("/api/cases/prepare-new", headers=REQUESTED_WITH)

    events = events_of(response.text)
    total = new_cases[0][0]
    assert events[0] == (
        "case",
        {
            "index": 1,
            "total": total,
            "case_id": events[0][1]["case_id"],
            "member_name": events[0][1]["member_name"],
            "status": "running",
        },
    )
    assert events[-1] == ("done", {"total": total, "prepared": total, "skipped": 0})
    assert await rows(
        connect_as, "SELECT count(*) FROM cases WHERE status IN ('new', 'running')"
    ) == [(0,)]
    daniel = [data for name, data in events if name == "case" and data["case_id"] == 5013]
    assert daniel[-1]["status_label"] == "Refunded automatically"
    assert await rows(connect_as, "SELECT actor_id FROM refund_actions WHERE case_id = 5013") == [
        ("S00",)
    ]


async def test_a_case_at_its_hourly_run_limit_is_skipped(
    api: AsyncClient, sign_in: SignIn, connect_as
) -> None:
    async with connect_as("app_rw") as db:
        await db.execute(
            "INSERT INTO agent_runs (id, case_id, status) SELECT gen_random_uuid(), 5013, 'completed' FROM generate_series(1, 5)"
        )
    await sign_in(api, "luis")

    response = await api.post("/api/cases/prepare-new", headers=REQUESTED_WITH)

    events = events_of(response.text)
    assert ("case", "skipped") in {
        (name, data.get("status")) for name, data in events if data.get("case_id") == 5013
    }
    assert events[-1][1]["skipped"] == 1
    assert await rows(connect_as, "SELECT status FROM cases WHERE conversation_id = 5013") == [
        ("new",)
    ]


async def test_only_one_batch_runs_at_a_time(
    staff_app: FastAPI, api: AsyncClient, sign_in: SignIn
) -> None:
    await sign_in(api, "luis")
    await staff_app.state.batch_lock.acquire()
    try:
        response = await api.post("/api/cases/prepare-new", headers=REQUESTED_WITH)
    finally:
        staff_app.state.batch_lock.release()

    assert response.status_code == 409
    assert response.json()["error"]["message"] == "New messages are already being prepared."

"""Staff asks a supervisor to decide a case (ui.md §2.7, design §4.3a; Camila's P10 request)."""

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from httpx import AsyncClient, Response

REQUESTED_WITH = {"X-Requested-With": "refund-app"}
SignIn = Callable[[AsyncClient, str], Awaitable[None]]
Prepare = Callable[..., Awaitable[Any]]


async def ask_supervisor(client: AsyncClient, case_id: int) -> Response:
    return await client.post(f"/api/cases/{case_id}/escalate", headers=REQUESTED_WITH)


async def rows(connect_as, sql: str, *args: Any) -> list[tuple[Any, ...]]:
    async with connect_as("app_rw") as db:
        return [tuple(r) for r in await db.fetch(sql, *args)]


def queue_item(queue: Response, case_id: int) -> dict[str, Any]:
    item: dict[str, Any] = next(i for i in queue.json() if i["id"] == case_id)
    return item


async def test_staff_can_send_a_ready_case_to_a_supervisor(
    api: AsyncClient, sign_in: SignIn, prepare: Prepare, connect_as
) -> None:
    await prepare(5015)
    await sign_in(api, "luis")

    response = await ask_supervisor(api, 5015)

    assert response.status_code == 200
    assert response.json() == {
        "case_id": 5015, "status": "needs_supervisor", "status_label": "Needs a supervisor",
    }  # fmt: skip
    assert await rows(connect_as, "SELECT status FROM cases WHERE conversation_id = 5015") == [
        ("needs_supervisor",)
    ]


async def test_asking_a_supervisor_is_audited_without_free_text(
    api: AsyncClient, sign_in: SignIn, prepare: Prepare, connect_as
) -> None:
    await prepare(5015)
    await sign_in(api, "luis")

    await ask_supervisor(api, 5015)

    assert await rows(
        connect_as,
        "SELECT actor_id, details::text FROM audit_log WHERE event = 'supervisor_asked'",
    ) == [("S14", '{"from_status": "ready"}')]


async def test_the_queue_and_the_case_show_who_asked(
    api: AsyncClient, sign_in: SignIn, prepare: Prepare
) -> None:
    await prepare(5015)
    await sign_in(api, "luis")
    await ask_supervisor(api, 5015)
    await sign_in(api, "marta")

    queue = await api.get("/api/cases")
    case = await api.get("/api/cases/5015")

    assert queue_item(queue, 5015)["asked_by"] == "Luis"
    assert case.json()["asked_by"] == "Luis"


async def test_a_case_nobody_sent_shows_no_one(
    api: AsyncClient, sign_in: SignIn, prepare: Prepare
) -> None:
    await prepare(5015)
    await sign_in(api, "marta")

    queue = await api.get("/api/cases")
    case = await api.get("/api/cases/5015")

    assert queue_item(queue, 5015)["asked_by"] is None
    assert case.json()["asked_by"] is None


async def test_a_supervisor_can_make_the_exception_on_a_sent_case(
    api: AsyncClient, sign_in: SignIn, prepare: Prepare, connect_as
) -> None:
    await prepare(5015)
    await sign_in(api, "luis")
    await ask_supervisor(api, 5015)
    await sign_in(api, "marta")

    response = await api.post(
        "/api/cases/5015/decision",
        json={"action": "edit", "outcome": "refund", "reply_text": "Hi Olivia, we've refunded it."},
        headers={**REQUESTED_WITH, "Idempotency-Key": str(uuid.uuid4())},
    )

    assert response.status_code == 200
    assert response.json()["refunded"] is True
    assert await rows(connect_as, "SELECT actor_id FROM refund_actions WHERE case_id = 5015") == [
        ("S02",)
    ]


async def test_asking_twice_changes_nothing_the_second_time(
    api: AsyncClient, sign_in: SignIn, prepare: Prepare, connect_as
) -> None:
    await prepare(5015)
    await sign_in(api, "luis")
    await ask_supervisor(api, 5015)

    again = await ask_supervisor(api, 5015)

    assert again.status_code == 200
    assert again.json()["status"] == "needs_supervisor"
    assert await rows(
        connect_as, "SELECT count(*) FROM audit_log WHERE event = 'supervisor_asked'"
    ) == [(1,)]


async def test_only_a_case_ready_for_staff_can_go_to_a_supervisor(
    api: AsyncClient, sign_in: SignIn, prepare: Prepare, connect_as
) -> None:
    await prepare(5027)  # Lucas: no fee found, so manual review
    await sign_in(api, "luis")

    response = await ask_supervisor(api, 5027)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_decision"
    assert await rows(connect_as, "SELECT status FROM cases WHERE conversation_id = 5027") == [
        ("manual_review",)
    ]


async def test_a_supervisor_decides_instead_of_asking(
    api: AsyncClient, sign_in: SignIn, prepare: Prepare
) -> None:
    await prepare(5015)
    await sign_in(api, "marta")

    response = await ask_supervisor(api, 5015)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_decision"


async def test_a_decided_case_cannot_be_sent_to_a_supervisor(
    api: AsyncClient, sign_in: SignIn, prepare: Prepare
) -> None:
    await prepare(5012)
    await sign_in(api, "luis")
    await api.post(
        "/api/cases/5012/decision",
        json={"action": "approve"},
        headers={**REQUESTED_WITH, "Idempotency-Key": str(uuid.uuid4())},
    )

    response = await ask_supervisor(api, 5012)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "already_decided"


async def test_preparing_the_case_again_forgets_who_asked(
    api: AsyncClient, sign_in: SignIn, prepare: Prepare
) -> None:
    await prepare(5015)
    await sign_in(api, "luis")
    await ask_supervisor(api, 5015)

    await prepare(5015)
    case = await api.get("/api/cases/5015")

    assert case.json()["status"] == "ready"
    assert case.json()["asked_by"] is None

"""Staff decisions through the API (tasks P6; R-14, R-15, R-23; BR-09…BR-12; design §4.3)."""

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from fakes import ScriptedDecider
from httpx import AsyncClient, Response

REQUESTED_WITH = {"X-Requested-With": "refund-app"}
SignIn = Callable[[AsyncClient, str], Awaitable[None]]
Prepare = Callable[..., Awaitable[Any]]

OLIVIA_NEEDS_A_SUPERVISOR = "This refund needs a supervisor's approval because Olivia has already used every refund available this year."
NO_FEE = "No fee was identified for this case, so it can't be refunded here."


async def decide(
    client: AsyncClient,
    case_id: int,
    body: dict[str, Any],
    key: uuid.UUID | None = None,
    **headers: str,
) -> Response:
    sent = {**REQUESTED_WITH, "Idempotency-Key": str(key or uuid.uuid4()), **headers}
    return await client.post(f"/api/cases/{case_id}/decision", json=body, headers=sent)


async def rows(connect_as, sql: str, *args: Any) -> list[tuple[Any, ...]]:
    async with connect_as("app_rw") as db:
        return [tuple(r) for r in await db.fetch(sql, *args)]


async def test_approving_twice_with_the_same_key_refunds_once_and_answers_the_same(
    api: AsyncClient, sign_in: SignIn, prepare: Prepare, connect_as
) -> None:
    await prepare(5012)
    await sign_in(api, "luis")
    key = uuid.uuid4()

    first = await decide(api, 5012, {"action": "approve"}, key)
    again = await decide(api, 5012, {"action": "approve"}, key)

    assert (first.status_code, again.status_code) == (200, 200)
    assert first.json() == again.json()
    assert first.json() | {"status_label": "Done"} == {
        "case_id": 5012, "status": "resolved", "status_label": "Done", "action": "approve",
        "outcome": "refund", "refunded": True, "amount": "35.00",
    }  # fmt: skip
    assert await rows(
        connect_as, "SELECT amount::text, actor_id FROM refund_actions WHERE case_id = 5012"
    ) == [("35.00", "S14")]
    assert await rows(connect_as, "SELECT count(*) FROM decisions WHERE case_id = 5012") == [(1,)]


async def test_another_decision_on_a_decided_case_is_a_conflict(
    api: AsyncClient, sign_in: SignIn, prepare: Prepare, connect_as
) -> None:
    await prepare(5012)
    await sign_in(api, "luis")
    await decide(api, 5012, {"action": "approve"})

    second = await decide(api, 5012, {"action": "approve"})

    assert second.status_code == 409
    assert second.json()["error"]["code"] == "already_decided"
    assert await rows(connect_as, "SELECT count(*) FROM refund_actions") == [(1,)]


async def test_staff_cannot_override_limit_reached(
    api: AsyncClient, sign_in: SignIn, prepare: Prepare, connect_as
) -> None:
    await prepare(5015)
    await sign_in(api, "luis")

    response = await decide(
        api,
        5015,
        {"action": "edit", "outcome": "refund", "reply_text": "Hi Olivia, we've refunded the fee."},
    )

    assert response.status_code == 403
    assert response.json()["error"]["message"] == OLIVIA_NEEDS_A_SUPERVISOR
    assert await rows(connect_as, "SELECT count(*) FROM refund_actions") == [(0,)]
    assert await rows(connect_as, "SELECT status FROM cases WHERE conversation_id = 5015") == [
        ("ready",)
    ]
    assert await rows(
        connect_as, "SELECT actor_id FROM audit_log WHERE event = 'decision_refused'"
    ) == [("S14",)]


async def test_a_supervisor_can_override_limit_reached(
    api: AsyncClient, sign_in: SignIn, prepare: Prepare, connect_as
) -> None:
    await prepare(5015)
    await sign_in(api, "marta")

    response = await decide(
        api,
        5015,
        {"action": "edit", "outcome": "refund", "reply_text": "Hi Olivia, we've refunded the fee."},
    )

    assert response.status_code == 200
    assert response.json()["refunded"] is True
    assert await rows(connect_as, "SELECT actor_id FROM refund_actions WHERE case_id = 5015") == [
        ("S02",)
    ]


async def test_the_actor_is_always_the_signed_in_staff_member(
    api: AsyncClient, sign_in: SignIn, prepare: Prepare, connect_as
) -> None:
    await prepare(5012)
    await sign_in(api, "luis")

    smuggled = await decide(api, 5012, {"action": "approve", "actor_id": "S02"})
    response = await decide(api, 5012, {"action": "approve"}, X_Staff_Id="S02")

    assert smuggled.status_code == 422  # unknown fields are refused
    assert response.status_code == 200
    assert await rows(connect_as, "SELECT actor_id FROM decisions") == [("S14",)]
    assert await rows(connect_as, "SELECT actor_id FROM refund_actions") == [("S14",)]
    assert await rows(
        connect_as,
        "SELECT author_id FROM messages WHERE conversation_id = 5012 ORDER BY id DESC LIMIT 1",
    ) == [("S14",)]


async def test_a_manual_case_with_no_fee_can_only_get_a_reply(
    api: AsyncClient, sign_in: SignIn, prepare: Prepare, connect_as
) -> None:
    await prepare(5022, ScriptedDecider(injection=0.97))  # INJECTION_SUSPECTED
    await sign_in(api, "marta")

    refund = await decide(
        api, 5022, {"action": "edit", "outcome": "refund", "reply_text": "Refunded."}
    )
    reply = await decide(
        api,
        5022,
        {"action": "edit", "outcome": "no_refund", "reply_text": "Hi Noah, we're looking into it."},
    )

    assert (refund.status_code, refund.json()["error"]["message"]) == (422, NO_FEE)
    assert reply.status_code == 200
    assert reply.json()["status"] == "resolved"
    assert await rows(connect_as, "SELECT count(*) FROM refund_actions") == [(0,)]


async def test_an_ambiguous_fee_case_refunds_only_a_fee_shown_to_luis(
    api: AsyncClient, sign_in: SignIn, prepare: Prepare, connect_as
) -> None:
    await prepare(5023, ScriptedDecider(fee="unclear"))  # AMBIGUOUS_FEE, two candidates
    await sign_in(api, "luis")
    choices = (await api.get("/api/cases/5023")).json()["proposal"]["fee_choices"]
    body = {"action": "edit", "outcome": "refund", "reply_text": "Hi Emma, we've refunded the fee."}

    unknown = await decide(api, 5023, body | {"fee_transaction_id": 88002})
    picked = await decide(api, 5023, body | {"fee_transaction_id": choices[0]["id"]})

    assert [c["label"].split(" · ")[0] for c in choices] == ["Overdraft fee", "Overdraft fee"]
    assert unknown.status_code == 422
    assert picked.status_code == 200
    assert await rows(connect_as, "SELECT fee_transaction_id FROM refund_actions") == [
        (choices[0]["id"],)
    ]


async def test_a_fee_can_only_be_picked_on_an_ambiguous_fee_case(
    api: AsyncClient, sign_in: SignIn, prepare: Prepare
) -> None:
    await prepare(5012)
    await sign_in(api, "luis")

    response = await decide(api, 5012, {"action": "approve", "fee_transaction_id": 88002})

    assert response.status_code == 422


async def test_rejecting_sends_nothing_and_records_a_feedback_eval(
    api: AsyncClient, sign_in: SignIn, prepare: Prepare, connect_as
) -> None:
    await prepare(5012)
    await sign_in(api, "luis")
    messages_before = await rows(
        connect_as, "SELECT count(*) FROM messages WHERE conversation_id = 5012"
    )

    rejected = await decide(
        api, 5012, {"action": "reject", "reason": "The paycheck posted the next day."}
    )
    answered = await decide(
        api,
        5012,
        {
            "action": "edit",
            "outcome": "no_refund",
            "reply_text": "Hi Ana, we can't refund this fee.",
        },
    )

    assert rejected.json()["status"] == "manual_review"
    assert answered.json()["status"] == "resolved"
    assert await rows(connect_as, "SELECT count(*) FROM messages WHERE conversation_id = 5012") == [
        (messages_before[0][0] + 1,)
    ]
    feedback = await rows(
        connect_as,
        "SELECT payload->'staff'->>'action', payload->'expected'->>'recommendation' FROM feedback_evals ORDER BY id",
    )
    assert feedback == [("reject", None), ("edit", "NO_REFUND")]
    assert await rows(connect_as, "SELECT count(*) FROM refund_actions") == [(0,)]

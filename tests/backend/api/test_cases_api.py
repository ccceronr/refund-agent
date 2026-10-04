"""The queue, the case page and running the flow through the API (R-01…R-03, R-16, R-17, R-33;
design §4.1, §4.2, §4.4). Models are faked."""

import json
from collections.abc import Awaitable, Callable
from typing import Any

from httpx import AsyncClient

REQUESTED_WITH = {"X-Requested-With": "refund-app"}
SignIn = Callable[[AsyncClient, str], Awaitable[None]]
Prepare = Callable[..., Awaitable[Any]]


async def test_the_queue_lists_open_cases_oldest_first_in_plain_words(
    api: AsyncClient, sign_in: SignIn
) -> None:
    await sign_in(api, "luis")

    queue = (await api.get("/api/cases")).json()

    received = [item["received_at"] for item in queue]
    assert received == sorted(received)
    ana = next(item for item in queue if item["id"] == 5012)
    assert ana == {
        "id": 5012, "member_name": "Ana Ruiz", "topic": "Overdraft fee", "status": "new",
        "status_label": "Not prepared yet", "received_at": "2026-09-15T08:12:44", "tier": None,
        "asked_by": None,
    }  # fmt: skip
    # R-01: a closed conversation shows only if decided in the last 24 h (5009: in August).
    assert 5009 not in {item["id"] for item in queue}


async def test_the_queue_can_be_filtered_by_a_known_status_only(
    api: AsyncClient, sign_in: SignIn, prepare: Prepare
) -> None:
    await prepare(5012)
    await sign_in(api, "luis")

    ready = (await api.get("/api/cases", params={"status": "ready"})).json()
    unknown = await api.get("/api/cases", params={"status": "approved; DROP TABLE cases"})

    assert [(item["id"], item["topic"], item["tier"]) for item in ready] == [
        (5012, "Overdraft fee refund", "STAFF")
    ]
    assert unknown.status_code == 422


async def test_a_prepared_case_shows_the_recommendation_evidence_and_run(
    api: AsyncClient, sign_in: SignIn, prepare: Prepare
) -> None:
    await prepare(5012)
    await sign_in(api, "luis")

    case = (await api.get("/api/cases/5012")).json()

    proposal, evidence = case["proposal"], case["evidence"]
    assert proposal["headline"] == "Refund the $35.00 overdraft fee"
    assert proposal["authority_note"] == "You can approve this."
    assert [c["rule"] for c in proposal["checks"]] == [
        "BR-02",
        "BR-04",
        "BR-06",
        "BR-03",
        "BR-05",
        "BR-01",
    ]
    assert evidence["fee"]["account"].startswith("Everyday Checking ••")
    assert evidence["fee"]["account_number_full"].endswith(evidence["fee"]["account"][-4:])
    assert [p["is_fee"] for p in evidence["day_postings"]].count(True) == 1
    assert (evidence["refunds_used"], evidence["refunds_limit"]) == (2, 3)
    assert case["messages"][0]["from"] == "member"
    assert case["run"]["status"] == "completed"
    assert case["run"]["steps"][0]["label"] == "Opening the conversation"


async def test_the_full_account_number_appears_only_in_the_evidence(
    api: AsyncClient, sign_in: SignIn, prepare: Prepare
) -> None:
    # R-33: masked everywhere else (here: the queue and the rest of the case page).
    await prepare(5012)
    await sign_in(api, "luis")
    case = (await api.get("/api/cases/5012")).json()
    full = case["evidence"]["fee"]["account_number_full"]

    outside_evidence = json.dumps({k: v for k, v in case.items() if k != "evidence"})
    queue = (await api.get("/api/cases")).text

    assert full not in outside_evidence
    assert full not in queue


async def test_an_unknown_case_is_a_friendly_404(api: AsyncClient, sign_in: SignIn) -> None:
    await sign_in(api, "luis")

    response = await api.get("/api/cases/999999")

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "We couldn't find that case."


async def test_running_a_case_answers_with_the_prepared_case(
    api: AsyncClient, sign_in: SignIn
) -> None:
    await sign_in(api, "luis")

    response = await api.post("/api/cases/5012/run", headers=REQUESTED_WITH)

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["proposal"]["recommendation"] == "REFUND"


async def test_running_a_case_streams_each_step_then_the_case(
    api: AsyncClient, sign_in: SignIn
) -> None:
    await sign_in(api, "luis")

    response = await api.post(
        "/api/cases/5012/run", headers={**REQUESTED_WITH, "Accept": "text/event-stream"}
    )

    events = [block.split("\n") for block in response.text.strip().split("\n\n")]
    names = [lines[0].removeprefix("event: ") for lines in events]
    assert response.headers["content-type"].startswith("text/event-stream")
    assert names[0] == "step"
    assert names[-1] == "completed"
    first_step = json.loads(events[0][1].removeprefix("data: "))
    assert first_step == {
        "name": "load_case",
        "label": "Opening the conversation",
        "status": "running",
    }
    assert json.loads(events[-1][1].removeprefix("data: "))["status"] == "ready"


async def test_a_decided_case_cannot_be_run_again(
    api: AsyncClient, sign_in: SignIn, prepare: Prepare
) -> None:
    await prepare(5013)  # AUTO: refunded and closed by the flow
    await sign_in(api, "luis")

    response = await api.post("/api/cases/5013/run", headers=REQUESTED_WITH)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "already_decided"

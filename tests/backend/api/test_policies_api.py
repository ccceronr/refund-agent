"""The policy side sheet's document (ui.md §2.3): read-only, signed in."""

from collections.abc import Awaitable, Callable

from httpx import AsyncClient

SignIn = Callable[[AsyncClient, str], Awaitable[None]]


async def test_a_policy_document_comes_back_passage_by_passage(
    api: AsyncClient, sign_in: SignIn
) -> None:
    await sign_in(api, "luis")

    response = await api.get("/api/policies/fee-refund-policy")

    document = response.json()
    assert response.status_code == 200
    assert document["title"] == "Fee Refund Policy"
    assert any(
        p["text"].startswith("An overdraft fee qualifies for a refund")
        for p in document["passages"]
    )


async def test_an_unknown_or_malformed_policy_slug_is_refused(
    api: AsyncClient, sign_in: SignIn
) -> None:
    await sign_in(api, "luis")

    unknown = await api.get("/api/policies/no-such-policy")
    malformed = await api.get("/api/policies/..%2Fsecrets")

    assert unknown.status_code == 404
    assert malformed.status_code in {404, 422}

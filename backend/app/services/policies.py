"""The full policy documents behind the quotes (ui.md §2.3 side sheet). Reads only.

Policies are seeded verbatim from specs/policies.md (LLM04, LLM09).
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncConnection

from app.db.models import PolicyDocument, PolicyPassage
from app.services.errors import PolicyNotFound
from app.services.view_models import PassageView, PolicyDocumentView


async def policy_document(connection: AsyncConnection, slug: str) -> PolicyDocumentView:
    document = (
        await connection.execute(
            select(PolicyDocument.id, PolicyDocument.title).where(PolicyDocument.slug == slug)
        )
    ).first()
    if document is None:
        raise PolicyNotFound(slug)
    passages = await connection.execute(
        select(PolicyPassage.id, PolicyPassage.text)
        .where(PolicyPassage.document_id == document.id)
        .order_by(PolicyPassage.ordinal)
    )
    return PolicyDocumentView(
        slug=slug,
        title=document.title,
        passages=[PassageView(id=p.id, text=p.text) for p in passages],
    )

"""GET /api/policies/{slug}: a whole policy document for the side sheet (ui.md §2.3)."""

from typing import Annotated

from fastapi import APIRouter, Path

from app.api.dependencies import RwEngine
from app.services.policies import policy_document
from app.services.view_models import PolicyDocumentView

Slug = Annotated[str, Path(pattern=r"^[a-z0-9-]{1,64}$")]

router = APIRouter(prefix="/policies")


@router.get("/{slug}")
async def get_policy(slug: Slug, engine: RwEngine) -> PolicyDocumentView:
    async with engine.connect() as connection:
        return await policy_document(connection, slug)

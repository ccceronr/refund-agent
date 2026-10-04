"""Exports staff feedback (R-23) to evals/cases/feedback/*.json, in the eval case format.

They are not run until a person reviews them and moves them into evals/cases/ (LLM04:
feedback is never trusted automatically). Needs DATABASE_URL_RW (make export-feedback).
"""

import asyncio
import json
import os
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine

from app.db.models import FeedbackEval

OUT = Path(__file__).parent / "cases" / "feedback"


async def main() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL_RW"])
    try:
        async with engine.connect() as connection:
            rows = (await connection.execute(select(FeedbackEval).order_by(FeedbackEval.id))).all()
    finally:
        await engine.dispose()
    OUT.mkdir(parents=True, exist_ok=True)
    for row in rows:
        payload = row.payload
        staff = payload.get("staff", {})
        case = {
            "id": f"F{row.id:04d}-case-{row.case_id}",
            "description": f"Staff {staff.get('action')} ({staff.get('outcome')}): {staff.get('reason') or 'reply edited'}",
            "conversation_id": payload["conversation_id"],
            "message_override": payload.get("message_override"),
            "expected": payload.get("expected", {}),
        }
        (OUT / f"{case['id']}.json").write_text(
            json.dumps(case, indent=2, ensure_ascii=False) + "\n"
        )
    print(f"{len(rows)} feedback cases written to {OUT}")


if __name__ == "__main__":
    asyncio.run(main())

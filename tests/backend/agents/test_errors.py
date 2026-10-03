"""Which manual-review reason a failure becomes (BR-13; R-19, R-20)."""

import pytest
from sqlalchemy.exc import OperationalError

from app.agents.errors import ModelUnavailable, failure_code
from app.tools.queries import CaseDataMissing


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (ModelUnavailable("jev", "http_529"), "AI_UNAVAILABLE"),
        (OperationalError("SELECT 1", {}, Exception("down")), "DATA_UNAVAILABLE"),
        (ConnectionRefusedError(), "DATA_UNAVAILABLE"),
        (CaseDataMissing("case 1"), "DATA_UNAVAILABLE"),
        (KeyError("bug"), "UNEXPECTED_ERROR"),
    ],
    ids=["model", "database", "connection", "missing-row", "bug"],
)
def test_each_failure_gets_the_code_of_what_failed(error: Exception, code: str) -> None:
    assert failure_code(error) == code

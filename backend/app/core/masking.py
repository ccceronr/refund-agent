"""Personal data out of logs and screens (R-33, design §8)."""

import re
from typing import Any

from structlog.typing import EventDict

MASK = "••"
LAST_DIGITS_SHOWN = 4
# Log keys that may carry member text, names or account numbers: dropped, never masked.
DROPPED_LOG_KEYS = frozenset({"body", "message", "reply", "name", "account_number"})
# Identifiers we need for correlating logs; they are not personal data.
UNMASKED_LOG_KEYS = frozenset({"event", "timestamp", "request_id", "run_id", "logger", "level"})
_LONG_DIGIT_RUN = re.compile(r"\d{5,}")


def mask_account(account_number: str) -> str:
    """`mask_account("884210")` → "••4210" (the evidence panel alone shows the full number)."""
    return f"{MASK}{account_number[-LAST_DIGITS_SHOWN:]}"


def drop_personal_data(_logger: Any, _method: str, event_dict: EventDict) -> EventDict:
    """structlog processor: drop risky keys, redact digit runs of 5+ (account numbers)."""
    for key in DROPPED_LOG_KEYS & event_dict.keys():
        del event_dict[key]
    for key, value in event_dict.items():
        if isinstance(value, str) and key not in UNMASKED_LOG_KEYS:
            event_dict[key] = _LONG_DIGIT_RUN.sub(MASK, value)
    return event_dict

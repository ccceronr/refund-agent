"""Fee and refund transactions, fee types and their plain names (business-rules.md)."""

from app.rules.model import FeeType, LedgerEntry

FEE_PREFIX = "Fee Withdrawal"
REFUND_PREFIX = "Deposit Fee Refund"
PAYROLL_SUFFIX = "*PAYROLL"

# Checked in this order against the lower-cased fee type text.
_FEE_TYPE_MARKERS: tuple[tuple[str, FeeType], ...] = (
    ("courtesy pay fee", FeeType.COURTESY_PAY),
    ("nsf fee", FeeType.NSF),
    ("returned item fee", FeeType.NSF),
    ("out of network", FeeType.OUT_OF_NETWORK_ATM),
    ("excess withdrawal", FeeType.EXCESS_WITHDRAWAL),
)
_PLAIN_NAMES = {
    FeeType.COURTESY_PAY: "overdraft fee",
    FeeType.NSF: "returned payment fee",
    FeeType.OUT_OF_NETWORK_ATM: "out-of-network ATM fee",
    FeeType.EXCESS_WITHDRAWAL: "savings withdrawal fee",
    FeeType.OTHER: "fee",
}
COVERED_FEE_TYPES = frozenset({FeeType.COURTESY_PAY, FeeType.NSF})  # BR-01


def is_fee(entry: LedgerEntry) -> bool:
    return entry.amount < 0 and entry.description.startswith(FEE_PREFIX)


def is_refund(entry: LedgerEntry) -> bool:
    return entry.amount > 0 and entry.description.startswith(REFUND_PREFIX)


def fee_type_text(description: str) -> str:
    """The text after `;`, trimmed (e.g. "Courtesy Pay fee")."""
    return description.split(";", 1)[-1].strip()


def fee_type(description: str) -> FeeType:
    text = fee_type_text(description).lower()
    for marker, kind in _FEE_TYPE_MARKERS:
        if marker in text:
            return kind
    return FeeType.OTHER


def plain_name(kind: FeeType) -> str:
    return _PLAIN_NAMES[kind]

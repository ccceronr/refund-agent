"""The rows given in the technical test PDF, kept exactly as given (seed-and-evals §1).

Do not "fix" them, even where balances don't chain across days.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

CONVERSATIONS: list[dict[str, Any]] = [
    {"id": 5012, "member_id": 301, "subject": "Overdraft fee", "status": "waiting_for_bank", "created_at": datetime(2026, 9, 15, 8, 12, 44)},
    {"id": 5011, "member_id": 288, "subject": "Card not working", "status": "read_by_bank", "created_at": datetime(2026, 9, 14, 17, 3, 10)},
    {"id": 5010, "member_id": 276, "subject": "Update my address", "status": "waiting_for_member", "created_at": datetime(2026, 9, 14, 11, 40, 2)},
    {"id": 5009, "member_id": 301, "subject": "Statement question", "status": "closed", "created_at": datetime(2026, 8, 2, 9, 15, 30)},
    {"id": 5008, "member_id": 254, "subject": "Fee on my savings", "status": "waiting_for_bank", "created_at": datetime(2026, 9, 13, 19, 22, 51)},
]  # fmt: skip

MESSAGES: list[dict[str, Any]] = [
    {"id": 9120, "conversation_id": 5012, "author_id": "301", "body": "My paycheck came the same day. Can you refund this?", "created_at": datetime(2026, 9, 15, 8, 12, 44)},
    {"id": 9119, "conversation_id": 5011, "author_id": "S14", "body": "Thanks, we are checking your card now.", "created_at": datetime(2026, 9, 14, 17, 40, 12)},
    {"id": 9118, "conversation_id": 5011, "author_id": "288", "body": "My card gets declined at the gas station.", "created_at": datetime(2026, 9, 14, 17, 3, 10)},
    {"id": 9117, "conversation_id": 5010, "author_id": "276", "body": "I moved, how do I change my address?", "created_at": datetime(2026, 9, 14, 11, 40, 2)},
    {"id": 9116, "conversation_id": 5008, "author_id": "254", "body": "Why was I charged $5 on my savings?", "created_at": datetime(2026, 9, 13, 19, 22, 51)},
]  # fmt: skip

ACCOUNTS: list[dict[str, Any]] = [
    {"id": 710, "member_id": 301, "credit_union_id": 7, "account_number": "884210", "is_primary": True},
    {"id": 711, "member_id": 301, "credit_union_id": 7, "account_number": "884211", "is_primary": False},
    {"id": 702, "member_id": 288, "credit_union_id": 7, "account_number": "883977", "is_primary": True},
    {"id": 699, "member_id": 276, "credit_union_id": 7, "account_number": "883540", "is_primary": True},
    {"id": 655, "member_id": 254, "credit_union_id": 9, "account_number": "510332", "is_primary": True},
]  # fmt: skip

SUB_ACCOUNTS: list[dict[str, Any]] = [
    {"id": 1301, "account_id": 710, "type": "SAVINGS", "name": "Primary Savings", "balance": Decimal("215.40"), "available": Decimal("210.40")},
    {"id": 1302, "account_id": 710, "type": "CHECKING", "name": "Everyday Checking", "balance": Decimal("1325.00"), "available": Decimal("1325.00")},
    {"id": 1303, "account_id": 711, "type": "SAVINGS", "name": "Vacation Savings", "balance": Decimal("48.00"), "available": Decimal("48.00")},
    {"id": 1290, "account_id": 702, "type": "CHECKING", "name": "Everyday Checking", "balance": Decimal("92.17"), "available": Decimal("92.17")},
    {"id": 1255, "account_id": 655, "type": "SAVINGS", "name": "Primary Savings", "balance": Decimal("1040.00"), "available": Decimal("1040.00")},
]  # fmt: skip

TRANSACTIONS: list[dict[str, Any]] = [
    {"id": 88001, "sub_account_id": 1302, "date": date(2026, 9, 14), "description": "Withdrawal Debit Card CITY POWER & LIGHT", "amount": Decimal("-60.00"), "balance_after": Decimal("-40.00"), "posting_ref": "20260914-0000"},
    {"id": 88002, "sub_account_id": 1302, "date": date(2026, 9, 14), "description": "Fee Withdrawal ; Courtesy Pay fee", "amount": Decimal("-35.00"), "balance_after": Decimal("-75.00"), "posting_ref": "20260914-0005"},
    {"id": 88003, "sub_account_id": 1302, "date": date(2026, 9, 14), "description": "Deposit ACH ACME LOGISTICS*PAYROLL", "amount": Decimal("1400.00"), "balance_after": Decimal("1325.00"), "posting_ref": "20260914-0010"},
    {"id": 87410, "sub_account_id": 1302, "date": date(2026, 3, 3), "description": "Deposit Fee Refund Courtesy Pay Fee", "amount": Decimal("35.00"), "balance_after": Decimal("412.10"), "posting_ref": "20260303-0002"},
    {"id": 87390, "sub_account_id": 1301, "date": date(2026, 1, 20), "description": "Deposit Fee Refund Out of Network Fee", "amount": Decimal("5.00"), "balance_after": Decimal("880.45"), "posting_ref": "20260120-0002"},
]  # fmt: skip

# Members from the PDF need names for the UI (design §3.2 member_profiles).
PROFILES: list[dict[str, Any]] = [
    {"member_id": 301, "first_name": "Ana", "last_name": "Ruiz"},
    {"member_id": 288, "first_name": "Marcus", "last_name": "Lee"},
    {"member_id": 276, "first_name": "Priya", "last_name": "Shah"},
    {"member_id": 254, "first_name": "Tom", "last_name": "Becker"},
]

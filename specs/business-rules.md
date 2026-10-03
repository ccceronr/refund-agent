# Business rules

These rules decide every refund. They are implemented in **pure Python**
(`backend/app/rules/`), with no I/O and no LLM calls, and are unit-tested from the tables
below. The LLM never changes an outcome.

All thresholds live in `backend/app/core/config.py` and are read from env vars
(defaults below).

| Setting | Default | Meaning |
|---|---|---|
| `REFUND_LIMIT_PER_WINDOW` | `3` | Max fee refunds per member in the rolling window |
| `REFUND_WINDOW_DAYS` | `365` | Rolling window for counting refunds |
| `CLAIM_WINDOW_DAYS` | `60` | Max days between the fee and the request |
| `STAFF_APPROVAL_LIMIT` | `50.00` | Max refund a staff member can approve alone |
| `AUTO_REFUND_ENABLED` | `true` | Allows the AUTO tier |
| `AUTO_REFUND_MAX_AMOUNT` | `35.00` | Max amount the flow may refund on its own |
| `AUTO_MIN_CONFIDENCE` | `0.95` | Min confidence on every typed decision for AUTO |
| `DECISION_MIN_CONFIDENCE` | `0.85` | Below this, the case goes to manual review |
| `INJECTION_THRESHOLD` | `0.5` | Injection probability at or above this → manual review |
| `AUTO_MAX_INJECTION` | `0.1` | Injection probability must be at or below this for AUTO |

## Definitions

- **as_of**: `created_at` of the latest member-authored message in the conversation.
  All date rules use `as_of`, never the wall clock. This makes runs and evals deterministic.
- **Member scope**: all `accounts` with the conversation's `member_id`, and all their
  `sub_accounts`. Rules always look across the whole member scope unless stated otherwise.
- **Posting order**: order of transactions within a day, from `posting_ref`
  (`YYYYMMDD-NNNN`, sort by the numeric suffix). `date` alone has no order.
- **Fee transaction**: `amount < 0` and `description` starts with `Fee Withdrawal`.
  Fee type comes from the text after `;` (trimmed, case-insensitive):

  | Description contains | Fee type | Plain name (UI and replies) |
  |---|---|---|
  | `Courtesy Pay fee` | `COURTESY_PAY` | overdraft fee |
  | `NSF fee` or `Returned item fee` | `NSF` | returned payment fee |
  | `Out of Network` | `OUT_OF_NETWORK_ATM` | out-of-network ATM fee |
  | `Excess Withdrawal` | `EXCESS_WITHDRAWAL` | savings withdrawal fee |
  | anything else | `OTHER` | fee |

- **Refund transaction**: `amount > 0` and `description` starts with `Deposit Fee Refund`.
- **Fee candidates**: fee transactions in the member scope with
  `as_of.date - CLAIM_WINDOW_DAYS*2 <= date <= as_of.date`, **including** fees already
  refunded. The wider lookback lets BR-04 explain "too old" instead of "not found", and
  keeping refunded fees lets BR-05 explain "already refunded" instead of "not found".

## Rules

### BR-01 Refundable fee types
`COURTESY_PAY` and `NSF` are covered by the refund policy. Any other type is **not covered**:
the agent does not recommend, it sends the case to manual review with reason
`FEE_TYPE_NOT_COVERED`. Staff may still refund it at their discretion (BR-09).

### BR-02 Posting-order qualifying reason
Let `F` be the fee, on date `d`, in sub-account `s`. Let `P` be all transactions on `s`
dated `d`, sorted by posting order.
- `opening = P[0].balance_after - P[0].amount`
- `credits = sum(amount for t in P if amount > 0 and t is not a refund transaction)`
- `debits = sum(amount for t in P if amount < 0 and t is not a fee transaction)`

`F` **qualifies** if both are true:
1. At least one credit in `P` posted **after** `F`.
2. `opening + credits + debits >= 0`, meaning the day's deposits would have covered the
   day's payments if they had posted first.

Example (Ana, 2026-09-14): opening = 20.00, credits = 1400.00, debits = -60.00 →
1360.00 ≥ 0, and the payroll posted after the fee → **qualifies**.

### BR-03 Refund limit
`refunds_in_window` = count of refund transactions in the member scope with
`as_of.date - REFUND_WINDOW_DAYS < date <= as_of.date`. Refunds of **any** fee type count.
- If `refunds_in_window >= REFUND_LIMIT_PER_WINDOW` → limit reached.
- `refunds_left_after = REFUND_LIMIT_PER_WINDOW - refunds_in_window - 1` (if refunded now).

Ana: refunds on 2026-01-20 and 2026-03-03 → 2 in window → can refund; 0 left after.

### BR-04 Claim window
`as_of.date - F.date <= CLAIM_WINDOW_DAYS`. Otherwise reason `OUT_OF_WINDOW`.

### BR-05 Already refunded
`F` is already refunded if either:
- a row exists in `refund_actions` for `F`, or
- a refund transaction exists in sub-account `s` with `amount == -F.amount`,
  `date >= F.date`, and the same fee type text in its description.

An already-refunded fee can **never** be refunded again, by anyone (hard block).

### BR-06 Good standing
The member is in good standing unless `member_flags` has:
- any `PAST_FRAUD` flag (resolved or not), or
- a `DEBT_IN_COLLECTIONS` flag with `resolved_at IS NULL`.

### BR-07 Outcome
All checks are evaluated and all results are returned (the UI shows each one).
The **recommendation** is chosen by the first match, top to bottom:

| # | Condition | Recommendation | Reason code |
|---|---|---|---|
| 1 | Already refunded (BR-05) | `NO_REFUND` | `ALREADY_REFUNDED` |
| 2 | Fee type not covered (BR-01) | `MANUAL` | `FEE_TYPE_NOT_COVERED` |
| 3 | Out of claim window (BR-04) | `NO_REFUND` | `OUT_OF_WINDOW` |
| 4 | Not in good standing (BR-06) | `NO_REFUND` | `NOT_GOOD_STANDING` |
| 5 | Does not qualify (BR-02) | `NO_REFUND` | `NO_QUALIFYING_REASON` |
| 6 | Limit reached (BR-03) | `NO_REFUND` | `LIMIT_REACHED` |
| 7 | Otherwise | `REFUND` | `ELIGIBLE` |

The refund amount is always `abs(F.amount)` from the ledger (BR-10).

### BR-08 Approval tier
| Recommendation | Condition | Tier |
|---|---|---|
| `MANUAL` | — | `MANUAL` (Luis handles it) |
| `NO_REFUND` | — | `STAFF` (Luis sends the explanation) |
| `REFUND` | amount > `STAFF_APPROVAL_LIMIT` | `SUPERVISOR` |
| `REFUND` | all AUTO conditions below | `AUTO` |
| `REFUND` | otherwise | `STAFF` |

**AUTO conditions (all required):**
- `AUTO_REFUND_ENABLED` is true
- fee type is `COURTESY_PAY` and amount ≤ `AUTO_REFUND_MAX_AMOUNT`
- `refunds_left_after >= 1` (never use the member's last available refund automatically)
- every typed decision that counts came from Jev (not the fallback) with confidence
  ≥ `AUTO_MIN_CONFIDENCE`. The decisions that count are: the **intent**, the **language**,
  the **fee** when Jev chose it among several candidates (a single candidate is identified
  deterministically and passes), and the guard's two checks (**reply language** and
  **reply outcome**, design §7.5).
  Tone and the policy passage do **not** count: they only shape the wording and the quote
  shown to Luis, never the money or what the member is told.
- injection probability ≤ `AUTO_MAX_INJECTION`
- the draft reply was written by the writer model (not the template fallback) and passed
  the output guard

Ana: 0 refunds left after → **not AUTO** → tier `STAFF` (Luis approves).

### BR-09 Approval authority
Who may **execute** a refund through `POST /cases/{id}/decision`:

| Situation | Staff (`role=staff`) | Supervisor |
|---|---|---|
| Recommendation `REFUND`, amount ≤ `STAFF_APPROVAL_LIMIT` | ✅ | ✅ |
| Amount > `STAFF_APPROVAL_LIMIT` | ❌ | ✅ |
| Refund overriding `NO_REFUND` with reason `LIMIT_REACHED`, `OUT_OF_WINDOW`, `NOT_GOOD_STANDING` or `NO_QUALIFYING_REASON` (policy exception) | ❌ | ✅ |
| Refund of a `FEE_TYPE_NOT_COVERED` fee, amount ≤ limit (staff discretion) | ✅ | ✅ |
| `ALREADY_REFUNDED` | ❌ | ❌ |
| Manual case with reason `AMBIGUOUS_FEE`: the staff member picks the fee | Same matrix, applied to a fresh `evaluate()` with the picked fee | same |
| Any other manual case (no fee identified) | ❌ reply only | ❌ reply only |

**Manual cases.** Only `AMBIGUOUS_FEE` allows a refund decision: the request names the
fee (`fee_transaction_id`), which must be one of the fee candidates stored in the case
evidence (otherwise 422). `evaluate()` (BR-01…BR-07) runs again with that fee and the
rows above apply to the new result. No new rules. In every other manual case
(`NO_FEE_FOUND`, `INJECTION_SUSPECTED`, `INTENT_UNCLEAR`, `AI_UNAVAILABLE`, `TIMEOUT`,
`DATA_UNAVAILABLE`, `REJECTED_BY_STAFF` without an identified fee) the decision can only
send a reply; a refund request returns 422 "No fee was identified for this case, so it
can't be refunded here." (`FEE_TYPE_NOT_COVERED` has an identified fee and follows the
matrix above.)

Sending a reply **without** a refund never needs a supervisor.
A refused attempt returns 403 with a plain message, e.g.
"This refund needs a supervisor's approval because Ana has already used every refund available this year."

### BR-10 Refund amount
The refund amount is `abs(F.amount)` read from the ledger at execution time. It is never
taken from the customer message, the LLM output, or the request body.

### BR-11 Executing a refund (one explicit action)
`RefundService.execute(case, fee, actor, idempotency_key)` is the **only** code path that
moves money, used by both the auto tier and staff decisions. In one DB transaction it:
1. Re-checks BR-05 and BR-09 against the current ledger.
2. Inserts a transaction on the fee's sub-account:
   `description = "Deposit Fee Refund " + <fee type text>`, `amount = abs(F.amount)`,
   `balance_after = sub_account.balance + amount`, `date = today`,
   `posting_ref = next ref for today`.
3. Updates `sub_accounts.balance` and `available` by `+amount`.
4. Inserts `refund_actions` (unique on `fee_transaction_id` and on `case_id`).
5. Writes an `audit_log` entry.

In this demo the "core banking system" is the same Postgres; the service is the adapter a
real core integration would replace.

### BR-12 After the decision
- Refund executed or reply sent → insert the reply as a message (`author_id` = actor staff id,
  or `S00` for the automatic flow), set conversation `status = closed`, case `resolved`
  (or `auto_resolved`).
- Rejected proposal → no message sent; case goes to `manual_review` with reason
  `REJECTED_BY_STAFF`; a feedback eval is recorded (R-23).

### BR-13 Manual review reasons (codes → text shown to Luis)
`{name}` is the member's first name.

| Code | Text |
|---|---|
| `INJECTION_SUSPECTED` | "This message includes instructions aimed at our system. Please read it yourself before acting." |
| `INTENT_UNCLEAR` | "I couldn't tell what {name} is asking for." |
| `NO_FEE_FOUND` | "I couldn't find a fee on {name}'s accounts in the last 60 days." |
| `AMBIGUOUS_FEE` | "{name} has more than one recent fee and I can't tell which one {name} means." |
| `FEE_TYPE_NOT_COVERED` | "This kind of fee isn't covered by the refund policy, so it's your call." |
| `AI_UNAVAILABLE` | "The assistant wasn't available, so this case wasn't prepared. Try again, or handle it yourself." |
| `TIMEOUT` | "Preparing this case took too long. Try again, or handle it yourself." |
| `DATA_UNAVAILABLE` | "I couldn't read {name}'s account information. Try again in a moment." |
| `REJECTED_BY_STAFF` | "You rejected the suggestion. Handle this one yourself." |

`NOT_A_REFUND` is not a manual-review reason: it is the proposal's reason code when the
message is not a refund request (intent `other_banking`, design §5.2). No rule is evaluated
and no reply is drafted; the case status is `not_refund` and the UI shows "Not a refund
request" (ui.md).

No gendered pronouns in any generated UI text: repeat the first name instead.

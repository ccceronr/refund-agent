# UI — the one page Luis uses

Goal: Luis makes the final call **in seconds**. He sees what he needs to trust the result,
can drill into the evidence, and it is obvious what he has to approve.
"The best design is the least design": nothing that doesn't earn its place, subtle motion,
elegant and professional. No AI slop (no gradients, no sparkles, no robot icons, no
"✨ AI-powered", no glassmorphism, no emoji).

## 1. Brand
| Token | Value | Use |
|---|---|---|
| `navy` | `#001D3D` | Text, primary buttons, headings |
| `clay` | `#EFEEED` | Page background, quiet surfaces |
| `terracotta` | `#DC634B` | Accent: selected item, focus ring, "needs attention" |
| `white` | `#FFFFFF` | Cards |
| `grey-*` | neutral scale (e.g. 50–700) derived toward navy | Secondary text, borders |
| `success` | `#2F7D5B` | Checks passed, refunded |
| `error` | `#B42318` | Checks failed, errors |
| `warning` | `#B26B00` | Last refund available, needs supervisor |

Typography: a serif for headings (e.g. Newsreader) and a clean sans for body (e.g.
Figtree). Tabular numerals for money and dates. Body 15px, generous line height.
Motion: 150–250 ms ease-out fades/slides only; respect `prefers-reduced-motion`.
Accessible: WCAG AA contrast, keyboard navigable, visible focus, status not by color alone.

## 2. Layout (desktop first, works ≥ 1024px; stacks on narrow screens)
```
┌───────────────┬─────────────────────────────────────────────────────────┐
│ Header: Member messages · Luis (Staff) · Sign out                       │
├───────────────┼─────────────────────────────────────────────────────────┤
│ QUEUE         │ Ana Ruiz · Overdraft fee refund · received Tue 8:12 AM  │
│ (320px)       │                                                         │
│ ● Ana Ruiz    │ ┌ RECOMMENDATION ───────────────────────────────────┐   │
│   Overdraft…  │ │ Refund the $35.00 overdraft fee                   │   │
│   Ready · 2h  │ │ You can approve this.                             │   │
│ ○ Marcus …    │ │ ✓ Paycheck of $1,400 arrived the same day …       │   │
│               │ │ ✓ Request made within 60 days                     │   │
│ Sections:     │ │ ✓ In good standing                                │   │
│ Ready for you │ │ ! This is Ana's last refund available this year   │   │
│ Needs review  │ │ “Members in good standing may receive up to 3…”   │   │
│ Supervisor    │ │   — Fee Refund Policy                             │   │
│ Not a refund  │ └───────────────────────────────────────────────────┘   │
│ Done today    │ ▸ See the evidence                                      │
│               │ Ana wrote: "My paycheck came the same day…"             │
│               │ ┌ REPLY TO ANA (English) ───────────────────────────┐   │
│               │ │ editable textarea                                 │   │
│               │ └───────────────────────────────────────────────────┘   │
│               │ [Approve and send]  [Reject]   Prepared in 4.2 s · $0.004│
└───────────────┴─────────────────────────────────────────────────────────┘
```

### 2.1 Queue
- Grouped sections, in order: **Ready for you**, **New** (not prepared yet, or being
  prepared), **Needs your review**, **Needs a supervisor**, **Not a refund**, **Done
  today** (includes "Refunded automatically"). Empty sections hidden.
- Item: member name, topic, status label, relative time ("2 h ago"). Selected item has a
  terracotta left bar. Count per section.
- When there are new cases, a quiet button at the top of the queue: **Prepare new messages
  (18)**. While it runs it shows progress ("Preparing 3 of 18 · Daniel Kim") and each case
  moves to its section as it finishes; at the end the queue refreshes ("17 prepared,
  1 skipped"). Opening a new case still prepares it right away (§2.8).
- Supervisor view (signed in as Marta): "Needs a supervisor" section first.

### 2.2 Case header
Member name, topic, received time, credit union (small, grey).

### 2.3 Recommendation card (the heart of the page)
- **Headline** (serif, large): "Refund the $35.00 overdraft fee" /
  "Don't refund the $35.00 overdraft fee" / "This one needs your review" /
  "Refunded automatically" / "This isn't a refund request".
- **Authority line**: "You can approve this." · "A supervisor needs to approve this." ·
  "Done — the $35.00 is back in Ana's account and the reply was sent." (AUTO).
- **Checklist**: each rule check as a line with icon + plain sentence
  (✓ success, ✕ error, ! warning). Text comes from the API (`checks[].text`).
- **Policy quote**: italic quote + document title. Click → shows the full document in a
  side panel (non-modal, `Esc` closes it) with the passage highlighted.
- For manual review: the reason sentence (BR-13) in place of the checklist, plus whatever
  evidence was found.

### 2.4 Evidence (collapsed by default: "See the evidence")
- **What happened on Mon, Sep 14**: vertical timeline of that day's postings in order:
  `1. Card payment · City Power & Light  −$60.00  balance −$40.00`
  `2. Overdraft fee  −$35.00  balance −$75.00` (highlighted)
  `3. Paycheck · Acme Logistics  +$1,400.00  balance $1,325.00`
  Caption (only when the BR-02 check passed and a deposit posted after the fee): "The
  paycheck was processed after the fee. If it had come first, it would have covered the
  payment."
  Clean the core descriptions for display ("Withdrawal Debit Card CITY POWER & LIGHT" →
  "Card payment · City Power & Light"; "Deposit ACH ACME LOGISTICS*PAYROLL" → "Paycheck ·
  Acme Logistics"). Keep the raw description available in a tooltip.
- **Refunds in the last 12 months**: list, "2 of 3 used".
- **Account**: sub-account name, full account number (the only place it's shown), standing.

### 2.5 Member message
Quoted, with send time. Full thread if more than one message.

### 2.6 Reply
- Label: "Reply to Ana (English)" / "(Spanish)".
- Editable textarea prefilled with the draft. If the draft came from the template:
  small note "Written from a standard template."
- Editing the text switches the primary action to **"Send edited reply"** (action `edit`).
- For manual cases: an outcome selector ("Refund $35.00" / "Don't refund") above an empty
  or template reply; action `edit`. For `AMBIGUOUS_FEE`, Luis first picks the fee from the
  ones shown, by date and amount ("Overdraft fee · Mon, Sep 8 · $35.00"), never by ID. Other
  manual cases offer "Don't refund" only (BR-09 "Manual cases").
- On a "Don't refund" proposal that a supervisor may override (BR-09 policy exceptions),
  the same selector appears: "Refund $35.00" is enabled for a supervisor (primary action
  "Refund and send") and disabled for staff with "Only a supervisor can make this
  exception."

### 2.7 Actions (sticky bottom bar)
- Primary (navy): **Approve and send** · **Send edited reply** · (supervisor needed and
  actor is staff → disabled with "Waiting for a supervisor").
- Secondary: **Reject** → inline form under the bar (no modal, so the CSP stays strict)
  "What's wrong with this suggestion?" (required
  reason, 1–500 chars) → confirm.
- Confirmation is inline (no extra modal for approve): button shows a spinner, then a
  success state "Refunded and sent" with a subtle check animation; case moves to "Done
  today". Keyboard: `⌘/Ctrl + Enter` approves.
- Errors from the API shown inline in plain text above the bar, e.g. 403 message from
  BR-09. Never codes or traces.
- Right side, small grey: "Prepared in 4.2 s · $0.004" and a "Run again" text button
  (disabled once decided).

### 2.8 Running state (R-03, R-16)
When a case is opened with status `new` (or "Run again"): the recommendation area shows
the step list streaming in (label + spinner → check + duration), fading in one by one.
On `completed`, it collapses into the recommendation card with a short crossfade.
On `failed`, show the plain message and "Try again".

### 2.9 Sign-in screen
Centered card on clay background: product name, username, password, "Sign in".
Errors: "Wrong username or password." / "Too many attempts. Try again in a few minutes."
No sign-up, no password reset (demo users only).

## 3. Copy rules
- Friendly, plain, direct, explicit. Sentence case. Talk like Luis would.
- No internal terms, IDs, model names, probabilities, "AI", "agent", "LLM", "confidence".
  If uncertainty matters, say it: "I can't tell which fee Ana means."
- Dates like "Mon, Sep 14"; times like "8:12 AM"; money "$35.00", negatives "−$60.00".
- No gendered pronouns in generated text: repeat the first name.
- Status labels: `new` "Not prepared yet" · `running` "Preparing…" · `ready` "Ready for
  you" · `needs_supervisor` "Needs a supervisor" · `manual_review` "Needs your review" ·
  `not_refund` "Not a refund request" · `auto_resolved` "Refunded automatically" ·
  `resolved` "Done".
- Empty queue: "You're all caught up."
- Network error: "We couldn't reach the server. Check your connection and try again."

## 4. Tech notes
- TanStack Query: `['cases']`, `['case', id]`; invalidate both after a decision or run.
- Decision mutation generates a UUID `Idempotency-Key` per user action (kept while
  retrying the same click).
- Auth: session cookie (design §4.0); every mutating request sends
  `X-Requested-With: refund-app`. On 401 → login screen. Never store tokens or
  passwords in localStorage.
- Selected case in the URL (`?case=5012`) so a refresh keeps context.
- Components: `Queue`, `CaseHeader`, `RecommendationCard`, `Checklist`, `PolicyQuote`,
  `EvidencePanel`, `DayTimeline`, `ReplyEditor`, `ActionBar` (with the inline reject form), `RunProgress`, `PrepareNew`.
- Vitest: formatting helpers (money, dates), status → section mapping, action bar state
  logic (which button for which tier/actor/edit state).

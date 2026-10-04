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
| `terracotta` | `#DC634B` | Accent: selected item, focus ring, "needs attention" — backgrounds, borders, icons only |
| `terracotta-text` | `#B8472F` | Every text in terracotta (links); 5.28:1 on white, 4.55:1 on clay |
| `terracotta-light` | `#FD8973` | Link hover underline (blossom.net's coral); decoration only, never text (2.33:1) |
| `white` | `#FFFFFF` | Cards |
| `grey-*` | neutral scale (e.g. 50–700) derived toward navy | Secondary text, borders |
| `success` | `#2F7D5B` | Checks passed, refunded |
| `error` | `#B42318` | Checks failed, errors |
| `warning` | `#B26B00` | Last refund available, needs supervisor |

The four brand colors are required by the test; greys and status colors are used as
needed. Soft tints of these same colors (e.g. terracotta at 14 %) fill icon tiles, chips and
the recommendation's top; text on a tint stays navy so it keeps AA contrast. The brand
terracotta is 3.54:1 on white (3.06:1 on clay), below AA for normal text, so text in
terracotta always uses `terracotta-text`, a darker shade of it that passes AA on both.

Typography: one sans family (Figtree), as on blossom.net: large, light headings with tight
tracking; semibold card titles; 13px medium labels. Tabular numerals for money and dates.
Body 15px, generous line height. Shapes: cards with a 16px radius and a navy hairline (no
grey drop shadows), pill buttons, round icon tiles.
Motion: 150–250 ms ease-out fades/slides only; respect `prefers-reduced-motion`.
Accessible: WCAG AA contrast, keyboard navigable, visible focus, status not by color alone.

## 2. Layout (desktop first, works ≥ 1024px; one column at a time on narrow screens)
```
┌ clay ──────────┬────────────────────────────────────────────────────────────┐
│ ■ Member       │ (AR) Ana Ruiz                              [● Ready for you] │
│   messages     │      Overdraft fee refund · Received Tue, Sep 15, 8:12 AM ·  │
│ (Prepare new   │      Riverbend Credit Union                                  │
│  messages (18))├──────────────────────────────────┬─────────────────────────┤
│ Ready for you 7│ (✓) Recommendation               │ ✉ Ana wrote             │
│ ▌Ana Ruiz      │ Refund the $35.00 overdraft fee  │   "My paycheck came…"   │
│  Sofia Ramirez │ You can approve this.            │ ✎ Reply to Ana (English)│
│ Needs your     │ ✓ … ✓ … ! last refund            │   [textarea] 129 / 2000 │
│  review 4      │ ┃"An overdraft fee qualifies…"   │─────────────────────────│
│  Noah Patel    │ ┃— Fee Refund Policy (link)      │ Overdraft fee · Sep 14  │
│ Done today 3   │ ◷ What happened on Mon, Sep 14   │ Everyday Checking ••4210│
│  …             │   ① Card payment −$60 [−$40.00]  │               $35.00    │
│                │   ② Overdraft fee −$35 [−$75.00] │ ( Approve and send )    │
│                │   ③ Paycheck +$1,400 [$1,325.00] │ ( Reject )              │
│┌──────────────┐│ [Fee charged] [Refunds 2 of 3]   │ or press Ctrl + Enter   │
││(L) Luis  ⎋   ││ [Standing]    [Account]          │ (stays in view)         │
│└──── navy ────┘│                                  │                         │
└────────────────┴──────────────────────────────────┴─────────────────────────┘
```
- **Left column** (320px, clay like the case area, a hairline between them): product mark
  (navy tile) and name, **Overview** (desktop: back to the overview from any case, marked
  like a selected item while it's shown), the queue (§2.1), and who is signed in with
  **Sign out** at the bottom, in the one navy block. The browser's back button also works:
  every opened case is a history entry (`?case=5012`).
- **Case area** (clay): the case header (§2.2), then two columns when the case area is wide
  enough (≥ 896px). On the left, why: the recommendation with the policy quote (§2.3) and
  the evidence (§2.4). On the right, what to do: the member's message (§2.5), the reply
  (§2.6) and the decision (§2.7); this column stays in view while Luis scrolls (and scrolls
  on its own if taller than the window). Narrower, one column in the order Luis needs it:
  recommendation, message, reply, decision, then the evidence.
- **Before a case is opened** (desktop): "Hi Luis, here's what's waiting", four overview
  cards (Ready for you, Needs your review, Needs a supervisor, Done today: icon tile +
  count) and a **Next up** card with the case that has waited longest (same rule as "Next
  case", §2.7) and the button **Open Ana Ruiz's case**; otherwise "Nothing is ready to
  decide. Choose a conversation from the list to see it here."
- **Narrow screens** (< 1024px): the list, the case and the policy take turns instead of
  stacking: opening a case shows it full width with **← Back to list** at the top; the
  policy panel replaces the case until it is closed.

### 2.1 Queue
- Grouped sections, in order: **Ready for you**, **New** (not prepared yet, or being
  prepared), **Needs your review**, **Needs a supervisor**, **Not a refund**, **Done
  today** (includes "Refunded automatically"). Empty sections hidden.
- Item: member name, topic, relative time ("2 h ago"). The status label shows only where
  the section title doesn't already say it ("Preparing…" in New, "Refunded automatically"
  in Done today). Selected item: white background and a terracotta left bar. Each section
  title has a small icon and its count (the "Ready for you" count in navy).
- When there are new cases, a terracotta pill button at the top of the queue: **Prepare
  new messages (18)**. While it runs it shows progress ("Preparing 3 of 18 · Daniel Kim") and each case
  moves to its section as it finishes; at the end the queue refreshes ("17 prepared,
  1 skipped"). Opening a new case still prepares it right away (§2.8).
- Supervisor view (signed in as Marta): "Needs a supervisor" section first.

### 2.2 Case header
Initials avatar, member name (large), then topic, received time and credit union (grey),
and a status chip on the right (icon + status label, tinted like its queue section).

### 2.3 Recommendation card (the heart of the page)
- **Headline** (large): "Refund the $35.00 overdraft fee" /
  "Don't refund the $35.00 overdraft fee" / "This one needs your review" /
  "Refunded automatically" / "This isn't a refund request".
- **Authority line**: "You can approve this." · "A supervisor needs to approve this." ·
  "Done — the $35.00 is back in Ana's account and the reply was sent." (AUTO).
- **Checklist**: each rule check as a line with icon + plain sentence
  (✓ success, ✕ error, ! warning). Text comes from the API (`checks[].text`).
- **Verdict**: the top of the card is tinted by the kind of outcome, with an icon in a
  filled circle: refund (success, check) · don't refund (navy, ban) · needs review
  (terracotta, eye) · not a refund request (grey, message). The headline always says it
  in words. The authority line has an icon that carries the color (warning text on white
  is below AA); the words stay navy.
- Each check's icon sits in a small tinted circle; failed and warning checks are in
  medium weight.
- **Policy quote**, right under the checks, set as a quotation: a thin grey rule, the
  quote in italics, then "— Fee Refund Policy" as an underlined link in `terracotta-text`;
  on hover the underline turns `terracotta-light` and thicker, the text keeps its color.
  Click → shows the full document in a side panel (non-modal, `Esc` closes it) with the
  passage highlighted.
- For manual review: the reason sentence (BR-13) in place of the checklist, plus whatever
  evidence was found.

### 2.4 Evidence (open, in the left column)
- **What happened on Mon, Sep 14** ("In the order the payments were processed"): that
  day's postings in order, each with a numbered circle (the fee in terracotta, money coming
  in in success, the rest neutral), the amount and the balance after it in a chip (error
  tint when overdrawn, success tint otherwise):
  `1. Card payment · City Power & Light  −$60.00  balance −$40.00`
  `2. Overdraft fee  −$35.00  balance −$75.00` (highlighted)
  `3. Paycheck · Acme Logistics  +$1,400.00  balance $1,325.00`
  Caption (only when the BR-02 check passed and a deposit posted after the fee): "The
  paycheck was processed after the fee. If it had come first, it would have covered the
  payment."
  Clean the core descriptions for display ("Withdrawal Debit Card CITY POWER & LIGHT" →
  "Card payment · City Power & Light"; "Deposit ACH ACME LOGISTICS*PAYROLL" → "Paycheck ·
  Acme Logistics"). Keep the raw description available in a tooltip.
  Amounts carry their sign ("+$1,400.00", "−$35.00"), so direction never relies on color.
- Four fact cards (icon tile + label + value): **Fee charged** ($35.00 · Overdraft fee ·
  Mon, Sep 14) · **Refunds in the last 12 months** ("2 of 3" with a meter, one segment per
  refund allowed, and the list) · **Standing** · **Account** (sub-account name and the full
  account number: the only place it's shown).

### 2.5 Member message
A card "Ana wrote" (or "Conversation" for a thread): each message with initials, author,
send time and the text; the member's messages tinted terracotta, the credit union's grey.

### 2.6 Reply
- Label: "Reply to Ana (English)" / "(Spanish)".
- Editable textarea prefilled with the draft. If the draft came from the template:
  small note "Written from a standard template."
- Editing the text switches the primary action to **"Send edited reply"** (action `edit`)
  and shows **Restore suggested reply**, which puts the draft back. A counter shows
  "129 / 2000".
- For manual cases: an outcome selector ("Refund $35.00" / "Don't refund") above an empty
  or template reply; action `edit`. For `AMBIGUOUS_FEE`, Luis first picks the fee from the
  ones shown, by date and amount ("Overdraft fee · Mon, Sep 8 · $35.00"), never by ID. Other
  manual cases offer "Don't refund" only (BR-09 "Manual cases").
- On a "Don't refund" proposal that a supervisor may override (BR-09 policy exceptions),
  the same selector appears: "Refund $35.00" is enabled for a supervisor (primary action
  "Refund and send") and disabled for staff with "Only a supervisor can make this
  exception."

### 2.7 Decision (card in the right column, under the reply)
- First the fee that would move: "Overdraft fee · Mon, Sep 14 · $35.00" and the masked
  account ("Everyday Checking ••4210"), then the outcome selector when Luis has to pick
  (§2.6), then the buttons, full width.
- Primary (navy): **Approve and send** · **Send edited reply** · (supervisor needed and
  actor is staff → disabled with "Waiting for a supervisor").
- Secondary: **Reject** → inline form under the buttons (no modal, so the CSP stays strict)
  "What's wrong with this suggestion?" (required
  reason, 1–500 chars) → confirm.
- Confirmation is inline (no extra modal for approve): button shows a spinner, then a
  success state "Refunded and sent" with a subtle check animation; case moves to "Done
  today". Keyboard: `⌘/Ctrl + Enter` approves (shown under the buttons: "or press Ctrl +
  Enter").
- After a decision, **Next case** (focused, so Enter opens it) opens the oldest case in
  "Ready for you"; for a supervisor, "Needs a supervisor" first. Hidden when there is none.
- "Waiting for a supervisor" shows a lock icon.
- Errors from the API shown inline in plain text above the buttons, e.g. 403 message from
  BR-09. Never codes or traces.
- **How this case was prepared** — supervisors only, for audit (R-17): last card on the
  left, folded: "Prepared in 4.2 s · $0.004", the steps of the run when unfolded, and a
  "Run again" button (hidden once decided). Luis doesn't see it: it doesn't help him
  decide. The live steps while a case is being prepared (§2.8) show to everyone.

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
- Components: `Sidebar`, `Queue`, `NoCaseOpen`, `CaseHeader`, `RecommendationCard`,
  `Checklist`, `PolicyQuote`, `EvidencePanel`, `DayTimeline`, `MemberMessages`,
  `ReplyEditor`, `DecisionCard` (with the inline reject form), `PreparedCard`,
  `RunProgress`, `PrepareNew`.
- Vitest: formatting helpers (money, dates), status → section mapping, action bar state
  logic (which button for which tier/actor/edit state), next case, section counts,
  initials, verdict tone.

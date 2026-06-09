# Spec 5 · Seed Dataset + UI Polish + Demo

**Date:** 2026-06-09
**Phase:** 4 — Stage-ready (⭐ critical path for the demo).
**Anchor:** `2026-06-09-continuum-overview-design.md` (stack, auth topology, phase map).
**Depends on:** Spec 0 (scaffold) · Spec 1 (Role/Successor/ingestion/FoundryKnowledge) · Spec 2 (mentor agent, SSE chat, citations) · Spec 3 (OnboardingPlan/Exercise/Progress). Spec 4 (Work IQ + Fabric IQ) is optional/mockable — the demo runs on fakes if Phase 3 is not wired.
**Feeds:** The live hackathon demo. Everything provisioned here is the demo org that runs on stage.

---

## 1. Purpose

Make Continuum stage-ready. The building blocks from Specs 1–3 exist; what is missing is a
believable company to demonstrate them with, an idempotent script to provision that company
end-to-end on a local or cloud environment (no Azure account required on stage), polished
hero screens the audience can follow, and an exact demo runbook that a presenter can execute
under pressure.

When this spec is done: one command provisions the demo org (org, roles, successors, seeded
docs, ingested knowledge, onboarding plan). A presenter follows a five-step script that
navigates from an admin view of the pre-built Successor, to a new-hire sign-in, to mentor
chat with cited answers, to a generated exercise, to visible progress — all on fake/local
backends, no Azure account needed on stage.

---

## 2. Scope

**In scope**
- A `seed/` directory: the sample company manifest + seed documents (real-ish prose, not
  lorem ipsum) for two roles.
- A `seed/seed.py` script: idempotent end-to-end provisioner (org → roles → successors →
  upload docs → ingest → build onboarding plan). Uses the fake `FoundryKnowledge` and local
  Postgres; runs on `uv run python seed/seed.py`.
- A `seed/reset.py` script: tear-down + re-provision (idempotent; safe to run between
  demo rehearsals).
- UI polish on the four hero screens: mentor chat (citation chips), onboarding plan view,
  exercise view, progress bar. Design-token compliance; loading/empty/error states.
- The employee entry path: sign-in → role assignment page → mentor chat.
- A written demo runbook: exact steps, talking points, fallbacks.
- A pre-warm step: provisioning + ingestion happen before going on stage, not live.

**Out of scope**
- New backend features. Spec 5 wires and polishes; it does not add API endpoints.
- Real Azure / M365 credentials. The demo runs on the fake `FoundryKnowledge` and the
  Phase 4 mock Work IQ / Fabric IQ. A note in the runbook documents the one-line env-var
  flip to real backends.
- Analytics dashboards, reporting, admin RBAC beyond what Better Auth provides.
- Multiple seed companies or more than two roles (one is the demo, two is the backup).

---

## 3. The Sample Org

**Company name:** Meridian Ops  
**Industry:** B2B SaaS (infrastructure monitoring)  
**Tone:** 60-person startup, mature engineering culture, some documented process debt

### 3.1 Role A — Senior Backend Engineer (primary demo role)

The new hire is an engineer joining a team that built a proprietary alerting pipeline.
The documents ground the mentor's answers in real-sounding architectural decisions and
on-call runbooks.

| Filename | Type | Content summary |
|---|---|---|
| `alerting-architecture-v2.md` | Decision record | Why the team moved from polling to push-based alerting in 2023; tradeoffs; the "always-ack-before-resolve" rule and why it prevents alert storms. |
| `oncall-runbook.md` | Runbook | Incident severity levels (P0–P3), escalation path, what to page vs slack, PagerDuty rotation setup, post-mortem template. |
| `backend-engineering-norms.md` | Policy | Code review SLA (24h), merge-queue rules, deploy-on-green policy, feature-flag conventions, service-name registry. |
| `q1-2024-postmortem.md` | Post-mortem | The March 2024 alert-flood incident; root cause (missing dedup window); resolution; the rule added to the runbook. |
| `new-hire-faq.md` | FAQ | "Why do we use Kafka instead of SQS?", "Who approves production access?", "Where is the internal service registry?", "What counts as a P1?" — answers grounded in the above docs. |

This set is enough to ground a "why do we do X?" answer with a citation, produce a
five-item onboarding plan, and generate an exercise (e.g., "read the runbook and answer
three questions about the escalation path").

### 3.2 Role B — Customer Success Manager (backup demo role)

Exists to show the system works across non-engineering roles and as a fallback if the
primary demo role has any data issue.

| Filename | Type | Content summary |
|---|---|---|
| `cs-playbook.md` | Policy | Onboarding customer segments (SMB vs Enterprise), QBR cadence, escalation to Solutions Engineering, churn risk signals. |
| `handoff-process.md` | Runbook | How deals hand off from Sales to CS; required fields in HubSpot; first-call agenda template. |
| `renewal-decision-record.md` | Decision record | Why the team moved from annual-only to monthly renewals for SMB in 2024; revenue tradeoff rationale. |
| `cs-faq.md` | FAQ | "What is our first-response SLA?", "Who owns the technical escalation?", "Why do we do QBRs quarterly, not monthly?" |

### 3.3 Seed user accounts

| Display name | Email (local dev) | Better Auth role | Purpose |
|---|---|---|---|
| Alex Rivera | alex@meridianops.local | `owner` | Admin; has the pre-built Successors |
| Jordan Lee | jordan@meridianops.local | `member` | New hire; assigned to Senior Backend Engineer |

Passwords are set to `demo1234` in the seed script (local dev only; never committed for
a real environment).

---

## 4. Seed / Reset Script

### 4.1 Location

```
continuum/
└── seed/
    ├── seed.py          # idempotent provision script
    ├── reset.py         # tear-down + re-provision (calls seed.py after wipe)
    ├── manifest.json    # declarative description of the sample org (consumed by seed.py)
    └── docs/
        ├── backend-engineer/
        │   ├── alerting-architecture-v2.md
        │   ├── oncall-runbook.md
        │   ├── backend-engineering-norms.md
        │   ├── q1-2024-postmortem.md
        │   └── new-hire-faq.md
        └── customer-success/
            ├── cs-playbook.md
            ├── handoff-process.md
            ├── renewal-decision-record.md
            └── cs-faq.md
```

### 4.2 Manifest (`manifest.json`)

```json
{
  "org": { "name": "Meridian Ops", "slug": "meridianops" },
  "users": [
    { "name": "Alex Rivera", "email": "alex@meridianops.local", "password": "demo1234", "role": "owner" },
    { "name": "Jordan Lee",  "email": "jordan@meridianops.local", "password": "demo1234", "role": "member" }
  ],
  "roles": [
    {
      "title": "Senior Backend Engineer",
      "description": "Owns the alerting pipeline and on-call rotation.",
      "docs_dir": "backend-engineer",
      "assign_to": "jordan@meridianops.local"
    },
    {
      "title": "Customer Success Manager",
      "description": "Owns the post-sale customer relationship for SMB and Enterprise segments.",
      "docs_dir": "customer-success"
    }
  ]
}
```

### 4.3 What `seed.py` does (in order, idempotent)

1. **Ensure org** — create the Better Auth Organization `meridianops` if absent (POST to
   Better Auth's organization API via the Node-side admin endpoint). Idempotent: check by slug.
2. **Ensure users** — create Alex and Jordan if absent; add both as members. Idempotent: check by email.
3. **Ensure roles** — POST `/orgs/{orgId}/roles` for each role. Idempotent: check by `(org_id, title)`.
4. **Ensure successors** — POST `/roles/{roleId}/successor` for each role. Idempotent: Spec 1's KB-name convention (`kb-{org_id}-{role_id}`) makes this safe to call twice.
5. **Upload documents** — POST `/successors/{id}/documents` for each file under `docs_dir/`. Skip files already in `uploaded`/`indexed` status (check by filename).
6. **Ingest** — POST `/successors/{id}/ingest`. Poll until `succeeded` (fake backend completes in-process; should be instant). Log each job status.
7. **Build onboarding plan** — POST `/onboarding/plans` for Jordan's role assignment (Spec 3 endpoint). Skip if a plan for `(user_id, role_id)` already exists.
8. **Assign role to Jordan** — persist the `(user_id, role_id)` assignment if not present.
9. Print a summary table: org slug, user emails, role titles, successor statuses, doc counts, plan item counts.

**Run:**
```bash
cd continuum
uv run python seed/seed.py
```

**Environment variables consumed (all have local defaults):**
```
API_BASE_URL=http://localhost:8000     # FastAPI
WEB_BASE_URL=http://localhost:3000     # Next.js (for Better Auth admin calls)
SERVICE_TOKEN=dev-service-token        # X-Service-Token for BFF trust
FAKE_BACKENDS=true                     # uses FakeFoundryKnowledge + mock Work/Fabric IQ
```

No Azure credentials needed when `FAKE_BACKENDS=true`.

### 4.4 `reset.py`

Deletes all Postgres rows created by `seed.py` for the `meridianops` org (cascade-deletes
via FK), then calls `seed.py`. Safe to run between rehearsals. Does NOT drop Alembic
migration tables or Better Auth schema tables.

### 4.5 Pre-warm step

Run `seed.py` and verify output at least **30 minutes before the demo**. The fake backend
is instant; if a real Foundry IQ resource is wired in, allow 3–5 minutes for ingestion.
Leave the browser signed in as Jordan with the mentor chat open to the first message. Do
not sign out between pre-warm and the demo.

---

## 5. Hero Flow + UI Polish

The four screens that appear on stage must look complete: no broken tokens, no empty-state
placeholders, graceful loading states. All use the design tokens from
`apps/web/src/app/globals.css`. Do NOT restyle `components/ui/*` (shadcn primitives).

### 5.1 Employee entry path

```
/sign-in
  └─ Microsoft sign-in button (Better Auth)
       └─ /onboarding  (role assignment check)
            ├─ if role assigned → /mentor           (chat view)
            └─ if no role      → /onboarding/setup  (pick role; admin assigns)
```

- `/sign-in` — the existing page; polish: center the card, show the Continuum wordmark, a
  one-line tagline ("Your role's AI mentor, from day one."), no extraneous nav links.
- `/onboarding` — a simple redirect shim; reads the user's role assignment from
  `GET /users/me/role-assignment` and routes. Shows a spinner with "Getting your workspace
  ready…" while the API call is in flight.

### 5.2 Mentor chat screen (`/mentor`)

This is the demo's emotional center. The goal: it feels like talking to someone who has
read everything about the role.

**Layout:** two-column on ≥md viewports (left: onboarding plan sidebar; right: chat).
Single-column on mobile (not demoed, but must not break).

**Chat panel (assistant-ui `Thread`):**
- `PageHeader` at the top: "Your AI Mentor · Senior Backend Engineer". Subtitle: "Meridian
  Ops — powered by Continuum."
- Each assistant message has a `CitationChips` component below the message text: small
  pill badges (shadcn `Badge` variant `outline`) showing `[Doc title]`. Clicking a chip
  opens a `Sheet` with the snippet and document name.
- A `RetrievalIndicator` ("Searching knowledge base…") renders while the `RetrievalStarted`
  SSE event is active and clears on `Citations` / `Done`.
- Loading state: assistant bubble shows a three-dot pulse animation (CSS keyframes, using
  `--color-muted-foreground` token) until the first text delta arrives.
- Empty state (no messages yet): a welcome card inside the thread area:
  ```
  "Hi Jordan — I'm your Meridian Ops mentor for the Senior Backend Engineer role.
   Ask me anything about how we work, why we made the decisions we did, or
   where to start on your first week."
  ```
  Pre-loaded quick-start prompts as `Button` variant `outline` chips:
  - "Why do we use push-based alerting?"
  - "Walk me through the on-call escalation path."
  - "What should I do in my first week?"

**Onboarding plan sidebar:**
- Header: "Your onboarding plan". A `Progress` component (shadcn) showing `N of M complete`.
- A vertically scrollable list of plan items as `Card` components; completed items show
  a checkmark icon in `--color-success` (green token); in-progress items show a filled
  circle in `--color-primary`.
- Clicking a plan item that has an exercise opens the exercise sheet (§5.3).
- Loading state: three `Skeleton` rows.
- Empty state (plan not yet generated): a `Button` "Generate my onboarding plan" that
  calls `POST /onboarding/plans` and refetches.

### 5.3 Exercise sheet

A `Sheet` (side panel, right, 480px wide) opened from a plan item.

- Header: plan item title. Subheader: "Exercise".
- The exercise prompt in a `Card` with a light `--color-muted` background.
- A `Textarea` for the employee's written answer.
- A `Button` "Submit" that calls `POST /exercises/{id}/submissions` and on success:
  - Shows a `Toast` ("Nice work — plan updated").
  - Marks the plan item complete; the progress bar ticks up (TanStack Query invalidation).
- Loading state: spinner on the Submit button while in flight.
- Error state: inline `Alert` variant `destructive` with the error message.

### 5.4 Progress indicator

The `Progress` component in the sidebar is the primary indicator. Additionally:

- A small `Badge` in the `PageHeader` shows "N% complete" and updates on plan-item
  completion without a full page reload (TanStack Query background refetch).
- On 100% completion: confetti burst (use `canvas-confetti`, ~2 KB gzipped) + a
  `Dialog` "Onboarding complete — great start, Jordan!"

### 5.5 Design-token compliance checklist

For each of the four screens:
- [ ] All colors reference CSS custom properties from `globals.css` — no hardcoded hex.
- [ ] Typography uses Tailwind classes mapped to the token scale (`text-sm`, `text-base`,
      `font-medium`, etc.), not arbitrary values.
- [ ] Spacing uses the Tailwind 4 spacing scale (4-pt grid).
- [ ] Dark mode: test with the shadcn dark class applied — no invisible text.
- [ ] Focus rings: all interactive elements show a visible focus ring using
      `ring-ring` token.

---

## 6. Demo Script

**Setup before walking on stage:**
1. Run `uv run python seed/seed.py` — verify "all systems ready" summary.
2. Open three browser tabs: (A) admin view at `/admin/roles`, (B) incognito tab at `/sign-in`
   for Jordan's new-hire flow, (C) a spare tab at `/admin/roles` as a fallback.
3. Sign in as Alex Rivera in tab A. Confirm the Senior Backend Engineer role card shows
   "Successor: Ready · 5 documents."
4. Do NOT sign in as Jordan yet — the sign-in moment is part of the demo.
5. Have the seed docs open in a local text editor as a backstop if the chat is slow.

---

### Step 1 — The knowledge problem (30 seconds)

**Tab A** (Alex / admin view, `/admin/roles`).

_Talking point:_ "Every company has this problem: a senior engineer leaves, and everything
they knew — the architectural decisions, the unwritten rules, the 'why do we do it this
way' — walks out the door with them. Continuum fixes that before it happens."

Point to the Senior Backend Engineer role card. "We've already built Alex's successor from
five real documents: an architecture decision record, the on-call runbook, engineering
norms, a post-mortem, and a FAQ. Five documents; five minutes to ingest. That's the
knowledge base."

---

### Step 2 — New hire signs in (30 seconds)

**Switch to tab B** (incognito, `/sign-in`).

Click "Sign in with Microsoft." Enter Jordan Lee's credentials (`jordan@meridianops.local` /
`demo1234`). After redirect, the `/onboarding` shim resolves and lands on `/mentor`.

_Talking point:_ "Jordan just joined as a Senior Backend Engineer. From the moment they
sign in, they're not staring at a Confluence wiki. They're talking to a mentor who has read
everything about this role."

Point to the welcome card and the onboarding plan sidebar. "Five plan items, auto-generated
from the knowledge base. Jordan can see exactly what to learn and in what order."

---

### Step 3 — Grounded "why" answer with citations (90 seconds — the money shot)

Click the quick-start chip: **"Why do we use push-based alerting?"**

The `RetrievalIndicator` appears briefly ("Searching knowledge base…"). The answer streams
in — two to three sentences explaining the push vs polling decision with a direct reference
to the architectural decision record.

When the answer lands, point to the `CitationChips`: "That's not a hallucination. Every
claim is grounded in a real document — click it."

Click the chip. The `Sheet` opens with the exact snippet from
`alerting-architecture-v2.md`.

_Talking point:_ "The mentor can't make things up. If it's not in the org's knowledge
base, it says so. Grounded answers with citations — that's Foundry IQ doing the work."

If Spec 4 (Work IQ / Fabric IQ) is wired in, add: "And if we have Microsoft 365 context
turned on, it also tells Jordan who originally made this decision and what metric it
affected."

---

### Step 4 — Exercise + progress tick (45 seconds)

In the sidebar, click the plan item: **"On-call runbook review"**.

The exercise sheet opens. Read the prompt aloud: "After reading the runbook, answer: what
is the escalation path for a P1 incident?"

Type a short answer in the textarea. Click **Submit**.

_Talking point:_ "Jordan submits their answer. The plan item marks complete."

Point to the progress bar ticking from 1/5 to 2/5 (20% → 40%).

---

### Step 5 — Continuity is the product (30 seconds)

**Switch back to tab A** (Alex / admin view).

_Talking point:_ "Back in the admin view — Alex can see Jordan's onboarding progress in
real time. And the next time someone joins this role, the knowledge base is still there.
The successor outlasts the employee. That's Continuum."

Optional: click the **Rebuild Successor** button (if surfaced in admin) to show that the
knowledge base can be updated when new documents arrive.

**Total runtime: ~3.5 minutes.** Leave 90 seconds for Q&A or a second pass at step 3 with
a different question.

---

## 7. Error Handling / Demo Resilience

| Risk | Likelihood | Mitigation |
|---|---|---|
| FastAPI not running | Low (pre-warm) | Start both `turbo dev` processes in the terminal before the demo and leave them running. Show the terminal briefly to establish credibility. |
| Port 3000 conflict | Medium | Next.js binds to 3000 by default; if another process holds it, set `PORT=3001` in `.env.local` and update `API_BASE_URL` accordingly. Check with `lsof -i :3000` during setup. |
| SSE stream hangs | Low | Set a 15-second timeout on the BFF proxy. If the stream stalls, the UI shows an error state. Reload the page — the conversation is persisted (Spec 2) so messages are not lost. |
| Mentor gives a weak answer | Medium | The seed docs are written to make the "why do we use push-based alerting?" answer land well. If the answer is thin, click the citation chip and read the snippet directly — "even if the mentor's answer isn't perfect, the grounding is real." |
| Postgres not running | Low (pre-warm) | Run `docker compose up -d postgres` before the demo. Check with `psql $DATABASE_URL -c "SELECT 1"`. |
| Sign-in fails for Jordan | Low | Keep tab A (Alex) as the fallback admin demo. The admin flow (show the role card, show the documents, show the ingestion job status) tells the same story without the new-hire sign-in. |
| Ingestion not yet complete | Avoided by pre-warm | Run `seed.py` at least 30 min before the demo and confirm `Successor.status = ready` in the seed summary output. |
| Spec 4 mock errors | Low | `FAKE_BACKENDS=true` skips Work IQ / Fabric IQ entirely. If the Phase 4 mock throws, wrap the enrichment call in a try/except that returns an empty enrichment dict — the answer lands without the IQ context. |

**To flip to real backends (note for production demo):**
```
FAKE_BACKENDS=false
AZURE_FOUNDRY_ENDPOINT=https://<your-resource>.services.ai.azure.com
AZURE_SEARCH_ENDPOINT=https://<your-search>.search.windows.net
# Work IQ + Fabric IQ (Phase 3 only)
COPILOT_RETRIEVAL_ENABLED=true
FABRIC_AGENT_ENABLED=true
```
No code changes required — the `FoundryKnowledge` interface swap is Spec 1's architecture.

---

## 8. Testing / Dry-Run Strategy

### 8.1 Seed script test

`seed/test_seed.py` — a pytest test that:
1. Spins up a fresh Postgres via `pytest-docker` (or a test DB URL from env).
2. Runs `seed.py` against it with `FAKE_BACKENDS=true`.
3. Asserts: org exists, two roles exist, two successors with `status=ready`, 9 documents
   total across both successors, one onboarding plan for Jordan with ≥3 plan items.
4. Runs `seed.py` a second time — asserts all counts are identical (idempotency).
5. Runs `reset.py` — asserts clean state, then runs `seed.py` again — asserts same counts.

This test is the gate for CI: it fails if the seed script is broken before the demo day.

### 8.2 UI smoke test (Playwright)

A single `e2e/demo-flow.spec.ts` that follows the demo script steps automatically:
1. `seed.py` is called as a `globalSetup` fixture.
2. Sign in as Jordan (Playwright credentials from env).
3. Assert mentor chat welcome card is visible.
4. Click "Why do we use push-based alerting?" chip.
5. Wait for the assistant response (up to 10 s with fake backend).
6. Assert at least one citation chip is visible.
7. Open the citation sheet — assert the snippet text contains "push-based".
8. Navigate to the first plan item exercise, submit an answer, assert progress increments.

This test runs in CI and as the **final rehearsal gate** on demo day (run once, confirm
green, then do not touch the environment).

### 8.3 Dry-run rehearsal checklist

Run this checklist at T-24h and again at T-1h:

- [ ] `docker compose up -d postgres` — Postgres is healthy.
- [ ] `turbo dev` — both Next.js (port 3000) and FastAPI (port 8000) start without errors.
- [ ] `uv run python seed/reset.py` — clean state.
- [ ] `uv run python seed/seed.py` — "all systems ready" summary printed.
- [ ] `uv run pytest seed/test_seed.py` — all assertions pass.
- [ ] `pnpm test:e2e` — demo-flow spec is green.
- [ ] Manual walk-through: follow steps 1–5 of §6 at normal speaking pace. Time it.
      Target ≤ 4 minutes including talk time.
- [ ] Browser zoom set to 125% (readable from the back of the room).
- [ ] No pending OS updates, screensaver disabled, notifications silenced.

---

## 9. Acceptance Criteria

1. `uv run python seed/seed.py` completes without errors on a fresh database (with
   `FAKE_BACKENDS=true`); prints a summary showing both roles at `successor.status=ready`
   and document counts matching the manifest.
2. Running `seed.py` twice produces the same state (idempotency — no duplicate rows,
   no error on second run).
3. `uv run python seed/reset.py` followed by `seed.py` restores the full demo state.
4. The scripted five-step demo flow (§6) runs start-to-finish on fake backends — sign-in
   to progress tick — with no manual workarounds required.
5. The mentor chat for "Why do we use push-based alerting?" returns an answer with at
   least one citation chip that opens to a snippet from `alerting-architecture-v2.md`.
6. The onboarding plan sidebar shows ≥3 plan items for Jordan; submitting one exercise
   increments the progress bar.
7. All four hero screens pass the design-token compliance checklist (§5.5): no hardcoded
   hex colors, no broken dark-mode text, focus rings visible on all interactive elements.
8. The Playwright `e2e/demo-flow.spec.ts` is green in CI.
9. The `seed/test_seed.py` idempotency test is green in CI.
10. A presenter with no prior rehearsal can complete the demo in under 5 minutes using
    only the runbook in §6.

---

## 10. Open Questions / Risks

- **Fake backend completeness.** The `FakeFoundryKnowledge` from Spec 1 was built for
  unit tests; it may not return realistic multi-sentence snippets. Spec 5 should extend
  the fake to return canned snippets from the actual seed docs (load them from disk at
  import time) so the demo answers look real even without Azure.

- **Better Auth Organization admin API.** `seed.py` needs to create users and orgs
  programmatically. Better Auth exposes an `auth.api` server-side method and an
  `/api/auth/admin` endpoint; verify the exact call shape against the installed version
  before writing the seed script to avoid breakage.

- **Password auth in local dev.** The demo users sign in with email/password, not
  Microsoft SSO (no Azure tenant available on stage). Better Auth's credential provider
  needs to be enabled alongside the Microsoft provider in the local dev config. Confirm
  this is already wired in Spec 0's scaffold; if not, add it as part of Spec 5.

- **Port 3000 vs 3001 consistency.** If the Next.js dev server is configured to fallback
  to an alternate port, all BFF service token validation and CORS settings must reflect
  that. Document the canonical dev ports in a `CONTRIBUTING.md` note.

- **Confetti library size.** `canvas-confetti` is ~2 KB gzipped and a dynamic import —
  acceptable. If the project has a strict bundle-size budget, the 100% completion
  celebration can fall back to a simple `Toast`.

- **Demo Wi-Fi reliability.** If the venue has unreliable Wi-Fi, the demo must run
  entirely offline. Confirm: Next.js dev server, FastAPI, and Postgres all run on localhost
  with `FAKE_BACKENDS=true` and zero outbound calls. Mark any call that phones home
  (telemetry, font loading) as a risk and disable it in the demo `.env.local`.

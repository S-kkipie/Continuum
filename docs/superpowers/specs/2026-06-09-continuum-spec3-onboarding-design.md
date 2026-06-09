# Spec 3 · Onboarding Plan + Exercises + Progress

**Date:** 2026-06-09
**Phase:** 2 — Mentor loop (thin). ⭐ Critical path.
**Anchor:** `2026-06-09-continuum-overview-design.md` (stack, auth topology, phase map).
**Depends on:** Spec 0 (scaffold) + **Spec 1** (`Role`, `Successor`, `FoundryKnowledge` interface) + **Spec 2** (`MentorAgent.stream`, `Conversation`, `Message`). Spec 3 reuses `MentorAgent` and `FoundryKnowledge.retrieve`; it does not rebuild the agent or ingestion.
**Feeds:** Spec 5 (demo polish — the progress page is the closing act of the demo).

---

## 1. Purpose

Turn the Successor's grounded knowledge and the employee's context (role, experience level) into a
**structured onboarding experience**: an ordered plan of learning steps, practical exercises for
each step, and a lightweight progress tracker. This is the "what you should learn and how you're
doing" layer on top of Spec 2's open-ended chat.

When this spec is done: an employee assigned to a Role has an auto-generated onboarding plan
tailored to their experience level, can generate a short exercise for any step, submit an answer
and receive agent-graded feedback with a score, and view a progress summary showing completed
steps and overall exercise scores.

## 2. Scope

**In scope**
- An `EmployeeProfile` row per (org user, Role) — ties the Better Auth user to a Role with an
  experience level and start date.
- `OnboardingPlan`, `PlanStep` (ordered, with status) — generated once on demand via `PlanGenerator`
  (which calls `MentorAgent` + `FoundryKnowledge.retrieve`).
- `Exercise` — a short prompt + grading rubric generated on demand for a given step/topic.
- `ExerciseSubmission` — stores the employee's answer, the agent's score (0–100) and textual
  feedback.
- `PlanGenerator`, `ExerciseGenerator`, `ProgressService` components in `apps/api`.
- FastAPI internal endpoints + BFF routes for the full flow.
- A minimal `OnboardingDashboard` in `apps/web` (plan steps, exercise modal, progress summary).

**Out of scope (deferred)**
- Work IQ / Fabric IQ enrichment of plans or exercises — Spec 4.
- Multi-employee analytics, cohort views, manager dashboards.
- Regenerating or customizing individual plan steps after generation.
- Gamification, badges, leaderboards.
- Scheduled or recurring exercises; adaptive difficulty beyond the initial level parameter.
- File/media submissions — plain text answers only.

## 3. Domain Additions (SQLModel — add all to `_MANAGED_TABLES`)

```
Successor (Spec 1)
   └── OnboardingPlan (1 per EmployeeProfile) ── generated from the Successor's knowledge
         └── PlanStep (n, ordered)
               └── Exercise (1 per step, generated on demand)
                     └── ExerciseSubmission (n)

User (Better Auth / Drizzle) ← referenced by user_id only; no cross-ORM FK
   └── EmployeeProfile (1 per user+role combo)
         └── OnboardingPlan (1)
```

**Note:** `user_id` and `org_id` on every entity below reference Better Auth tables owned by
Drizzle. There are no cross-ORM foreign keys; the BFF validates org/user ownership before
forwarding to FastAPI.

| Entity | Key fields | Notes |
|---|---|---|
| `EmployeeProfile` | `id`, `user_id`, `org_id`, `role_id`, `experience_level` (`entry`/`mid`/`senior`), `start_date` (date), `created_at` | `role_id` → `Role` (SQLModel FK). `user_id`+`role_id` unique per org. |
| `OnboardingPlan` | `id`, `employee_profile_id`, `successor_id`, `title`, `status` (`generating`/`ready`/`failed`), `created_at`, `updated_at` | 1:1 with `EmployeeProfile`. `successor_id` → `Successor`; plan is regenerable (mark old as superseded via status). |
| `PlanStep` | `id`, `plan_id`, `order` (int), `title`, `description`, `topic_tags` (JSONB, list[str]), `status` (`not_started`/`in_progress`/`complete`), `completed_at` | Ordered by `order`. `topic_tags` drives `ExerciseGenerator` retrieval. |
| `Exercise` | `id`, `step_id`, `prompt` (text), `rubric` (text), `status` (`ready`/`failed`), `created_at` | 1 per step (generated on demand; re-request replaces). `rubric` is the agent's private grading guide — not shown to the employee. |
| `ExerciseSubmission` | `id`, `exercise_id`, `user_id`, `answer` (text), `score` (int, 0–100, nullable), `feedback` (text, nullable), `graded_at` (nullable), `created_at` | Multiple submissions allowed; the latest graded one is used for progress. |

## 4. Architecture & Components

All generation components live in `apps/api`. The web layer in `apps/web` is a thin dashboard
wired through the BFF. No new agent framework primitives — `MentorAgent` and
`FoundryKnowledge.retrieve` are reused as-is.

### 4.1 `PlanGenerator`

- **Does:** generate an ordered list of `PlanStep`s for an `EmployeeProfile` by invoking the
  `MentorAgent` with a planning prompt, grounded on retrieval from the Successor's knowledge base.
  Persists the `OnboardingPlan` + `PlanStep` rows.
- **Interface:**
  ```python
  async def generate(
      profile: EmployeeProfile,
      successor: Successor,
  ) -> OnboardingPlan
  ```
- **Generation contract:** constructs a planning prompt that includes the role title, the
  employee's `experience_level`, and instructs the model to produce N ordered steps (default 6–8)
  grounded in retrieved knowledge. Each step must have a `title`, a one-sentence `description`,
  and 1–3 `topic_tags`. The model calls `retrieve` (the existing tool) to ground step topics
  before listing them. Steps are parsed from the model's structured output (JSON mode or a
  schema-constrained response).
- **Depends on:** `MentorAgent` (Spec 2), `FoundryKnowledge` (Spec 1), `OnboardingPlanRepo`,
  `PlanStepRepo`.
- **Error:** if generation fails or parsing fails, the `OnboardingPlan` is set to `status=failed`
  with an error; the employee can retry (a new plan generation call replaces the failed one).

### 4.2 `ExerciseGenerator`

- **Does:** generate a single `Exercise` (prompt + rubric) for a `PlanStep` by invoking the
  `MentorAgent` grounded on the step's `topic_tags`, replacing any existing exercise for that
  step.
- **Interface:**
  ```python
  async def generate(step: PlanStep, successor: Successor) -> Exercise
  ```
- **Generation contract:** planning prompt specifies the step title, description, and topic tags;
  instructs the model to write a short open-ended exercise question (2–4 sentences) testing
  practical understanding, plus a private grading rubric listing key expected points (3–5
  bullets). Uses `retrieve(query=step.title + " " + " ".join(step.topic_tags))` for grounding.
  Returns `{prompt, rubric}` parsed from structured output.
- **Depends on:** `MentorAgent`, `FoundryKnowledge`, `ExerciseRepo`.

### 4.3 `GradingAgent`

- **Does:** grade a submitted answer against the exercise's `prompt` + `rubric` and return a
  `score` (0–100) and textual `feedback`.
- **Interface:**
  ```python
  async def grade(
      exercise: Exercise,
      answer: str,
  ) -> GradeResult  # GradeResult(score: int, feedback: str)
  ```
- **Grounding contract:** the grading system prompt gives the model the `prompt`, the `rubric`,
  and the `answer`; instructs it to score 0–100 against the rubric criteria and write 1–3
  sentences of constructive feedback. The rubric is the retrieved-and-generated grading guide —
  not shown to the employee. No additional retrieval needed at grading time.
- **Depends on:** `MentorAgent`'s underlying Azure OpenAI chat client (same model, no agent
  framework loop needed here — a single structured completion call). No `retrieve` tool call.

### 4.4 `ProgressService`

- **Does:** compute and return the progress summary for an employee's onboarding plan: count of
  steps completed vs total, list of step statuses, latest submission score per step (if any).
- **Interface:**
  ```python
  def summary(plan: OnboardingPlan) -> ProgressSummary
  # ProgressSummary(total_steps, completed_steps, steps: list[StepProgress])
  # StepProgress(step_id, title, status, exercise_score: int | None)
  ```
- **Depends on:** `PlanStepRepo`, `ExerciseRepo`, `ExerciseSubmissionRepo`. Pure DB reads, no
  agent calls.

### 4.5 BFF routes (`apps/web`)

- Validate the Better Auth session + org ownership on every request; attach `X-Service-Token` +
  `X-Org-Id` before forwarding to FastAPI internal routes.
- No SSE in Spec 3 — all generation endpoints are synchronous (short-lived; plan generation
  expected < 10 s, exercise < 5 s, grading < 5 s; surface a loading state in the UI).

### 4.6 `OnboardingDashboard` (`apps/web`)

- **Does:** render the employee's plan (list of steps with status checkboxes), an "Generate
  Exercise" button per step (opens a modal), answer submission + feedback display, and a progress
  summary bar.
- **Depends on:** TanStack Query for plan/progress polling, shadcn components, BFF routes.

## 5. Data Flow

```
Employee (Next.js)
  │
  ├── GET  /api/bff/me/profile         → EmployeeProfile (or 404 if not yet assigned)
  │
  ├── POST /api/bff/me/profile         → create EmployeeProfile {role_id, experience_level, start_date}
  │
  ├── POST /api/bff/me/plan            → BFF → FastAPI: PlanGenerator.generate(profile, successor)
  │         OnboardingPlan status=generating → (synchronous, ~5–10 s) → status=ready
  │         returns plan_id
  │
  ├── GET  /api/bff/me/plan            → OnboardingPlan + PlanSteps (ordered, with statuses)
  │
  ├── PATCH /api/bff/me/plan/steps/{stepId}   → mark step complete (status=complete, completed_at=now)
  │
  ├── POST /api/bff/me/plan/steps/{stepId}/exercise
  │         → ExerciseGenerator.generate(step, successor)  → Exercise (prompt only, rubric hidden)
  │
  ├── GET  /api/bff/me/plan/steps/{stepId}/exercise  → Exercise {id, prompt, status}
  │
  ├── POST /api/bff/me/plan/steps/{stepId}/exercise/submissions
  │         → persist ExerciseSubmission(answer); GradingAgent.grade(exercise, answer)
  │         → ExerciseSubmission updated with score + feedback; returns score + feedback
  │
  └── GET  /api/bff/me/progress        → ProgressService.summary(plan)
```

All FastAPI internal endpoints receive `{userId, orgId}` from the BFF headers and authorize on
`EmployeeProfile.user_id` + `EmployeeProfile.org_id` ownership.

## 6. API Surface

**FastAPI internal (service-token guarded, `{userId, orgId}` from BFF headers):**

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/internal/users/{userId}/profile` | Get EmployeeProfile (404 if none) |
| `POST` | `/internal/users/{userId}/profile` | Create EmployeeProfile `{role_id, experience_level, start_date}` |
| `POST` | `/internal/users/{userId}/plan` | Generate OnboardingPlan (Successor must be `ready`) → returns plan |
| `GET` | `/internal/users/{userId}/plan` | Current plan + steps (latest `ready` plan) |
| `PATCH` | `/internal/plan-steps/{stepId}` | Set step `status` (`in_progress`/`complete`) |
| `POST` | `/internal/plan-steps/{stepId}/exercise` | Generate (or regenerate) Exercise for step → returns `{id, prompt}` |
| `GET` | `/internal/plan-steps/{stepId}/exercise` | Get current Exercise `{id, prompt, status}` |
| `POST` | `/internal/exercises/{exerciseId}/submissions` | Submit answer → grade → return `{score, feedback}` |
| `GET` | `/internal/users/{userId}/progress` | ProgressSummary for current plan |

**BFF (Next.js) — mirror paths under `/api/bff/me/...`:**

| Method | BFF path | Proxied to |
|---|---|---|
| `GET/POST` | `/api/bff/me/profile` | `/internal/users/{userId}/profile` |
| `GET/POST` | `/api/bff/me/plan` | `/internal/users/{userId}/plan` |
| `PATCH` | `/api/bff/me/plan/steps/{stepId}` | `/internal/plan-steps/{stepId}` |
| `GET/POST` | `/api/bff/me/plan/steps/{stepId}/exercise` | `/internal/plan-steps/{stepId}/exercise` |
| `POST` | `/api/bff/me/plan/steps/{stepId}/exercise/submissions` | `/internal/exercises/{exerciseId}/submissions` (BFF resolves exercise id from step) |
| `GET` | `/api/bff/me/progress` | `/internal/users/{userId}/progress` |

## 7. Error Handling

- **Successor not `ready`:** plan/exercise generation returns 409 with code `successor_not_ready`;
  UI shows "Your role's knowledge base is still indexing — check back soon."
- **Plan generation failure:** `OnboardingPlan.status=failed`; POST `/plan` can be re-called to
  replace it. UI surfaces a retry button.
- **Exercise generation failure:** `Exercise.status=failed`; step-level "Generate Exercise" button
  retries (POST replaces the failed row).
- **Grading failure:** `ExerciseSubmission.score` and `feedback` remain null; submission row is
  retained with a `grading_failed` note; UI shows "Grading unavailable — try resubmitting."
- **EmployeeProfile missing:** 404 from plan/progress endpoints; UI redirects to the profile
  setup flow.
- **Auth / org mismatch:** BFF returns 404 (not 403) for any resource whose org_id differs from
  the session's org, to avoid leaking existence.
- **Model / Azure OpenAI unavailable:** typed `GenerationError` propagated as 502; operations
  are idempotent — safe to retry from the UI.

## 8. Testing Strategy

- **Unit — `PlanGenerator`:** against a `FakeMentorAgent` that deterministically returns a
  canned ordered list of steps when called with any prompt, and a `FakeFoundryKnowledge` (Spec
  1's shared fake). Assert: plan status transitions `generating → ready`, step count matches
  output, `topic_tags` populated, `order` is 1-indexed and contiguous.
- **Unit — `ExerciseGenerator`:** same fakes. Assert: `Exercise.prompt` non-empty, `rubric`
  non-empty, status=`ready`, previous exercise for the step is replaced on regeneration.
- **Unit — `GradingAgent`:** stub the Azure OpenAI completion to return `{"score": 75,
  "feedback": "Good effort"}`. Assert: `ExerciseSubmission` updated with score + feedback +
  graded_at.
- **Unit — `ProgressService`:** fully deterministic (pure DB reads via in-memory SQLite or
  factory fixtures). Assert: `completed_steps` counts match, per-step exercise scores reflect
  latest submission.
- **API tests (FastAPI `TestClient`):**
  - Full plan create → get → patch step → generate exercise → submit → progress flow with faked
    generation services. Assert HTTP status codes, response shapes, and DB state after each call.
  - 409 on plan generate when Successor is `provisioning`.
  - 404 on plan get when EmployeeProfile missing.
- **Contract:** `FakeMentorAgent` must implement the same interface as the real `MentorAgent`
  (Spec 2) — a shared minimal contract test keeps the swap honest.
- **Integration (one, gated `@integration`):** against a real `ready` Successor (Spec 1 dev
  resource) and real Azure OpenAI — generate a plan, generate and submit an exercise answer,
  assert a score is returned. Skipped without Azure creds.
- **Web (component test):** `OnboardingDashboard` renders steps from a mocked plan query,
  "Generate Exercise" opens the modal, submission triggers a mocked POST and shows score + feedback.

## 9. Acceptance Criteria

1. An employee assigned to a Role (via `EmployeeProfile`) can generate an `OnboardingPlan` with
   6–8 ordered steps, each grounded in the Successor's knowledge base topics.
2. Steps generated for an `entry`-level employee are visibly broader/more foundational than for a
   `senior`-level employee (observable in the step titles/descriptions on the same Successor).
3. Clicking "Generate Exercise" for any step produces a non-empty exercise prompt in < 10 s; the
   rubric is never exposed to the employee.
4. Submitting a plain-text answer returns a score (0–100) and 1–3 sentences of feedback grounded
   in the rubric, in < 10 s.
5. Marking a step complete updates `PlanStep.status=complete`; the progress summary reflects the
   new count immediately.
6. The progress summary correctly reports `completed_steps / total_steps` and the latest exercise
   score per step.
7. All of the above flow browser → BFF → FastAPI with the browser never calling FastAPI directly
   (BFF validates session + org on every hop).
8. If the Successor is not `ready`, attempting to generate a plan returns a clear "knowledge base
   not ready" error in the UI — no 500s.

## 10. Open Questions / Risks

- **Structured output reliability:** plan and exercise generation depend on the model returning
  valid JSON conforming to the expected schema. Use Azure OpenAI's `response_format={"type":
  "json_schema", schema=...}` (if available on the chosen deployment) or a post-parse retry with
  a correction prompt. Validate early — a silent schema mismatch could silently generate empty
  plans.
- **Plan generation latency:** plan generation involves retrieval + a longer prompt + structured
  output parsing. Benchmark on the chosen model/deployment; if > 15 s, add an SSE progress
  stream (matching Spec 2's SSE plumbing) rather than a blocking POST. For the hackathon, a
  spinner with a 10 s timeout is acceptable.
- **One plan per employee per role:** the current model allows one `ready` plan at a time. Define
  "replace" behavior: on re-generate, set old plan to `status=superseded` (add the status value)
  and create a new one. Ensure progress is reset or carried over intentionally.
- **Exercise rubric quality:** rubric is generated alongside the prompt. A poor rubric produces
  inconsistent grading. Consider a two-step generation: prompt first, rubric separately with the
  prompt in context — evaluate if it improves quality on the demo dataset.
- **Score calibration:** the grading agent may grade inconsistently across re-submissions. For
  the hackathon, exact calibration is out of scope; document it as a known limitation and cap
  the score display at "indicative."
- **`FakeMentorAgent` maintenance cost:** Spec 2 owns `MentorAgent`; if its interface changes,
  Spec 3's fake must be updated. Keep the fake in a shared `tests/fakes/` module so both specs
  import from one place.

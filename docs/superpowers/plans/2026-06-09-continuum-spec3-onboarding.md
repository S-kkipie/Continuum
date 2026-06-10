# Spec 3 — Onboarding Plan + Exercises + Progress Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn a Successor's captured knowledge + an employee's role/experience into a structured onboarding experience: an auto-generated ordered plan, on-demand graded exercises per step, and a progress summary.

**Architecture:** Three generators — `PlanGenerator`, `ExerciseGenerator`, `GradingAgent` — behind Protocols, chosen by a `generation_backend=fake|live` setting (mirrors Spec 1's blob/knowledge + Spec 2's chat backends). **Fake** generators return deterministic canned output → CI-green + the whole demo runs with **no Azure**; **live** generators ground on `FoundryKnowledge.retrieve` (Spec 1) + a structured-output completion via the `ChatModel` (Spec 2 swap point), gated by `@integration`. An `OnboardingService` composes generators + repos into the full flow (profile → plan → steps → exercise → submit/grade → progress). Synchronous (no SSE). FastAPI `/internal/*` + a Next.js BFF + a minimal `OnboardingDashboard`.

**Tech Stack:** FastAPI · SQLModel · Alembic (Python); reuses Spec 2 `ChatModel`/`build_chat_model` + Spec 1 `FoundryKnowledge`/`build_knowledge`. Next.js BFF + TanStack Query dashboard (web). Default `generation_backend=fake` (no Azure for dev/CI).

**Conventions:** Python cmds from `apps/api`. Web from repo root via `pnpm --filter web ...` + `pnpm check` (Biome). Append to every commit: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. NEVER `alembic revision --autogenerate` — hand-write migrations + add new tables to `_MANAGED_TABLES`. Reuse `require_service_token` + the `_org` header. Add a `_user` header dep (Spec 2 introduced `X-User-Id`).

---

## Architecture decisions (read before starting)

1. **Generators are the swap point, NOT MentorAgent.** Plan/exercise/grading are one-shot **structured** tasks, not streamed chat. The `live` generators reuse the `ChatModel` Protocol (Spec 2) for the completion + `FoundryKnowledge.retrieve` (Spec 1) for grounding — they do their own single `retrieve` + one structured completion, parsing JSON from the accumulated text. They do NOT use `MentorAgent.stream` (which bakes in the chat system prompt). This keeps each generator's prompt purpose-built (planning / exercise / grading).
2. **`generation_backend=fake` default.** Fake generators return deterministic, believable canned output with **no model call** — so CI is green and the demo runs end-to-end with zero Azure. `live` flips on Azure OpenAI structured output. Same discipline as Spec 1/2.
3. **`live` generators' JSON parsing is unit-tested without Azure** by injecting a tiny stub `ChatModel` that yields canned JSON `TextDelta`s — so the parse-and-persist path is covered in CI; only the real Azure round-trip is gated.
4. **`order` is a SQL reserved word** → the `PlanStep` ordering column is named `step_order` (Python field + DB column), not `order`. (Deviates from the design doc's `order` label; same meaning.)
5. **One `EmployeeProfile` per (user, org) in v1** (the design allows per-role; we simplify to match the singular `/users/{userId}/profile` endpoints). Re-generating a plan supersedes the prior one (`status=superseded`).
6. **Synchronous generation** (no SSE) — generation is short; the UI shows a spinner. (If real latency > 15s later, reuse Spec 2's SSE plumbing.)

## File structure

```
apps/api/src/continuum_api/
├── settings.py                          # + generation_backend, plan step bounds
├── models/
│   ├── employee_profile.py  onboarding_plan.py  plan_step.py  exercise.py  exercise_submission.py
│   └── __init__.py                      # export all 5
├── onboarding/
│   ├── __init__.py
│   ├── types.py                         # GeneratedStep/Plan/Exercise, GradeResult + Protocols
│   ├── fake.py                          # Fake{Plan,Exercise}Generator + FakeGradingAgent
│   ├── live.py                          # Live generators (ChatModel + retrieve + JSON), gated
│   └── factory.py                       # settings-driven build_generators()
├── repos/onboarding.py                  # 5 repos
├── services/onboarding.py               # OnboardingService (composition + progress)
├── routes/onboarding.py                 # FastAPI internal endpoints
alembic/versions/0004_onboarding.py
apps/web/src/app/api/bff/me/[...path]/route.ts   # BFF proxy for /me/*
apps/web/src/components/onboarding-dashboard.tsx
apps/web/src/app/onboarding/page.tsx
apps/web/src/lib/onboarding-api.ts        # typed client helpers (browser)
tests/fakes.py                            # shared FakeMentorAgent-style stub ChatModel (for live-parser test)
```

---

## Task 1: Settings

**Files:** Modify `apps/api/src/continuum_api/settings.py`

- [ ] **Step 1: Add fields** to the `Settings` class (keep all existing; append after the mentor fields):
```python
    # Onboarding generation backend — fake = deterministic canned (no Azure), default.
    generation_backend: Literal["fake", "live"] = "fake"
    onboarding_min_steps: int = 6
    onboarding_max_steps: int = 8
```

- [ ] **Step 2: Verify** `cd /home/skkippie/work/continuum/apps/api && uv run python -c "from continuum_api.settings import settings; print(settings.generation_backend, settings.onboarding_min_steps)"` → `fake 6`. `uv run ruff check .` → clean.

- [ ] **Step 3: Commit**
```bash
cd /home/skkippie/work/continuum
git add apps/api/src/continuum_api/settings.py
git commit -m "feat(onboarding): generation backend setting (fake default) + step bounds

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Domain models

**Files:** Create `models/{employee_profile,onboarding_plan,plan_step,exercise,exercise_submission}.py`; modify `models/__init__.py`; create `tests/test_models_onboarding.py`

- [ ] **Step 1: Write the failing test** `tests/test_models_onboarding.py`:
```python
from continuum_api.models import (
    EmployeeProfile, Exercise, ExerciseSubmission, OnboardingPlan, PlanStep,
)


def test_onboarding_tablenames():
    assert EmployeeProfile.__tablename__ == "employee_profile"
    assert OnboardingPlan.__tablename__ == "onboarding_plan"
    assert PlanStep.__tablename__ == "plan_step"
    assert Exercise.__tablename__ == "exercise"
    assert ExerciseSubmission.__tablename__ == "exercise_submission"


def test_defaults():
    p = OnboardingPlan(employee_profile_id="e1", successor_id="s1", title="t")
    assert p.status == "generating"
    s = PlanStep(plan_id="p1", step_order=1, title="t", description="d")
    assert s.status == "not_started"
    sub = ExerciseSubmission(exercise_id="x1", user_id="u1", answer="a")
    assert sub.score is None
```

- [ ] **Step 2: Run, confirm fail** `cd /home/skkippie/work/continuum/apps/api && uv run pytest tests/test_models_onboarding.py -v` → ImportError.

- [ ] **Step 3: Create `models/employee_profile.py`**:
```python
from datetime import date, datetime

from sqlmodel import Field, SQLModel


class EmployeeProfile(SQLModel, table=True):
    __tablename__ = "employee_profile"

    id: str = Field(primary_key=True)
    user_id: str = Field(index=True)  # Better Auth user (no cross-ORM FK)
    org_id: str = Field(index=True)
    role_id: str = Field(index=True)
    experience_level: str = Field(default="mid")  # entry | mid | senior
    start_date: date | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

- [ ] **Step 4: Create `models/onboarding_plan.py`**:
```python
from datetime import datetime

from sqlmodel import Field, SQLModel


class OnboardingPlan(SQLModel, table=True):
    __tablename__ = "onboarding_plan"

    id: str = Field(primary_key=True)
    employee_profile_id: str = Field(index=True)
    successor_id: str = Field(index=True)
    title: str = Field(default="")
    status: str = Field(default="generating")  # generating | ready | failed | superseded
    error: str = Field(default="")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    # set by the service whenever the plan row changes
    updated_at: datetime = Field(default_factory=datetime.utcnow)
```

- [ ] **Step 5: Create `models/plan_step.py`** (`step_order`, not `order` — reserved word; `topic_tags` JSONB):
```python
from datetime import datetime

from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class PlanStep(SQLModel, table=True):
    __tablename__ = "plan_step"

    id: str = Field(primary_key=True)
    plan_id: str = Field(index=True)
    step_order: int  # 1-indexed, contiguous
    title: str
    description: str = Field(default="")
    topic_tags: list[str] = Field(default_factory=list, sa_column=Column(JSONB))
    status: str = Field(default="not_started")  # not_started | in_progress | complete
    completed_at: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

- [ ] **Step 6: Create `models/exercise.py`**:
```python
from datetime import datetime

from sqlmodel import Field, SQLModel


class Exercise(SQLModel, table=True):
    __tablename__ = "exercise"

    id: str = Field(primary_key=True)
    step_id: str = Field(index=True)
    prompt: str
    rubric: str = Field(default="")  # private grading guide — never returned to the employee
    status: str = Field(default="ready")  # ready | failed
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

- [ ] **Step 7: Create `models/exercise_submission.py`**:
```python
from datetime import datetime

from sqlmodel import Field, SQLModel


class ExerciseSubmission(SQLModel, table=True):
    __tablename__ = "exercise_submission"

    id: str = Field(primary_key=True)
    exercise_id: str = Field(index=True)
    user_id: str = Field(index=True)
    answer: str
    score: int | None = None  # 0–100
    feedback: str | None = None
    graded_at: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

- [ ] **Step 8: Update `models/__init__.py`** — add the 5 imports + `__all__` entries (keep all existing capture/mentor/app_info exports; `__all__` alphabetical). Final `__all__`:
```python
__all__ = [
    "AppInfo",
    "Conversation",
    "Document",
    "EmployeeProfile",
    "Exercise",
    "ExerciseSubmission",
    "IngestionJob",
    "KnowledgeSource",
    "Message",
    "OnboardingPlan",
    "PlanStep",
    "Role",
    "Successor",
]
```
(Add the matching `from continuum_api.models.<module> import <Class>` lines in alphabetical order alongside the existing imports.)

- [ ] **Step 9: Run, confirm pass** `cd /home/skkippie/work/continuum/apps/api && uv run pytest tests/test_models_onboarding.py -v` → 2 passed. Full suite `uv run pytest -q` → all pass. `uv run ruff check .` → clean.

- [ ] **Step 10: Commit**
```bash
cd /home/skkippie/work/continuum
git add apps/api/src/continuum_api/models apps/api/tests/test_models_onboarding.py
git commit -m "feat(onboarding): EmployeeProfile/OnboardingPlan/PlanStep/Exercise/ExerciseSubmission models

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Alembic 0004 — onboarding tables

**Files:** Create `alembic/versions/0004_onboarding.py`; modify `alembic/env.py` (`_MANAGED_TABLES`)

- [ ] **Step 1: Add the 5 tables to `_MANAGED_TABLES`** in `alembic/env.py` (keep all existing — should currently have the 8 from Spec 0–2). Add: `"employee_profile"`, `"onboarding_plan"`, `"plan_step"`, `"exercise"`, `"exercise_submission"`.

- [ ] **Step 2: Hand-write `alembic/versions/0004_onboarding.py`** (`down_revision` = the `revision` in `0003_mentor.py`, which is `"0003_mentor"`):
```python
"""onboarding: employee_profile, onboarding_plan, plan_step, exercise, exercise_submission"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0004_onboarding"
down_revision = "0003_mentor"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "employee_profile",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("user_id", sa.String, nullable=False, index=True),
        sa.Column("org_id", sa.String, nullable=False, index=True),
        sa.Column("role_id", sa.String, nullable=False, index=True),
        sa.Column("experience_level", sa.String, nullable=False, server_default="mid"),
        sa.Column("start_date", sa.Date, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_table(
        "onboarding_plan",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("employee_profile_id", sa.String, nullable=False, index=True),
        sa.Column("successor_id", sa.String, nullable=False, index=True),
        sa.Column("title", sa.String, nullable=False, server_default=""),
        sa.Column("status", sa.String, nullable=False, server_default="generating"),
        sa.Column("error", sa.String, nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )
    op.create_table(
        "plan_step",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("plan_id", sa.String, nullable=False, index=True),
        sa.Column("step_order", sa.Integer, nullable=False),
        sa.Column("title", sa.String, nullable=False),
        sa.Column("description", sa.String, nullable=False, server_default=""),
        sa.Column("topic_tags", JSONB, nullable=True),
        sa.Column("status", sa.String, nullable=False, server_default="not_started"),
        sa.Column("completed_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_table(
        "exercise",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("step_id", sa.String, nullable=False, index=True),
        sa.Column("prompt", sa.String, nullable=False),
        sa.Column("rubric", sa.String, nullable=False, server_default=""),
        sa.Column("status", sa.String, nullable=False, server_default="ready"),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_table(
        "exercise_submission",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("exercise_id", sa.String, nullable=False, index=True),
        sa.Column("user_id", sa.String, nullable=False, index=True),
        sa.Column("answer", sa.String, nullable=False),
        sa.Column("score", sa.Integer, nullable=True),
        sa.Column("feedback", sa.String, nullable=True),
        sa.Column("graded_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("exercise_submission")
    op.drop_table("exercise")
    op.drop_table("plan_step")
    op.drop_table("onboarding_plan")
    op.drop_table("employee_profile")
```
(ruff may reorder imports / want a `# noqa: I001` on the `op` import — match `0003_mentor.py`'s style; run `uv run ruff check .` and fix any nit.)

- [ ] **Step 3: Apply + verify coexistence**:
```bash
cd /home/skkippie/work/continuum/apps/api && uv run alembic upgrade head
cd /home/skkippie/work/continuum && docker compose exec -T postgres psql -U continuum -d continuum -c "\dt"
```
Expected: 7 Better Auth + `app_info` + 5 capture + 2 mentor + the 5 new onboarding tables + `alembic_version` (= 21). **If ANY Better Auth table is gone → STOP, BLOCKED.**

- [ ] **Step 4: Verify reversibility** `uv run alembic downgrade -1` → the 5 onboarding tables gone, rest intact; `uv run alembic upgrade head` again. Leave at head.

- [ ] **Step 5: Tests green** `cd /home/skkippie/work/continuum/apps/api && uv run pytest -q` → all pass. `uv run ruff check .` → clean.

- [ ] **Step 6: Commit**
```bash
cd /home/skkippie/work/continuum
git add apps/api/alembic
git commit -m "feat(onboarding): alembic 0004 creates onboarding tables (Better Auth intact)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Generation types + generator Protocols

**Files:** Create `onboarding/__init__.py`, `onboarding/types.py`

- [ ] **Step 1: Create `onboarding/types.py`**:
```python
from collections.abc import Awaitable
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class GeneratedStep:
    title: str
    description: str
    topic_tags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class GeneratedPlan:
    title: str
    steps: list[GeneratedStep]


@dataclass(frozen=True)
class GeneratedExercise:
    prompt: str
    rubric: str


@dataclass(frozen=True)
class GradeResult:
    score: int  # 0–100
    feedback: str


class GenerationError(RuntimeError):
    """Raised when a generator's model call or output parsing fails."""


class PlanGenerator(Protocol):
    def generate(
        self, *, role_title: str, experience_level: str, knowledge_base_name: str
    ) -> Awaitable[GeneratedPlan]: ...


class ExerciseGenerator(Protocol):
    def generate(
        self, *, step_title: str, step_description: str, topic_tags: list[str],
        knowledge_base_name: str,
    ) -> Awaitable[GeneratedExercise]: ...


class GradingAgent(Protocol):
    def grade(self, *, prompt: str, rubric: str, answer: str) -> Awaitable[GradeResult]: ...
```
(The Protocol methods are typed `-> Awaitable[...]` because implementations are `async def`; this is the precise way to declare an awaitable-returning Protocol method. Generators take primitives — role title, kb name, etc. — NOT ORM rows, so they stay decoupled from the DB.)

- [ ] **Step 2: Create `onboarding/__init__.py`**:
```python
# onboarding package
```

- [ ] **Step 3: Verify** `cd /home/skkippie/work/continuum/apps/api && uv run python -c "from continuum_api.onboarding.types import GeneratedPlan, GeneratedStep, GeneratedExercise, GradeResult, PlanGenerator, ExerciseGenerator, GradingAgent, GenerationError; print('ok')"` → `ok`. `uv run ruff check .` → clean.

- [ ] **Step 4: Commit**
```bash
cd /home/skkippie/work/continuum
git add apps/api/src/continuum_api/onboarding
git commit -m "feat(onboarding): generation types + PlanGenerator/ExerciseGenerator/GradingAgent protocols

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Fake generators (deterministic) — TDD

**Files:** Create `onboarding/fake.py`, `tests/test_fake_generators.py`

The fakes return deterministic, believable output with NO model call — so CI + the demo run with no Azure. Experience level visibly changes plan breadth (acceptance #2).

- [ ] **Step 1: Write failing test** `tests/test_fake_generators.py`:
```python
import pytest

from continuum_api.onboarding.fake import (
    FakeExerciseGenerator, FakeGradingAgent, FakePlanGenerator,
)


@pytest.mark.asyncio
async def test_plan_steps_scale_with_experience():
    gen = FakePlanGenerator()
    entry = await gen.generate(role_title="Support Lead", experience_level="entry",
                               knowledge_base_name="kb")
    senior = await gen.generate(role_title="Support Lead", experience_level="senior",
                                knowledge_base_name="kb")
    assert 6 <= len(entry.steps) <= 8
    # entry-level gets a broader/more foundational plan than senior
    assert len(entry.steps) > len(senior.steps)
    assert all(s.topic_tags for s in entry.steps)
    assert entry.title


@pytest.mark.asyncio
async def test_exercise_has_prompt_and_rubric():
    ex = await FakeExerciseGenerator().generate(
        step_title="Refund policy", step_description="learn refunds",
        topic_tags=["refunds"], knowledge_base_name="kb")
    assert ex.prompt and ex.rubric


@pytest.mark.asyncio
async def test_grading_scores_by_answer_substance():
    grader = FakeGradingAgent()
    thin = await grader.grade(prompt="p", rubric="r", answer="dunno")
    rich = await grader.grade(prompt="p", rubric="r",
                              answer=" ".join(["word"] * 40))
    assert 0 <= thin.score <= 100 and 0 <= rich.score <= 100
    assert rich.score > thin.score
    assert thin.feedback and rich.feedback
```

- [ ] **Step 2: Run, confirm fail** `cd /home/skkippie/work/continuum/apps/api && uv run pytest tests/test_fake_generators.py -v` → ImportError.

- [ ] **Step 3: Create `onboarding/fake.py`**:
```python
from continuum_api.onboarding.types import (
    GeneratedExercise, GeneratedPlan, GeneratedStep, GradeResult,
)

_CORE_STEPS = [
    ("Orientation & context", "context"),
    ("Core responsibilities", "responsibilities"),
    ("Key processes & policies", "processes"),
    ("Tools & systems", "tools"),
    ("Stakeholders & communication", "stakeholders"),
    ("First independent task", "delivery"),
]


class FakePlanGenerator:
    async def generate(
        self, *, role_title: str, experience_level: str, knowledge_base_name: str
    ) -> GeneratedPlan:
        items = list(_CORE_STEPS)
        if experience_level == "entry":
            items = [("Welcome & glossary", "glossary"), *items, ("Foundations recap", "foundations")]
        elif experience_level == "senior":
            items = items[1:]  # seniors skip the orientation/context ramp
        steps = [
            GeneratedStep(
                title=title,
                description=f"Learn {title.lower()} for the {role_title} role.",
                topic_tags=[tag],
            )
            for title, tag in items
        ]
        return GeneratedPlan(title=f"Onboarding plan — {role_title}", steps=steps)


class FakeExerciseGenerator:
    async def generate(
        self, *, step_title: str, step_description: str, topic_tags: list[str],
        knowledge_base_name: str,
    ) -> GeneratedExercise:
        return GeneratedExercise(
            prompt=(
                f"In your own words, explain {step_title.lower()} and why it matters "
                f"for this role. Give one concrete example."
            ),
            rubric=(
                f"- correctly describes {step_title.lower()}\n"
                "- explains why it matters\n"
                "- provides a concrete, relevant example"
            ),
        )


class FakeGradingAgent:
    async def grade(self, *, prompt: str, rubric: str, answer: str) -> GradeResult:
        # Deterministic: substance proxied by word count, capped at 100.
        score = max(0, min(100, len(answer.split()) * 5))
        feedback = (
            "Clear, concrete answer that covers the key points."
            if score >= 60
            else "Add more detail and a concrete example to strengthen this."
        )
        return GradeResult(score=score, feedback=feedback)
```

- [ ] **Step 4: Run, confirm pass** `cd /home/skkippie/work/continuum/apps/api && uv run pytest tests/test_fake_generators.py -v` → 3 passed. `uv run ruff check .` → clean.

- [ ] **Step 5: Commit**
```bash
cd /home/skkippie/work/continuum
git add apps/api/src/continuum_api/onboarding/fake.py apps/api/tests/test_fake_generators.py
git commit -m "feat(onboarding): deterministic fake generators (plan/exercise/grading)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Repositories — TDD

**Files:** Create `repos/onboarding.py`, `tests/test_onboarding_repos.py`

- [ ] **Step 1: Write failing test** `tests/test_onboarding_repos.py`:
```python
import uuid

from sqlmodel import Session

from continuum_api.db import engine
from continuum_api.models import EmployeeProfile
from continuum_api.repos.onboarding import EmployeeProfileRepo


def test_profile_create_and_get_by_user():
    with Session(engine) as s:
        repo = EmployeeProfileRepo(s)
        uid = f"u-{uuid.uuid4().hex[:8]}"
        repo.create(EmployeeProfile(id=f"e-{uuid.uuid4().hex[:8]}", user_id=uid,
                                    org_id="o1", role_id="r1"))
        s.commit()
        got = repo.for_user(uid, "o1")
        assert got is not None and got.role_id == "r1"
```

- [ ] **Step 2: Run, confirm fail** → ImportError.

- [ ] **Step 3: Create `repos/onboarding.py`** (thin repos; callers own commit; ordered queries):
```python
from sqlmodel import Session, select

from continuum_api.models import (
    EmployeeProfile, Exercise, ExerciseSubmission, OnboardingPlan, PlanStep,
)


class EmployeeProfileRepo:
    def __init__(self, session: Session) -> None:
        self._s = session

    def create(self, profile: EmployeeProfile) -> EmployeeProfile:
        self._s.add(profile)
        return profile

    def get(self, profile_id: str) -> EmployeeProfile | None:
        return self._s.get(EmployeeProfile, profile_id)

    def for_user(self, user_id: str, org_id: str) -> EmployeeProfile | None:
        return self._s.exec(
            select(EmployeeProfile)
            .where(EmployeeProfile.user_id == user_id, EmployeeProfile.org_id == org_id)
            .order_by(EmployeeProfile.created_at)
        ).first()


class OnboardingPlanRepo:
    def __init__(self, session: Session) -> None:
        self._s = session

    def create(self, plan: OnboardingPlan) -> OnboardingPlan:
        self._s.add(plan)
        return plan

    def get(self, plan_id: str) -> OnboardingPlan | None:
        return self._s.get(OnboardingPlan, plan_id)

    def latest_ready(self, employee_profile_id: str) -> OnboardingPlan | None:
        return self._s.exec(
            select(OnboardingPlan)
            .where(OnboardingPlan.employee_profile_id == employee_profile_id,
                   OnboardingPlan.status == "ready")
            .order_by(OnboardingPlan.created_at.desc())
        ).first()

    def active(self, employee_profile_id: str) -> list[OnboardingPlan]:
        return list(self._s.exec(
            select(OnboardingPlan).where(
                OnboardingPlan.employee_profile_id == employee_profile_id,
                OnboardingPlan.status.in_(("generating", "ready")),
            )
        ))


class PlanStepRepo:
    def __init__(self, session: Session) -> None:
        self._s = session

    def create(self, step: PlanStep) -> PlanStep:
        self._s.add(step)
        return step

    def get(self, step_id: str) -> PlanStep | None:
        return self._s.get(PlanStep, step_id)

    def for_plan(self, plan_id: str) -> list[PlanStep]:
        return list(self._s.exec(
            select(PlanStep).where(PlanStep.plan_id == plan_id).order_by(PlanStep.step_order)
        ))


class ExerciseRepo:
    def __init__(self, session: Session) -> None:
        self._s = session

    def create(self, exercise: Exercise) -> Exercise:
        self._s.add(exercise)
        return exercise

    def get(self, exercise_id: str) -> Exercise | None:
        return self._s.get(Exercise, exercise_id)

    def for_step(self, step_id: str) -> Exercise | None:
        return self._s.exec(
            select(Exercise).where(Exercise.step_id == step_id)
            .order_by(Exercise.created_at.desc())
        ).first()

    def delete_for_step(self, step_id: str) -> None:
        for ex in self._s.exec(select(Exercise).where(Exercise.step_id == step_id)):
            self._s.delete(ex)


class ExerciseSubmissionRepo:
    def __init__(self, session: Session) -> None:
        self._s = session

    def create(self, submission: ExerciseSubmission) -> ExerciseSubmission:
        self._s.add(submission)
        return submission

    def latest_for_exercise(self, exercise_id: str) -> ExerciseSubmission | None:
        return self._s.exec(
            select(ExerciseSubmission).where(ExerciseSubmission.exercise_id == exercise_id)
            .order_by(ExerciseSubmission.created_at.desc())
        ).first()
```

- [ ] **Step 4: Run, confirm pass** `cd /home/skkippie/work/continuum/apps/api && uv run pytest tests/test_onboarding_repos.py -v` → 1 passed. Full suite green. `uv run ruff check .` → clean.

- [ ] **Step 5: Commit**
```bash
cd /home/skkippie/work/continuum
git add apps/api/src/continuum_api/repos/onboarding.py apps/api/tests/test_onboarding_repos.py
git commit -m "feat(onboarding): SQLModel repositories for onboarding entities

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Generator factory (settings-driven)

**Files:** Create `onboarding/factory.py`, `tests/test_generator_factory.py`

- [ ] **Step 1: Write failing test** `tests/test_generator_factory.py`:
```python
from continuum_api.onboarding.factory import build_generators
from continuum_api.onboarding.fake import (
    FakeExerciseGenerator, FakeGradingAgent, FakePlanGenerator,
)


def test_default_generators_are_fake():
    plan, exercise, grading = build_generators()
    assert isinstance(plan, FakePlanGenerator)
    assert isinstance(exercise, FakeExerciseGenerator)
    assert isinstance(grading, FakeGradingAgent)
```

- [ ] **Step 2: Run, confirm fail** → ImportError.

- [ ] **Step 3: Create `onboarding/factory.py`** (lazy live import — `live.py` exists in Task 9; the factory must import it only on the live branch):
```python
from continuum_api.onboarding.types import ExerciseGenerator, GradingAgent, PlanGenerator
from continuum_api.settings import settings


def build_generators() -> tuple[PlanGenerator, ExerciseGenerator, GradingAgent]:
    if settings.generation_backend == "live":
        from continuum_api.agent.factory import build_chat_model
        from continuum_api.knowledge.factory import build_blob_store, build_knowledge
        from continuum_api.onboarding.live import (
            LiveExerciseGenerator, LiveGradingAgent, LivePlanGenerator,
        )

        chat = build_chat_model()
        knowledge = build_knowledge(build_blob_store())
        return (
            LivePlanGenerator(chat, knowledge),
            LiveExerciseGenerator(chat, knowledge),
            LiveGradingAgent(chat),
        )
    from continuum_api.onboarding.fake import (
        FakeExerciseGenerator, FakeGradingAgent, FakePlanGenerator,
    )

    return FakePlanGenerator(), FakeExerciseGenerator(), FakeGradingAgent()
```

- [ ] **Step 4: Run, confirm pass** → 1 passed. `uv run ruff check .` → clean.

- [ ] **Step 5: Commit**
```bash
cd /home/skkippie/work/continuum
git add apps/api/src/continuum_api/onboarding/factory.py apps/api/tests/test_generator_factory.py
git commit -m "feat(onboarding): settings-driven generator factory (fake default, lazy live import)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: OnboardingService (composition) — TDD vs fakes

**Files:** Create `services/onboarding.py`, `tests/test_onboarding_service.py`

`OnboardingService` owns the flow: profile CRUD, plan generation (calls `PlanGenerator` → persists `OnboardingPlan` + `PlanStep`s, supersedes the prior plan), step status, exercise generation, submit+grade, and the progress summary. It takes a `Session` + the three generators (injected → testable with fakes). Authorization is by `org_id` ownership through the profile chain.

- [ ] **Step 1: Write failing test** `tests/test_onboarding_service.py`:
```python
import uuid

import pytest
from sqlmodel import Session

from continuum_api.db import engine
from continuum_api.models import Role, Successor
from continuum_api.onboarding.fake import (
    FakeExerciseGenerator, FakeGradingAgent, FakePlanGenerator,
)
from continuum_api.services.onboarding import OnboardingService


def _svc(session: Session) -> OnboardingService:
    return OnboardingService(session, FakePlanGenerator(), FakeExerciseGenerator(),
                             FakeGradingAgent())


def _seed_role_successor(session: Session, org: str) -> str:
    role_id = f"r-{uuid.uuid4().hex[:8]}"
    session.add(Role(id=role_id, org_id=org, title="Support Lead"))
    session.add(Successor(id=f"s-{uuid.uuid4().hex[:8]}", role_id=role_id,
                          knowledge_base_name="kb", status="ready"))
    session.commit()
    return role_id


@pytest.mark.asyncio
async def test_full_onboarding_flow():
    with Session(engine) as session:
        org = f"o-{uuid.uuid4().hex[:8]}"
        user = f"u-{uuid.uuid4().hex[:8]}"
        role_id = _seed_role_successor(session, org)
        svc = _svc(session)

        profile = svc.create_profile(user_id=user, org_id=org, role_id=role_id,
                                     experience_level="entry")
        session.commit()
        plan = await svc.generate_plan(user_id=user, org_id=org)
        session.commit()
        assert plan.status == "ready"
        steps = svc.plan_steps(plan.id)
        assert 6 <= len(steps) <= 10
        assert [s.step_order for s in steps] == list(range(1, len(steps) + 1))

        first = steps[0]
        svc.set_step_status(first.id, org_id=org, status="complete")
        session.commit()
        ex = await svc.generate_exercise(first.id, org_id=org)
        session.commit()
        assert ex.prompt
        result = await svc.submit_and_grade(ex.id, user_id=user, org_id=org,
                                            answer=" ".join(["solid"] * 30))
        session.commit()
        assert 0 <= result.score <= 100 and result.feedback

        summary = svc.progress(user_id=user, org_id=org)
        assert summary.total_steps == len(steps)
        assert summary.completed_steps == 1
        scored = [sp for sp in summary.steps if sp.exercise_score is not None]
        assert scored and scored[0].exercise_score == result.score


@pytest.mark.asyncio
async def test_generate_plan_409_when_successor_not_ready():
    with Session(engine) as session:
        org = f"o-{uuid.uuid4().hex[:8]}"
        user = f"u-{uuid.uuid4().hex[:8]}"
        role_id = f"r-{uuid.uuid4().hex[:8]}"
        session.add(Role(id=role_id, org_id=org, title="X"))
        session.add(Successor(id=f"s-{uuid.uuid4().hex[:8]}", role_id=role_id,
                              knowledge_base_name="kb", status="provisioning"))
        session.commit()
        svc = _svc(session)
        svc.create_profile(user_id=user, org_id=org, role_id=role_id, experience_level="mid")
        session.commit()
        with pytest.raises(SuccessorNotReady):
            await svc.generate_plan(user_id=user, org_id=org)
```
(Add `from continuum_api.services.onboarding import OnboardingService, SuccessorNotReady` to the imports — `SuccessorNotReady` is defined in Step 3.)

- [ ] **Step 2: Run, confirm fail** → ImportError.

- [ ] **Step 3: Create `services/onboarding.py`**:
```python
import uuid
from dataclasses import dataclass
from datetime import date, datetime

from sqlmodel import Session

from continuum_api.models import (
    EmployeeProfile, Exercise, ExerciseSubmission, OnboardingPlan, PlanStep, Role, Successor,
)
from continuum_api.onboarding.types import (
    ExerciseGenerator, GradeResult, GradingAgent, PlanGenerator,
)
from continuum_api.repos.capture import RoleRepo, SuccessorRepo
from continuum_api.repos.onboarding import (
    EmployeeProfileRepo, ExerciseRepo, ExerciseSubmissionRepo, OnboardingPlanRepo, PlanStepRepo,
)


class SuccessorNotReady(RuntimeError):
    """The role's Successor knowledge base is not ready for generation."""


@dataclass
class StepProgress:
    step_id: str
    title: str
    status: str
    exercise_score: int | None


@dataclass
class ProgressSummary:
    total_steps: int
    completed_steps: int
    steps: list[StepProgress]


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


class OnboardingService:
    def __init__(
        self, session: Session, plans: PlanGenerator, exercises: ExerciseGenerator,
        grading: GradingAgent,
    ) -> None:
        self._s = session
        self._plan_gen = plans
        self._exercise_gen = exercises
        self._grading = grading
        self.profiles = EmployeeProfileRepo(session)
        self.plans = OnboardingPlanRepo(session)
        self.steps = PlanStepRepo(session)
        self.exercises = ExerciseRepo(session)
        self.submissions = ExerciseSubmissionRepo(session)
        self.roles = RoleRepo(session)
        self.successors = SuccessorRepo(session)

    # --- profile --------------------------------------------------------
    def create_profile(
        self, *, user_id: str, org_id: str, role_id: str, experience_level: str,
        start_date: date | None = None,
    ) -> EmployeeProfile:
        role = self.roles.get(role_id)
        if role is None or role.org_id != org_id:
            raise LookupError("role not found in org")
        existing = self.profiles.for_user(user_id, org_id)
        if existing is not None:
            return existing  # idempotent: one profile per user+org in v1
        profile = self.profiles.create(EmployeeProfile(
            id=_id("emp"), user_id=user_id, org_id=org_id, role_id=role_id,
            experience_level=experience_level, start_date=start_date,
        ))
        self._s.flush()
        return profile

    def get_profile(self, *, user_id: str, org_id: str) -> EmployeeProfile | None:
        return self.profiles.for_user(user_id, org_id)

    # --- plan -----------------------------------------------------------
    async def generate_plan(self, *, user_id: str, org_id: str) -> OnboardingPlan:
        profile = self.profiles.for_user(user_id, org_id)
        if profile is None:
            raise LookupError("employee profile not found")
        successor = self.successors.by_role(profile.role_id)
        role = self.roles.get(profile.role_id)
        if successor is None or role is None:
            raise LookupError("role/successor not found")
        if successor.status != "ready":
            raise SuccessorNotReady("successor not ready")

        # supersede any active plan
        for old in self.plans.active(profile.id):
            old.status = "superseded"
            old.updated_at = datetime.utcnow()

        plan = self.plans.create(OnboardingPlan(
            id=_id("plan"), employee_profile_id=profile.id, successor_id=successor.id,
            status="generating",
        ))
        self._s.flush()
        try:
            generated = await self._plan_gen.generate(
                role_title=role.title, experience_level=profile.experience_level,
                knowledge_base_name=successor.knowledge_base_name,
            )
        except Exception as exc:  # noqa: BLE001 — record failure, allow retry
            plan.status = "failed"
            plan.error = str(exc)
            plan.updated_at = datetime.utcnow()
            self._s.flush()
            return plan

        plan.title = generated.title
        for i, step in enumerate(generated.steps, start=1):
            self.steps.create(PlanStep(
                id=_id("step"), plan_id=plan.id, step_order=i, title=step.title,
                description=step.description, topic_tags=list(step.topic_tags),
            ))
        plan.status = "ready"
        plan.updated_at = datetime.utcnow()
        self._s.flush()
        return plan

    def current_plan(self, *, user_id: str, org_id: str) -> OnboardingPlan | None:
        profile = self.profiles.for_user(user_id, org_id)
        return self.plans.latest_ready(profile.id) if profile else None

    def plan_steps(self, plan_id: str) -> list[PlanStep]:
        return self.steps.for_plan(plan_id)

    # --- ownership helper ----------------------------------------------
    def _owned_step(self, step_id: str, org_id: str) -> PlanStep:
        step = self.steps.get(step_id)
        if step is None:
            raise LookupError("step not found")
        plan = self.plans.get(step.plan_id)
        profile = self.profiles.get(plan.employee_profile_id) if plan else None
        if profile is None or profile.org_id != org_id:
            raise LookupError("step not found")  # 404, no existence leak
        return step

    def set_step_status(self, step_id: str, *, org_id: str, status: str) -> PlanStep:
        step = self._owned_step(step_id, org_id)
        step.status = status
        step.completed_at = datetime.utcnow() if status == "complete" else None
        self._s.flush()
        return step

    # --- exercise -------------------------------------------------------
    async def generate_exercise(self, step_id: str, *, org_id: str) -> Exercise:
        step = self._owned_step(step_id, org_id)
        plan = self.plans.get(step.plan_id)
        successor = self.successors.get(plan.successor_id)
        self.exercises.delete_for_step(step_id)  # regenerate replaces
        self._s.flush()
        try:
            generated = await self._exercise_gen.generate(
                step_title=step.title, step_description=step.description,
                topic_tags=list(step.topic_tags),
                knowledge_base_name=successor.knowledge_base_name,
            )
        except Exception as exc:  # noqa: BLE001
            ex = self.exercises.create(Exercise(
                id=_id("ex"), step_id=step_id, prompt="", rubric="", status="failed"))
            ex.prompt = f"generation failed: {exc}"
            self._s.flush()
            return ex
        ex = self.exercises.create(Exercise(
            id=_id("ex"), step_id=step_id, prompt=generated.prompt, rubric=generated.rubric,
            status="ready"))
        self._s.flush()
        return ex

    def get_exercise(self, step_id: str, *, org_id: str) -> Exercise | None:
        self._owned_step(step_id, org_id)
        return self.exercises.for_step(step_id)

    # --- submission + grading ------------------------------------------
    async def submit_and_grade(
        self, exercise_id: str, *, user_id: str, org_id: str, answer: str
    ) -> GradeResult:
        exercise = self.exercises.get(exercise_id)
        if exercise is None:
            raise LookupError("exercise not found")
        self._owned_step(exercise.step_id, org_id)  # authorize via the step's org
        submission = self.submissions.create(ExerciseSubmission(
            id=_id("sub"), exercise_id=exercise_id, user_id=user_id, answer=answer))
        result = await self._grading.grade(
            prompt=exercise.prompt, rubric=exercise.rubric, answer=answer)
        submission.score = result.score
        submission.feedback = result.feedback
        submission.graded_at = datetime.utcnow()
        self._s.flush()
        return result

    # --- progress -------------------------------------------------------
    def progress(self, *, user_id: str, org_id: str) -> ProgressSummary:
        plan = self.current_plan(user_id=user_id, org_id=org_id)
        if plan is None:
            return ProgressSummary(total_steps=0, completed_steps=0, steps=[])
        steps = self.steps.for_plan(plan.id)
        out: list[StepProgress] = []
        completed = 0
        for step in steps:
            if step.status == "complete":
                completed += 1
            exercise = self.exercises.for_step(step.id)
            score = None
            if exercise is not None:
                latest = self.submissions.latest_for_exercise(exercise.id)
                score = latest.score if latest else None
            out.append(StepProgress(step_id=step.id, title=step.title,
                                    status=step.status, exercise_score=score))
        return ProgressSummary(total_steps=len(steps), completed_steps=completed, steps=out)
```

- [ ] **Step 4: Run, confirm pass** `cd /home/skkippie/work/continuum/apps/api && uv run pytest tests/test_onboarding_service.py -v` → 2 passed. Full suite green. `uv run ruff check .` → clean.

- [ ] **Step 5: Commit**
```bash
cd /home/skkippie/work/continuum
git add apps/api/src/continuum_api/services/onboarding.py apps/api/tests/test_onboarding_service.py
git commit -m "feat(onboarding): OnboardingService orchestrates plan/exercise/grade/progress (TDD vs fakes)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Live generators (real, structured output) — gated integration

**Files:** Create `onboarding/live.py`, `tests/fakes.py`, `tests/test_live_generators_parse.py`, `tests/test_onboarding_integration.py`

Live generators ground on `FoundryKnowledge.retrieve` + one structured completion via the `ChatModel` (Spec 2). They parse JSON from the accumulated stream text. The **parse path is unit-tested with a stub ChatModel** (no Azure); the **real Azure round-trip is gated**.

- [ ] **Step 1: Create `tests/fakes.py`** — a shared stub ChatModel that yields a fixed text (so live-generator parsing is testable without Azure):
```python
from collections.abc import AsyncIterator

from continuum_api.agent.types import ChatMessage, ChatModelEvent, TextDelta, TurnDone


class ScriptedChatModel:
    """A ChatModel stub that streams a fixed response text, ignoring tool calls.

    Used to unit-test the live generators' JSON parsing without Azure.
    """

    def __init__(self, response_text: str) -> None:
        self._text = response_text

    async def stream_turn(
        self, messages: list[ChatMessage], tools: list
    ) -> AsyncIterator[ChatModelEvent]:
        yield TextDelta(text=self._text)
        yield TurnDone(finish_reason="stop")
```

- [ ] **Step 2: Create `onboarding/live.py`**:
```python
import json

from continuum_api.agent.chat_model import ChatModel
from continuum_api.agent.types import ChatMessage, TextDelta
from continuum_api.knowledge.interface import FoundryKnowledge
from continuum_api.onboarding.types import (
    GeneratedExercise, GeneratedPlan, GeneratedStep, GenerationError, GradeResult,
)


async def _complete(chat: ChatModel, system: str, user: str) -> str:
    text = ""
    async for ev in chat.stream_turn(
        [ChatMessage(role="system", content=system), ChatMessage(role="user", content=user)],
        [],  # no tools — single structured completion
    ):
        if isinstance(ev, TextDelta):
            text += ev.text
    return text


def _parse_json(raw: str) -> dict:
    """Tolerant JSON parse: strips ```json fences and leading/trailing prose."""
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("```", 2)[1]
        if s.startswith("json"):
            s = s[4:]
    start, end = s.find("{"), s.rfind("}")
    if start == -1 or end == -1:
        raise GenerationError(f"no JSON object in model output: {raw[:200]!r}")
    try:
        return json.loads(s[start : end + 1])
    except ValueError as exc:
        raise GenerationError(f"invalid JSON from model: {exc}") from exc


class LivePlanGenerator:
    def __init__(self, chat: ChatModel, knowledge: FoundryKnowledge) -> None:
        self._chat = chat
        self._kn = knowledge

    async def generate(
        self, *, role_title: str, experience_level: str, knowledge_base_name: str
    ) -> GeneratedPlan:
        snippets = self._kn.retrieve(
            knowledge_base_name, f"{role_title} responsibilities onboarding key topics", top=8)
        context = "\n\n".join(s.content for s in snippets) or "(no captured knowledge yet)"
        system = (
            "You design onboarding plans grounded ONLY in the provided organizational knowledge. "
            "Respond with a single JSON object and nothing else."
        )
        user = (
            f"Role: {role_title}\nEmployee experience level: {experience_level}\n\n"
            f"Organizational knowledge:\n{context}\n\n"
            "Produce 6–8 ordered onboarding steps tailored to the experience level "
            "(entry = broader/more foundational; senior = more advanced). "
            'JSON shape: {"title": str, "steps": [{"title": str, "description": str, '
            '"topic_tags": [str]}]}. Each description is one sentence; 1–3 topic_tags each.'
        )
        data = _parse_json(await _complete(self._chat, system, user))
        steps = [
            GeneratedStep(title=str(s["title"]), description=str(s.get("description", "")),
                          topic_tags=[str(t) for t in s.get("topic_tags", [])])
            for s in data.get("steps", [])
        ]
        if not steps:
            raise GenerationError("model returned no steps")
        return GeneratedPlan(title=str(data.get("title", f"Onboarding — {role_title}")), steps=steps)


class LiveExerciseGenerator:
    def __init__(self, chat: ChatModel, knowledge: FoundryKnowledge) -> None:
        self._chat = chat
        self._kn = knowledge

    async def generate(
        self, *, step_title: str, step_description: str, topic_tags: list[str],
        knowledge_base_name: str,
    ) -> GeneratedExercise:
        query = f"{step_title} {' '.join(topic_tags)}".strip()
        snippets = self._kn.retrieve(knowledge_base_name, query, top=5)
        context = "\n\n".join(s.content for s in snippets) or "(no captured knowledge yet)"
        system = (
            "You write short practical onboarding exercises grounded ONLY in the provided "
            "knowledge. Respond with a single JSON object and nothing else."
        )
        user = (
            f"Step: {step_title}\n{step_description}\n\nKnowledge:\n{context}\n\n"
            'JSON shape: {"prompt": str, "rubric": str}. prompt = a 2–4 sentence open-ended '
            "question testing practical understanding. rubric = 3–5 bullet grading points "
            "(the employee never sees the rubric)."
        )
        data = _parse_json(await _complete(self._chat, system, user))
        prompt = str(data.get("prompt", "")).strip()
        if not prompt:
            raise GenerationError("model returned an empty exercise prompt")
        return GeneratedExercise(prompt=prompt, rubric=str(data.get("rubric", "")).strip())


class LiveGradingAgent:
    def __init__(self, chat: ChatModel) -> None:
        self._chat = chat

    async def grade(self, *, prompt: str, rubric: str, answer: str) -> GradeResult:
        system = (
            "You grade onboarding exercise answers against a private rubric. "
            "Respond with a single JSON object and nothing else."
        )
        user = (
            f"Exercise: {prompt}\n\nRubric (private):\n{rubric}\n\nEmployee answer:\n{answer}\n\n"
            'JSON shape: {"score": int 0-100, "feedback": str}. feedback = 1–3 sentences of '
            "constructive, specific feedback."
        )
        data = _parse_json(await _complete(self._chat, system, user))
        try:
            score = max(0, min(100, int(data["score"])))
        except (KeyError, ValueError, TypeError) as exc:
            raise GenerationError(f"invalid score from model: {exc}") from exc
        return GradeResult(score=score, feedback=str(data.get("feedback", "")).strip())
```

- [ ] **Step 3: Write the parse unit test** `tests/test_live_generators_parse.py` (no Azure — uses the scripted stub):
```python
import pytest

from continuum_api.knowledge.fake import FakeFoundryKnowledge
from continuum_api.knowledge.local_blob import LocalBlobStore
from continuum_api.onboarding.live import (
    LiveExerciseGenerator, LiveGradingAgent, LivePlanGenerator,
)
from continuum_api.onboarding.types import GenerationError
from tests.fakes import ScriptedChatModel


def _kn(tmp_path):
    blob = LocalBlobStore(root=str(tmp_path))
    c = blob.ensure_container("s1")
    blob.put(c, "d.txt", b"We deploy on Fridays.", "text/plain")
    kn = FakeFoundryKnowledge(blob)
    kn.ensure_knowledge_base("kb")
    kn.ensure_blob_source("kb", c)
    kn.start_indexing("kb")
    return kn


@pytest.mark.asyncio
async def test_plan_parses_fenced_json(tmp_path):
    raw = '```json\n{"title":"P","steps":[{"title":"A","description":"d","topic_tags":["x"]}]}\n```'
    gen = LivePlanGenerator(ScriptedChatModel(raw), _kn(tmp_path))
    plan = await gen.generate(role_title="Lead", experience_level="entry", knowledge_base_name="kb")
    assert plan.title == "P" and plan.steps[0].title == "A" and plan.steps[0].topic_tags == ["x"]


@pytest.mark.asyncio
async def test_plan_raises_on_garbage(tmp_path):
    gen = LivePlanGenerator(ScriptedChatModel("no json here"), _kn(tmp_path))
    with pytest.raises(GenerationError):
        await gen.generate(role_title="Lead", experience_level="mid", knowledge_base_name="kb")


@pytest.mark.asyncio
async def test_grade_clamps_and_parses():
    grader = LiveGradingAgent(ScriptedChatModel('{"score": 142, "feedback": "ok"}'))
    res = await grader.grade(prompt="p", rubric="r", answer="a")
    assert res.score == 100 and res.feedback == "ok"


@pytest.mark.asyncio
async def test_exercise_parses(tmp_path):
    raw = '{"prompt": "Explain X.", "rubric": "- a\\n- b"}'
    gen = LiveExerciseGenerator(ScriptedChatModel(raw), _kn(tmp_path))
    ex = await gen.generate(step_title="X", step_description="d", topic_tags=["x"],
                            knowledge_base_name="kb")
    assert ex.prompt == "Explain X." and ex.rubric
```

- [ ] **Step 4: Write the gated integration test** `tests/test_onboarding_integration.py`:
```python
import os

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_AZURE_INTEGRATION") != "1",
    reason="set RUN_AZURE_INTEGRATION=1 + AZURE_OPENAI_ENDPOINT + AZURE_OPENAI_DEPLOYMENT + "
    "AZURE_SEARCH_ENDPOINT + az login",
)


@pytest.mark.asyncio
async def test_live_plan_and_grade_end_to_end():
    # Requires chat_backend=azure_openai + knowledge_backend=foundry + a ready Successor.
    from continuum_api.agent.factory import build_chat_model
    from continuum_api.knowledge.factory import build_blob_store, build_knowledge
    from continuum_api.onboarding.live import LiveGradingAgent, LivePlanGenerator

    chat = build_chat_model()
    knowledge = build_knowledge(build_blob_store())
    kb = os.environ.get("AZURE_TEST_KB")
    if not kb:
        pytest.skip("AZURE_TEST_KB not set")
    plan = await LivePlanGenerator(chat, knowledge).generate(
        role_title="Support Lead", experience_level="entry", knowledge_base_name=kb)
    assert plan.steps
    grade = await LiveGradingAgent(chat).grade(
        prompt="Explain refunds.", rubric="- mentions approval", answer="Refunds need manager approval.")
    assert 0 <= grade.score <= 100
```

- [ ] **Step 5: Verify** `cd /home/skkippie/work/continuum/apps/api`:
  - `uv run python -c "import continuum_api.onboarding.live; print('imports-ok')"` → ok.
  - `uv run pytest tests/test_live_generators_parse.py -v` → 4 passed.
  - `uv run pytest tests/test_onboarding_integration.py -v` → 1 skipped.
  - Full suite `uv run pytest -q` → all green + skips. `uv run ruff check .` → clean.
  - NOTE: `tests/fakes.py` — confirm pytest does NOT try to collect it as a test module (it has no `test_` functions, so it won't). The live-parser test imports `from tests.fakes import ScriptedChatModel`; ensure `apps/api/tests/` is importable as a package (it works because pytest adds the rootdir; if the import fails, add an empty `apps/api/tests/__init__.py` — check whether one already exists first).

- [ ] **Step 6: Commit**
```bash
cd /home/skkippie/work/continuum
git add apps/api/src/continuum_api/onboarding/live.py apps/api/tests/fakes.py apps/api/tests/test_live_generators_parse.py apps/api/tests/test_onboarding_integration.py
git commit -m "feat(onboarding): live generators (ChatModel + retrieve + JSON) + parse tests + gated IT

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: FastAPI onboarding endpoints — TDD with TestClient

**Files:** Create `routes/onboarding.py`, `tests/test_onboarding_api.py`; modify `main.py`

Endpoints reuse `require_service_token` + `_org` + a new `_user` header dep. Build the service from `get_session` + the generator factory (`generation_backend=fake` in CI). Authorize on org ownership.

- [ ] **Step 1: Write failing test** `tests/test_onboarding_api.py`:
```python
import uuid

from sqlmodel import Session

from continuum_api.db import engine
from continuum_api.models import Role, Successor


def _h(user="u-onb"):
    from continuum_api.settings import settings
    return {"X-Service-Token": settings.api_service_token, "X-Org-Id": "o-onb", "X-User-Id": user}


def _seed_ready_role(org="o-onb"):
    role_id = f"r-{uuid.uuid4().hex[:8]}"
    with Session(engine) as s:
        s.add(Role(id=role_id, org_id=org, title="Support Lead"))
        s.add(Successor(id=f"s-{uuid.uuid4().hex[:8]}", role_id=role_id,
                        knowledge_base_name="kb", status="ready"))
        s.commit()
    return role_id


def test_full_onboarding_flow_via_api(client):
    h = _h()
    role_id = _seed_ready_role()
    # create profile
    r = client.post("/internal/users/u-onb/profile",
                    json={"role_id": role_id, "experience_level": "entry"}, headers=h)
    assert r.status_code == 201
    # generate plan
    r = client.post("/internal/users/u-onb/plan", headers=h)
    assert r.status_code == 201
    plan = r.json()
    assert plan["status"] == "ready" and len(plan["steps"]) >= 6
    step_id = plan["steps"][0]["id"]
    # mark complete
    assert client.patch(f"/internal/plan-steps/{step_id}",
                        json={"status": "complete"}, headers=h).status_code == 200
    # generate exercise
    r = client.post(f"/internal/plan-steps/{step_id}/exercise", headers=h)
    assert r.status_code == 201 and r.json()["prompt"]
    assert "rubric" not in r.json()  # rubric never exposed
    ex_id = r.json()["id"]
    # submit + grade
    r = client.post(f"/internal/exercises/{ex_id}/submissions",
                    json={"answer": " ".join(["good"] * 30)}, headers=h)
    assert r.status_code == 200
    assert 0 <= r.json()["score"] <= 100 and r.json()["feedback"]
    # progress
    prog = client.get("/internal/users/u-onb/progress", headers=h).json()
    assert prog["total_steps"] == len(plan["steps"]) and prog["completed_steps"] == 1


def test_plan_409_when_successor_not_ready(client):
    h = _h(user="u-notready")
    role_id = f"r-{uuid.uuid4().hex[:8]}"
    with Session(engine) as s:
        s.add(Role(id=role_id, org_id="o-onb", title="X"))
        s.add(Successor(id=f"s-{uuid.uuid4().hex[:8]}", role_id=role_id,
                        knowledge_base_name="kb", status="provisioning"))
        s.commit()
    client.post("/internal/users/u-notready/profile",
                json={"role_id": role_id, "experience_level": "mid"}, headers=h)
    assert client.post("/internal/users/u-notready/plan", headers=h).status_code == 409


def test_profile_404_when_missing(client):
    assert client.get("/internal/users/nobody/plan", headers=_h(user="nobody")).status_code == 404
```

- [ ] **Step 2: Run, confirm fail** → 404 (routes absent).

- [ ] **Step 3: Create `routes/onboarding.py`**:
```python
from datetime import date

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from continuum_api.db import get_session
from continuum_api.onboarding.factory import build_generators
from continuum_api.routes.capture import _org
from continuum_api.routes.internal import require_service_token
from continuum_api.services.onboarding import OnboardingService, SuccessorNotReady

router = APIRouter(prefix="/internal", dependencies=[Depends(require_service_token)])


def _user(x_user_id: str | None = Header(default=None), org: str = Depends(_org)) -> str:
    return x_user_id or org


def _service(session: Session) -> OnboardingService:
    plan, exercise, grading = build_generators()
    return OnboardingService(session, plan, exercise, grading)


class CreateProfile(BaseModel):
    role_id: str
    experience_level: str = "mid"
    start_date: date | None = None


class SetStepStatus(BaseModel):
    status: str


class SubmitAnswer(BaseModel):
    answer: str


def _require_path_user(user_id: str, user: str) -> None:
    # the BFF sets X-User-Id from the session; it must match the path user.
    if user_id != user:
        raise HTTPException(status_code=404, detail="not found")


@router.get("/users/{user_id}/profile")
def get_profile(user_id: str, org: str = Depends(_org), user: str = Depends(_user),
                session: Session = Depends(get_session)) -> dict:
    _require_path_user(user_id, user)
    profile = _service(session).get_profile(user_id=user_id, org_id=org)
    if profile is None:
        raise HTTPException(status_code=404, detail="not found")
    return {"id": profile.id, "role_id": profile.role_id,
            "experience_level": profile.experience_level}


@router.post("/users/{user_id}/profile", status_code=201)
def create_profile(user_id: str, body: CreateProfile, org: str = Depends(_org),
                   user: str = Depends(_user), session: Session = Depends(get_session)) -> dict:
    _require_path_user(user_id, user)
    try:
        profile = _service(session).create_profile(
            user_id=user_id, org_id=org, role_id=body.role_id,
            experience_level=body.experience_level, start_date=body.start_date)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    session.commit()
    return {"id": profile.id, "role_id": profile.role_id}


def _plan_dict(svc: OnboardingService, plan) -> dict:
    steps = svc.plan_steps(plan.id)
    return {"id": plan.id, "title": plan.title, "status": plan.status, "steps": [
        {"id": s.id, "order": s.step_order, "title": s.title, "description": s.description,
         "topic_tags": s.topic_tags, "status": s.status} for s in steps
    ]}


@router.post("/users/{user_id}/plan", status_code=201)
async def generate_plan(user_id: str, org: str = Depends(_org), user: str = Depends(_user),
                        session: Session = Depends(get_session)) -> dict:
    _require_path_user(user_id, user)
    svc = _service(session)
    try:
        plan = await svc.generate_plan(user_id=user_id, org_id=org)
    except SuccessorNotReady as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    session.commit()
    return _plan_dict(svc, plan)


@router.get("/users/{user_id}/plan")
def get_plan(user_id: str, org: str = Depends(_org), user: str = Depends(_user),
             session: Session = Depends(get_session)) -> dict:
    _require_path_user(user_id, user)
    svc = _service(session)
    plan = svc.current_plan(user_id=user_id, org_id=org)
    if plan is None:
        raise HTTPException(status_code=404, detail="not found")
    return _plan_dict(svc, plan)


@router.patch("/plan-steps/{step_id}")
def set_step_status(step_id: str, body: SetStepStatus, org: str = Depends(_org),
                    session: Session = Depends(get_session)) -> dict:
    try:
        step = _service(session).set_step_status(step_id, org_id=org, status=body.status)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    session.commit()
    return {"id": step.id, "status": step.status}


@router.post("/plan-steps/{step_id}/exercise", status_code=201)
async def generate_exercise(step_id: str, org: str = Depends(_org),
                            session: Session = Depends(get_session)) -> dict:
    try:
        ex = await _service(session).generate_exercise(step_id, org_id=org)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    session.commit()
    return {"id": ex.id, "prompt": ex.prompt, "status": ex.status}  # rubric intentionally omitted


@router.get("/plan-steps/{step_id}/exercise")
def get_exercise(step_id: str, org: str = Depends(_org),
                 session: Session = Depends(get_session)) -> dict:
    try:
        ex = _service(session).get_exercise(step_id, org_id=org)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    if ex is None:
        raise HTTPException(status_code=404, detail="not found")
    return {"id": ex.id, "prompt": ex.prompt, "status": ex.status}


@router.post("/exercises/{exercise_id}/submissions")
async def submit(exercise_id: str, body: SubmitAnswer, org: str = Depends(_org),
                 user: str = Depends(_user), session: Session = Depends(get_session)) -> dict:
    try:
        result = await _service(session).submit_and_grade(
            exercise_id, user_id=user, org_id=org, answer=body.answer)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    session.commit()
    return {"score": result.score, "feedback": result.feedback}


@router.get("/users/{user_id}/progress")
def progress(user_id: str, org: str = Depends(_org), user: str = Depends(_user),
             session: Session = Depends(get_session)) -> dict:
    _require_path_user(user_id, user)
    summary = _service(session).progress(user_id=user_id, org_id=org)
    return {"total_steps": summary.total_steps, "completed_steps": summary.completed_steps,
            "steps": [{"step_id": s.step_id, "title": s.title, "status": s.status,
                       "exercise_score": s.exercise_score} for s in summary.steps]}
```

- [ ] **Step 4: Register the router in `main.py`** — extend the import to `from continuum_api.routes import capture, chat, health, internal, onboarding` and add `app.include_router(onboarding.router)` after `chat`. Keep `serve()`.

- [ ] **Step 5: Run, confirm pass** `cd /home/skkippie/work/continuum/apps/api && uv run pytest tests/test_onboarding_api.py -v` → 3 passed. Full suite `uv run pytest -q` → all pass. `uv run ruff check .` → clean.

- [ ] **Step 6: Commit**
```bash
cd /home/skkippie/work/continuum
git add apps/api/src/continuum_api/routes/onboarding.py apps/api/src/continuum_api/main.py apps/api/tests/test_onboarding_api.py
git commit -m "feat(onboarding): FastAPI endpoints (profile/plan/steps/exercise/submit/progress)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 11: BFF onboarding routes (web)

**Files:** Create `apps/web/src/app/api/bff/me/[...path]/route.ts`

A single catch-all proxy under `/api/bff/me/*` → FastAPI `/internal/users/{userId}/...` and the step/exercise paths. The BFF resolves `{userId, orgId}` from the session and rewrites `me` → the real user id, attaching `X-User-Id`.

- [ ] **Step 1: Create `apps/web/src/app/api/bff/me/[...path]/route.ts`**:
```typescript
import { type NextRequest, NextResponse } from "next/server";
import { forwardToApi } from "@/lib/api";
import { resolveSession } from "@/lib/bff";

// Maps a /api/bff/me/<...> path to the FastAPI /internal/... path for this user.
function toInternalPath(path: string[], userId: string): string | null {
  const [head, ...rest] = path;
  if (head === "profile") return `users/${userId}/profile`;
  if (head === "plan" && rest.length === 0) return `users/${userId}/plan`;
  if (head === "progress") return `users/${userId}/progress`;
  if (head === "plan" && rest[0] === "steps") {
    // plan/steps/{stepId}[/exercise[/submissions]]
    const tail = rest.slice(1).join("/"); // {stepId}[/exercise...]
    if (rest.length === 2) return `plan-steps/${rest[1]}`;
    if (rest[2] === "exercise" && rest.length === 3) return `plan-steps/${rest[1]}/exercise`;
    // submissions are addressed by exercise id at the API; the browser posts by step,
    // so the client must resolve the exercise id first (see onboarding-api.ts). If a
    // submissions path reaches here, reject — it should target /exercises/{id}/submissions.
    if (tail.endsWith("submissions")) return null;
  }
  if (head === "exercises" && rest[1] === "submissions") {
    return `exercises/${rest[0]}/submissions`;
  }
  return null;
}

async function handle(req: NextRequest, path: string[]): Promise<Response> {
  const session = await resolveSession();
  if (!session) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const internal = toInternalPath(path, session.userId);
  if (!internal) return NextResponse.json({ error: "not_found" }, { status: 404 });
  const init: RequestInit = { method: req.method, headers: { "X-User-Id": session.userId } };
  if (req.method !== "GET") init.body = await req.arrayBuffer();
  const contentType = req.headers.get("content-type");
  if (contentType) (init.headers as Record<string, string>)["content-type"] = contentType;
  try {
    const upstream = await forwardToApi(internal, init, session.orgId);
    return new NextResponse(upstream.body, {
      status: upstream.status,
      headers: { "content-type": upstream.headers.get("content-type") ?? "application/json" },
    });
  } catch {
    return NextResponse.json({ error: "upstream_unavailable" }, { status: 503 });
  }
}

export async function GET(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  return handle(req, (await params).path);
}
export async function POST(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  return handle(req, (await params).path);
}
export async function PATCH(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  return handle(req, (await params).path);
}
```
NOTE: the `X-User-Id` is set in `init.headers` and preserved by `forwardToApi` (which only overrides `X-Service-Token`/`X-Org-Id`). Submissions are posted directly to `/api/bff/me/exercises/{exerciseId}/submissions` by the client (it already has the exercise id from the generate-exercise response), so the BFF maps that to `/internal/exercises/{id}/submissions` — no step→exercise resolution needed in the BFF.

- [ ] **Step 2: Verify** (repo root): `cd /home/skkippie/work/continuum && pnpm --filter web typecheck` → 0; `pnpm check` → clean; `pnpm --filter web build` → green (`ƒ /api/bff/me/[...path]` in output).

- [ ] **Step 3: Commit**
```bash
cd /home/skkippie/work/continuum
git add apps/web/src/app/api/bff/me
git commit -m "feat(web): BFF proxy for onboarding (/api/bff/me/* -> /internal/users/{id}/...)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 12: OnboardingDashboard (web)

**Files:** Create `apps/web/src/lib/onboarding-api.ts`, `apps/web/src/components/onboarding-dashboard.tsx`, `apps/web/src/app/onboarding/page.tsx`

A minimal client dashboard: shows the plan steps with status, a "Generate exercise" action per step (opens an inline panel), answer submission + score/feedback, and a progress bar. Uses plain `fetch` against the BFF (no TanStack Query needed for this minimal slice — keep it consistent with the Spec 1 `/admin` + Spec 2 chat style).

- [ ] **Step 1: Create `apps/web/src/lib/onboarding-api.ts`** (typed BFF helpers):
```typescript
export type Step = {
  id: string;
  order: number;
  title: string;
  description: string;
  topic_tags: string[];
  status: string;
};
export type Plan = { id: string; title: string; status: string; steps: Step[] };
export type Exercise = { id: string; prompt: string; status: string };
export type Grade = { score: number; feedback: string };
export type Progress = {
  total_steps: number;
  completed_steps: number;
  steps: { step_id: string; title: string; status: string; exercise_score: number | null }[];
};

async function bff<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api/bff/me/${path}`, init);
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return (await res.json()) as T;
}

export const onboardingApi = {
  getPlan: () => bff<Plan>("plan"),
  generatePlan: () => bff<Plan>("plan", { method: "POST" }),
  createProfile: (roleId: string, level: string) =>
    bff<{ id: string }>("profile", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ role_id: roleId, experience_level: level }),
    }),
  setStep: (stepId: string, status: string) =>
    bff<{ id: string; status: string }>(`plan/steps/${stepId}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ status }),
    }),
  generateExercise: (stepId: string) =>
    bff<Exercise>(`plan/steps/${stepId}/exercise`, { method: "POST" }),
  submit: (exerciseId: string, answer: string) =>
    bff<Grade>(`exercises/${exerciseId}/submissions`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ answer }),
    }),
  getProgress: () => bff<Progress>("progress"),
};
```

- [ ] **Step 2: Create `apps/web/src/components/onboarding-dashboard.tsx`**:
```tsx
"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { type Exercise, type Plan, onboardingApi } from "@/lib/onboarding-api";

export function OnboardingDashboard() {
  const [plan, setPlan] = useState<Plan | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exercises, setExercises] = useState<Record<string, Exercise>>({});
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [grades, setGrades] = useState<Record<string, { score: number; feedback: string }>>({});

  async function guard(fn: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const loadPlan = () => guard(async () => setPlan(await onboardingApi.getPlan()));
  const generatePlan = () => guard(async () => setPlan(await onboardingApi.generatePlan()));

  const complete = (stepId: string) =>
    guard(async () => {
      await onboardingApi.setStep(stepId, "complete");
      setPlan(await onboardingApi.getPlan());
    });

  const genExercise = (stepId: string) =>
    guard(async () => {
      const ex = await onboardingApi.generateExercise(stepId);
      setExercises((m) => ({ ...m, [stepId]: ex }));
    });

  const submit = (stepId: string, exerciseId: string) =>
    guard(async () => {
      const grade = await onboardingApi.submit(exerciseId, answers[stepId] ?? "");
      setGrades((m) => ({ ...m, [stepId]: grade }));
    });

  const done = plan?.steps.filter((s) => s.status === "complete").length ?? 0;
  const total = plan?.steps.length ?? 0;

  return (
    <main className="mx-auto max-w-3xl space-y-4 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Your onboarding</h1>
        <div className="flex gap-2">
          <Button variant="outline" disabled={busy} onClick={() => void loadPlan()}>
            Load
          </Button>
          <Button disabled={busy} onClick={() => void generatePlan()}>
            {busy ? "…" : "Generate plan"}
          </Button>
        </div>
      </div>
      {error && <p className="text-sm text-destructive">Error: {error}</p>}
      {total > 0 && (
        <div className="h-2 w-full overflow-hidden rounded bg-muted">
          <div
            className="h-full bg-primary transition-all"
            style={{ width: `${total ? (done / total) * 100 : 0}%` }}
          />
        </div>
      )}
      {plan && (
        <p className="text-sm text-muted-foreground">
          {done}/{total} steps complete — {plan.title}
        </p>
      )}
      <div className="space-y-3">
        {plan?.steps.map((step) => {
          const ex = exercises[step.id];
          const grade = grades[step.id];
          return (
            <Card key={step.id} className="space-y-2 p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-medium">
                    {step.order}. {step.title}{" "}
                    {step.status === "complete" && <span className="text-primary">✓</span>}
                  </p>
                  <p className="text-sm text-muted-foreground">{step.description}</p>
                </div>
                <div className="flex shrink-0 gap-2">
                  <Button size="sm" variant="outline" disabled={busy}
                    onClick={() => void genExercise(step.id)}>
                    Exercise
                  </Button>
                  {step.status !== "complete" && (
                    <Button size="sm" disabled={busy} onClick={() => void complete(step.id)}>
                      Mark done
                    </Button>
                  )}
                </div>
              </div>
              {ex && (
                <div className="space-y-2 rounded-md bg-muted/40 p-3 text-sm">
                  <p>{ex.prompt}</p>
                  <textarea
                    className="w-full rounded-md border border-border bg-background px-2 py-1"
                    rows={3}
                    value={answers[step.id] ?? ""}
                    onChange={(e) => setAnswers((m) => ({ ...m, [step.id]: e.target.value }))}
                  />
                  <Button size="sm" disabled={busy}
                    onClick={() => void submit(step.id, ex.id)}>
                    Submit answer
                  </Button>
                  {grade && (
                    <p className="text-sm">
                      <span className="font-medium">Score {grade.score}/100.</span> {grade.feedback}
                    </p>
                  )}
                </div>
              )}
            </Card>
          );
        })}
      </div>
    </main>
  );
}
```

- [ ] **Step 3: Create `apps/web/src/app/onboarding/page.tsx`**:
```tsx
import { OnboardingDashboard } from "@/components/onboarding-dashboard";

export default function OnboardingPage() {
  return <OnboardingDashboard />;
}
```

- [ ] **Step 4: Verify** (repo root): `cd /home/skkippie/work/continuum && pnpm --filter web typecheck` → 0; `pnpm check` → clean (if Biome flags the `style={{ width }}` inline style or anything, fix minimally); `pnpm --filter web build` → green (`/onboarding` route present). Confirm `Button` supports `size`/`variant` props (it does — shadcn). If `variant="destructive"`/`size="sm"` aren't in the installed button variants, use the defaults + token classes.

- [ ] **Step 5: Commit**
```bash
cd /home/skkippie/work/continuum
git add apps/web/src/lib/onboarding-api.ts apps/web/src/components/onboarding-dashboard.tsx apps/web/src/app/onboarding
git commit -m "feat(web): minimal onboarding dashboard (plan, exercises, grade, progress bar)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Final verification (run after all tasks)

```bash
docker compose up -d
(cd apps/api && uv run alembic upgrade head && uv run pytest -q)   # all pass; Azure ITs skipped
pnpm --filter web typecheck && pnpm check && pnpm --filter web build
```

## Definition of Done

- A user with an `EmployeeProfile` for a `ready` Successor generates an `OnboardingPlan` of 6–8 ordered steps; entry-level plans are visibly broader than senior (fake generator already reflects this; live generator is prompt-instructed).
- "Generate exercise" returns a non-empty prompt and NEVER exposes the rubric (API omits it).
- Submitting a plain-text answer returns a 0–100 score + feedback.
- Marking a step complete updates its status; progress reports `completed_steps / total_steps` + latest exercise score per step.
- The whole flow runs on `generation_backend=fake` with no Azure; flips to real with `generation_backend=live` + `chat_backend=azure_openai` + `knowledge_backend=foundry`. Live generation verified by the gated `@integration` test; live parsing verified by the scripted-stub unit tests.
- Browser → BFF (`/api/bff/me/*`) → FastAPI; cross-org/cross-user access → 404; rubric never leaves the server.
- The 5 onboarding tables are Alembic-owned, in `_MANAGED_TABLES`; the 7 Better Auth tables remain intact.

## Notes for the implementer

- **Reuse, don't reinvent:** `require_service_token`, `_org`, the `_user` header dep pattern (Spec 2), `resolveSession`/`forwardToApi` (web), `build_chat_model` (Spec 2), `build_knowledge`/`build_blob_store` (Spec 1), `RoleRepo`/`SuccessorRepo` (Spec 1). The shared `ScriptedChatModel` stub lives in `tests/fakes.py`.
- **`generation_backend=fake` is the demo + CI default** — the fake generators produce believable canned output with no model call. Flip to `live` for real Azure structured generation.
- **The rubric is private** — it's persisted on `Exercise` but every API/BFF response omits it. Don't add it to a response shape.
- **`step_order`, not `order`** (SQL reserved word). The API still exposes it to the client as `order` in the JSON (`_plan_dict` maps `s.step_order` → `"order"`).
- **Live generators parse model JSON** — the `_parse_json` helper strips ```json fences + surrounding prose; a malformed response raises `GenerationError` → the service marks the plan/exercise `failed` (retryable), and grading propagates a 502-able error. Verify structured-output behavior against the real deployment when `live` (Open Question §10 in the design).
- **Never `alembic revision --autogenerate`** — hand-write; new tables → `_MANAGED_TABLES`.
- The web dashboard assumes a signed-in session with an active org (the BFF 401s otherwise) — same runtime prereq as Spec 1's `/admin` + Spec 2's `/chat`.
- **v1 authorization scope:** the step/exercise routes (`_owned_step`) authorize at the **org** level (the cross-tenant boundary that matters), returning 404 on org mismatch. They do NOT additionally enforce that the step belongs to the *calling user* within the same org — a same-org colleague who knows a step id could read/patch it. Acceptable for v1 (the BFF forwards a session-derived `X-User-Id`, ids are uuid4, and onboarding is single-user-per-role); if multi-user-per-org hardening is needed, thread `user_id` into `_owned_step` and check `profile.user_id == user`. (Mirrors Spec 1's deferred read-path org-ownership note.)

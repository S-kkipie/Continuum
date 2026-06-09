# Continuum — Roadmap

A phased program. Each sub-spec is its own spec → plan → implement cycle. Canonical design: `docs/superpowers/specs/2026-06-09-continuum-overview-design.md`.

| Phase | Sub-spec | Status |
|---|---|---|
| 0 | **Scaffold & infra** (walking skeleton) | ✅ DONE — plan: `docs/superpowers/plans/2026-06-09-continuum-scaffold.md` |
| 1 | **Domain model + ingestion → Foundry IQ** (capture loop) | 📝 Speced (`…-spec1-capture-design.md`), not yet planned — **NEXT** |
| 2 | **Grounded mentor agent** (Agent Framework + Foundry IQ retrieval) | 📝 Speced (`…-spec2-mentor-design.md`), not yet planned |
| 2 | **Onboarding plan + exercises + progress** | ⬜ Not started |
| 3 | **Work IQ + Fabric IQ enrichment** | ⬜ Not started — prereq: Copilot-licensed M365 tenant + Fabric capacity |
| 4 | **Seed dataset + UI polish + demo script** | ⬜ Not started |

**Critical path for the demo**: 0 → 1 → 2 → 3 → 4. Phase 3 is "wow insurance" — drop it first if time runs short; the IQ story then leans on Foundry IQ (fully GA). See `SPEC1-HANDOFF.md` for the immediate next work.

## The three-IQ story (demo narrative)

- **Foundry IQ** — the org's captured knowledge (reliable GA core; grounded answers).
- **Work IQ** — *who* knew this and *how the team actually worked* (collaboration signals via the M365 Copilot Retrieval API, a Graph endpoint).
- **Fabric IQ** — *why it matters* to the business (one metric, via a Fabric Data agent).

# Continuum — Roadmap

A phased program. Each sub-spec is its own spec → plan → implement cycle. Canonical design: `docs/superpowers/specs/2026-06-09-continuum-overview-design.md`.

| Phase | Sub-spec | Status |
|---|---|---|
| 0 | **Scaffold & infra** (walking skeleton) | ✅ DONE — plan: `docs/superpowers/plans/2026-06-09-continuum-scaffold.md` |
| 1 | **Domain model + ingestion → Foundry IQ** (capture loop) | ✅ DONE — plan: `plans/…-spec1-capture.md` (merged 2026-06-09; local/fake default, gated Azure ITs) |
| 2 | **Grounded mentor agent** (own loop + Azure OpenAI tool-calling + Foundry IQ retrieval) | ✅ DONE — plan: `plans/…-spec2-mentor.md` (merged 2026-06-09; fake-first, gated Azure IT). NB: own-loop NOT Agent Framework, minimal SSE chat NOT assistant-ui — see plan §Architecture decisions + `STATE.md`. |
| 2 | **Onboarding plan + exercises + progress** | 📝 Speced (`…-spec3-onboarding-design.md`), not yet planned, **NEXT**. Reuses the Spec 2 `MentorAgent` + `Conversation`/`Message` (note `user_id` is now a real user id). |
| 3 | **Work IQ + Fabric IQ enrichment** | 📝 Speced (`…-spec4-iq-enrichment-design.md`) — prereq: Copilot-licensed M365 tenant + Fabric capacity (mockable) |
| 4 | **Seed dataset + UI polish + demo script** | 📝 Speced (`…-spec5-demo-design.md`), not yet planned |

**Critical path for the demo**: 0 → 1 → 2 → 3 → 4. Phases 0, 1, and 2 are ✅ DONE — the core demo loop (capture → grounded cited chat) works end-to-end on local/fake with no Azure. Phase 3 (Work IQ + Fabric IQ) is "wow insurance" — drop it first if time runs short; the IQ story then leans on Foundry IQ (fully GA). See `STATE.md` for current facts + deferred follow-ups.

## The three-IQ story (demo narrative)

- **Foundry IQ** — the org's captured knowledge (reliable GA core; grounded answers).
- **Work IQ** — *who* knew this and *how the team actually worked* (collaboration signals via the M365 Copilot Retrieval API, a Graph endpoint).
- **Fabric IQ** — *why it matters* to the business (one metric, via a Fabric Data agent).

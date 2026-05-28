# Engineering Decision Log — SalesFlow AI

Decisions made building to the PRD, with the reasoning. PRD-level product
decisions are in the PRD itself; this records the *implementation* choices and
their trade-offs.

## Eval-first, deterministic core

**Decision:** Make the decisioning engine (state machine, question selector,
escalation, pivot, RAG retrieval) fully deterministic and offline; keep the LLM
as an optional natural-language layer behind `llm.LLMClient`.

**Why:** The environment has no `ANTHROPIC_API_KEY` and CI never will. A
deterministic core means the golden set can use exact-match assertions, the
harness runs at zero cost, and quality gates are reproducible. Behaviour that
depends on an LLM's mood is neither testable nor auditable.

**Trade-off:** Field extraction and phrasing are simpler than an LLM would
produce. The seams (`llm.get_client`, the voice protocols) make the upgrade
additive, not a rewrite.

## Grounding over generation for facts

**Decision:** Pricing comes from `config.Pricing` (structured); policy answers
are **retrieval-only** from the KB; the objection playbook is parsed, not
generated. The post-call `GroundingJudge` verifies every dollar figure the agent
utters is a real configured price.

**Why:** Hallucinated pricing/policy on a sales call is the highest-stakes
failure mode. Making facts un-generatable means the hallucination rate is 0 by
construction, and the judge proves it on every transcript.

## Objection detection is phrase-based, not token-based

**Decision:** `classify_objection` matches multi-word phrase markers
("too expensive", "talk to my husband"), not single shared tokens.

**Why:** Token overlap misfires — a neutral field answer like "before the test
in May" would trip an "effectiveness"/"timing" classifier. The golden set caught
exactly this; phrase markers fixed it. Critically, a price *question*
("how much does it cost?") is routed to grounded pricing, **not** treated as a
price *objection*.

## The objection playbook is excluded from policy retrieval

**Decision:** The internal A-R-C playbook (`objections.md`) populates the
rebuttal lookup only; it is **not** in the customer-facing retrieval corpus.

**Why:** A "refund policy" query was matching the objection playbook's prose
(it contains the word "work", "refund", etc.) over the actual policy doc. The
golden set caught it. Internal sales scripts must never surface as a policy
answer.

## Out-of-scope factual probes escalate, not guess

**Decision:** A question hitting `_OUT_OF_SCOPE` cues (license #, credentials,
revenue, …) escalates as low-confidence rather than answering from a
loosely-matching chunk.

**Why:** Conservative escalation (a PRD decision) — better to hand a specific
factual question we can't ground to a human than to answer it from a tangentially
related policy paragraph.

## Unproductive re-pivots count as probes

**Decision:** When the agent re-pivots in `PIVOT_TO_CLOSE` without a commitment,
it increments `probe_attempts`, so a prospect who never commits (Silent Sam)
eventually escalates as disqualification-uncertainty instead of looping forever.

**Why:** First self-play run, Silent Sam ran to the 60-turn cap. The fix turns a
non-terminating loop into the *correct* conservative outcome (escalate when fit
can't be determined) and exercises the 5th escalation trigger.

## A/B world encodes hidden ground-truth persuasiveness

**Decision:** In the A/B runner, each variant carries a `true_persuasiveness`
known only to the simulated prospect (the "world"), not the agent. The
experiment recovers it from outcomes via a two-proportion z-test.

**Why:** The 5 scripted personas are deterministic, so a rebuttal text change
alone produces zero variance and no measurable lift. Modelling the prospect's
conversion as `Bernoulli(true_persuasiveness)` gives a real distribution, so the
significance test is meaningful and the loop demonstrably promotes the better
variant while rejecting a marginal one.

## Voice pipeline is protocol-first with simulated audio

**Decision:** `voice/` defines `STT`/`TTS`/`VAD`/`Transport` protocols; the mock
encodes text as audio (~60ms/word) so latency budgeting and barge-in are tested
deterministically. Live Deepgram/Cartesia adapters are import-safe stubs behind
the same protocols.

**Why:** The ≤800ms budget and "no audio overlap on barge-in" KPIs can be
validated offline without telephony or keys. Going live is implementing two
`synthesize`/`transcribe` bodies, not changing the pipeline.

## StrEnum for all enumerations

**Decision:** Domain enums subclass `enum.StrEnum` (Python 3.11+).

**Why:** They serialise to readable strings in transcripts/JSON and the golden
set, while still being type-checked. (Also what ruff's `UP042` wants.)

# SalesFlow AI

An autonomous voice sales agent (persona **Alex**) for Nerdy tutoring, built
**eval-first**: the golden set, self-play harness, KPI scorers, grounding judge,
and quality gates came before the feature work, so every behaviour is measured
rather than vibe-checked. Implements Part 2 of the Nerdy Gauntlet PRD.

> **Design stance.** The decisioning core (7-phase state machine, question
> selector, escalation classifier, pivot logic, RAG retrieval) is **fully
> deterministic and runs offline** with no API key. The LLM (Claude) is an
> optional layer for natural-language surfaces; a deterministic mock backs every
> test. Pricing and policy answers are **grounded** (structured config + retrieval),
> never generated — so a post-call judge can verify there are zero hallucinations.

## Quick start

```bash
cd salesflow
pip install ruff mypy pytest pytest-cov pyyaml types-PyYAML
export PYTHONPATH=src            # PowerShell: $env:PYTHONPATH = "src"

# The three quality gates (all run offline, no API key):
ruff check src tests             # lint
mypy                             # typecheck
pytest --cov --cov-report=term-missing   # tests + 85% coverage gate

# The eval harness:
python -m salesflow.eval.cli all          # self-play KPIs + A/B experiment
python -m salesflow.eval.cli suite --transcripts ./transcripts
python -m salesflow.eval.cli ab --n 500 --seed 7
```

## What's here

| Layer | Module | Notes |
|-------|--------|-------|
| Domain + state machine | `domain/` | 7 phases, auditable transition allow-list |
| Decisioning engine | `agent/` | question selector · escalation (5 triggers) · A-R-C objections · pivot (5-signal) |
| Grounded knowledge | `knowledge/` + `config.py` | retrieval-only policy answers; pricing from config |
| LLM abstraction | `llm/` | `MockLLMClient` (offline) · `AnthropicClient` (Claude, prompt-cached) |
| Cross-call memory | `memory.py` | session-id + phone **double-key** |
| Adversarial personas | `personas.py` | Ready Rita · Hesitant Henry · Pushback Paula · Disqualifier Dan · Silent Sam |
| Eval | `eval/` | self-play harness · KPI scorers · grounding judge · golden set · A/B runner |
| Observability | `observability.py` | per-call transcript + decision log, version-tagged |
| Voice pipeline | `voice/` | VAD→STT→agent→TTS over protocols; mock + live Deepgram/Cartesia stubs |

## Eval-first: the spec is executable

[`src/salesflow/eval/goldens/golden_set.yaml`](src/salesflow/eval/goldens/golden_set.yaml)
is the spec. It pins exact expected behaviour for objection classification,
question selection, RAG retrieval, phase transitions, all 5 escalation triggers,
the 5-signal pivot, and end-to-end self-play outcomes. `tests/test_golden_set.py`
runs the core against every case with exact-match assertions. **Grow this file
whenever a new failure shows up in the wild.**

### Current measured baseline (offline, deterministic)

Self-play vs the 5 adversarial personas:

| Persona | Outcome | Why |
|---------|---------|-----|
| Ready Rita | `closed_won` | high intent, converts cleanly |
| Hesitant Henry | `closed_won` | converts after A-R-C on timing + price |
| Pushback Paula | `escalated` (high-stakes pricing) | demands 25% > 10% autonomous limit |
| Disqualifier Dan | `graceful_exit` | self-disqualifies at warm-up |
| Silent Sam | `escalated` (disqualification uncertainty) | never commits after repeated probes |

KPIs: conversion 0.40 · discovery completion 1.00 · escalation 0.40 ·
false-positive close **0.00** · hallucination rate **0.00**.

### A/B improvement loop (recursive improvement)

`python -m salesflow.eval.cli ab` runs 3 price-objection rebuttal variants vs
baseline in self-play and reports per-variant lift with a two-proportion z-test.
The runner correctly recovers the most persuasive variant (`smaller_entry`,
p≈1e-3) and **does not** promote a marginal one (`social_proof`, p≈0.08) —
matching the PRD's "auto-promote only on statistical significance" rule.

## Going live (requires keys)

The offline build is complete; live wiring is additive behind the existing
interfaces:

- **LLM** — set `ANTHROPIC_API_KEY` and `pip install salesflow[llm]`;
  `llm.get_client()` switches from mock to Claude automatically (prompt caching
  on the system prompt is already wired).
- **Voice** — implement the streaming bodies in `voice/live_deepgram.py`
  (`DEEPGRAM_API_KEY`) and `voice/live_cartesia.py` (`CARTESIA_API_KEY`); they
  already satisfy the `STT`/`TTS` protocols the `VoicePipeline` consumes. The
  mock pipeline already validates the ≤800ms latency budget and barge-in (no
  audio overlap).
- **Telephony/session store** — swap `memory.SessionStore`'s dict for Redis
  behind the same methods; connect Vapi/LiveKit to `voice.VoicePipeline`.

See [`DECISIONS.md`](DECISIONS.md) for the non-obvious engineering choices and
[`LIMITATIONS.md`](LIMITATIONS.md) for what v1 does not do.

# SalesFlow AI

An autonomous voice sales agent (persona **Vani**) for Nerdy tutoring, built
**eval-first**: the golden set, self-play harness, KPI scorers, grounding judge,
and quality gates came before the feature work, so every behaviour is measured
rather than vibe-checked. Implements Part 2 of the Nerdy Gauntlet PRD.

> **Design stance.** The decisioning core (7-phase state machine, question
> selector, escalation classifier, pivot logic, RAG retrieval) is **fully
> deterministic and runs offline** with no API key. The LLM (OpenAI GPT) is an
> optional layer for natural-language surfaces; a deterministic mock backs every
> test. Pricing, policy, and competitive answers are **grounded** (structured
> config + retrieval), never generated — so a post-call judge can verify there
> are zero hallucinations.
>
> **Full stack.** A React UI (`frontend/`) provides three surfaces over a FastAPI
> backend (`web.py`): **Chat** (text), **Voice** (real-time WebSocket loop with
> barge-in, Cartesia STT+TTS), and a **Dashboard** (live KPIs, the A/B improvement
> loop, and a PII-redacted sample transcript with per-turn decisions). One Docker
> image builds the SPA and serves it with the APIs — see [`deploy/DEPLOY.md`](deploy/DEPLOY.md).

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

## Web app (Chat · Voice · Dashboard)

```bash
pip install -e ".[web]"                   # FastAPI + uvicorn
cd frontend && npm install && npm run build && cd ..   # build the React SPA
uvicorn salesflow.web:app --reload        # http://localhost:8000
```

`/` Chat · `/voice` live voice (WebSocket + barge-in) · `/dashboard` KPIs + A/B +
redacted transcript. Without the React build, `/` serves a lightweight fallback
chat. Frontend dev with hot-reload + API proxy: `cd frontend && npm run dev`.

## What's here

| Layer | Module | Notes |
|-------|--------|-------|
| Domain + state machine | `domain/` | 7 phases, auditable transition allow-list |
| Decisioning engine | `agent/` | question selector · escalation (5 triggers) · A-R-C objections · pivot (5-signal) |
| Grounded knowledge | `knowledge/` + `config.py` | retrieval-only policy answers; pricing from config |
| LLM abstraction | `llm/` | `MockLLMClient` (offline) · `OpenAIClient` (GPT, auto prompt-cached) |
| Cross-call memory | `memory.py` | session-id + phone **double-key** |
| Adversarial personas | `personas.py` | Ready Rita · Hesitant Henry · Pushback Paula · Disqualifier Dan · Silent Sam |
| Eval | `eval/` | self-play harness · KPI scorers · grounding judge · golden set · A/B runner |
| Observability | `observability.py` | per-call transcript + decision log, version-tagged, **PII-redacted** (`privacy.py`) |
| Voice pipeline | `voice/` | VAD→STT→agent→TTS over protocols; mock + live Cartesia (Sonic TTS · Ink-Whisper STT) |
| Web app | `web.py` + `frontend/` | FastAPI APIs + `/ws/voice` WebSocket; React SPA (Chat · Voice · Dashboard) |

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

- **LLM** — set `OPENAI_API_KEY` and `pip install salesflow[llm]`;
  `llm.get_client()` switches from mock to OpenAI GPT automatically (OpenAI
  auto-caches the stable system prefix).
- **Voice** — TTS is Cartesia Sonic (`voice/live_cartesia.py`, `CARTESIA_API_KEY`).
  STT is provider-pluggable via `voice.get_stt()` / the `SALESFLOW_STT` env var:
  - `cartesia` (default) — Ink-Whisper, **reuses the same Cartesia key** as TTS
  - `groq` — whisper-large-v3-turbo (`GROQ_API_KEY`)
  - `local` — faster-whisper, on-device, **no key** (`pip install salesflow[voice-local]`)
  - `mock` — offline default

  All satisfy the `STT`/`TTS` protocols the `VoicePipeline` consumes; the mock
  pipeline already validates the ≤800ms latency budget and barge-in (no audio
  overlap). (Deepgram was dropped — key provisioning was unavailable.)
- **Telephony/session store** — swap `memory.SessionStore`'s dict for Redis
  behind the same methods; connect Vapi/LiveKit to `voice.VoicePipeline`.

See [`EVIDENCE.md`](EVIDENCE.md) for the before/after A/B evidence + failure-mode
report (PRD Phase-4 deliverable), [`DECISIONS.md`](DECISIONS.md) for the
non-obvious engineering choices, and [`LIMITATIONS.md`](LIMITATIONS.md) for what
v1 does not do.

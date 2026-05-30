# SalesFlow AI — Context

Autonomous voice sales agent **"Vani"** for Nerdy/Varsity Tutors (Gauntlet Week 5,
Part 2 of `nerdy-gauntlet-prd.md`). Built **eval-first**: the golden set is the
executable spec, the harness runs every scenario, KPI scorers + a grounding judge
are the quality gates.

## Core principle: deterministic offline core, optional LLM layer

The decision engine (state machine, question selection, escalation, pivot, RAG
retrieval, pricing) is **fully deterministic and runs with no API key**. The LLM is
an *optional* natural-language layer behind `llm.LLMClient`; `llm.get_client()`
returns `MockLLMClient` whenever `OPENAI_API_KEY` is unset (CI never has one).
This is why every gate is reproducible at zero cost. Do not move decision logic
into the LLM — keep facts un-generatable. **LLM backend is OpenAI GPT**
(`llm/openai_client.py`); Claude was swapped out to match the platform stack.

## Commands (run from `salesflow/`)

```powershell
pip install -e ".[dev]"            # core + test tooling (offline)
pip install -e ".[dev,llm,voice,web]"  # + OpenAI + Cartesia voice + FastAPI
pytest --cov                       # full suite + coverage gate (fail_under = 85)
ruff check src tests ; mypy        # lint + type gates (must be clean)
salesflow-eval all                 # golden set + suite + A/B  (CLI: eval/cli.py)
# Web app (React UI + FastAPI):
cd frontend && npm install && npm run build && cd ..
uvicorn salesflow.web:app --reload # / chat · /voice · /dashboard · /ws/voice
```

All gates (pytest, coverage ≥85, ruff, mypy) must be green before calling work
done. Last known state: **94 tests pass, ~93.6% coverage**, ruff + mypy clean,
React build succeeds.

## Layout (`src/salesflow/`)

- `domain/models.py` — dataclasses + StrEnums: `Phase`, `EscalationTrigger`,
  `Outcome`, `Sentiment`, `Lead`, `Turn`, `ConversationState`, `CallLog`.
- `domain/phases.py` — `ALLOWED_TRANSITIONS` allow-list, `PhaseMachine`,
  `IllegalTransitionError`. Off-ramps (ESCALATION, GRACEFUL_EXIT) reachable from any
  non-terminal phase.
- `config.py` — `Pricing` (starter 40 / standard 60 / intensive 90; max autonomous
  discount 0.10), `Thresholds`, `SETTINGS` singleton.
- `agent/agent.py` — orchestrator `SalesAgent.respond()`. Priority order:
  escalation → disqualification → objection → phase advance. `_grounded_answer()`
  routes pricing→config, out-of-scope→escalate, policy→KB retrieval.
- `agent/{escalation,question_selector,pivot}.py` — 5 escalation triggers,
  field-question selection, 5-signal pivot-to-close.
- `knowledge/kb.py` — markdown KB (data/*.md), `classify_objection()`
  (phrase-based, not token-based), A-R-C rebuttals. **objections.md is excluded
  from policy retrieval** — it only feeds rebuttals.
- `personas.py` — 5 adversarial personas: ReadyRita, HesitantHenry, PushbackPaula,
  DisqualifierDan, SilentSam (`ALL_PERSONAS`).
- `eval/` — `harness.py` (run_call/run_suite, MAX_TURNS=60), `scorers.py` (KPIs),
  `judge.py` (`GroundingJudge` verifies every `$` figure matches config →
  hallucination rate 0 by construction), `ab.py` (two-proportion z-test),
  `golden.py` + `goldens/golden_set.yaml` (the spec), `cli.py`.
- `memory.py` — `SessionStore`, double-keyed `session_id::phone`, JSON persistence.
- `voice/` — `interfaces.py` (STT/TTS/VAD/Transport Protocols), `mock.py`
  (text↔audio ~60ms/word, deterministic), `pipeline.py` (`VoicePipeline`, 800ms
  latency budget, barge-in), `factory.py` (`get_stt()`/`get_tts()`/`voice_available()`
  select backend via `SALESFLOW_STT`/`CARTESIA_API_KEY`). Live adapters `live_*.py`
  are import-safe and excluded from coverage.
- `privacy.py` — PII scrubber (email/phone/name); `observability.save_transcript`
  redacts by default so the on-disk transcript DB is PII-protected.
- `web.py` — FastAPI: `/api/start`,`/api/chat`,`/api/kpis`,`/api/voice/status`,
  `/ws/voice` WebSocket; serves the React build (vanilla fallback when unbuilt).
  `eval/dashboard.py` assembles the dashboard data (testable, no web concern).
- `frontend/` — Vite + React SPA: Chat, Voice (mic/playback + barge-in), Dashboard.
  Built to `frontend/dist`; `test_web.py` skips when fastapi/httpx absent.
- `deploy/` — `DEPLOY.md`, `cloudrun.service.yaml`, `apprunner-service.json`;
  root `Dockerfile` is multi-stage (node build → python runtime), `render.yaml`.

## Hard-won invariants (do not regress — each is a golden-set finding)

- Pricing is **never** LLM-generated; it comes from `config.Pricing` and the judge
  enforces it. Policy answers are **retrieval-only**.
- "How much does it cost?" is a pricing *question* (→ grounded pricing), **not** a
  price *objection*. Keep `classify_objection` phrase-based.
- objections.md must stay out of the customer-facing retrieval corpus.
- Competitive *questions* ("how are you different from a local tutor?") route to
  `competitive.md` retrieval (`grounded_sources=["competitive"]`); a competitor
  *name* ("Wyzant") classifies as a COMPETITOR objection first.
- Out-of-scope factual probes (license #, credentials, revenue) **escalate** as
  low-confidence rather than answering from a weak chunk.
- Unproductive re-pivots increment `probe_attempts` so a non-committing prospect
  (Silent Sam) escalates as disqualification-uncertainty instead of looping to the
  turn cap.
- Voice latency stages sum to 750ms (50+150+400+100+50) ≤ 800ms budget.

## Voice / STT note

Deepgram (the PRD's STT) was dropped — key unobtainable. STT is now pluggable via
`SALESFLOW_STT`: **cartesia** (Ink-Whisper, default, reuses the TTS key), **groq**
(whisper-large-v3-turbo), **local** (faster-whisper, no key), **mock** (tests).
Mock is the fallback when no key is set.

## Secrets

Keys live in the **shared** `C:\Pavan\AI Projects\.env` (git-ignored; template is
`.env.example`). The app reads `os.environ` directly and does **not** auto-load
`.env` — a key only takes effect once the env var is actually exported into the
shell/process.

## More detail

`README.md` (usage), `DECISIONS.md` (full rationale for every choice above),
`RESEARCH.md` (experiments + what was tried), `LIMITATIONS.md` (known gaps —
incl. live Cartesia path unverified without a key), `EVIDENCE.md` (Phase-4
results), `deploy/DEPLOY.md` (Render/Cloud Run/App Runner).

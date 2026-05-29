# Limitations — SalesFlow AI v1

Mirrors the PRD's limitations, annotated with what this codebase does and does
not implement.

- **Live voice path is written but unverified without a key.** The `/ws/voice`
  loop, barge-in, and the React mic/playback UI are wired end-to-end and tested
  against the deterministic mock (turn-taking + decision events). The real
  Cartesia calls (`live_cartesia.py` Sonic TTS, `live_cartesia_stt.py`
  Ink-Whisper) run only when `CARTESIA_API_KEY` is set and have **not** been
  exercised against the live API — the SDK signatures may need a minor tweak on
  first real run. Offline, mic audio cannot be transcribed (the mock STT returns
  no text), so the voice page falls back to a typed-utterance driver.

- **No telephony bridge.** Browser voice (WebSocket) is the demo channel; a
  Vapi/LiveKit/Twilio bridge to a real phone number is not wired.

- **Field extraction is naive.** The deterministic core stores the prospect's
  raw answer as the field value (e.g. "His name is Sam"). An LLM extraction pass
  (behind `llm.LLMClient`) would normalise this; the seam exists, the pass does
  not.

- **Synthetic validity.** The 5 personas are scripted and the A/B world uses a
  modelled conversion probability. This makes evaluation reproducible but does
  not replicate real human variability — live A/B on real calls remains the gold
  standard for promotion decisions (a PRD decision).

- **Grounding judge scope.** The offline judge verifies pricing exactly and
  flags ungrounded dollar figures. Fuzzy policy-claim grounding is stubbed for an
  optional LLM judge (OpenAI backend); it is not run offline.

- **React build required for the full UI.** `/voice` and `/dashboard` need the
  built SPA (`cd frontend && npm run build`). Without it the backend serves a
  vanilla fallback chat at `/`; the Docker image always builds the SPA.

- **Sentiment is lexicon-based.** Negative/positive detection uses a word list,
  not an LLM. Good enough for the escalation streak trigger; a noisy real call
  would benefit from an LLM sentiment scorer (same function seam).

- **English-only; no fine-tuning.** v1 is prompt + RAG + rules. Per the PRD,
  Spanish and model fine-tuning are v2.

- **Pricing concession autonomy capped.** The agent will not autonomously offer a
  discount above `config.Pricing.max_autonomous_discount` (10%); larger requests
  escalate to a human.

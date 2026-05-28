# Limitations — SalesFlow AI v1

Mirrors the PRD's limitations, annotated with what this codebase does and does
not implement.

- **Live voice not connected.** The voice pipeline, latency budgeting, and
  barge-in handling are validated against a deterministic mock. Deepgram/Cartesia
  adapters are import-safe stubs; real streaming bodies + a Vapi/LiveKit
  telephony bridge are needed for live calls. No audio is processed in v1.

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
  optional LLM judge (real Claude backend); it is not run offline.

- **Sentiment is lexicon-based.** Negative/positive detection uses a word list,
  not an LLM. Good enough for the escalation streak trigger; a noisy real call
  would benefit from an LLM sentiment scorer (same function seam).

- **English-only; no fine-tuning.** v1 is prompt + RAG + rules. Per the PRD,
  Spanish and model fine-tuning are v2.

- **Pricing concession autonomy capped.** The agent will not autonomously offer a
  discount above `config.Pricing.max_autonomous_discount` (10%); larger requests
  escalate to a human.

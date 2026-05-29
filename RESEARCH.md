# Research Notes — SalesFlow AI

Running log of experiments and investigations behind the build: what we tried,
what the data said, and what we kept. Decisions that became permanent are
promoted to [`DECISIONS.md`](DECISIONS.md); this file keeps the *why we explored*
trail (PRD "research-note tracking").

## Objection detection: token overlap vs. phrase markers

**Tried:** token-overlap classification (share enough words with an objection
category → classify). **Found:** neutral field answers misfired — "before the
test in May" tripped *timing*/*effectiveness*. **Kept:** multi-word phrase
markers (`"too expensive"`, `"talk to my husband"`). The golden set caught the
regression first, which is exactly its job. A price *question* ("how much does it
cost?") is deliberately **not** a price objection — it routes to grounded pricing.

## RAG corpus hygiene

**Observed:** a "refund policy" query sometimes retrieved the internal A-R-C
objection playbook (it contains "refund", "work", …) over the real policy doc.
**Kept:** `objections.md` is excluded from the customer-facing retrieval corpus
and used only to populate rebuttals. Internal sales scripts must never surface as
a policy answer.

## Competitive questions were dead weight

**Observed:** `competitive.md` was loaded but never retrieved — the agent only
fired *competitor objections* (A-R-C), so a neutral "how are you different from a
local tutor?" got no grounded answer. **Kept:** a competitive-intent route that
retrieves battlecards (`grounded_sources=["competitive"]`); a competitor *name*
("Wyzant") still classifies as an objection first, which is the right reflex.

## Recursive improvement: modelling a real signal

**Problem:** the 5 personas are deterministic, so a rebuttal-text change produced
zero variance — no measurable lift, no meaningful experiment. **Approach:** give
each A/B variant a hidden `true_persuasiveness` known only to the simulated
"world", and model prospect conversion as `Bernoulli(p)`. The loop then recovers
the better variant (`smaller_entry`, highest hidden p) via a two-proportion
z-test and **withholds** a marginal one (`social_proof`) until significant —
which is the anti-vanity-metric behaviour the PRD asks for.

## Non-terminating pivot (Silent Sam)

**Observed:** first self-play run, a prospect who neither accepts nor objects in
`PIVOT_TO_CLOSE` looped to the 60-turn cap. **Kept:** unproductive re-pivots
increment `probe_attempts`, so "can't determine fit" converges to the *correct*
conservative outcome — escalate as disqualification-uncertainty.

## Voice: STT provider exploration

Deepgram was the PRD's STT but the key could not be provisioned. Explored three
interchangeable backends behind one `STT` protocol: **Cartesia Ink-Whisper**
(reuses the TTS key — lowest setup, the default), **Groq** whisper-large-v3-turbo
(easy free key), **local faster-whisper** (no key, on-device). The ≤800ms budget
and barge-in are validated offline against the mock so the live swap is additive.

## LLM backend

Started on Claude; **switched to OpenAI GPT** to match the platform's stated
stack. The swap is contained entirely in `llm/` behind the `LLMClient` protocol —
the deterministic core, golden set, and every gate are untouched, since the LLM
is only an optional phrasing layer. OpenAI auto-caches the stable system prefix,
so no explicit cache-control wiring is needed.

## Open questions / next experiments

- Tune the browser VAD threshold (`SPEAK_THRESHOLD`) against real mic noise once
  a Cartesia key is available; current value is a desk-quiet default.
- A/B a *sequencing* change (ask budget earlier vs later), not just rebuttal text,
  to prove the loop generalises beyond phrasing.
- Replace keyword-overlap retrieval with embeddings behind the same `KnowledgeBase`
  interface and measure retrieval precision on the golden RAG cases.

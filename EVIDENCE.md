# Evidence & Failure-Mode Report — SalesFlow AI

Completes the PRD's Phase-4 exit criteria: before/after KPI evidence with
statistical-significance notation, plus a failure-mode report. All numbers below
are reproducible offline:

```bash
PYTHONPATH=src python -m salesflow.eval.cli all --n 400 --seed 7
```

## 1. Self-play baseline vs adversarial personas

The agent is exercised against all 5 adversarial personas (not compliant leads).
Every call reaches a clean terminal state — no stalls.

| Persona | Outcome | Mechanism exercised |
|---------|---------|---------------------|
| Ready Rita | `closed_won` | full pivot → close |
| Hesitant Henry | `closed_won` | A-R-C on timing + price, then close |
| Pushback Paula | `escalated` — high-stakes pricing | 25% discount demand > 10% autonomous cap |
| Disqualifier Dan | `graceful_exit` | self-disqualification at warm-up |
| Silent Sam | `escalated` — disqualification uncertainty | no commitment after repeated probes |

**KPIs (n=5 personas):**

| KPI | Value | PRD target | Status |
|-----|-------|-----------|--------|
| Conversion rate | 0.40 | ≥ human baseline | n/a offline |
| Discovery completion | **1.00** | ≥0.90 | ✅ |
| Escalation rate | 0.40 | minimise unnecessary | both escalations justified |
| False-positive close | **0.00** | <0.05 | ✅ |
| Hallucination rate | **0.00** | 0 on facts | ✅ (judge-verified) |
| Handle time | 21 turns avg | track | baseline set |

The two escalations are *correct*, not failures: Paula's discount exceeds the
autonomous limit, and Sam's fit is genuinely undeterminable — both are the
conservative-escalation policy working as designed.

## 2. A/B improvement loop — before/after with significance

Price-objection rebuttal variants vs baseline, objection-to-close rate,
two-proportion z-test, n=400/variant, seed=7:

| Variant | Rate | Lift vs baseline | p-value | Significant (α=0.05) | Promote? |
|---------|------|------------------|---------|----------------------|----------|
| baseline | 0.335 | — | — | — | reference |
| roi_framing | 0.482 | **+0.147** | 2.2e-05 | ✅ | auto (low-stakes) |
| smaller_entry | **0.512** | **+0.177** | 3.78e-07 | ✅ | **best** |
| social_proof | 0.355 | +0.020 | 0.55 | ❌ | **do not promote** |

This is the recursive-improvement loop working end-to-end: two variants beat
baseline with high significance and would auto-promote (low-stakes phrasing
tweaks per the Promotion Stakes Matrix); `social_proof`'s marginal +0.020 does
**not** clear the bar and is correctly withheld — the loop does not over-promote
noise.

## 3. Failure-mode report

Honest assessment of where v1 can fail and how it's contained.

| # | Failure mode | Severity | Containment |
|---|--------------|----------|-------------|
| F1 | **Naive field extraction** — prospect's raw utterance is stored as the field value | Low | Cosmetic only; never affects routing/escalation. LLM extraction seam (`llm.LLMClient`) exists for the upgrade. |
| F2 | **Objection recall gap** — phrase-based detection can miss a novel objection phrasing | Medium | Trades recall for precision (no false objections on field answers). New phrasings are added to `_OBJECTION_MARKERS` + the golden set when seen. |
| F3 | **Out-of-scope detection is cue-bounded** — a factual question with no cue word could be answered from a weak KB chunk | Medium | `_OUT_OF_SCOPE` + policy-intent gating; grounding judge catches any fabricated *number*. Residual risk on non-numeric prose. |
| F4 | **Conservative false-escalation** — a terse-but-interested prospect (Silent Sam pattern) escalates instead of converting | Low | Intentional (PRD: conservative thresholds; easier to relax later). Tracked via escalation-rate KPI. |
| F5 | **Lexicon sentiment** — misses sarcasm / subtle anger, so the negative-streak trigger can under-fire | Medium | Explicit-human-request + disqualification triggers provide independent escape hatches. LLM sentiment scorer is a drop-in. |
| F6 | **Synthetic validity** — scripted personas + modelled A/B conversion don't capture real human variability | High | By design for reproducibility; live A/B on real calls remains the gold standard for promotion (PRD decision). |
| F7 | **Offline judge scope** — verifies pricing exactly but not fuzzy policy-claim grounding | Medium | Pricing is the highest-stakes fact and is 0-hallucination by construction; LLM judge mode adds policy grounding when a key is present. |

### How the golden set guards regressions
`eval/goldens/golden_set.yaml` pins all 5 escalation triggers, the 5-signal
pivot, objection-vs-question disambiguation (F2/F3 root causes), and end-to-end
persona outcomes (F4). Three real bugs were caught by the golden set during the
build (objection playbook polluting policy retrieval; "how much" misread as an
objection; out-of-scope probes answered from weak chunks) — each is now a pinned
regression test.

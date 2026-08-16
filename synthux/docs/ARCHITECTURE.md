# SynthUX System Architecture

## 1. Pipeline overview

```
                     ┌──────────────────────┐
                     │ Product / Prototype  │
                     │ Figma / URL / Images │
                     └──────────┬───────────┘
                                │
                         UI Perception (A1)
                                │
                     ┌──────────▼───────────┐
                     │   UI World Model     │
                     │ elements / states /  │
                     │ actions / hierarchy  │
                     └──────────┬───────────┘
                                │
       ┌────────────────────────┴────────────────────────┐
       │                                                 │
 Persona Generator (A2)                          Task Generator (A3)
       │                                                 │
       └──────────────────────┬──────────────────────────┘
                              │
                  Synthetic User Agents (A4)
                   User 01 ... User 50/100
                              │
                   browser / prototype actions
                              │
                     Interaction Telemetry
                              │
            ┌─────────────────┴─────────────────┐
            │                                   │
      UX Evaluator (A5)                Behaviour Judge (A6)
            │                                   │
            └─────────────────┬─────────────────┘
                              │
                    Evidence Aggregator (A7)
                              │
                   Synthetic Research Report
```

Seven components, six of them LLM-backed agents (the aggregator is mostly
deterministic code + embeddings). Each has one job, its own prompt
(`prompts/`), and a declared model binding (`orchestrator.py::MODEL_ROUTING`).

## 2. Agents

### A1 — UI Perception
Converts screenshots (or Playwright-rendered pages, or Figma frame exports)
into a **UI World Model**: a graph of screens, visible elements, affordances,
and legal transitions. This is the only component allowed to see raw pixels
at full fidelity. Model: Qwen3-VL-8B; grounding assist: GUI-Actor / ShowUI.

The world model is *perceptual*, not structural: element records store what a
human could see (label text, visual prominence, position, apparent
affordance), never DOM ids, `aria-*` internals, or off-viewport content.
**If the synthetic user receives the DOM directly it becomes superhuman and
corrupts results** — the world model is the firewall that prevents that.

### A2 — Persona Generator
Retrieves candidate personas from datasets (Nemotron-Personas-India first),
filters by the study's audience definition, then applies the **behavioural
augmentation layer**: sampling the ten 0–1 behavioural dimensions from
cohort-conditioned distributions (see `schemas/persona.schema.json`).
Demographics are never treated as deterministic behaviour — they condition
the *distributions* the behaviour is sampled from, with per-participant noise.

### A3 — Task Generator
Turns the researcher's task ("Change my payment method from card to direct
debit") into: a success predicate over world-model states, an optimal action
path (for efficiency baselines), and persona-appropriate task phrasings (a
low-domain-knowledge user is told the *goal*, not the product's vocabulary).

### A4 — Synthetic User (× N participants)
One independent agent instance per participant. Each step it receives ONLY:
persona card, task goal, limited working memory (see §4), and the current
screen's perceptual description. It emits a think-aloud utterance, a
confidence rating, and one action. Model: Qwen3-8B for cognition; UI-TARS /
ShowUI for translating intent into concrete browser actions via Playwright
or the Figma prototype player.

### A5 — UX Evaluator
Scores each session against the metrics framework (`backend/synthux/scoring.py`):
effectiveness, efficiency, discoverability, comprehension, interaction
errors, cognitive friction, confidence. Deterministic where possible; LLM
only for classification (e.g. failure taxonomy).

### A6 — Behaviour Judge
**Runs on a different model (or at minimum a fully isolated instance) than
A4.** First pass sees only: persona constraints, task, screens observed,
actions, outcome, telemetry — **not** the user's internal reasoning. It asks
"what evidence demonstrates a usability problem?" Only in a second pass are
the think-aloud utterances exposed as secondary qualitative evidence. This
ordering prevents the invent-then-confirm failure mode.

### A7 — Evidence Aggregator
Embeds every observation (Qwen3-Embedding-0.6B, 1024-dim, pgvector), clusters
semantically similar problems, ranks clusters by severity (frequency ×
impact × cohort skew — see scoring.py), attaches verbatim evidence quotes,
and emits the report: task success, efficiency stats, failure taxonomy
breakdown, cohort comparison table, and per-issue recommendations.

## 3. Perception constraints (anti-cheating contract)

Every synthetic user operates under a hard contract, enforced structurally
(the data simply isn't in its context) and restated in its prompt:

1. No HTML/DOM access — only the perceptual screen description.
2. No knowledge of content below the viewport until it scrolls.
3. No inferring button behaviour the interface doesn't communicate.
4. Only information already seen (and still in working memory) is usable.
5. No product documentation or domain knowledge beyond the persona's
   `domain_expertise` level.

## 4. Working memory model

Real users forget. Each participant has a `memory` block in its persona:

| Profile | `working_memory_items` |
|---|---|
| Expert | 8 |
| Average | 4 |
| Distracted / low literacy | 2–3 |

`backend/synthux/memory.py` implements a salience-weighted ring buffer: each
observation gets a salience score (task relevance × visual prominence ×
recency), and only the top-k survive into the next step's context. Without
this, an LLM remembers every label from a 15-minute journey — humans don't.

## 5. Predicted attention

For every screen, the perception layer emits a **Predicted Attention** map:
per-element likelihood that this persona notices the element (driven by
visual prominence, position, scanning tendency, and label/goal semantic
match). It is compared against the expected target's attention to explain
discoverability failures. Always labeled a model prediction — never framed
as eye tracking.

## 6. Model routing & anti-correlation rules

- **User ≠ Judge:** A4 and A6 must not share a model instance; prefer
  different model families. A shared model rationalizes its own behaviour.
- **Participant independence:** each A4 instance runs with independent
  sampling (temperature per persona's `exploration` dimension, distinct
  seeds) and no shared conversation state. One LLM roleplaying 20 users
  produces correlated, fake-looking results — this is the failure mode the
  whole architecture exists to avoid.
- **Determinism where possible:** metrics, clustering thresholds, severity
  ranking are code, not model output.

## 7. Failure taxonomy

Every failed/struggling session is classified into:

`DISCOVERABILITY` · `COMPREHENSION` · `INFORMATION_ARCHITECTURE` ·
`EXPECTATION_MISMATCH` · `FEEDBACK` · `RECOVERY` · `COGNITIVE_LOAD` ·
`TRUST` · `CONTENT` · `ACCESSIBILITY`

(Enumerated in `models.py::FailureCategory`; definitions in the evaluator
prompt.)

## 8. Calibration path

Synthetic studies are stored with full telemetry so that when a matched human
study exists, we fit per-cohort correction factors:

```
calibration_factor(cohort, metric) =
    human_observed(metric) / synthetic_predicted(metric)
```

persisted in the `calibration_factors` table and applied (and disclosed) in
reports as "calibrated estimate". Over dozens of paired studies this is what
turns the product from an AI UX toy into a credible research system. Until a
study category has calibration data, reports label results **uncalibrated**.

## 9. Study modes

V1 ships mode 01; the schema and DB already carry a `mode` field for:

```
01 TASK TEST        Can users complete this?
02 DISCOVERABILITY  Can users find this?
03 COMPREHENSION    Do users understand this?
04 COMPARATIVE      Design A vs Design B
05+ accessibility personas, expert vs novice, cross-cultural, IA testing,
    copy testing, regression (re-run the same frozen participant panel on
    every product change; report deltas)
```

Regression mode reuses a **frozen panel**: persona + sampled behaviour +
seeds are persisted per study so the identical synthetic population can be
replayed against a new build, making success-rate deltas attributable to the
design change rather than sampling noise.

## 10. Serving & infra (V1)

- **Orchestration:** Python + FastAPI (`orchestrator.py` is transport-agnostic).
- **Interaction:** Playwright (live URLs), Figma REST prototype export
  (frames), plain screenshots (static walkthrough mode).
- **Models:** HF Inference Providers for Qwen3-VL / UI-TARS / Qwen3-8B;
  local ShowUI-2B / Vocaela-500M for cheap grounding during development.
- **Storage:** PostgreSQL + pgvector (`migrations/001_init.sql`).
- **UI:** Gradio (`ui/app.py`), later a proper front end; Gradio Spaces
  doubles as a demo API.

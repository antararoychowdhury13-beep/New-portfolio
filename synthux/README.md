# SynthUX — Synthetic UX Research Engine

AI Synthetic Usability Testing / Predictive UX Testing. The system simulates
diverse users attempting realistic tasks against a prototype or live product,
observes their behaviour, diagnoses friction, and aggregates evidence across
synthetic participants into a research-grade report.

**Positioning:** a predictive complement to human usability research — never a
replacement, and never presented as physiological data (attention output is
labeled *Predicted Attention*, not eye tracking).

**Core design principle:** we do **not** use one LLM pretending to be N users.
Each synthetic participant is an independent agent instance with its own
persona, behavioural parameters, and limited working memory — and the judge
runs on a **different model** than the user, so the system cannot rationalize
its own behaviour.

## Repository layout

```
synthux/
├── README.md                  ← you are here
├── docs/
│   └── ARCHITECTURE.md        ← six-agent pipeline, model routing, calibration
├── schemas/
│   └── persona.schema.json    ← JSON Schema for synthetic participants
├── personas/examples/         ← example persona files (YAML)
├── prompts/                   ← agent system prompts (one file per agent)
│   ├── 01_ui_perception.md
│   ├── 02_persona_generator.md
│   ├── 03_task_generator.md
│   ├── 04_synthetic_user.md
│   ├── 05_ux_evaluator.md
│   ├── 06_behaviour_judge.md
│   └── 07_evidence_aggregator.md
├── backend/
│   ├── pyproject.toml
│   ├── migrations/001_init.sql  ← Postgres + pgvector DDL
│   └── synthux/
│       ├── models.py          ← Pydantic domain models
│       ├── memory.py          ← limited working-memory simulation
│       ├── scoring.py         ← usability metrics engine (pure Python, tested)
│       ├── db.py              ← SQLAlchemy ORM mirror of the DDL
│       └── orchestrator.py    ← pipeline wiring + model routing
└── ui/
    └── app.py                 ← Gradio MVP ("SYNTH UX" study runner)
```

## Model stack (V1 — no fine-tuning)

| Role | Model | Serving |
|---|---|---|
| UI perception / world model | `Qwen/Qwen3-VL-8B-Instruct` | HF Inference Providers |
| GUI interaction (act) | `ByteDance-Seed/UI-TARS-1.5-7B` | HF Inference Providers |
| Persona reasoning / behaviour | `Qwen/Qwen3-8B` | HF Inference Providers |
| UX judge (separate instance) | `Qwen/Qwen3-VL-8B-Instruct` (isolated) or different family | HF Inference Providers |
| Issue clustering | `Qwen/Qwen3-Embedding-0.6B` (1024-dim) | local |
| Lightweight local grounding | `showlab/ShowUI-2B` / `vocaela/Vocaela-500M` | local (M1 16 GB) |

Persona sources: `nvidia/Nemotron-Personas-India` (CC BY 4.0, India-first),
`proj-persona/PersonaHub` (research only — licensing caveats, keep out of the
commercial path), `argilla/FinePersonas-v0.1` (selective, domain filter).

## Quickstart (mock mode)

```bash
cd synthux/backend
pip install -e ".[dev]"
pytest                      # runs the scoring engine tests
cd ../ui
python app.py               # launches the Gradio MVP with a mock runner
```

The MVP runs end-to-end on synthetic fixture data (no GPUs, no API keys) so
the report UI, metrics, and aggregation logic can be iterated on before any
model is wired in.

## Live perception (Step 3 — first real model)

`synthux/perception.py` is the live A1 agent: screenshot in →
Qwen3-VL-8B via HF Inference Providers → validated `ScreenPerception` out,
with a one-round correction retry on invalid JSON. It activates when a
Hugging Face token is present:

```bash
export SYNTHUX_HF_TOKEN=hf_...   # from huggingface.co/settings/tokens
cd synthux/backend
python -m synthux.perception tests/fixtures/payment_methods.png
```

The fixture is a rendered screen of the fictional billing app (including the
"Manage mandate" trap), so the smoke test doubles as a sanity check: the
output must list "Manage mandate" as a visible element WITHOUT resolving its
meaning — ambiguity in the UI must survive into the world model.

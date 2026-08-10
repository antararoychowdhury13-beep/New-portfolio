"""Pipeline wiring: model routing, study execution, aggregation.

Two runners:
- ``mock``  — deterministic simulation of a full study against a fixture
  product (an electricity-billing app with the "Manage mandate" trap). Runs
  with no models, no network, no GPU. This is what the MVP UI and the test
  suite use, so report rendering, metrics, and aggregation can be iterated
  before any model is attached.
- ``live``  — the real thing: HF Inference Providers + Playwright. Stubbed
  here; each agent's contract is its prompt file + models.py schema.
"""
from __future__ import annotations

import random
import uuid
from collections import defaultdict

from .models import (
    Action,
    CohortStats,
    FailureCategory,
    Issue,
    Observation,
    SessionMetrics,
    SessionTelemetry,
    StudyReport,
    TaskSpec,
    UserStep,
)
from .scoring import (
    aggregate_outcomes,
    cohort_stats,
    score_session,
    severity_score,
)

# ------------------------------------------------------------ model routing

# User ≠ Judge is a hard rule (docs/ARCHITECTURE.md §6): the judge must never
# share an instance with the synthetic user, or it rationalizes its own
# behaviour instead of auditing it.
MODEL_ROUTING: dict[str, dict[str, str]] = {
    "ui_perception":    {"model": "Qwen/Qwen3-VL-8B-Instruct", "serving": "hf-inference"},
    "grounding":        {"model": "showlab/ShowUI-2B", "serving": "local"},
    "gui_actor":        {"model": "ByteDance-Seed/UI-TARS-1.5-7B", "serving": "hf-inference"},
    "persona_generator": {"model": "Qwen/Qwen3-8B", "serving": "hf-inference"},
    "task_generator":   {"model": "Qwen/Qwen3-8B", "serving": "hf-inference"},
    "synthetic_user":   {"model": "Qwen/Qwen3-8B", "serving": "hf-inference"},
    "behaviour_judge":  {"model": "Qwen/Qwen3-VL-8B-Instruct", "serving": "hf-inference-isolated"},
    "embeddings":       {"model": "Qwen/Qwen3-Embedding-0.6B", "serving": "local"},
}

# Agglomerative clustering over observation embeddings (cosine distance).
CLUSTER_COSINE_THRESHOLD = 0.22


# ---------------------------------------------------------- mock fixture

# Fixture product: electricity-billing app. The IA trap is that changing the
# payment method to direct debit lives behind a link labelled "Manage
# mandate" — domain vocabulary novices don't have.
FIXTURE_TASK = TaskSpec(
    task_id="task-dd-switch",
    goal_statement={
        "novice": "Get your electricity bill paid automatically from your bank account instead of your card.",
        "expert": "Change your payment method from card to direct debit.",
    },
    success_screens=["dd_confirm"],
    partial_credit_screens=["manage_mandate"],
    optimal_path=[
        ("home", "Billing"),
        ("billing", "Payment methods"),
        ("payment_methods", "Manage mandate"),
        ("manage_mandate", "Switch to direct debit"),
    ],
    max_actions=18,
    expected_target_elements={
        "home": "Billing",
        "billing": "Payment methods",
        "payment_methods": "Manage mandate",
        "manage_mandate": "Switch to direct debit",
    },
)

_COHORT_PLANS = [
    ("low_digital_literacy", dict(digital_literacy=0.30, domain_expertise=0.20)),
    ("moderate_digital_literacy", dict(digital_literacy=0.55, domain_expertise=0.40)),
    ("expert_users", dict(digital_literacy=0.90, domain_expertise=0.60)),
    ("55+", dict(digital_literacy=0.40, domain_expertise=0.30)),
    ("low_domain_knowledge", dict(digital_literacy=0.60, domain_expertise=0.12)),
]

_CONFUSED_QUOTES = [
    "I'm not sure what 'mandate' means.",
    "I assumed 'Manage mandate' controls account permissions.",
    "I expected something called 'payment method' here.",
    "This is about my bank account, so maybe it's under Account?",
]


def _simulate_participant(rng: random.Random, pid: str, cohort: str, centres: dict) -> tuple[SessionTelemetry, list[Observation]]:
    """Stochastic walk through the fixture app, driven by two behaviour dims."""
    lit = min(1.0, max(0.0, rng.gauss(centres["digital_literacy"], 0.15)))
    dom = min(1.0, max(0.0, rng.gauss(centres["domain_expertise"], 0.15)))
    session_id = str(uuid.uuid4())
    steps: list[UserStep] = []
    observations: list[Observation] = []

    def step(screen: str, action: str, target: str | None, said: str, conf: float) -> None:
        steps.append(UserStep(
            index=len(steps), screen_id=screen,
            thinking_aloud=said, confidence=round(min(1.0, max(0.0, conf)), 2),
            feeling="confused" if conf < 0.35 else "neutral",
            action=Action(type=action, target_label=target),
            dwell_seconds=round(rng.uniform(2, 12), 1),
        ))

    # Step 1: find Billing (experts direct; novices may try Account first).
    if rng.random() < 0.25 * (1 - lit):
        step("home", "click", "Account", "Since this is about my bank account, I'll try Account.", 0.45)
        step("account", "back", None, "This is profile settings. Wrong place.", 0.25)
        observations.append(Observation(
            observation_id=str(uuid.uuid4()), session_id=session_id,
            screen_id="home", element_label="Account",
            category=FailureCategory.INFORMATION_ARCHITECTURE,
            statement="Payment change was expected under Account rather than Billing.",
            evidence="Visited Account first, backed out within one step.",
            quote="Since this is about my bank account, I'll try Account.",
        ))
    step("home", "click", "Billing", "Billing sounds like where payments live.", 0.5 + 0.4 * lit)
    step("billing", "click", "Payment methods", "Payment methods — that's what I want.", 0.6 + 0.3 * lit)

    # The trap: does 'Manage mandate' read as the payment-method control?
    understands_mandate = rng.random() < (0.15 + 0.75 * dom)
    if understands_mandate:
        step("payment_methods", "click", "Manage mandate", "Mandate — that's the direct debit authorisation.", 0.7)
        step("manage_mandate", "click", "Switch to direct debit", "Here it is.", 0.85)
        step("dd_confirm", "declare_done", None, "Done — direct debit is set up.", 0.9)
        return SessionTelemetry(
            session_id=session_id, participant_id=pid, cohorts=[cohort],
            task_id=FIXTURE_TASK.task_id, steps=steps,
            end_screen_id="dd_confirm", outcome_claimed_done=True,
        ), observations

    # Confusion branch.
    quote = rng.choice(_CONFUSED_QUOTES)
    step("payment_methods", "click", "Manage mandate", quote, 0.3)
    step("manage_mandate", "back", None, "This doesn't look like what I wanted.", 0.2)
    observations.append(Observation(
        observation_id=str(uuid.uuid4()), session_id=session_id,
        screen_id="payment_methods", element_label="Manage mandate",
        category=FailureCategory.COMPREHENSION,
        statement="The label 'Manage mandate' was interpreted as account administration, not payment setup.",
        evidence="Entered Manage mandate with low confidence, exited within one step without changes.",
        quote=quote,
    ))
    recovers = rng.random() < (0.2 + 0.6 * lit)
    if recovers:
        step("payment_methods", "click", "Help", "Let me check Help.", 0.3)
        step("help", "back", None, "Help says use 'Manage mandate' for direct debit. Odd name.", 0.5)
        step("payment_methods", "click", "Manage mandate", "Apparently that WAS the right place.", 0.55)
        step("manage_mandate", "click", "Switch to direct debit", "Switching now.", 0.7)
        step("dd_confirm", "declare_done", None, "That's done, I think.", 0.75)
        end, done = "dd_confirm", True
    else:
        step("payment_methods", "click", "Help", "I give up looking on my own.", 0.2)
        step("help", "give_up", None, "I'd rather call customer care than break something.", 0.1)
        end, done = "help", False
        observations.append(Observation(
            observation_id=str(uuid.uuid4()), session_id=session_id,
            screen_id="help", element_label=None,
            category=FailureCategory.TRUST,
            statement="Participant abandoned rather than risk an unclear payment change.",
            evidence="Opened Help after a failed attempt, then gave up.",
            quote="I'd rather call customer care than break something.",
        ))
    return SessionTelemetry(
        session_id=session_id, participant_id=pid, cohorts=[cohort],
        task_id=FIXTURE_TASK.task_id, steps=steps,
        end_screen_id=end, outcome_claimed_done=done,
    ), observations


def run_mock_study(n_participants: int = 25, seed: int = 7) -> tuple[StudyReport, list[SessionTelemetry], dict[str, SessionMetrics]]:
    """Run a full deterministic study against the fixture product."""
    rng = random.Random(seed)
    sessions: list[SessionTelemetry] = []
    all_obs: list[Observation] = []

    for i in range(n_participants):
        cohort, centres = _COHORT_PLANS[i % len(_COHORT_PLANS)]
        telemetry, obs = _simulate_participant(rng, f"IND_{i:05d}", cohort, centres)
        sessions.append(telemetry)
        all_obs.extend(obs)

    metrics = {s.session_id: score_session(s, FIXTURE_TASK) for s in sessions}
    outcomes = aggregate_outcomes(list(metrics.values()))
    cohorts = cohort_stats(sessions, metrics)
    issues = _aggregate_issues(sessions, metrics, all_obs, cohorts)

    report = StudyReport(
        study_id=str(uuid.uuid4()),
        n_participants=n_participants,
        success_rate=outcomes["success_rate"],
        success_ci=outcomes["success_ci"],
        partial_rate=outcomes["partial_rate"],
        failure_rate=outcomes["failure_rate"],
        abandon_rate=outcomes["abandon_rate"],
        median_actions=outcomes["median_actions"],
        optimal_actions=FIXTURE_TASK.optimal_actions,
        backtrack_rate=outcomes["backtrack_rate"],
        discoverability=outcomes["discoverability"],
        cohorts=cohorts,
        issues=issues,
    )
    return report, sessions, metrics


def _aggregate_issues(
    sessions: list[SessionTelemetry],
    metrics: dict[str, SessionMetrics],
    observations: list[Observation],
    cohorts: list[CohortStats],
) -> list[Issue]:
    """Mock-mode clustering: group by (category, element). Live mode replaces
    this key with agglomerative clustering over Qwen3 embeddings (pgvector)."""
    session_cohort = {s.session_id: s.cohorts[0] for s in sessions}
    cohort_n = {c.cohort: c.n for c in cohorts}
    blocked = {
        sid for sid, m in metrics.items() if m.success.value in ("FAILURE", "ABANDONED")
    }

    clusters: dict[tuple, list[Observation]] = defaultdict(list)
    for o in observations:
        clusters[(o.category, o.element_label)].append(o)

    issues: list[Issue] = []
    total = len(sessions)
    recommendations = {
        ("COMPREHENSION", "Manage mandate"): (
            "Payment terminology: 'Manage mandate'",
            "Rename 'Manage mandate' → 'Manage Direct Debit'.",
        ),
        ("INFORMATION_ARCHITECTURE", "Account"): (
            "Payment change expected under Account",
            "Cross-link payment methods from the Account screen.",
        ),
        ("TRUST", None): (
            "Abandonment at unclear payment change",
            "Add a reassurance note and explicit undo path before the switch.",
        ),
    }
    for (category, element), obs in clusters.items():
        affected_sessions = {o.session_id for o in obs}
        shares: dict[str, float] = defaultdict(float)
        for sid in affected_sessions:
            shares[session_cohort[sid]] += 1
        cohort_shares = {c: round(v / cohort_n[c], 3) for c, v in shares.items()}
        blocked_share = len(affected_sessions & blocked) / len(affected_sessions)
        score, severity = severity_score(
            len(affected_sessions), total, category,
            cohort_shares=cohort_shares, blocked_share=blocked_share,
        )
        title, fix = recommendations.get(
            (category.value, element), (f"{category.value.title()}: {element or 'flow'}", "Investigate.")
        )
        issues.append(Issue(
            issue_id=str(uuid.uuid4()), title=title, category=category,
            severity=severity, severity_score=score,
            affected_participants=len(affected_sessions), total_participants=total,
            cohort_shares=cohort_shares, statement=obs[0].statement,
            quotes=list(dict.fromkeys(o.quote for o in obs if o.quote))[:4],
            recommendation=fix,
        ))
    return sorted(issues, key=lambda i: -i.severity_score)

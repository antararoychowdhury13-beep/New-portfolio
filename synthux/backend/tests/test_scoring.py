"""Tests for the scoring engine and the mock study pipeline."""
import math

from synthux.memory import WorkingMemory
from synthux.models import (
    Action,
    FailureCategory,
    SessionTelemetry,
    Severity,
    SuccessLevel,
    TaskSpec,
    UserStep,
)
from synthux.orchestrator import FIXTURE_TASK, run_mock_study
from synthux.scoring import score_session, severity_score, wilson_ci


def _mk_session(path, end, done, task=FIXTURE_TASK):
    steps = [
        UserStep(
            index=i, screen_id=screen, thinking_aloud="...", confidence=0.5,
            action=Action(type=atype, target_label=target),
        )
        for i, (screen, atype, target) in enumerate(path)
    ]
    return SessionTelemetry(
        session_id="s1", participant_id="p1", cohorts=["test"],
        task_id=task.task_id, steps=steps,
        end_screen_id=end, outcome_claimed_done=done,
    )


def test_optimal_path_scores_clean_success():
    path = [
        ("home", "click", "Billing"),
        ("billing", "click", "Payment methods"),
        ("payment_methods", "click", "Manage mandate"),
        ("manage_mandate", "click", "Switch to direct debit"),
    ]
    m = score_session(_mk_session(path, "dd_confirm", True), FIXTURE_TASK)
    assert m.success == SuccessLevel.SUCCESS
    assert m.excess_actions == 0
    assert m.backtracks == 0
    assert m.lostness < 0.15
    assert m.discoverability.value == "IMMEDIATE"


def test_wrong_declare_done_is_failure_not_success():
    path = [("home", "click", "Billing"), ("billing", "declare_done", None)]
    m = score_session(_mk_session(path, "billing", True), FIXTURE_TASK)
    assert m.success == SuccessLevel.FAILURE


def test_give_up_is_abandoned():
    path = [("home", "click", "Billing"), ("billing", "give_up", None)]
    m = score_session(_mk_session(path, "billing", False), FIXTURE_TASK)
    assert m.success == SuccessLevel.ABANDONED


def test_backtracks_and_repeats_counted():
    path = [
        ("home", "click", "Account"),
        ("account", "back", None),
        ("home", "click", "Account"),      # repeated action
        ("account", "back", None),
        ("home", "click", "Billing"),
    ]
    m = score_session(_mk_session(path, "billing", False), FIXTURE_TASK)
    assert m.backtracks >= 2
    assert m.repeated_actions >= 1
    assert m.lostness > 0.3


def test_wilson_ci_sane():
    lo, hi = wilson_ci(18, 25)
    assert 0 < lo < 18 / 25 < hi < 1
    assert wilson_ci(0, 0) == (0.0, 0.0)
    lo_small, hi_small = wilson_ci(5, 5)
    assert hi_small <= 1.0 and lo_small < 1.0  # small-n never claims certainty


def test_severity_cohort_skew_upranks():
    base, _ = severity_score(10, 100, FailureCategory.COMPREHENSION,
                             cohort_shares={"all": 0.1}, blocked_share=0.5)
    skewed, _ = severity_score(10, 100, FailureCategory.COMPREHENSION,
                               cohort_shares={"low_digital_literacy": 0.74},
                               blocked_share=0.5)
    assert skewed > base


def test_severity_widespread_blocking_is_critical():
    score, level = severity_score(61, 100, FailureCategory.COMPREHENSION,
                                  cohort_shares={"low_domain_knowledge": 0.8},
                                  blocked_share=0.6)
    assert level == Severity.CRITICAL
    assert 0 < score <= 2


def test_working_memory_capacity_and_decay():
    wm = WorkingMemory(capacity=3, decay_per_step=0.3)
    for i in range(6):
        wm.observe(f"label {i}", salience=0.4 + 0.1 * i, step=i)
    assert len(wm.recall()) == 3
    assert wm.recall()[0] == "label 5"          # most salient first
    for _ in range(12):
        wm.tick()
    assert wm.recall() == []                    # everything decays eventually


def test_mock_study_deterministic_and_coherent():
    report1, sessions, metrics = run_mock_study(n_participants=50, seed=7)
    report2, _, _ = run_mock_study(n_participants=50, seed=7)
    assert report1.success_rate == report2.success_rate  # frozen panel replay

    assert report1.n_participants == 50
    assert len(sessions) == 50
    rates = (report1.success_rate + report1.partial_rate
             + report1.failure_rate + report1.abandon_rate)
    assert math.isclose(rates, 1.0, abs_tol=0.01)
    assert report1.success_ci[0] <= report1.success_rate <= report1.success_ci[1]
    assert report1.optimal_actions == 4
    assert report1.median_actions >= report1.optimal_actions

    # The planted trap must surface as the top issue.
    assert report1.issues, "expected issues from the fixture trap"
    top = report1.issues[0]
    assert top.category == FailureCategory.COMPREHENSION
    assert "mandate" in top.title.lower()
    assert top.quotes, "issues must carry verbatim evidence"
    assert top.affected_participants <= report1.n_participants

    # Experts should out-succeed low-digital-literacy users (who abandon),
    # and the comprehension trap must skew against the weaker cohort.
    success = {c.cohort: c.success_rate for c in report1.cohorts}
    assert success["expert_users"] > success["low_digital_literacy"]
    assert (top.cohort_shares["low_digital_literacy"]
            > top.cohort_shares["expert_users"])

    # Report must carry the synthetic-research disclaimer.
    assert "Synthetic study" in report1.disclaimer

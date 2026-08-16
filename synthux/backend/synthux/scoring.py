"""SynthUX scoring engine.

Every number in a SynthUX report is computed here, deterministically, from
telemetry — never asked of a model. LLMs classify; code measures.

Metric definitions
------------------
success            SUCCESS / PARTIAL / FAILURE (claimed done, predicate unmet)
                   / ABANDONED (gave up or hit the action cap)
excess_actions     actual - optimal (floored at 0)
backtracks         explicit `back` actions + returns to an already-left screen
repeated_actions   identical (screen, action, target) tuples issued again
lostness           Smith (1996): sqrt((N/S - 1)^2 + (R/N - 1)^2)
                   S = total screen visits, N = unique screens visited,
                   R = minimum screens required. 0 ≈ direct, ≥0.5 ≈ lost.
discoverability    IMMEDIATE (target element acted on during the first visit
                   to its screen) / AFTER_EXPLORATION / NEVER
severity           frequency^0.7 x impact x cohort-skew multiplier, mapped to
                   LOW/MEDIUM/HIGH/CRITICAL (see `severity_score`)
success CI         Wilson score interval (95%), suitable for small n
"""
from __future__ import annotations

import math
from collections import Counter
from statistics import median

from .models import (
    CohortStats,
    DiscoverabilityTier,
    FailureCategory,
    Severity,
    SessionMetrics,
    SessionTelemetry,
    SuccessLevel,
    TaskSpec,
)

# ------------------------------------------------------------ session level


def score_session(session: SessionTelemetry, task: TaskSpec) -> SessionMetrics:
    steps = session.steps
    actions = [s.action for s in steps]

    success = _success_level(session, task)

    actual = len(actions)
    optimal = task.optimal_actions
    excess = max(0, actual - optimal)

    backtracks = _count_backtracks(session)
    repeated = _count_repeated(session)
    lostness = _lostness(session, task)
    discover = _discoverability(session, task)

    confidences = [s.confidence for s in steps] or [0.0]
    mean_conf = sum(confidences) / len(confidences)
    final_conf = confidences[-1]

    return SessionMetrics(
        success=success,
        actual_actions=actual,
        optimal_actions=optimal,
        excess_actions=excess,
        backtracks=backtracks,
        repeated_actions=repeated,
        lostness=round(lostness, 3),
        discoverability=discover,
        mean_confidence=round(mean_conf, 3),
        final_confidence=round(final_conf, 3),
        confidence_band=_confidence_band(mean_conf),
        help_opened=any(a.type == "open_help" for a in actions),
    )


def _success_level(session: SessionTelemetry, task: TaskSpec) -> SuccessLevel:
    reached_success = session.end_screen_id in task.success_screens
    gave_up = any(s.action.type == "give_up" for s in session.steps)
    hit_cap = len(session.steps) >= task.max_actions

    if reached_success and session.outcome_claimed_done:
        return SuccessLevel.SUCCESS
    if gave_up or (hit_cap and not session.outcome_claimed_done):
        return SuccessLevel.ABANDONED
    if session.end_screen_id in task.partial_credit_screens:
        return SuccessLevel.PARTIAL
    # Declared done in the wrong place — a silent failure, the worst kind.
    return SuccessLevel.FAILURE


def _count_backtracks(session: SessionTelemetry) -> int:
    explicit = sum(1 for s in session.steps if s.action.type == "back")
    seen: set[str] = set()
    left: set[str] = set()
    returns = 0
    prev = None
    for s in session.steps:
        if prev is not None and s.screen_id != prev:
            left.add(prev)
            if s.screen_id in left and s.screen_id in seen:
                returns += 1
        seen.add(s.screen_id)
        prev = s.screen_id
    # An explicit `back` produces a return; count each backtrack once.
    return max(explicit, returns)


def _count_repeated(session: SessionTelemetry) -> int:
    sigs = Counter(
        (s.screen_id, s.action.type, s.action.target_label) for s in session.steps
    )
    return sum(n - 1 for n in sigs.values() if n > 1)


def _lostness(session: SessionTelemetry, task: TaskSpec) -> float:
    visits = [s.screen_id for s in session.steps]
    if session.end_screen_id and (not visits or visits[-1] != session.end_screen_id):
        visits.append(session.end_screen_id)
    if not visits:
        return 0.0
    S = len(visits)
    N = len(set(visits))
    R = max(1, len({sid for sid, _ in task.optimal_path} | set(task.success_screens)))
    return math.sqrt((N / S - 1.0) ** 2 + (R / N - 1.0) ** 2)


def _discoverability(session: SessionTelemetry, task: TaskSpec) -> DiscoverabilityTier:
    """Did the participant act on the expected target during the first visit
    to the screen where it lives?"""
    if not task.expected_target_elements:
        return DiscoverabilityTier.AFTER_EXPLORATION
    first_visit_done: set[str] = set()
    prev_screen = None
    for s in session.steps:
        target = task.expected_target_elements.get(s.screen_id)
        if target and s.action.target_label == target:
            if s.screen_id not in first_visit_done or s.screen_id == prev_screen:
                return DiscoverabilityTier.IMMEDIATE
            return DiscoverabilityTier.AFTER_EXPLORATION
        if prev_screen is not None and s.screen_id != prev_screen:
            first_visit_done.add(prev_screen)
        prev_screen = s.screen_id
    acted_labels = {s.action.target_label for s in session.steps}
    if acted_labels & set(task.expected_target_elements.values()):
        return DiscoverabilityTier.AFTER_EXPLORATION
    return DiscoverabilityTier.NEVER


def _confidence_band(mean_conf: float) -> str:
    if mean_conf >= 0.65:
        return "high"
    if mean_conf >= 0.4:
        return "medium"
    return "low"


# -------------------------------------------------------------- study level


def wilson_ci(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval — honest at the small n synthetic studies use."""
    if n == 0:
        return (0.0, 0.0)
    p = successes / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    half = (z / denom) * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2))
    return (round(max(0.0, centre - half), 3), round(min(1.0, centre + half), 3))


# Category impact weights: how strongly an issue in this category blocks task
# completion, on 0-1. Tuned initially by judgement; the calibration loop
# (docs/ARCHITECTURE.md §8) revises them from paired human studies.
IMPACT_WEIGHTS: dict[FailureCategory, float] = {
    FailureCategory.DISCOVERABILITY: 0.9,
    FailureCategory.COMPREHENSION: 0.9,
    FailureCategory.INFORMATION_ARCHITECTURE: 0.8,
    FailureCategory.EXPECTATION_MISMATCH: 0.7,
    FailureCategory.FEEDBACK: 0.6,
    FailureCategory.RECOVERY: 0.8,
    FailureCategory.COGNITIVE_LOAD: 0.6,
    FailureCategory.TRUST: 0.85,
    FailureCategory.CONTENT: 0.6,
    FailureCategory.ACCESSIBILITY: 0.95,
}


def severity_score(
    affected: int,
    total: int,
    category: FailureCategory,
    cohort_shares: dict[str, float] | None = None,
    blocked_share: float = 0.0,
) -> tuple[float, Severity]:
    """Rank an issue cluster.

    frequency^0.7      sub-linear: 30%→60% matters more than 60%→90%
    impact             category weight, boosted by the share of affected
                       sessions that actually FAILED/ABANDONED (blocked_share)
    skew multiplier    an issue concentrated in one cohort (e.g. 74% of
                       low-digital-literacy users) is up-weighted even if the
                       overall rate looks moderate — cohort harm hides in means
    """
    if total == 0:
        return (0.0, Severity.LOW)
    frequency = affected / total
    impact = IMPACT_WEIGHTS[category] * (0.6 + 0.4 * blocked_share)
    max_cohort = max(cohort_shares.values()) if cohort_shares else frequency
    skew = 1.0 + 0.5 * max(0.0, max_cohort - frequency)
    score = (frequency**0.7) * impact * skew

    if score >= 0.55 or (blocked_share >= 0.5 and frequency >= 0.4):
        level = Severity.CRITICAL
    elif score >= 0.35:
        level = Severity.HIGH
    elif score >= 0.18:
        level = Severity.MEDIUM
    else:
        level = Severity.LOW
    return (round(score, 3), level)


def aggregate_outcomes(
    metrics: list[SessionMetrics],
) -> dict[str, float | tuple[float, float]]:
    n = len(metrics)
    if n == 0:
        return {}
    counts = Counter(m.success for m in metrics)
    successes = counts[SuccessLevel.SUCCESS]
    tiers = Counter(m.discoverability for m in metrics)
    return {
        "n": n,
        "success_rate": round(successes / n, 3),
        "success_ci": wilson_ci(successes, n),
        "partial_rate": round(counts[SuccessLevel.PARTIAL] / n, 3),
        "failure_rate": round(counts[SuccessLevel.FAILURE] / n, 3),
        "abandon_rate": round(counts[SuccessLevel.ABANDONED] / n, 3),
        "median_actions": float(median(m.actual_actions for m in metrics)),
        "backtrack_rate": round(sum(1 for m in metrics if m.backtracks > 0) / n, 3),
        "discoverability": {
            tier.value: round(tiers[tier] / n, 3) for tier in DiscoverabilityTier
        },
    }


def cohort_stats(
    sessions: list[SessionTelemetry], metrics: dict[str, SessionMetrics]
) -> list[CohortStats]:
    by_cohort: dict[str, list[SessionMetrics]] = {}
    for s in sessions:
        for c in s.cohorts:
            by_cohort.setdefault(c, []).append(metrics[s.session_id])
    out = []
    for cohort, ms in sorted(by_cohort.items()):
        n = len(ms)
        wins = sum(1 for m in ms if m.success == SuccessLevel.SUCCESS)
        lo, hi = wilson_ci(wins, n)
        out.append(
            CohortStats(
                cohort=cohort,
                n=n,
                success_rate=round(wins / n, 3),
                ci_low=lo,
                ci_high=hi,
                median_actions=float(median(m.actual_actions for m in ms)),
            )
        )
    return sorted(out, key=lambda c: c.success_rate)

"""Domain models shared across the SynthUX pipeline.

These are the contracts between agents: every prompt in ``prompts/`` declares
which of these models its JSON output must match, and the scoring engine and
aggregator consume them. Keeping them in one module is deliberate — the
inter-agent interfaces ARE the architecture.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------- taxonomy

class FailureCategory(str, Enum):
    DISCOVERABILITY = "DISCOVERABILITY"            # didn't notice CTA
    COMPREHENSION = "COMPREHENSION"                # didn't understand label
    INFORMATION_ARCHITECTURE = "INFORMATION_ARCHITECTURE"  # wrong area
    EXPECTATION_MISMATCH = "EXPECTATION_MISMATCH"  # expected different behaviour
    FEEDBACK = "FEEDBACK"                          # didn't know action succeeded
    RECOVERY = "RECOVERY"                          # could not undo action
    COGNITIVE_LOAD = "COGNITIVE_LOAD"              # too many competing decisions
    TRUST = "TRUST"                                # didn't feel safe proceeding
    CONTENT = "CONTENT"                            # required information unclear
    ACCESSIBILITY = "ACCESSIBILITY"                # target hard to perceive/use


class SuccessLevel(str, Enum):
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"        # reached a partial-credit state
    FAILURE = "FAILURE"        # declared done but success predicate unmet
    ABANDONED = "ABANDONED"    # gave up / hit abandon condition


class DiscoverabilityTier(str, Enum):
    IMMEDIATE = "IMMEDIATE"            # target acted on at first exposure
    AFTER_EXPLORATION = "AFTER_EXPLORATION"
    NEVER = "NEVER"


class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


# ------------------------------------------------------------- perception

class UIElement(BaseModel):
    label: str
    kind: str = "text"                       # perceptual guess, not DOM truth
    region: str = "center"                   # 3x3 grid cell
    bbox: Optional[tuple[int, int, int, int]] = None
    prominence: float = Field(0.5, ge=0, le=1)
    affordance_clarity: float = Field(0.5, ge=0, le=1)


class ScreenPerception(BaseModel):
    """A1 output — the ONLY screen information a synthetic user ever sees."""
    screen_id: str
    screen_summary: str
    elements: list[UIElement]
    scroll_hint: bool = False


# ------------------------------------------------------------------ tasks

class TaskSpec(BaseModel):
    """A3 output."""
    task_id: str
    goal_statement: dict[str, str]           # expertise band -> phrasing
    success_screens: list[str]               # screen ids satisfying the predicate
    partial_credit_screens: list[str] = []
    optimal_path: list[tuple[str, str]]      # (screen_id, element_label)
    max_actions: int                         # abandon hard cap
    expected_target_elements: dict[str, str] = {}  # screen_id -> element label
    feasibility: str = "feasible"

    @property
    def optimal_actions(self) -> int:
        return len(self.optimal_path)


# -------------------------------------------------------------- telemetry

class Action(BaseModel):
    type: str                                # click|scroll|type|back|open_help|give_up|declare_done
    target_label: Optional[str] = None
    value: Optional[str] = None


class UserStep(BaseModel):
    """A4 output for one step, plus runtime-attached context."""
    index: int
    screen_id: str
    thinking_aloud: str
    confidence: float = Field(ge=0, le=1)
    feeling: str = "neutral"
    action: Action
    dwell_seconds: float = 0.0               # simulated from reading speed


class SessionTelemetry(BaseModel):
    """The full observable record of one participant's attempt."""
    session_id: str
    participant_id: str
    cohorts: list[str] = []
    task_id: str
    steps: list[UserStep]
    end_screen_id: str
    outcome_claimed_done: bool = False       # participant declared_done


# ------------------------------------------------------------- evaluation

class ComprehensionEvent(BaseModel):
    screen_id: str
    label: str
    verdict: str                             # understood|ambiguous|misinterpreted
    evidence: str


class Observation(BaseModel):
    """One specific, testable problem statement from one session (A5)."""
    observation_id: str
    session_id: str
    screen_id: str
    element_label: Optional[str] = None
    category: FailureCategory
    statement: str
    evidence: str
    quote: Optional[str] = None              # verbatim think-aloud


class SessionMetrics(BaseModel):
    """Computed by scoring.py — never by a model."""
    success: SuccessLevel
    actual_actions: int
    optimal_actions: int
    excess_actions: int
    backtracks: int
    repeated_actions: int
    lostness: float                          # Smith (1996), 0=direct, ~1=lost
    discoverability: DiscoverabilityTier
    mean_confidence: float
    final_confidence: float
    confidence_band: str                     # high|medium|low
    help_opened: bool


class SessionEvaluation(BaseModel):
    """A5 output for one session."""
    session_id: str
    metrics: SessionMetrics
    primary_failure: Optional[FailureCategory] = None
    secondary_failures: list[FailureCategory] = []
    comprehension_events: list[ComprehensionEvent] = []
    interaction_events: list[str] = []       # misclick|dead_end|unexpected_state|recovery
    friction_flags: list[str] = []           # decision_uncertainty|competing_choices|...
    observations: list[Observation] = []


class JudgeFinding(BaseModel):
    statement: str
    evidence: str
    screen_id: str
    element_label: Optional[str] = None
    attribution: str                         # interface|persona_limit|mixed
    confidence: float = Field(ge=0, le=1)
    qualitative_only: bool = False
    benign_explanation: Optional[str] = None


class JudgeReport(BaseModel):
    """A6 output (both passes merged into one record, provenance kept)."""
    session_id: str
    findings: list[JudgeFinding] = []
    implausible_steps: list[int] = []        # step indices violating persona constraints
    session_plausible: bool = True


# -------------------------------------------------------------- reporting

class Issue(BaseModel):
    """One clustered, ranked problem in the final report (A7)."""
    issue_id: str
    title: str
    category: FailureCategory
    severity: Severity
    severity_score: float
    affected_participants: int
    total_participants: int
    cohort_shares: dict[str, float] = {}     # cohort -> share affected within cohort
    statement: str
    quotes: list[str] = []
    recommendation: str
    calibrated: bool = False


class CohortStats(BaseModel):
    cohort: str
    n: int
    success_rate: float
    ci_low: float
    ci_high: float
    median_actions: float


class StudyReport(BaseModel):
    study_id: str
    mode: str = "TASK_TEST"
    disclaimer: str = (
        "Synthetic study — model-predicted behaviour. "
        "Uncalibrated estimates unless marked otherwise."
    )
    n_participants: int
    success_rate: float
    success_ci: tuple[float, float]
    partial_rate: float
    failure_rate: float
    abandon_rate: float
    median_actions: float
    optimal_actions: int
    backtrack_rate: float                    # share of sessions with >=1 backtrack
    discoverability: dict[str, float]        # tier -> share
    cohorts: list[CohortStats] = []
    issues: list[Issue] = []

"""SQLAlchemy ORM mirror of migrations/001_init.sql.

The SQL migration is the source of truth; this module exists so application
code gets typed access. Requires the ``db`` extra:
``pip install -e ".[db]"`` (sqlalchemy, psycopg, pgvector).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    Boolean,
    BigInteger,
    Float,
    ForeignKey,
    Integer,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

EMBED_DIM = 1024  # Qwen3-Embedding-0.6B


class Base(DeclarativeBase):
    pass


class Study(Base):
    __tablename__ = "studies"
    study_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(Text, default="TASK_TEST")
    product_context: Mapped[str | None] = mapped_column(Text)
    audience_spec: Mapped[dict] = mapped_column(JSONB)
    input_kind: Mapped[str] = mapped_column(Text)
    input_ref: Mapped[str | None] = mapped_column(Text)
    panel_frozen: Mapped[bool] = mapped_column(Boolean, default=False)
    parent_study_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("studies.study_id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Task(Base):
    __tablename__ = "tasks"
    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    study_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("studies.study_id", ondelete="CASCADE"))
    researcher_prompt: Mapped[str] = mapped_column(Text)
    spec: Mapped[dict] = mapped_column(JSONB)
    optimal_actions: Mapped[int] = mapped_column(Integer)


class Participant(Base):
    __tablename__ = "participants"
    participant_id: Mapped[str] = mapped_column(Text, primary_key=True)
    study_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("studies.study_id", ondelete="CASCADE"))
    source_dataset: Mapped[str] = mapped_column(Text)
    source_license: Mapped[str | None] = mapped_column(Text)
    persona: Mapped[dict] = mapped_column(JSONB)
    cohorts: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    seed: Mapped[int] = mapped_column(BigInteger)
    temperature: Mapped[float] = mapped_column(Float)


class Screen(Base):
    __tablename__ = "screens"
    study_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("studies.study_id", ondelete="CASCADE"), primary_key=True)
    screen_id: Mapped[str] = mapped_column(Text, primary_key=True)
    summary: Mapped[str | None] = mapped_column(Text)
    perception: Mapped[dict] = mapped_column(JSONB)
    screenshot: Mapped[str | None] = mapped_column(Text)


class Session(Base):
    __tablename__ = "sessions"
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    study_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("studies.study_id", ondelete="CASCADE"))
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.task_id"))
    participant_id: Mapped[str] = mapped_column(ForeignKey("participants.participant_id"))
    outcome: Mapped[str | None] = mapped_column(Text)
    end_screen_id: Mapped[str | None] = mapped_column(Text)
    claimed_done: Mapped[bool] = mapped_column(Boolean, default=False)
    plausible: Mapped[bool] = mapped_column(Boolean, default=True)
    metrics: Mapped[dict | None] = mapped_column(JSONB)
    started_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Step(Base):
    __tablename__ = "steps"
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.session_id", ondelete="CASCADE"), primary_key=True)
    step_index: Mapped[int] = mapped_column(Integer, primary_key=True)
    screen_id: Mapped[str] = mapped_column(Text)
    action_type: Mapped[str] = mapped_column(Text)
    target_label: Mapped[str | None] = mapped_column(Text)
    typed_value: Mapped[str | None] = mapped_column(Text)
    thinking_aloud: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float)
    feeling: Mapped[str | None] = mapped_column(Text)
    dwell_seconds: Mapped[float | None] = mapped_column(Float)
    memory_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    attention_map: Mapped[dict | None] = mapped_column(JSONB)


class ObservationRow(Base):
    __tablename__ = "observations"
    observation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.session_id", ondelete="CASCADE"))
    study_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("studies.study_id", ondelete="CASCADE"))
    screen_id: Mapped[str] = mapped_column(Text)
    element_label: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(Text)
    statement: Mapped[str] = mapped_column(Text)
    evidence: Mapped[str] = mapped_column(Text)
    quote: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text, default="evaluator")
    judge_attribution: Mapped[str | None] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBED_DIM))


class IssueRow(Base):
    __tablename__ = "issues"
    issue_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    study_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("studies.study_id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(Text)
    severity_score: Mapped[float] = mapped_column(Float)
    affected_participants: Mapped[int] = mapped_column(Integer)
    cohort_shares: Mapped[dict] = mapped_column(JSONB, default=dict)
    statement: Mapped[str] = mapped_column(Text)
    recommendation: Mapped[str] = mapped_column(Text)
    calibrated: Mapped[bool] = mapped_column(Boolean, default=False)
    centroid: Mapped[list[float] | None] = mapped_column(Vector(EMBED_DIM))


class IssueEvidence(Base):
    __tablename__ = "issue_evidence"
    issue_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("issues.issue_id", ondelete="CASCADE"), primary_key=True)
    observation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("observations.observation_id", ondelete="CASCADE"), primary_key=True)


class StudyReportRow(Base):
    __tablename__ = "study_reports"
    study_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("studies.study_id", ondelete="CASCADE"), primary_key=True)
    report: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class CalibrationFactor(Base):
    __tablename__ = "calibration_factors"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cohort: Mapped[str] = mapped_column(Text)
    metric: Mapped[str] = mapped_column(Text)
    domain: Mapped[str] = mapped_column(Text, default="*")
    factor: Mapped[float] = mapped_column(Float)
    n_paired_studies: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())

import time
import uuid
from sqlalchemy import (
    JSON,
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


def uid():
    return str(uuid.uuid4())


class Identity:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class Project(Identity, Base):
    __tablename__ = "projects"
    name: Mapped[str] = mapped_column(String(120))


class Dataset(Identity, Base):
    __tablename__ = "datasets"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")


class DatasetVersion(Identity, Base):
    __tablename__ = "dataset_versions"
    __table_args__ = (UniqueConstraint("dataset_id", "number"),)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    fingerprint: Mapped[str] = mapped_column(String(64))
    case_count: Mapped[int] = mapped_column(Integer)


class TestCase(Identity, Base):
    __tablename__ = "test_cases"
    __table_args__ = (UniqueConstraint("version_id", "case_id"),)
    version_id: Mapped[str] = mapped_column(
        ForeignKey("dataset_versions.id"), index=True
    )
    case_id: Mapped[str] = mapped_column(String(100))
    data: Mapped[dict] = mapped_column(JSON)


class PromptVersion(Identity, Base):
    __tablename__ = "prompt_versions"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    template: Mapped[str] = mapped_column(Text)


class Experiment(Identity, Base):
    __tablename__ = "experiments"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    config: Mapped[dict] = mapped_column(JSON)


class Run(Identity, Base):
    __tablename__ = "evaluation_runs"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiments.id"))
    dataset_version_id: Mapped[str] = mapped_column(ForeignKey("dataset_versions.id"))
    name: Mapped[str] = mapped_column(String(120))
    config: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", index=True)
    total: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[float | None] = mapped_column(Float)
    finished_at: Mapped[float | None] = mapped_column(Float)


class Result(Identity, Base):
    __tablename__ = "evaluation_results"
    __table_args__ = (
        UniqueConstraint("run_id", "test_case_id"),
        Index("ix_results_available", "status", "available_at"),
    )
    run_id: Mapped[str] = mapped_column(ForeignKey("evaluation_runs.id"), index=True)
    test_case_id: Mapped[str] = mapped_column(ForeignKey("test_cases.id"))
    case_id: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[float] = mapped_column(Float, default=time.time)
    lease_until: Mapped[float | None] = mapped_column(Float)
    lease_token: Mapped[str | None] = mapped_column(String(36))
    output: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(String(80))
    score: Mapped[float | None] = mapped_column(Float)
    passed: Mapped[bool | None] = mapped_column(Boolean)
    latency_ms: Mapped[float | None] = mapped_column(Float)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost: Mapped[float] = mapped_column(Float, default=0)
    trace_id: Mapped[str | None] = mapped_column(String(32), index=True)
    spans: Mapped[list] = mapped_column(JSON, default=list)
    human_score: Mapped[float | None] = mapped_column(Float)
    human_note: Mapped[str | None] = mapped_column(Text)


class Score(Identity, Base):
    __tablename__ = "evaluator_scores"
    __table_args__ = (UniqueConstraint("result_id", "evaluator"),)
    result_id: Mapped[str] = mapped_column(
        ForeignKey("evaluation_results.id"), index=True
    )
    evaluator: Mapped[str] = mapped_column(String(50))
    version: Mapped[str] = mapped_column(String(30))
    value: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSON, default=dict)


class Attempt(Identity, Base):
    __tablename__ = "execution_attempts"
    __table_args__ = (UniqueConstraint("result_id", "number"),)
    result_id: Mapped[str] = mapped_column(
        ForeignKey("evaluation_results.id"), index=True
    )
    number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20))
    error: Mapped[str | None] = mapped_column(String(80))
    finished_at: Mapped[float | None] = mapped_column(Float)


class Baseline(Identity, Base):
    __tablename__ = "baselines"
    __table_args__ = (UniqueConstraint("project_id", "name"),)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    name: Mapped[str] = mapped_column(String(120))
    run_id: Mapped[str] = mapped_column(ForeignKey("evaluation_runs.id"))


class RegressionReport(Identity, Base):
    __tablename__ = "regression_reports"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    baseline_id: Mapped[str] = mapped_column(ForeignKey("evaluation_runs.id"))
    candidate_id: Mapped[str] = mapped_column(ForeignKey("evaluation_runs.id"))
    decision: Mapped[str] = mapped_column(String(20))
    report: Mapped[dict] = mapped_column(JSON)


class OnlineTrace(Identity, Base):
    __tablename__ = "online_traces"
    __table_args__ = (UniqueConstraint("project_id", "trace_id"),)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    trace_id: Mapped[str] = mapped_column(String(32), index=True)
    service: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20))
    latency_ms: Mapped[float] = mapped_column(Float)
    spans: Mapped[list] = mapped_column(JSON)

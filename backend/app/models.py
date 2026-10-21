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
    false,
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
    content_purged_at: Mapped[float | None] = mapped_column(Float)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")


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
    trace_id: Mapped[str | None] = mapped_column(String(32), index=True)
    spans: Mapped[list] = mapped_column(JSON, default=list, server_default="[]")
    trace_complete: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false()
    )
    trace_purged_at: Mapped[float | None] = mapped_column(Float)


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


class User(Identity, Base):
    __tablename__ = "users"
    name: Mapped[str] = mapped_column(String(120))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)


class Membership(Identity, Base):
    __tablename__ = "project_memberships"
    __table_args__ = (UniqueConstraint("project_id", "user_id"),)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))


class Credential(Identity, Base):
    __tablename__ = "credentials"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    ciphertext: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class ApplicationTarget(Identity, Base):
    __tablename__ = "application_targets"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    url: Mapped[str] = mapped_column(String(2000))
    credential_id: Mapped[str | None] = mapped_column(ForeignKey("credentials.id"))
    protocol: Mapped[str] = mapped_column(String(20), default="evalscope-v1")


class UsageEvent(Identity, Base):
    __tablename__ = "usage_events"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("evaluation_runs.id"), index=True)
    attempt_id: Mapped[str] = mapped_column(
        ForeignKey("execution_attempts.id"), index=True
    )
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("usage_events.id"))
    scope: Mapped[str] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(String(120))
    state: Mapped[str] = mapped_column(String(20), default="STARTED")
    source: Mapped[str] = mapped_column(String(20), default="provider")
    billable: Mapped[bool] = mapped_column(Boolean, default=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    input_rate: Mapped[float | None] = mapped_column(Float)
    output_rate: Mapped[float | None] = mapped_column(Float)
    estimated_cost: Mapped[float | None] = mapped_column(Float)
    request_id: Mapped[str | None] = mapped_column(String(200))
    error: Mapped[str | None] = mapped_column(String(80))
    finished_at: Mapped[float | None] = mapped_column(Float)


class ReviewCampaign(Identity, Base):
    __tablename__ = "review_campaigns"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    rubric: Mapped[str] = mapped_column(Text)
    minimum_reviews: Mapped[int] = mapped_column(Integer, default=2)


class ReviewItem(Identity, Base):
    __tablename__ = "review_items"
    __table_args__ = (UniqueConstraint("campaign_id", "result_id"),)
    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("review_campaigns.id"), index=True
    )
    result_id: Mapped[str] = mapped_column(ForeignKey("evaluation_results.id"))


class HumanLabel(Identity, Base):
    __tablename__ = "human_labels"
    __table_args__ = (UniqueConstraint("item_id", "reviewer_id"),)
    item_id: Mapped[str] = mapped_column(ForeignKey("review_items.id"), index=True)
    reviewer_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    score: Mapped[float] = mapped_column(Float)
    category: Mapped[str] = mapped_column(String(30))
    rationale: Mapped[str] = mapped_column(Text)


class RetentionPolicy(Identity, Base):
    __tablename__ = "retention_policies"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    content_days: Mapped[int] = mapped_column(Integer, default=30)
    trace_days: Mapped[int] = mapped_column(Integer, default=90)


class AuditEvent(Identity, Base):
    __tablename__ = "audit_events"
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id"), index=True
    )
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(60))
    target_id: Mapped[str | None] = mapped_column(String(36))
    details: Mapped[dict] = mapped_column(JSON, default=dict)

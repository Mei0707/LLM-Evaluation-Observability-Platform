import math
import string
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class CaseInput(StrictModel):
    case_id: str = Field(min_length=1, max_length=100)
    input: str = Field(min_length=1, max_length=20000)
    reference_answer: str = Field(max_length=20000)
    reference_contexts: list[str] = Field(default_factory=list, max_length=100)
    relevant_document_ids: list[str] = Field(default_factory=list, max_length=1000)
    retrieved_document_ids: list[str] = Field(default_factory=list, max_length=1000)
    tags: list[str] = Field(default_factory=list, max_length=30)
    # Explicit synthetic fixtures, only consumed by the mock provider.
    mock_output: str | None = Field(default=None, max_length=20000)
    mock_failure: Literal["timeout", "rate_limit", "permanent", "malformed"] | None = (
        None
    )


class VersionInput(StrictModel):
    cases: list[CaseInput] = Field(min_length=1, max_length=5000)

    @field_validator("cases")
    @classmethod
    def unique_cases(cls, cases):
        if len({c.case_id for c in cases}) != len(cases):
            raise ValueError("case_id must be unique within a dataset version")
        return cases


class DatasetInput(VersionInput):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)


class PromptInput(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    template: str = Field(min_length=1, max_length=30000)

    @field_validator("template")
    @classmethod
    def safe_template(cls, template):
        fields = [
            field
            for _, field, spec, conv in string.Formatter().parse(template)
            if field is not None
        ]
        if (
            not fields
            or "input" not in fields
            or any(f not in {"input", "contexts"} for f in fields)
        ):
            raise ValueError(
                "Template requires {input}; only {input} and {contexts} placeholders are supported"
            )
        for _, field, spec, conv in string.Formatter().parse(template):
            if spec or conv:
                raise ValueError("Format specifiers and conversions are not supported")
        return template


Evaluator = Literal["exact_match", "semantic_similarity", "retrieval", "llm_judge"]


class RunConfig(StrictModel):
    dataset_version_id: str
    prompt_version_id: str
    provider: Literal["mock", "openai_compatible"] = "mock"
    model: str = Field(default="mock-balanced", min_length=1, max_length=120)
    temperature: float = Field(default=0, ge=0, le=2)
    evaluators: list[Evaluator] = Field(
        default_factory=lambda: ["exact_match"], min_length=1, max_length=4
    )
    concurrency: int = Field(default=5, ge=1, le=32)
    max_attempts: int = Field(default=3, ge=1, le=5)
    timeout_seconds: float = Field(default=30, ge=0.01, le=120)
    pass_threshold: float = Field(default=0.8, ge=0, le=1)
    judge_model: str = Field(default="", max_length=120)
    embedding_model: str = Field(default="", max_length=120)
    retrieval_k: int = Field(default=5, ge=1, le=100)
    input_cost_per_million: float = Field(default=0, ge=0, le=1000)
    output_cost_per_million: float = Field(default=0, ge=0, le=1000)
    capture_content: bool = False
    mock_latency_ms: float = Field(default=80, ge=0, le=5000)

    @model_validator(mode="after")
    def validate_evaluators(self):
        if len(set(self.evaluators)) != len(self.evaluators):
            raise ValueError("Evaluators must be unique")
        if self.provider == "mock":
            if self.model not in {"mock-balanced", "mock-precise", "mock-regressed"}:
                raise ValueError(
                    "Choose mock-balanced, mock-precise, or mock-regressed"
                )
            if {"semantic_similarity", "llm_judge"} & set(self.evaluators):
                raise ValueError(
                    "Embedding and judge evaluators require a live provider; mock scores are not represented as LLM judgments"
                )
        else:
            if "llm_judge" in self.evaluators and not self.judge_model:
                raise ValueError("judge_model is required")
            if "semantic_similarity" in self.evaluators and not self.embedding_model:
                raise ValueError("embedding_model is required")
        return self


class ExperimentInput(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    config: RunConfig


class StartRun(StrictModel):
    experiment_id: str
    name: str | None = Field(default=None, min_length=1, max_length=120)


class ComparisonInput(StrictModel):
    baseline_id: str
    candidate_id: str


class Thresholds(StrictModel):
    minimum_pass_rate: float = Field(default=0.9, ge=0, le=1)
    maximum_pass_rate_drop: float = Field(default=0.03, ge=0, le=1)
    maximum_p95_latency_ms: float = Field(default=2500, gt=0)
    maximum_error_rate: float = Field(default=0.02, ge=0, le=1)
    minimum_coverage: float = Field(default=0.95, gt=0, le=1)
    minimum_paired_cases: int = Field(default=5, ge=1)


class GateInput(ComparisonInput):
    thresholds: Thresholds = Field(default_factory=Thresholds)


class BaselineInput(StrictModel):
    name: str = Field(default="main", min_length=1, max_length=120)
    run_id: str


class HumanReview(StrictModel):
    score: float = Field(ge=0, le=1)
    note: str = Field(default="", max_length=2000)


class SpanAttributes(StrictModel):
    model: str | None = Field(default=None, max_length=120)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    document_count: int | None = Field(default=None, ge=0)
    error_category: (
        Literal[
            "timeout",
            "rate_limit",
            "authentication",
            "tool_error",
            "retrieval_error",
            "unknown",
        ]
        | None
    ) = None


class OnlineSpan(StrictModel):
    name: Literal["request", "retrieval", "prompt", "generation", "tool", "evaluation"]
    span_id: str = Field(pattern=r"^[0-9a-f]{16}$")
    parent_span_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{16}$")
    started_at: float = Field(gt=0)
    ended_at: float = Field(gt=0)
    status: Literal["OK", "ERROR"] = "OK"
    attributes: SpanAttributes = Field(default_factory=SpanAttributes)

    @model_validator(mode="after")
    def valid_duration(self):
        if self.ended_at < self.started_at or self.ended_at - self.started_at > 86400:
            raise ValueError("Span duration must be between 0 and 24 hours")
        return self


class OnlineTraceInput(StrictModel):
    trace_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    service: str = Field(min_length=1, max_length=120)
    spans: list[OnlineSpan] = Field(min_length=1, max_length=512)

    @model_validator(mode="after")
    def validate_tree(self):
        spans = {s.span_id: s for s in self.spans}
        if len(spans) != len(self.spans):
            raise ValueError("Span IDs must be unique")
        for span in self.spans:
            seen, current = set(), span
            while current.parent_span_id:
                if current.span_id in seen or current.parent_span_id not in spans:
                    raise ValueError(
                        "Span parents must form an acyclic tree within this trace"
                    )
                seen.add(current.span_id)
                current = spans[current.parent_span_id]
        return self

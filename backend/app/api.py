import asyncio
import csv
import hmac
import io
import json
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field, ValidationError
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from sqlalchemy import case as sql_case, func, select, update, text
from sqlalchemy.exc import IntegrityError
from .config import settings
from .db import Base, engine, transaction
from .models import (
    Attempt,
    Baseline,
    Dataset,
    DatasetVersion,
    Experiment,
    OnlineTrace,
    Project,
    PromptVersion,
    RegressionReport,
    Result,
    Run,
    Score,
    TestCase,
    uid,
)
from .schemas import (
    BaselineInput,
    CaseInput,
    ComparisonInput,
    DatasetInput,
    ExperimentInput,
    GateInput,
    HumanReview,
    OnlineTraceInput,
    PromptInput,
    StartRun,
    StrictModel,
    VersionInput,
)
from .seed import DEFAULT_PROJECT, seed
from .services import (
    TERMINAL,
    aggregate,
    check_gate,
    columns,
    compare,
    create_version,
    freeze_config,
    require,
    run_view,
    start_run,
)
from .worker import serve
from .telemetry import HTTP_REQUESTS, HTTP_DURATION


@asynccontextmanager
async def lifespan(app):
    # SQLite convenience only; deployed PostgreSQL uses Alembic migrations.
    if settings.database_url.startswith("sqlite"):
        Base.metadata.create_all(engine)
    if settings.seed_demo:
        with transaction() as session:
            seed(session)
    else:
        with transaction() as session:
            if not session.get(Project, DEFAULT_PROJECT):
                session.add(Project(id=DEFAULT_PROJECT, name="Default workspace"))
    stop = asyncio.Event()
    task = asyncio.create_task(serve(stop)) if settings.embedded_worker else None
    yield
    stop.set()
    if task:
        await task


app = FastAPI(title="EvalScope API", version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def access_and_size(request: Request, call_next):
    started = time.monotonic()
    if request.url.path.startswith(("/api/", "/metrics")) and settings.api_token:
        supplied = request.headers.get("authorization", "").removeprefix("Bearer ")
        if not hmac.compare_digest(supplied.encode(), settings.api_token.encode()):
            return JSONResponse(
                {"detail": "Valid bearer token required"}, status_code=401
            )
    if request.method in {"POST", "PUT", "PATCH"}:
        size, chunks = 0, []
        async for chunk in request.stream():
            size += len(chunk)
            if size > 6 * 1024 * 1024:
                return JSONResponse(
                    {"detail": "Request exceeds the 6 MiB limit"}, status_code=413
                )
            chunks.append(chunk)
        request._body = b"".join(chunks)
    response = await call_next(request)
    route = getattr(request.scope.get("route"), "path", "unmatched")
    if route.startswith("/api/"):
        method = (
            request.method
            if request.method in {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"}
            else "OTHER"
        )
        HTTP_REQUESTS.labels(method, route, f"{response.status_code//100}xx").inc()
        HTTP_DURATION.labels(route).observe(time.monotonic() - started)
    return response


@app.exception_handler(IntegrityError)
async def integrity_error(request, exc):
    return JSONResponse(
        {"detail": "Conflicting write; refresh and retry"}, status_code=409
    )


def project(x_project_id: str = Header(default=DEFAULT_PROJECT)):
    with transaction() as session:
        require(session, Project, x_project_id)
    return x_project_id


@app.get("/health")
def health():
    try:
        with transaction() as session:
            session.execute(text("SELECT 1"))
        return {"status": "ok", "version": "0.1.0"}
    except Exception:
        return JSONResponse({"status": "unavailable"}, status_code=503)


@app.get("/api/v1/workspace")
def workspace(project_id=Depends(project)):
    with transaction() as session:
        return {
            "project": columns(require(session, Project, project_id)),
            "mode": "local prototype",
            "provider_configured": bool(settings.provider_key),
            "auth_enabled": bool(settings.api_token),
        }


@app.get("/api/v1/overview")
def overview(project_id=Depends(project)):
    with transaction() as session:
        runs = session.scalars(
            select(Run)
            .where(Run.project_id == project_id)
            .order_by(Run.created_at.desc())
            .limit(100)
        ).all()
        results = session.scalars(
            select(Result).join(Run).where(Run.project_id == project_id)
        ).all()
        return {
            "metrics": aggregate(results),
            "run_count": session.scalar(
                select(func.count())
                .select_from(Run)
                .where(Run.project_id == project_id)
            ),
            "active_runs": sum(run.status not in TERMINAL for run in runs),
            "dataset_count": session.scalar(
                select(func.count())
                .select_from(Dataset)
                .where(Dataset.project_id == project_id)
            ),
            "runs": [run_view(session, run) for run in runs],
            "error_categories": dict(
                session.execute(
                    select(Result.error, func.count())
                    .join(Run)
                    .where(Run.project_id == project_id, Result.error.is_not(None))
                    .group_by(Result.error)
                ).all()
            ),
        }


def dataset_view(session, dataset):
    versions = session.scalars(
        select(DatasetVersion)
        .where(DatasetVersion.dataset_id == dataset.id)
        .order_by(DatasetVersion.number.desc())
    ).all()
    return {**columns(dataset), "versions": [columns(v) for v in versions]}


@app.get("/api/v1/datasets")
def datasets(project_id=Depends(project)):
    with transaction() as session:
        return [
            dataset_view(session, d)
            for d in session.scalars(
                select(Dataset)
                .where(Dataset.project_id == project_id)
                .order_by(Dataset.created_at.desc())
            )
        ]


@app.post("/api/v1/datasets", status_code=201)
def create_dataset(body: DatasetInput, project_id=Depends(project)):
    with transaction() as session:
        dataset = Dataset(
            id=uid(),
            project_id=project_id,
            name=body.name,
            description=body.description,
        )
        session.add(dataset)
        session.flush()
        create_version(session, dataset, body.cases)
        session.flush()
        return dataset_view(session, dataset)


class ImportInput(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    format: Literal["jsonl", "csv"]
    content: str = Field(min_length=1, max_length=5_000_000)
    dataset_id: str | None = None


@app.post("/api/v1/datasets/import", status_code=201)
def import_dataset(body: ImportInput, project_id=Depends(project)):
    try:
        if body.format == "jsonl":
            rows = [
                json.loads(line) for line in body.content.splitlines() if line.strip()
            ]
        else:
            rows = list(csv.DictReader(io.StringIO(body.content)))
            for row in rows:
                for key in [
                    "tags",
                    "reference_contexts",
                    "relevant_document_ids",
                    "retrieved_document_ids",
                ]:
                    if key in row:
                        row[key] = json.loads(row[key]) if row[key] else []
                for key in ["mock_output", "mock_failure"]:
                    if row.get(key) == "":
                        row[key] = None
        validated = VersionInput(cases=rows)
    except (ValueError, TypeError, csv.Error, ValidationError):
        raise HTTPException(
            422,
            "Invalid dataset. Each row requires unique case_id, input, reference_answer; CSV list columns must contain JSON arrays.",
        )
    if body.dataset_id:
        return add_version(body.dataset_id, validated, project_id)
    return create_dataset(
        DatasetInput(name=body.name, cases=validated.cases), project_id
    )


@app.get("/api/v1/datasets/{dataset_id}")
def get_dataset(dataset_id: str, project_id=Depends(project)):
    with transaction() as session:
        return dataset_view(session, require(session, Dataset, dataset_id, project_id))


@app.post("/api/v1/datasets/{dataset_id}/versions", status_code=201)
def add_version(dataset_id: str, body: VersionInput, project_id=Depends(project)):
    with transaction() as session:
        dataset = require(session, Dataset, dataset_id, project_id)
        version = create_version(session, dataset, body.cases)
        session.flush()
        return columns(version)


@app.get("/api/v1/dataset-versions/{version_id}/cases")
def get_cases(
    version_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    project_id=Depends(project),
):
    with transaction() as session:
        version = require(session, DatasetVersion, version_id)
        require(session, Dataset, version.dataset_id, project_id)
        return {
            "total": version.case_count,
            "items": [
                case.data
                for case in session.scalars(
                    select(TestCase)
                    .where(TestCase.version_id == version_id)
                    .order_by(TestCase.case_id)
                    .offset(offset)
                    .limit(limit)
                )
            ],
        }


@app.get("/api/v1/prompts")
def prompts(project_id=Depends(project)):
    with transaction() as session:
        return [
            columns(p)
            for p in session.scalars(
                select(PromptVersion)
                .where(PromptVersion.project_id == project_id)
                .order_by(PromptVersion.created_at.desc())
            )
        ]


@app.post("/api/v1/prompts", status_code=201)
def create_prompt(body: PromptInput, project_id=Depends(project)):
    with transaction() as session:
        prompt = PromptVersion(id=uid(), project_id=project_id, **body.model_dump())
        session.add(prompt)
        session.flush()
        return columns(prompt)


@app.get("/api/v1/experiments")
def experiments(project_id=Depends(project)):
    with transaction() as session:
        return [
            columns(e)
            for e in session.scalars(
                select(Experiment)
                .where(Experiment.project_id == project_id)
                .order_by(Experiment.created_at.desc())
            )
        ]


@app.post("/api/v1/experiments", status_code=201)
def create_experiment(body: ExperimentInput, project_id=Depends(project)):
    config = body.config.model_dump()
    with transaction() as session:
        freeze_config(session, config, project_id)
        if config["provider"] != "mock" and not settings.provider_key:
            raise HTTPException(
                422,
                "Set PROVIDER_API_KEY on the server before running live evaluations",
            )
        experiment = Experiment(
            id=uid(), project_id=project_id, name=body.name, config=config
        )
        session.add(experiment)
        session.flush()
        return columns(experiment)


@app.post("/api/v1/runs", status_code=202)
def create_run(body: StartRun, project_id=Depends(project)):
    with transaction() as session:
        run = start_run(
            session,
            require(session, Experiment, body.experiment_id, project_id),
            body.name,
        )
        session.flush()
        return run_view(session, run)


@app.get("/api/v1/runs")
def runs(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    project_id=Depends(project),
):
    with transaction() as session:
        query = select(Run).where(Run.project_id == project_id)
        total = session.scalar(
            select(func.count()).select_from(Run).where(Run.project_id == project_id)
        )
        return {
            "total": total,
            "items": [
                run_view(session, r)
                for r in session.scalars(
                    query.order_by(Run.created_at.desc()).offset(offset).limit(limit)
                )
            ],
        }


@app.get("/api/v1/runs/{run_id}")
def get_run(run_id: str, project_id=Depends(project)):
    with transaction() as session:
        return run_view(session, require(session, Run, run_id, project_id))


@app.post("/api/v1/runs/{run_id}/cancel")
def cancel_run(run_id: str, project_id=Depends(project)):
    with transaction() as session:
        run = session.scalar(
            select(Run)
            .where(Run.id == run_id, Run.project_id == project_id)
            .with_for_update()
        )
        if not run:
            raise HTTPException(404, "Run not found")
        if run.status in TERMINAL:
            raise HTTPException(409, "Run has already finished")
        run.status, run.finished_at = "CANCELED", time.time()
        ids = select(Result.id).where(
            Result.run_id == run_id, Result.status.in_(["RUNNING", "PENDING"])
        )
        session.execute(
            update(Attempt)
            .where(Attempt.result_id.in_(ids), Attempt.status == "RUNNING")
            .values(status="CANCELED", finished_at=time.time())
        )
        session.execute(
            update(Result)
            .where(Result.run_id == run_id, Result.status.in_(["RUNNING", "PENDING"]))
            .values(status="CANCELED", lease_token=None, lease_until=None)
        )
        session.flush()
        return run_view(session, run)


def result_view(session, result, with_case=False):
    data = {
        k: v
        for k, v in columns(result).items()
        if k not in {"lease_token", "lease_until", "spans"}
    }
    data["scores"] = [
        columns(s)
        for s in session.scalars(select(Score).where(Score.result_id == result.id))
    ]
    if with_case:
        data["case"] = session.get(TestCase, result.test_case_id).data
        data["spans"] = result.spans
        data["attempt_history"] = [
            columns(a)
            for a in session.scalars(
                select(Attempt)
                .where(Attempt.result_id == result.id)
                .order_by(Attempt.number)
            )
        ]
    return data


@app.get("/api/v1/runs/{run_id}/results")
def get_results(
    run_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    status: str | None = None,
    project_id=Depends(project),
):
    with transaction() as session:
        require(session, Run, run_id, project_id)
        query = select(Result).where(Result.run_id == run_id)
        if status:
            query = query.where(Result.status == status)
        return {
            "total": session.scalar(select(func.count()).select_from(query.subquery())),
            "items": [
                result_view(session, r)
                for r in session.scalars(
                    query.order_by(Result.case_id).offset(offset).limit(limit)
                )
            ],
        }


@app.get("/api/v1/results/{result_id}")
def get_result(result_id: str, project_id=Depends(project)):
    with transaction() as session:
        result = require(session, Result, result_id)
        require(session, Run, result.run_id, project_id)
        return result_view(session, result, True)


@app.put("/api/v1/results/{result_id}/review")
def review_result(result_id: str, body: HumanReview, project_id=Depends(project)):
    with transaction() as session:
        result = require(session, Result, result_id)
        run = require(session, Run, result.run_id, project_id)
        if result.status != "COMPLETED" or not run.config["capture_content"]:
            raise HTTPException(
                409, "Review requires a completed case with captured output"
            )
        result.human_score, result.human_note = body.score, body.note
        session.flush()
        return result_view(session, result, True)


@app.get("/api/v1/runs/{run_id}/calibration")
def calibration(run_id: str, project_id=Depends(project)):
    with transaction() as session:
        require(session, Run, run_id, project_id)
        pairs = session.execute(
            select(Result.human_score, Score.value)
            .join(Score, Score.result_id == Result.id)
            .where(
                Result.run_id == run_id,
                Result.human_score.is_not(None),
                Score.evaluator == "llm_judge",
            )
        ).all()
        return {
            "reviewed_judge_pairs": len(pairs),
            "mean_absolute_error": (
                sum(abs(a - b) for a, b in pairs) / len(pairs) if pairs else None
            ),
            "agreement_within_025": (
                sum(abs(a - b) <= 0.25 for a, b in pairs) / len(pairs)
                if pairs
                else None
            ),
            "note": "Only explicit human reviews paired with llm_judge scores are included.",
        }


@app.get("/api/v1/traces")
def traces(limit: int = Query(100, ge=1, le=500), project_id=Depends(project)):
    with transaction() as session:
        query = (
            select(Result)
            .join(Run)
            .where(Run.project_id == project_id, Result.trace_id.is_not(None))
            .order_by(Result.created_at.desc())
            .limit(limit)
        )
        items = [
            {
                "trace_id": r.trace_id,
                "case_id": r.case_id,
                "run_id": r.run_id,
                "result_id": r.id,
                "status": r.status,
                "latency_ms": r.latency_ms,
                "error": r.error,
                "span_count": len(r.spans),
                "created_at": r.created_at,
                "source": "evaluation",
            }
            for r in session.scalars(query)
        ]
        online = session.scalars(
            select(OnlineTrace)
            .where(OnlineTrace.project_id == project_id)
            .order_by(OnlineTrace.created_at.desc())
            .limit(limit)
        )
        items.extend(
            {
                "trace_id": t.trace_id,
                "case_id": t.service,
                "run_id": None,
                "result_id": None,
                "status": "COMPLETED" if t.status == "OK" else "FAILED",
                "latency_ms": t.latency_ms,
                "error": "application_error" if t.status == "ERROR" else None,
                "span_count": len(t.spans),
                "created_at": t.created_at,
                "source": "online",
            }
            for t in online
        )
        return sorted(items, key=lambda t: t["created_at"], reverse=True)[:limit]


@app.post("/api/v1/traces", status_code=201)
def ingest_trace(body: OnlineTraceInput, project_id=Depends(project)):
    spans = [
        {
            **s.model_dump(exclude_none=True),
            "duration_ms": (s.ended_at - s.started_at) * 1000,
        }
        for s in body.spans
    ]
    with transaction() as session:
        existing = session.scalar(
            select(OnlineTrace).where(
                OnlineTrace.project_id == project_id,
                OnlineTrace.trace_id == body.trace_id,
            )
        )
        if existing:
            if existing.spans != spans or existing.service != body.service:
                raise HTTPException(
                    409, "Trace ID already exists with different content"
                )
            return {"trace_id": existing.trace_id, "id": existing.id, "duplicate": True}
        trace = OnlineTrace(
            id=uid(),
            project_id=project_id,
            trace_id=body.trace_id,
            service=body.service,
            status="ERROR" if any(s.status == "ERROR" for s in body.spans) else "OK",
            latency_ms=(
                max(s.ended_at for s in body.spans)
                - min(s.started_at for s in body.spans)
            )
            * 1000,
            spans=spans,
        )
        session.add(trace)
        return {"trace_id": trace.trace_id, "id": trace.id, "duplicate": False}


@app.get("/api/v1/traces/{trace_id}")
def get_trace(trace_id: str, project_id=Depends(project)):
    with transaction() as session:
        result = session.scalar(
            select(Result)
            .join(Run)
            .where(Result.trace_id == trace_id, Run.project_id == project_id)
        )
        if not result:
            online = session.scalar(
                select(OnlineTrace).where(
                    OnlineTrace.project_id == project_id,
                    OnlineTrace.trace_id == trace_id,
                )
            )
            if not online:
                raise HTTPException(404, "Trace not found")
            return {
                "trace_id": trace_id,
                "result_id": None,
                "service": online.service,
                "spans": online.spans,
                "content_captured": False,
            }
        return {
            "trace_id": trace_id,
            "result_id": result.id,
            "spans": result.spans,
            "content_captured": session.get(Run, result.run_id).config[
                "capture_content"
            ],
        }


@app.post("/api/v1/comparisons")
def create_comparison(body: ComparisonInput, project_id=Depends(project)):
    with transaction() as session:
        return compare(
            session,
            require(session, Run, body.baseline_id, project_id),
            require(session, Run, body.candidate_id, project_id),
        )


@app.post("/api/v1/quality-gates/check")
def quality_gate(body: GateInput, project_id=Depends(project)):
    with transaction() as session:
        comparison = compare(
            session,
            require(session, Run, body.baseline_id, project_id),
            require(session, Run, body.candidate_id, project_id),
        )
        report = check_gate(comparison, body.thresholds.model_dump())
        record = RegressionReport(
            id=uid(),
            project_id=project_id,
            baseline_id=body.baseline_id,
            candidate_id=body.candidate_id,
            decision=report["decision"],
            report=report,
        )
        session.add(record)
        return {"id": record.id, **report}


@app.get("/api/v1/quality-gates")
def reports(project_id=Depends(project)):
    with transaction() as session:
        return [
            columns(r)
            for r in session.scalars(
                select(RegressionReport)
                .where(RegressionReport.project_id == project_id)
                .order_by(RegressionReport.created_at.desc())
                .limit(50)
            )
        ]


@app.get("/api/v1/baselines")
def baselines(project_id=Depends(project)):
    with transaction() as session:
        return [
            columns(b)
            for b in session.scalars(
                select(Baseline).where(Baseline.project_id == project_id)
            )
        ]


@app.post("/api/v1/baselines", status_code=201)
def set_baseline(body: BaselineInput, project_id=Depends(project)):
    with transaction() as session:
        run = require(session, Run, body.run_id, project_id)
        if run.status != "COMPLETED":
            raise HTTPException(409, "Only a fully completed run can be a baseline")
        baseline = session.scalar(
            select(Baseline)
            .where(Baseline.project_id == project_id, Baseline.name == body.name)
            .with_for_update()
        )
        if baseline:
            baseline.run_id = run.id
        else:
            baseline = Baseline(
                id=uid(), project_id=project_id, name=body.name, run_id=run.id
            )
            session.add(baseline)
        session.flush()
        return columns(baseline)


@app.get("/metrics")
def metrics():
    with transaction() as session:
        run_counts = dict(
            session.execute(select(Run.status, func.count()).group_by(Run.status)).all()
        )
        result_counts = dict(
            session.execute(
                select(Result.status, func.count()).group_by(Result.status)
            ).all()
        )
        tokens = session.execute(
            select(
                func.sum(Result.input_tokens),
                func.sum(Result.output_tokens),
                func.sum(sql_case((Result.attempts > 1, Result.attempts - 1), else_=0)),
            )
        ).one()
        lines = [
            "# TYPE evaluation_runs_total gauge",
            f"evaluation_runs_total {sum(run_counts.values())}",
            "# TYPE evaluation_cases_total gauge",
            f"evaluation_cases_total {sum(result_counts.values())}",
            "# TYPE evaluation_failures_total gauge",
            f"evaluation_failures_total {result_counts.get('FAILED', 0)}",
            "# TYPE evaluation_queue_depth gauge",
            f"evaluation_queue_depth {result_counts.get('PENDING', 0)}",
            "# TYPE llm_tokens_total gauge",
            f'llm_tokens_total{{direction="input"}} {tokens[0] or 0}',
            f'llm_tokens_total{{direction="output"}} {tokens[1] or 0}',
            "# TYPE evaluation_retries_total gauge",
            f"evaluation_retries_total {tokens[2] or 0}",
        ]
    return Response(
        generate_latest() + ("\n".join(lines) + "\n").encode(),
        media_type=CONTENT_TYPE_LATEST,
    )


frontend = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if frontend.is_dir():
    app.mount("/assets", StaticFiles(directory=frontend / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def dashboard(path: str):
        if path.startswith(("api/", "metrics", "health")):
            raise HTTPException(404)
        if path == "favicon.svg":
            return FileResponse(frontend / "favicon.svg")
        return FileResponse(frontend / "index.html")

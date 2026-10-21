"""Database-backed case execution with renewable leases and fenced persistence."""

import asyncio
import logging
import random
import signal
import statistics
import time
from sqlalchemy import func, select, update
from .config import settings
from .db import transaction
from .models import Attempt, Result, Run, Score, TestCase, uid
from .providers import Provider, ProviderError, ProviderLimiter
from .evaluators import (
    VERSIONS,
    cosine_similarity,
    estimate_cost,
    exact_match,
    retrieval_metrics,
)
from .services import TERMINAL
from . import usage
from .targets import invoke
from .telemetry import Recorder, CASE_DURATION, LLM_DURATION, WORKER_ACTIVE

log = logging.getLogger("evalscope.worker")


def finalize_run(session, run):
    statuses = session.execute(
        select(Result.status, func.count())
        .where(Result.run_id == run.id)
        .group_by(Result.status)
    ).all()
    counts = dict(statuses)
    if run.status == "CANCELED" or counts.get("PENDING", 0) or counts.get("RUNNING", 0):
        return
    run.status = (
        "COMPLETED"
        if counts.get("COMPLETED", 0) == run.total
        else "PARTIAL" if counts.get("COMPLETED", 0) else "FAILED"
    )
    run.finished_at = time.time()


def claim(config=settings):
    now = time.time()
    with transaction() as session:
        # Consistent lock ordering: run row then result row. Skip busy runs.
        runs = session.scalars(
            select(Run)
            .where(Run.status.in_(["PENDING", "RUNNING"]))
            .order_by(Run.created_at)
            .with_for_update(skip_locked=True)
        ).all()
        for run in runs:
            expired = session.scalars(
                select(Result).where(
                    Result.run_id == run.id,
                    Result.status == "RUNNING",
                    Result.lease_until < now,
                )
            ).all()
            for result in expired:
                attempt = session.scalar(
                    select(Attempt).where(
                        Attempt.result_id == result.id,
                        Attempt.number == result.attempts,
                    )
                )
                if attempt:
                    usage.uncertain_attempt(session, attempt.id)
                    attempt.status, attempt.error, attempt.finished_at = (
                        "ABANDONED",
                        "lease_expired",
                        now,
                    )
                result.status = (
                    "PENDING"
                    if result.attempts < run.config["max_attempts"]
                    else "FAILED"
                )
                result.error = "lease_expired"
                result.lease_token = result.lease_until = None
                result.available_at = now
            session.flush()
            active = session.scalar(
                select(func.count())
                .select_from(Result)
                .where(Result.run_id == run.id, Result.status == "RUNNING")
            )
            if active >= run.config["concurrency"]:
                continue
            result = session.scalar(
                select(Result)
                .where(
                    Result.run_id == run.id,
                    Result.status == "PENDING",
                    Result.available_at <= now,
                )
                .order_by(Result.created_at, Result.case_id)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if not result:
                finalize_run(session, run)
                continue
            token = uid()
            changed = session.execute(
                update(Result)
                .where(Result.id == result.id, Result.status == "PENDING")
                .values(
                    status="RUNNING",
                    lease_token=token,
                    lease_until=now + config.lease_seconds,
                    attempts=Result.attempts + 1,
                )
                .execution_options(synchronize_session=False)
            ).rowcount
            if not changed:
                continue
            session.refresh(result)
            attempt = Attempt(
                id=uid(), result_id=result.id, number=result.attempts, status="RUNNING"
            )
            session.add(attempt)
            run.status, run.started_at = "RUNNING", run.started_at or now
            case = session.get(TestCase, result.test_case_id)
            return {
                "result_id": result.id,
                "run_id": run.id,
                "project_id": run.project_id,
                "attempt_id": attempt.id,
                "token": token,
                "attempt": result.attempts,
                "config": run.config,
                "case": case.data,
            }
    return None


async def heartbeat(job, config, owner=None):
    deadline = time.time() + config.lease_seconds
    while True:
        await asyncio.sleep(min(1, config.lease_seconds / 3))
        try:
            with transaction() as session:
                changed = session.execute(
                    update(Result)
                    .where(
                        Result.id == job["result_id"],
                        Result.status == "RUNNING",
                        Result.lease_token == job["token"],
                        Result.lease_until > time.time(),
                    )
                    .values(lease_until=time.time() + config.lease_seconds)
                ).rowcount
            if changed:
                deadline = time.time() + config.lease_seconds
                continue
        except Exception:
            if time.time() < deadline:
                continue
        if owner:
            owner.cancel("ownership_lost")
        return


def persist(job, recorder, output, scores, latency, tokens, error=None, evidence=None):
    with recorder.span("results.persist"):
        with transaction() as session:
            run = session.scalar(
                select(Run).where(Run.id == job["run_id"]).with_for_update()
            )
            result = session.scalar(
                select(Result).where(Result.id == job["result_id"]).with_for_update()
            )
            if (
                result.lease_token != job["token"]
                or result.status != "RUNNING"
                or result.lease_until < time.time()
                or run.status == "CANCELED"
            ):
                return False
            attempt = session.scalar(
                select(Attempt).where(
                    Attempt.result_id == result.id, Attempt.number == job["attempt"]
                )
            )
            attempt.finished_at = time.time()
            if error:
                attempt.status, attempt.error = "FAILED", error.category
                result.error = error.category
                if error.transient and result.attempts < job["config"]["max_attempts"]:
                    result.status = "PENDING"
                    result.available_at = (
                        time.time()
                        + min(30, 2 ** (result.attempts - 1))
                        + random.uniform(0, 0.25)
                    )
                else:
                    result.status = "FAILED"
            else:
                result.status, result.error, attempt.status = (
                    "COMPLETED",
                    None,
                    "COMPLETED",
                )
                result.output = output if job["config"]["capture_content"] else None
                result.evidence = (
                    (evidence or {}) if job["config"]["capture_content"] else {}
                )
                result.score = statistics.mean(score[1] for score in scores)
                result.passed = result.score >= job["config"]["pass_threshold"]
                result.latency_ms = latency
                result.input_tokens, result.output_tokens = tokens
                result.cost = estimate_cost(*tokens, job["config"])
                for name, value, reason, details in scores:
                    if name == "llm_judge" and not job["config"]["capture_content"]:
                        reason = "Judge explanation hidden because content capture is disabled."
                    session.add(
                        Score(
                            result_id=result.id,
                            evaluator=name,
                            version=VERSIONS[name],
                            value=value,
                            reason=reason,
                            details=details,
                        )
                    )
            result.lease_token = result.lease_until = None
            session.flush()
            finalize_run(session, run)
        return True


def archive_trace(job, recorder):
    with transaction() as session:
        attempt = session.get(Attempt, job["attempt_id"])
        attempt.trace_id, attempt.spans, attempt.trace_complete = (
            recorder.trace_id,
            recorder.spans,
            True,
        )
        result = session.get(Result, job["result_id"])
        if result.attempts == job["attempt"]:
            result.trace_id, result.spans = recorder.trace_id, recorder.spans


async def execute(job, provider, config=settings):
    recorder = Recorder()
    started, output, scores, tokens, error = time.monotonic(), None, [], (0, 0), None
    owner = asyncio.current_task()
    pulse = asyncio.create_task(heartbeat(job, config, owner))
    WORKER_ACTIVE.inc()
    try:
        with (
            recorder.span("evaluation.case", attempt=job["attempt"]) as root,
            usage.accounting(job),
        ):
            with transaction() as session:
                session.get(Attempt, job["attempt_id"]).trace_id = recorder.trace_id
                owned = session.execute(
                    update(Result)
                    .where(
                        Result.id == job["result_id"],
                        Result.status == "RUNNING",
                        Result.lease_token == job["token"],
                        Result.lease_until > time.time(),
                    )
                    .values(trace_id=recorder.trace_id)
                ).rowcount
            if not owned:
                raise asyncio.CancelledError("ownership_lost")
            try:
                async with asyncio.timeout(job["config"]["timeout_seconds"]):
                    case, cfg = job["case"], job["config"]
                    with recorder.span("prompt.construct"):
                        prompt = cfg["prompt_template"].format(
                            input=case["input"],
                            contexts="\n".join(case["reference_contexts"]),
                        )
                    if cfg.get("target_snapshot"):
                        with recorder.span("application.request"):
                            response = await invoke(job, provider.client, recorder)
                        output, retrieved = (
                            response.output,
                            response.retrieved_document_ids,
                        )
                        # Judge groundedness against actual application retrieval.
                        evaluation_case = {
                            **case,
                            "reference_contexts": response.contexts,
                        }
                    else:
                        with recorder.span(
                            "retrieval.references",
                            document_count=len(case["retrieved_document_ids"]),
                        ):
                            retrieved = case["retrieved_document_ids"]
                        with recorder.span(
                            "llm.generate", model=cfg["model"], provider=cfg["provider"]
                        ) as span:
                            llm_started = time.monotonic()
                            output, incoming, outgoing = await provider.generate(
                                cfg, case, prompt, job["attempt"]
                            )
                            tokens = (incoming, outgoing)
                            span.set_attribute("gen_ai.usage.input_tokens", incoming)
                            span.set_attribute("gen_ai.usage.output_tokens", outgoing)
                            LLM_DURATION.labels(cfg["provider"]).observe(
                                time.monotonic() - llm_started
                            )
                        evaluation_case = case
                    with recorder.span("evaluation.score"):
                        for name in cfg["evaluators"]:
                            if name == "exact_match":
                                score = exact_match(output, case["reference_answer"])
                            elif name == "retrieval":
                                score = retrieval_metrics(
                                    retrieved,
                                    case["relevant_document_ids"],
                                    cfg["retrieval_k"],
                                )
                            elif name == "semantic_similarity":
                                embeddings = await provider.embeddings(
                                    cfg, output, case["reference_answer"]
                                )
                                score = cosine_similarity(*embeddings)
                            else:
                                score = await provider.judge(
                                    cfg, output, evaluation_case
                                )
                            scores.append((name, *score))
            except TimeoutError:
                error = ProviderError("timeout", True)
            except ProviderError as exc:
                error = exc
            except asyncio.CancelledError:
                raise
            except Exception:
                log.warning("Evaluation failed; content omitted")
                error = ProviderError("evaluation_error")
            if error:
                from opentelemetry.trace import Status, StatusCode

                root.set_status(Status(StatusCode.ERROR, error.category))
                recorder.spans[0].update(status="ERROR", error=error.category)
            accepted = persist(
                job,
                recorder,
                output,
                scores,
                (time.monotonic() - started) * 1000,
                tokens,
                error,
                (
                    {
                        "contexts": evaluation_case["reference_contexts"],
                        "retrieved_document_ids": retrieved,
                    }
                    if output is not None and not error
                    else {}
                ),
            )
            if not accepted:
                from opentelemetry.trace import Status, StatusCode

                root.set_status(Status(StatusCode.ERROR, "ownership_lost"))
                recorder.spans[0].update(status="ERROR", error="ownership_lost")
    finally:
        pulse.cancel()
        await asyncio.gather(pulse, return_exceptions=True)
        WORKER_ACTIVE.dec()
        CASE_DURATION.observe(time.monotonic() - started)
        # Every attempt keeps its own completed trace, even after retry/cancel.
        for retry in range(3):
            try:
                archive_trace(job, recorder)
                break
            except Exception:
                if retry == 2:
                    log.warning(
                        "Trace projection unavailable; OTel export and durable trace ID remain"
                    )
                else:
                    await asyncio.sleep(0.1 * 2**retry)


async def serve(stop=None, config=settings):
    stop = stop or asyncio.Event()
    provider = Provider(ProviderLimiter(config), config)
    tasks = set()
    try:
        while not stop.is_set():
            finished = {task for task in tasks if task.done()}
            for task in finished:
                try:
                    if not task.cancelled():
                        task.result()
                except Exception:
                    log.exception("Worker task failed; lease will expire")
            tasks -= finished
            if len(tasks) < config.worker_slots:
                try:
                    job = claim(config)
                except Exception:
                    log.exception("Could not claim work; retrying")
                    job = None
                if job:
                    tasks.add(asyncio.create_task(execute(job, provider, config)))
                    await asyncio.sleep(0)
                    continue
            await asyncio.sleep(config.poll_seconds)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await provider.close()


def main():
    import os

    if os.getenv("PROMETHEUS_WORKER_PORT"):
        from prometheus_client import start_http_server

        start_http_server(int(os.environ["PROMETHEUS_WORKER_PORT"]))

    async def run():
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for signum in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(signum, stop.set)
        await serve(stop)

    asyncio.run(run())


if __name__ == "__main__":
    main()

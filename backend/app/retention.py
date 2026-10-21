import asyncio
import time
from sqlalchemy import delete, select
from .db import transaction
from .models import (
    Attempt,
    HumanLabel,
    OnlineTrace,
    Result,
    RetentionPolicy,
    ReviewItem,
    Run,
    Score,
)
from .security import audit


def sweep(project_id=None, dry_run=True, actor_id=None, now=None):
    now = time.time() if now is None else now
    counts = {"results": 0, "attempt_traces": 0, "online_traces": 0}
    with transaction() as session:
        query = select(RetentionPolicy).where(RetentionPolicy.enabled.is_(True))
        if project_id:
            query = query.where(RetentionPolicy.project_id == project_id)
        for policy in session.scalars(query):
            old_runs = select(Run.id).where(
                Run.project_id == policy.project_id,
                Run.finished_at < now - policy.content_days * 86400,
            )
            results = session.scalars(
                select(Result)
                .where(Result.run_id.in_(old_runs), Result.content_purged_at.is_(None))
                .with_for_update(skip_locked=True)
            ).all()
            counts["results"] += len(results)
            trace_runs = select(Run.id).where(
                Run.project_id == policy.project_id,
                Run.finished_at < now - policy.trace_days * 86400,
            )
            trace_results = select(Result.id).where(Result.run_id.in_(trace_runs))
            attempts = session.scalars(
                select(Attempt).where(
                    Attempt.result_id.in_(trace_results),
                    Attempt.trace_purged_at.is_(None),
                )
            ).all()
            online = session.scalars(
                select(OnlineTrace).where(
                    OnlineTrace.project_id == policy.project_id,
                    OnlineTrace.created_at < now - policy.trace_days * 86400,
                )
            ).all()
            counts["attempt_traces"] += len(attempts)
            counts["online_traces"] += len(online)
            if dry_run:
                continue
            ids = [r.id for r in results]
            for result in results:
                result.output = result.human_note = None
                result.evidence = {}
                result.content_purged_at = now
            if ids:
                for score in session.scalars(
                    select(Score).where(Score.result_id.in_(ids))
                ):
                    score.reason = "Explanation expired under project retention policy."
                item_ids = select(ReviewItem.id).where(ReviewItem.result_id.in_(ids))
                for label in session.scalars(
                    select(HumanLabel).where(HumanLabel.item_id.in_(item_ids))
                ):
                    label.rationale = (
                        "Review explanation expired under project retention policy."
                    )
            for attempt in attempts:
                attempt.spans, attempt.trace_complete, attempt.trace_purged_at = (
                    [],
                    False,
                    now,
                )
            for result in session.scalars(
                select(Result).where(Result.run_id.in_(trace_runs))
            ):
                result.spans = []
            for trace in online:
                session.delete(trace)
            if results or attempts or online:
                audit(
                    session,
                    "retention.sweep",
                    policy.project_id,
                    actor_id,
                    results=len(results),
                    attempt_traces=len(attempts),
                    online_traces=len(online),
                )
    return {"dry_run": dry_run, **counts}


async def serve(stop):
    while not stop.is_set():
        try:
            sweep(dry_run=False)
        except Exception:
            import logging

            logging.getLogger("evalscope.retention").warning(
                "Retention sweep failed; retrying on next interval"
            )
        try:
            await asyncio.wait_for(stop.wait(), timeout=300)
        except TimeoutError:
            pass

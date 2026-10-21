"""Blinded, attributed human review. Machine scores never enter reviewer payloads."""

from collections import Counter, defaultdict
from itertools import combinations
import statistics
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from .db import transaction
from .models import (
    HumanLabel,
    Result,
    ReviewCampaign,
    ReviewItem,
    Run,
    Score,
    TestCase,
    uid,
)
from .schemas import CampaignInput, LabelInput
from .security import audit, authorize_project, principal
from .services import columns, require

router = APIRouter(prefix="/api/v1/review-campaigns")


def category_kappa(pairs):
    """Unweighted Cohen's kappa for one reviewer pair; no pooled-pair inference."""
    if not pairs:
        return None
    left, right = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    count = len(pairs)
    observed = sum(a == b for a, b in pairs) / count
    expected = sum(left[c] * right[c] for c in left.keys() | right.keys()) / count**2
    return (observed - expected) / (1 - expected) if expected < 1 else None


def campaign_view(session, campaign, reviewer_id):
    items = session.scalars(
        select(ReviewItem).where(ReviewItem.campaign_id == campaign.id)
    ).all()
    ids = [item.id for item in items]
    labels = session.scalars(
        select(HumanLabel).where(HumanLabel.item_id.in_(ids))
    ).all()
    counts = Counter(label.item_id for label in labels)
    return {
        **columns(campaign),
        "total_items": len(items),
        "labels": len(labels),
        "consensus_items": sum(
            count >= campaign.minimum_reviews for count in counts.values()
        ),
        "my_reviews": sum(label.reviewer_id == reviewer_id for label in labels),
        "independent_reviewers": len({label.reviewer_id for label in labels}),
    }


@router.get("")
def campaigns(request: Request, project_id=Depends(authorize_project)):
    with transaction() as session:
        return [
            campaign_view(session, c, principal(request)["id"])
            for c in session.scalars(
                select(ReviewCampaign)
                .where(ReviewCampaign.project_id == project_id)
                .order_by(ReviewCampaign.created_at.desc())
            )
        ]


@router.post("", status_code=201)
def create(
    body: CampaignInput, request: Request, project_id=Depends(authorize_project)
):
    with transaction() as session:
        runs = [
            require(session, Run, identity, project_id)
            for identity in set(body.run_ids)
        ]
        if len({r.dataset_version_id for r in runs}) != 1 or any(
            r.status not in {"COMPLETED", "PARTIAL"} for r in runs
        ):
            raise HTTPException(
                409, "Review runs must be terminal and use one dataset version"
            )
        results = session.scalars(
            select(Result).where(
                Result.run_id.in_(body.run_ids),
                Result.status == "COMPLETED",
                Result.output.is_not(None),
            )
        ).all()
        if not results:
            raise HTTPException(422, "Review requires captured, unexpired responses")
        campaign = ReviewCampaign(
            id=uid(),
            project_id=project_id,
            name=body.name,
            rubric=body.rubric,
            minimum_reviews=body.minimum_reviews,
        )
        session.add(campaign)
        session.flush()
        session.add_all(
            ReviewItem(campaign_id=campaign.id, result_id=r.id) for r in results
        )
        session.flush()
        audit(
            session,
            "review.campaign_created",
            project_id,
            principal(request)["id"],
            campaign.id,
            item_count=len(results),
        )
        return campaign_view(session, campaign, principal(request)["id"])


@router.get("/{campaign_id}/queue")
def queue(
    campaign_id: str,
    request: Request,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    project_id=Depends(authorize_project),
):
    reviewer = principal(request)["id"]
    with transaction() as session:
        campaign = require(session, ReviewCampaign, campaign_id, project_id)
        mine = select(HumanLabel.item_id).where(HumanLabel.reviewer_id == reviewer)
        query = (
            select(ReviewItem, Result, TestCase)
            .join(Result, Result.id == ReviewItem.result_id)
            .join(TestCase, TestCase.id == Result.test_case_id)
            .where(
                ReviewItem.campaign_id == campaign_id,
                ReviewItem.id.not_in(mine),
                Result.output.is_not(None),
            )
            .order_by(ReviewItem.id)
        )
        rows = session.execute(query).all()
        # IDs are random per campaign; no run/model IDs or evaluator scores leak.
        return {
            "campaign": columns(campaign),
            "remaining": len(rows),
            "items": [
                {
                    "id": item.id,
                    "input": case.data["input"],
                    "reference_answer": case.data["reference_answer"],
                    "reference_contexts": case.data["reference_contexts"],
                    "retrieved_contexts": result.evidence.get("contexts", []),
                    "retrieved_document_ids": result.evidence.get(
                        "retrieved_document_ids", []
                    ),
                    "output": result.output,
                }
                for item, result, case in rows[offset : offset + limit]
            ],
        }


@router.post("/{campaign_id}/items/{item_id}/labels", status_code=201)
def label(
    campaign_id: str,
    item_id: str,
    body: LabelInput,
    request: Request,
    project_id=Depends(authorize_project),
):
    actor = principal(request)
    with transaction() as session:
        require(session, ReviewCampaign, campaign_id, project_id)
        item = require(session, ReviewItem, item_id)
        if item.campaign_id != campaign_id:
            raise HTTPException(404, "Review item not found")
        result = session.scalar(
            select(Result).where(Result.id == item.result_id).with_for_update()
        )
        if result.output is None:
            raise HTTPException(410, "Response content has expired")
        if session.scalar(
            select(HumanLabel.id).where(
                HumanLabel.item_id == item_id, HumanLabel.reviewer_id == actor["id"]
            )
        ):
            raise HTTPException(
                409,
                "One independent label per reviewer and item; submitted labels are immutable",
            )
        value = HumanLabel(
            id=uid(), item_id=item_id, reviewer_id=actor["id"], **body.model_dump()
        )
        session.add(value)
        audit(session, "review.label_submitted", project_id, actor["id"], item_id)
        session.flush()
        return {"id": value.id, "submitted": True}


@router.get("/{campaign_id}/calibration")
def calibration(
    campaign_id: str, request: Request, project_id=Depends(authorize_project)
):
    if request.state.role == "reviewer":
        raise HTTPException(403, "Calibration is hidden from blind reviewers")
    with transaction() as session:
        campaign = require(session, ReviewCampaign, campaign_id, project_id)
        rows = session.execute(
            select(ReviewItem, Result)
            .join(Result, Result.id == ReviewItem.result_id)
            .where(ReviewItem.campaign_id == campaign_id)
        ).all()
        item_ids = [item.id for item, _ in rows]
        grouped = defaultdict(list)
        for label in session.scalars(
            select(HumanLabel).where(HumanLabel.item_id.in_(item_ids))
        ):
            grouped[label.item_id].append(label)
        score_map = {
            s.result_id: s
            for s in session.scalars(
                select(Score).where(
                    Score.result_id.in_([result.id for _, result in rows]),
                    Score.evaluator == "llm_judge",
                )
            )
        }
        pair_deltas, category_agreement, judge_deltas, disagreements = [], [], [], []
        pair_categories, run_coverage = defaultdict(list), defaultdict(Counter)
        judge_examples = []
        consensus_items = 0
        consensus_cases, reviewed_ids = set(), set()
        for item, result in rows:
            labels = sorted(grouped[item.id], key=lambda label: label.reviewer_id)
            run_coverage[result.run_id]["total_items"] += 1
            reviewed_ids.update(label.reviewer_id for label in labels)
            for a, b in combinations(labels, 2):
                pair_deltas.append(abs(a.score - b.score))
                category_agreement.append(a.category == b.category)
                pair_categories[(a.reviewer_id, b.reviewer_id)].append(
                    (a.category, b.category)
                )
            if len(labels) < campaign.minimum_reviews:
                continue
            consensus_cases.add(result.test_case_id)
            consensus_items += 1
            run_coverage[result.run_id]["consensus_items"] += 1
            human_score = statistics.median(label.score for label in labels)
            categories = Counter(label.category for label in labels)
            ordered = categories.most_common()
            category = (
                ordered[0][0]
                if len(ordered) == 1 or ordered[0][1] > ordered[1][1]
                else "disputed"
            )
            judge_record = score_map.get(result.id)
            judge = judge_record.value if judge_record is not None else None
            delta = abs(judge - human_score) if judge is not None else None
            if delta is not None:
                judge_deltas.append(delta)
                run_coverage[result.run_id]["judge_consensus_pairs"] += 1
                if delta > 0.25 and result.output is not None:
                    case = session.get(TestCase, result.test_case_id)
                    judge_examples.append(
                        {
                            "item_id": item.id,
                            "case_id": result.case_id,
                            "input": case.data["input"],
                            "reference_answer": case.data["reference_answer"],
                            "reference_contexts": case.data["reference_contexts"],
                            "retrieved_contexts": result.evidence.get("contexts", []),
                            "output": result.output,
                            "human_median": human_score,
                            "judge_score": judge,
                            "judge_reason": judge_record.reason,
                            "absolute_judge_delta": delta,
                            "direction": (
                                "over_scoring"
                                if judge > human_score
                                else "under_scoring"
                            ),
                            "reviews": [
                                {
                                    "reviewer_id": label.reviewer_id,
                                    "score": label.score,
                                    "category": label.category,
                                    "rationale": label.rationale,
                                }
                                for label in labels
                            ],
                        }
                    )
            spread = max(label.score for label in labels) - min(
                label.score for label in labels
            )
            if (
                spread > 0.25
                or len(categories) > 1
                or delta is not None
                and delta > 0.25
            ):
                disagreements.append(
                    {
                        "item_id": item.id,
                        "result_id": result.id,
                        "human_median": human_score,
                        "judge_score": judge,
                        "absolute_judge_delta": delta,
                        "reviewer_spread": spread,
                        "category": category,
                        "categories": dict(categories),
                    }
                )
        return {
            "campaign": campaign_view(session, campaign, principal(request)["id"]),
            "consensus_case_count": len(consensus_cases),
            "consensus_item_count": consensus_items,
            "campaign_complete": bool(rows) and consensus_items == len(rows),
            "coverage_by_run": {
                run_id: {
                    key: counts[key]
                    for key in (
                        "total_items",
                        "consensus_items",
                        "judge_consensus_pairs",
                    )
                }
                for run_id, counts in run_coverage.items()
            },
            "independent_reviewer_count": len(reviewed_ids),
            "human_corpus_target_met": len(consensus_cases) >= 100
            and len(reviewed_ids) >= 2
            and consensus_items == len(rows),
            "independence_status": "Distinct accounts are verified; human independence requires coordinator attestation.",
            "reviewer_pair_count": len(pair_deltas),
            "reviewer_mean_absolute_difference": (
                statistics.mean(pair_deltas) if pair_deltas else None
            ),
            "category_agreement": (
                statistics.mean(category_agreement) if category_agreement else None
            ),
            "category_agreement_by_reviewer_pair": [
                {
                    "reviewer_ids": list(pair),
                    "paired_items": len(categories),
                    "agreement": statistics.mean(a == b for a, b in categories),
                    "cohens_kappa": category_kappa(categories),
                }
                for pair, categories in sorted(pair_categories.items())
            ],
            "judge_consensus_pairs": len(judge_deltas),
            "judge_mean_absolute_error": (
                statistics.mean(judge_deltas) if judge_deltas else None
            ),
            "judge_agreement_within_025": (
                statistics.mean(d <= 0.25 for d in judge_deltas)
                if judge_deltas
                else None
            ),
            "disagreements": sorted(
                disagreements,
                key=lambda d: max(d["absolute_judge_delta"] or 0, d["reviewer_spread"]),
                reverse=True,
            ),
            "judge_disagreement_examples": sorted(
                judge_examples,
                key=lambda example: example["absolute_judge_delta"],
                reverse=True,
            )[:10],
            "example_method": "Up to ten largest judge/human gaps > .25 with retained content. These are candidates for human adjudication, not automatically confirmed judge failures. Expired content is excluded.",
            "method": "Explicit authenticated reviewers only; per-item median after the minimum distinct reviews. Pairwise reviewer differences and category agreement are descriptive; repeated reviewers/cases are not independent statistical samples.",
        }

import math
import pytest
from backend.app.evaluators import (
    cosine_similarity,
    estimate_cost,
    exact_match,
    percentile,
    retrieval_metrics,
)
from backend.app.schemas import PromptInput, RunConfig, VersionInput
from backend.app.services import check_gate


def test_exact_match_normalizes_unicode_case_and_whitespace():
    assert exact_match("  ＨＥＬＬＯ\n World  ", "hello world")[0] == 1
    assert exact_match("hello!", "hello")[0] == 0


def test_retrieval_deduplicates_and_uses_k_as_precision_denominator():
    score, _, details = retrieval_metrics(["bad", "a", "a", "b"], ["a", "b", "c"], 5)
    assert score == pytest.approx(2 / 3)
    assert details == {"precision_at_k": 0.4, "recall_at_k": 2 / 3, "mrr": 0.5, "k": 5}
    with pytest.raises(ValueError):
        retrieval_metrics([], [], 5)


def test_embedding_cosine_and_degenerate_vectors():
    assert cosine_similarity([1, 0], [1, 0])[0] == 1
    assert cosine_similarity([1, 0], [0, 1])[0] == 0
    for left, right in [([0, 0], [1, 0]), ([1], [1, 2]), ([math.nan], [1])]:
        with pytest.raises(ValueError):
            cosine_similarity(left, right)


def test_cost_and_percentiles():
    assert (
        estimate_cost(
            1_000_000,
            100_000,
            {"input_cost_per_million": 2, "output_cost_per_million": 5},
        )
        == 2.5
    )
    assert percentile([10, 20, 30, 40], 0.95) == pytest.approx(38.5)
    assert percentile([], 0.5) is None


@pytest.mark.parametrize(
    "template",
    ["{input.__class__}", "{input!r}", "{input:>8}", "{unknown}", "no placeholders"],
)
def test_prompt_rejects_unsafe_or_unrecognized_fields(template):
    with pytest.raises(ValueError):
        PromptInput(name="bad", template=template)


def test_dataset_rejects_duplicate_case_ids():
    case = {"case_id": "a", "input": "q", "reference_answer": "a"}
    with pytest.raises(ValueError):
        VersionInput(cases=[case, case])


def test_mock_cannot_claim_live_judge_or_embedding_scores():
    with pytest.raises(ValueError):
        RunConfig(
            dataset_version_id="a", prompt_version_id="b", evaluators=["llm_judge"]
        )

# Evaluation methodology

## Scores

- **Exact match (`exact-v1`):** normalize NFKC Unicode, casefold, collapse whitespace, strip edges, compare. Punctuation remains significant.
- **Semantic similarity (`embedding-cosine-v1`):** obtain real embeddings for prediction and reference from the configured model. Use cosine similarity; reject zero, nonfinite, or incompatible vectors. Negative cosine is clamped to zero for normalized aggregate quality. The raw cosine is retained. Similarity is not a factuality guarantee.
- **Retrieval (`retrieval-v1`):** deduplicate retrieved IDs in first-seen order; take the first K. Precision@K = hits/K, recall@K = hits/number of unique labeled relevant documents, MRR = reciprocal first relevant rank. Recall@K is the scalar used in multi-evaluator aggregation. Missing relevant-document labels reject experiment creation. Missing retrievals are a measured zero, not an execution failure.
- **LLM judge (`rubric-v1`):** correctness, relevance, completeness, and groundedness scored together on a 1–5 rubric. Strict application parsing requires an integer and a reason; bool, floats, out-of-range values, malformed JSON, and missing fields fail evaluation. Normalize `(score-1)/4`. The model receives a system rubric and user JSON with untrusted question, response, reference, and contexts. This separation reduces instruction confusion but cannot guarantee prompt-injection resistance.

Per-case quality is the arithmetic mean of the configured evaluator scores. A case passes when quality is at least the frozen threshold. This is a simple, visible weighting choice; selecting exact match and judge together can lower the score of a correct paraphrase. Select evaluators appropriate to the task and compare their details, not only the aggregate.

`pass_rate` divides passed cases by **all dataset cases**, so execution failures and missing cases do not inflate quality. Coverage is successfully evaluated / total cases. Error rate is permanently failed / total cases; canceled cases reduce coverage. Mean quality uses successful scores only, always alongside coverage. Latency percentiles use linear interpolation on successful case wall times, including generation and scoring but excluding queue wait. The usage ledger covers every recorded generation, embedding, judge, and application stage across attempts, including successful stages preceding later failure. Frozen prices and usage evidence determine known estimates; missing rates, unknown outcomes, and pre-ledger records remain explicit lower-bound gaps.

## Reproducibility and comparisons

Runs freeze dataset and prompt identities, dataset fingerprint, prompt text, model/generation configuration, evaluator names and versions, rubric, retry policy, and prices. Identical model IDs do not guarantee an external provider's behavior remains unchanged.

Comparisons require identical dataset version, evaluator versions, retrieval K, judge/embedding model IDs, and pass threshold. Configuration mismatches return 409. Compare only like-for-like meaning; changes to the generation model, prompt, temperature, and concurrency are allowed and displayed in frozen configurations.

Pairs require two successfully evaluated scores for the same case. Each pair is improved, regressed, or unchanged, using a 1e-9 tolerance; other pairs are missing/failed. A percentile bootstrap resamples paired score deltas 1,000 times with seed 42. At least two pairs are needed to report a 95% interval. This is descriptive uncertainty under an independence assumption, not a multiple-comparison correction or a causal experiment. Correlated or duplicated cases, including the synthetic demo corpus, weaken that assumption. Cases are not provider reruns, so the interval does not measure provider nondeterminism.

## Release decisions

The default requirements are: pass rate ≥ .90, pass-rate drop ≤ .03, p95 ≤ 2500 ms, error rate ≤ .02, coverage ≥ .95, and at least five paired successful cases. Runs must be terminal. Insufficient coverage, pair count, or unfinished data produces INCONCLUSIVE. Otherwise, any violated threshold produces FAIL. Passing all checks produces PASS. The confidence interval is included for review; the gate applies explicit thresholds and does not silently convert them into a significance test.

## Human review and calibration

The provided 100 examples are synthetic authored fixtures. No independent human labels are claimed. A reviewer can annotate a captured response; independent consensus instead requires a blinded campaign and the configured minimum distinct authenticated reviewers. See [human-review methodology](human-review.md). The calibration endpoint pairs only explicit human scores with `llm_judge` scores; it reports pair count, mean absolute error, and agreement within .25.

To conduct the proposal's real quality study, independently label at least 100 diverse cases spanning correct, incomplete, hallucinated, and irrelevant answers. Keep reviewers blind to model/judge identity, document the rubric, use multiple reviewers for a subset, resolve disagreements, and hold out calibration cases from prompt tuning. Record corpus provenance, reviewer agreement, model configuration, and case-level judge/human disagreements. This research work remains to be performed.

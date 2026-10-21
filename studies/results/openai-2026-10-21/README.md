# Real OpenAI prompt comparison — October 21, 2026

The candidate prompt did not improve the frozen LLM-judge score in this run. It cost more to generate and produced one lower-scored deadline answer. However, deterministic inspection also exposed errors that the judge missed in both configurations. The evidence supports a completed real-provider integration study and an exploratory prompt comparison; it does not establish human-validated accuracy or a general prompt winner.

## What actually ran

EvalScope's existing `cli.study prepare → execute → collect` workflow ran both original prompts against the same immutable 100-question snapshot. The API, worker, provider adapter, rubric-v1 scorer, per-attempt ledger and paired comparison were used directly. There were **200 real generation requests and 200 real judge requests**, all HTTP 200, with 200/200 cases completed, no retries, no timeouts, no truncated responses and no unresolved usage. An additional two-request arithmetic smoke test is disclosed separately.

Execution ran **October 21, 2026, 14:23:13–14:26:42 America/Los_Angeles (UTC−07:00)**, approximately 208.5 seconds. Both runs overlapped on one embedded worker with an isolated SQLite WAL database, two cases allowed concurrently per configuration, a shared two-request provider semaphore and a two-requests-per-second limiter. Allocation was not randomized. This was a small local measurement of remote API behavior, not a production throughput benchmark.

| Setting | Frozen value |
| --- | --- |
| Generator for both prompts | `gpt-4.1-mini-2025-04-14` |
| Judge for both prompts | `gpt-4.1-2025-04-14` |
| Provider | `https://api.openai.com/v1/chat/completions` |
| Decoding | Temperature 0; one attempt per case |
| Generation / judge completion limits | 512 / 256 tokens |
| Primary quality | Existing rubric-v1, integer 1–5 normalized as `(score − 1) / 4` |
| Passing threshold | Normalized judge score ≥ .75 |
| Baseline run ID | `d49a2417-a61f-4349-8567-9e790728c89c` |
| Candidate run ID | `55957ccb-ec01-4638-adb2-c64bb4ec51cd` |
| Dataset SHA-256 | See `dataset_sha256` in [summary.json](summary.json) |
| Complete study snapshot SHA-256 | `3037ca96276511caac787e1925cf9acd7dcdafe90bd18a2e9d2d87f8ba3aea6d` |

The provider returned exactly the requested dated model IDs; all request IDs and token counts reconcile with the durable ledger. These are legacy models marked deprecated in the [generator documentation](https://developers.openai.com/api/docs/models/gpt-4.1-mini) and [judge documentation](https://developers.openai.com/api/docs/models/gpt-4.1), but both were available to the study account and successfully served the requests. Fixed snapshots and support for the existing temperature-0 workflow motivated their use. This report makes no claim about the latest models.

The dataset contains ten cases in each of ten authored fictional task families: arithmetic, multi-hop routing, temporal calculations, boundaries, missing evidence, conflicting versions, instruction injection, structured output, unavailable tools and entity disambiguation. It is not production traffic or an independently validated benchmark. The candidate was designed with knowledge of these families; this is not an untouched holdout. Both generators received the question and evidence, with gold-answer fields and mock outputs withheld. The shared judge received the answer, question, reference and evidence, with no prompt label supplied. Models share a family/provider; the judge is not an independent human authority.

The baseline requests concise evidence-based answers. The candidate adds the prepared checks for calculations, conditions, revisions, missing facts, unavailable tools, embedded instructions and output format. The actual prompt strings were preserved exactly and are published in [prepared.json](prepared.json).

## Primary measured results

| Metric, 100 cases per configuration | Baseline | Candidate |
| --- | ---: | ---: |
| Mean normalized LLM-judge score | **0.9850** | **0.9775** |
| Judge-based pass rate | 100/100 (100%) | 99/100 (99%) |
| Generation HTTP p95 | **1.086 s** | **1.014 s** |
| Evaluation p95, including judge and limiter waits | **4.546 s** | **4.587 s** |
| Generation input / output tokens | 7,180 / 1,045 | 12,880 / 1,063 |
| Judge input / output tokens | 15,469 / 5,386 | 15,484 / 5,409 |
| All-stage input / output tokens | **22,649 / 6,431** | **28,364 / 6,472** |
| Estimated generation cost, USD | **$0.0045440** | **$0.0068528** |
| Estimated judge cost, USD | $0.0740260 | $0.0742400 |
| Estimated total cost, USD | **$0.0785700** | **$0.0810928** |
| API / evaluation execution failures | 0 / 0 | 0 / 0 |

Generation HTTP timing measures the complete non-streaming client request/response exchange, including reading the response body, and excludes the local limiter wait. Evaluation latency is EvalScope's case timer: prompt construction, generation, judging, local accounting and limiter waits; it excludes prior queue waiting and the final persistence transaction. Neither is time to first token. Percentiles use linear interpolation over the 100 observations. Small latency differences in one run should not be read as stable model speed differences.

The mean judge-score delta, candidate minus baseline, was **−0.0075**: 0 improved, 1 regressed, 99 unchanged, 0 missing pairs. The existing 1,000-resample paired case bootstrap gave **[−0.0225, 0.0000]**. A post hoc sensitivity analysis resampling the ten task families as clusters, 10,000 resamples with seed 42, also gave **[−0.0225, 0.0000]**. Both intervals include zero and concern this scoring process on this corpus; they do not measure provider rerun variation or establish a causal prompt effect.

Most family means were 1.0 for both prompts. Missing-evidence means were .85 for both; temporal means were 1.0 for baseline and .925 for candidate. The baseline had 94 scores of 1.0 and six of .75. The candidate had 93 scores of 1.0, six of .75 and one of .25. These are **judge scores, not factual accuracy estimates**.

## Cost and token accounting

The study used **63,916 tokens**: 51,013 input and 12,903 output. All 400 audited responses reported zero cached input tokens. Standard uncached USD rates per million tokens were frozen at **$0.40 input / $1.60 output** for generation and **$2.00 / $8.00** for judging, verified against the [generator](https://developers.openai.com/api/docs/models/gpt-4.1-mini) and [judge](https://developers.openai.com/api/docs/models/gpt-4.1) pricing pages on October 21, 2026.

Total study estimate: **$0.1596628**. The separate two-request smoke test used 125 input and 39 output tokens and adds **$0.0005252**, for **$0.1601880 including that smoke test**. Setup/model-discovery traffic is not counted as a study observation. No embedding calls were made. These are token-based standard-rate estimates; provider invoices, credit application, taxes and negotiated discounts were not accessed.

The candidate's longer input increased generation cost by **50.8%**, while total evaluation cost rose **3.21%** because judging dominated the bill. There is no measured judge-score gain to justify that additional cost in this one experiment. The original ledger's nominal estimates and cache-adjusted publication estimates agree, because every observed cache count was zero.

## Failure cases and judge limitations

Only one answer fell below the frozen judge threshold. That does not mean only one answer was defective. The following examples distinguish the original scores from subsequent diagnostic inspection. Every actual response and judge rationale is available in [cases.csv](cases.csv).

**Candidate regression — `review-053`.** Ticket T5 opens at `2027-01-06T09:00:00+00:00`; add 39 hours. The correct deadline is `2027-01-08T00:00:00+00:00`. The candidate returned `2027-01-07T00:00:00+00:00`, a day early, and received .25. The baseline included the correct instant in a parenthetical explanation and received 1.0, but its complete response was not a single machine-parseable ISO datetime. Adding an explicit calculation check did not prevent the candidate's arithmetic failure.

**Wrong answer accepted by the judge — `review-063`.** Both prompts returned `2027-01-08T03:00:00+00:00` for a ticket opened January 7 at 09:00 UTC with a 42-hour SLA. Independent `datetime + timedelta` arithmetic yields **January 9 at 03:00 UTC**, matching the authored reference. Both answers received **1.0**; both judge explanations incorrectly called the calculation accurate. This is a reproducible mathematical counterexample to treating a full judge score as correctness.

**A real improvement hidden by the judge — `review-073`.** Adding 45 hours to January 8 at 09:00 UTC gives January 10 at 06:00 UTC. The baseline returned January 9; the candidate returned January 10. Both received **1.0**. Thus the primary score comparison misses an actual arithmetic improvement, as well as other defects.

**Output-contract failure accepted by the judge — `review-008` and all other structured-output cases.** The question requests only JSON with `name` and integer `quota`. Both configurations wrapped the object in Markdown fences, for example:

````text
```json
{
  "name": "Tenant-0",
  "quota": 50
}
```
````

The object inside is correct, but the complete response fails a direct JSON parser. All ten structured-output responses per configuration had this defect, and all twenty received **1.0**. The candidate's format instruction did not eliminate it.

**Unsupported certainty despite a passing score — `review-005`.** The evidence describes domestic delivery and says no international insurance policy is available. Both configurations answered **“No.”** to whether international parcels are insured and received **.75**, which passes the frozen threshold. The reference is “Insufficient evidence.” Absence of a policy document does not establish that insurance is unavailable. This qualitative inspection is not an independent human annotation or a revised primary score.

## Post hoc deterministic diagnostics

After observing these failures, an offline audit checked **all** ten temporal and ten structured-output cases per configuration. Calendar answers were independently computed from the question and checked against the reference, then compared with a single Python-parseable UTC ISO datetime. JSON responses were parsed directly, without stripping Markdown fences, and checked for exact keys, values and field types. The generator was not rerun, the judge was not retrained, and no original score was changed.

| Diagnostic subset, 10 cases each | Baseline | Candidate |
| --- | ---: | ---: |
| Correct, directly parseable UTC deadline | **7/10** | **8/10** |
| Bare JSON satisfying the requested contract | **0/10** | **0/10** |
| Diagnostic failures nevertheless given judge score 1.0 | **13** | **11** |

These checks were selected post hoc and cover only 20 of the 100 questions; they are not a replacement overall accuracy metric. They show why this experiment cannot support choosing a prompt solely from the small difference in LLM-judge means. [mechanical-checks.json](mechanical-checks.json) publishes all forty checks and the original outputs, scores and explanations. No independent human study, human/judge agreement rate or reviewer consensus is claimed.

The practical next experiment should freeze JSON parsing, calendar arithmetic and evidence-abstention criteria as primary checks where applicable, use a fresh holdout, and calibrate the judge with independent reviewers. Preserve the current result rather than retrospectively optimizing this same test set and presenting that as independent validation.

## Evidence and reproducibility

| Artifact | Contents |
| --- | --- |
| [summary.json](summary.json) | Metrics, stage costs, tokens, latency, bootstrap intervals, deterministic diagnostic counts |
| [cases.csv](cases.csv) | All 200 actual responses with references, original judge scores/reasons, errors and evaluation timing |
| [model-report.json](model-report.json) | Original EvalScope export: immutable run configurations, results, comparison and 400-event usage ledger |
| [provider-audit.jsonl](provider-audit.jsonl) | 400 HTTP response metadata records: actual model IDs, request IDs, token details, finish reasons and monotonic timings; no credentials or request headers |
| [prepared.json](prepared.json) | Frozen 100-case input, exact prompts, settings and SHA-256 fingerprints |
| [quality-failures.json](quality-failures.json) | Cases below the **original judge** threshold or with execution errors; not an exhaustive defect list |
| [mechanical-checks.json](mechanical-checks.json) | Post hoc calendar/JSON checks, including judge false acceptances |
| [smoke.json](smoke.json) | Two disclosed preliminary arithmetic requests, excluded from study metrics |
| [software.json](software.json) | Source commit, per-file source hashes, library versions, local run times and base CI evidence |
| [SHA256SUMS](SHA256SUMS) | Integrity hashes for published artifacts |

`prepared.json` retains its preparation-time status to preserve the frozen hash. Its status describes creation of the snapshot; the completed execution is evidenced by `model-report.json`, provider metadata and the ledger. Raw private SQLite files, credentials, account details and authentication headers are not published.

The core runtime was commit `07cdd8dd20465617d1a077a4ed4040dc6e05f928`; its [hosted CI passed](https://github.com/Mei0707/LLM-Evaluation-Observability-Platform/actions/runs/39674621664). The study-specific addition is [metadata-only provider auditing](../../../scripts/study_server.py); it does not change prompts, scoring or provider transport. The post hoc [export script](../../../scripts/export_live_study.py) checks token/call/request-ID reconciliation and reproduces diagnostics from the completed evidence without making API calls.

To replay the offline export from the published raw files, put `prepared.json`, `model-report.json` and `provider-audit.jsonl` in a directory such as `artifacts/replay`; copy `smoke.json` to `artifacts/openai-study-2026-10-21-smoke.json`, then run:

```sh
.venv/bin/python scripts/export_live_study.py --source artifacts/replay --output artifacts/replayed-report
```

To execute a **new paid replication**, prepare a new directory with [the frozen model/price plan](../../live-workflow/openai-2026-10-21.yaml), configure the provider key through a protected secret file, start the audited server, and explicitly run `cli.study execute --allow-paid`. See [the workflow instructions](../../../docs/live-study.md). Request IDs, latency and token totals will differ across repetitions; model availability and pricing can change.

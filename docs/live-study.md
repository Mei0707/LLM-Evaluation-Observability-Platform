# Prepared live workflow and independent review study

Status on October 21, 2026: prepared for later execution, at the user's request. No paid calls or independent human labels have been collected. The hosted CI results are separate evidence about software execution, not model quality. No model winner, quality difference, human agreement rate, or judge failure is claimed yet.

## Frozen experiment

[The plan](../studies/live-workflow/plan.yaml) compares two actual prompt configurations on the same generation model. The baseline asks for concise evidence-based answers. The candidate adds explicit checks for calculations, revisions, missing facts, unavailable tools, and instructions embedded in evidence. Both receive the same question and reference context; generation never receives reference answers, mock outputs, synthetic perturbations, or judge scores.

The dataset is the existing 100-case authored fictional evidence-QA corpus across ten task families. It is useful for testing grounded reasoning under controlled conditions, and is not a production sample or independently validated benchmark. Its reference answers require human scrutiny. The candidate prompt was written with knowledge of the corpus's task families, so this is an exploratory comparison rather than an untouched holdout study. Freeze it before execution and use separate practice/development cases for subsequent tuning; any later prompt changes require a new study and fresh holdout data for confirmatory claims. Shared templates within task families also limit claims about statistical independence.

The primary quality measure is rubric-v1 LLM judging on a normalized 0–1 scale, with passing score .75. Exact match is exported as a secondary, format-sensitive diagnostic. Both prompts share the same judge, rubric, temperature 0, concurrency 2, timeout, output limits, and single-attempt policy. The judge can see references; the generator cannot see gold answers. A single paired run cannot establish general model superiority or stable provider latency. Use a different judge model/family where the configured endpoint supports one; record residual self-preference and shared-provider bias.

Prepare offline from the repository root:

```sh
.venv/bin/python -m cli.study prepare
```

This writes `artifacts/live-study/prepared.json`, including the sanitized case snapshot, both prompts, configurations, hashes, source commit, worktree status, rubric, and intended call counts. Preparation makes no API or provider calls and does not read provider credentials. The default model IDs are explicit placeholders. Existing snapshots cannot be overwritten.

When provider access and spending are authorized, edit model IDs/prices in a copy of the plan or prepare a new directory with exact supported IDs:

```sh
.venv/bin/python -m cli.study prepare \
  --directory artifacts/live-study-approved \
  --model YOUR_GENERATION_MODEL_ID --judge-model YOUR_JUDGE_MODEL_ID
```

The run schedules 200 generation requests and up to 200 judge requests. Generation and judge limits are respectively 512 and 256 completion tokens, for at most 153,600 generated tokens across scheduled requests. These are token ceilings, **not a dollar spending cap**; input tokens, provider-specific accounting and uncertain charges still matter. Prices default to unknown. Set provider-side spending controls and reviewed per-million-token rates before execution. The endpoint must support `max_completion_tokens` and JSON-object judge responses; this is not promised for every OpenAI-compatible server. See the [official request contract](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create).

## Execute later and collect evidence

Configure the server and worker with `PROVIDER_API_KEY` (or a protected project credential) and `PROVIDER_BASE_URL`. Keep credentials out of the plan, command arguments and Git. Client authentication uses `EVALSCOPE_API_TOKEN`; `EVALSCOPE_URL` and `EVALSCOPE_PROJECT_ID` select the API/project. HTTP is accepted only for localhost; use HTTPS for a shared deployment. The existing secure Compose setup supports personal-token reviewer identities.

Only the following command opts into paid work; **it was not run during preparation**:

```sh
.venv/bin/python -m cli.study execute \
  --directory artifacts/live-study-approved --allow-paid
```

Use `--credential-id PROJECT_CREDENTIAL_ID` if the server should use an encrypted project credential instead of its configured key. Both experiments are validated before either run is dispatched. They use one immutable dataset version, and are then submitted consecutively to the worker queue. This is not randomized/interleaved allocation; provider load or time drift can still confound latency. The server's existing queue/limiter and frozen run snapshots remain authoritative.

The launcher checkpoints dispatch intent before each POST and never automatically retries an ambiguous launch. Existing `state.json` blocks a second execution. If a network error occurs around submission, inspect `/api/v1/runs` for the recorded experiment IDs and confirm the actual run IDs before repairing state; do not start replacement runs blindly. This reduces accidental duplicate paid work, without claiming exactly-once provider billing. A timeout leaves server work running. Cancel through the dashboard if needed; repeat collection to resume without launching requests:

```sh
.venv/bin/python -m cli.study collect --directory artifacts/live-study-approved
```

`model-report.json` contains both run/config snapshots, every case result and judge explanation, the full per-attempt usage ledger/request IDs, errors, coverage, score/pass rate, p50/p95 end-to-end latency, generation/judge request timing, token totals, cost completeness, per-tag judge scores, and the platform's paired comparison/bootstrap interval. Request-stage timing includes accounting overhead; end-to-end latency includes evaluation. Failed/canceled cases remain visible in coverage and errors; successful-case quality and latency must be interpreted with those denominators. Unknown/unpriced/uncertain usage remains explicit, and estimates are not invoices. Reports may contain captured content and belong under the configured data-retention policy.

## Collect genuine human evidence later

Recruit at least two different people and give each their own `reviewer` account and personal token in **users** mode. Do not create fictitious reviewers or use model-generated labels as human evidence. Reviewers receive [the independent reviewer guide](../studies/live-workflow/reviewer-guide.md). Establish the rubric on separate practice examples, freeze it, and then have each person label all 200 captured answers independently (400 labels total if all cases succeed).

After captured runs finish, the coordinator can create the blinded campaign:

```sh
.venv/bin/python -m cli.study campaign --directory artifacts/live-study-approved
```

The command requires users mode. It does not create reviewer identities or send invitations. Use Settings to provision actual people and transfer their tokens through an appropriate channel. The queue randomizes order through opaque item IDs, withholds model/run identities, machine scores and other labels, and stores one immutable score/category/rationale per reviewer/item. Distinct accounts alone do not prove different people or independent behavior. Style and content can still suggest which prompt produced an answer.

Once labels arrive, export the coordinator report:

```sh
.venv/bin/python -m cli.study calibration --directory artifacts/live-study-approved
```

The dashboard also offers **Download calibration report**. The report includes selected-answer and per-run coverage, reviewer pair counts and category agreement, per-pair unweighted Cohen's kappa (null when undefined), score differences, human medians, paired judge MAE/agreement within .25, and up to ten largest judge/human disagreements with retained question, reference, response and rationales. Numeric metrics survive content expiry; examples do not. These are descriptive measurements over repeatedly observed reviewers and related cases; kappa is neither a reliability guarantee nor an independence test.

The 100-case target requires minimum distinct reviews on every selected campaign answer; seeing 100 reviewed case IDs from only one configuration does not complete a two-configuration campaign. Judge disagreements are **candidates for adjudication**, not automatically confirmed judge failures. A coordinator must inspect human disagreements and reference errors, record the final disposition and supporting evidence, and report whether a judge over-scored unsupported content, under-scored a correct abstention, or made another identifiable mistake. Preserve original labels; record adjudications separately using [the sign-off template](../studies/live-workflow/signoff.template.yaml).

Publish results only after the coordinator records real reviewer participation, independence, rubric/version, missingness, and adjudicated examples. Until then, the prepared study makes no human-validation claim. Keep generated snapshots, credentials, captured responses and labels in ignored protected artifacts; only publish reviewed evidence appropriate for the intended audience.

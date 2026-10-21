# Proposal review and delivery matrix

The 24-page proposal was reviewed as product and engineering requirements. Its prose, sample shell commands, roadmap, and resume bullets were not treated as instructions to execute commands, publish anything, contact anyone, or claim work was already done.

## Assessment

The proposal has a coherent audience and a valuable central workflow: pin a dataset and prompt, execute an evaluation, investigate a case, and compare a candidate with a baseline before release. Its distinction between proposed targets and measured evidence is sound. The 6–8 week roadmap is credible for an iterative local prototype; a production multi-tenant service, calibrated judge study, and broad infrastructure validation require additional work beyond the core implementation.

The important design gaps were worker ownership after a crash, evaluator compatibility, insufficient data in release decisions, and the line between synthetic test evidence and actual model quality. This implementation makes those decisions explicit.

| Area | Decision and rationale |
| --- | --- |
| Durable work | PostgreSQL rows are the work source; Redis handles cross-process provider limits. One durable source avoids reconciliation between independent queue and database state. |
| Recovery | Renewable 30-second leases, monotonic attempt numbers, and unique ownership tokens. Late owners cannot overwrite a replacement attempt. External calls may repeat. |
| Comparison | Exact same dataset version, evaluator versions, judge and embedding IDs, K, and pass threshold. Incompatibility returns HTTP 409. |
| Quality gates | PASS/FAIL/INCONCLUSIVE with explicit coverage and paired-case requirements; CLI rejects inconclusive releases. |
| Statistics | Deterministic paired bootstrap intervals on successful score deltas, reported as descriptive evidence. No claim of randomized experiments or general model superiority. |
| Similarity | Actual provider embeddings and cosine similarity. No token-overlap metric mislabeled as semantic understanding. |
| LLM judge | Versioned 1–5 rubric, JSON validation, normalized score, optional captured explanation, and explicit human-review calibration. No synthetic judge labels. |
| Cost | Stage-specific frozen prices and a durable usage ledger covering retries, generation, embeddings, judging, and application-reported stages; uncertain/unpriced charges stay explicit. No hardcoded provider prices or invented financial claims. |
| Content | Model output capture is opt-in; tracing accepts only allowlisted metadata. Dataset inputs and references are stored intentionally as evaluation data. |
| Deployment | Fully local PostgreSQL/Redis Compose deployment; lightweight SQLite development mode. No public hosting or paid inference required. |

## Acceptance coverage

| Proposal module / acceptance target | Implementation | Verification / remaining work |
| --- | --- | --- |
| Versioned datasets, JSONL/CSV, tags, validation | Implemented | API tests and browser workflow; stored fingerprints and case counts. |
| Frozen configurations and prompt versions | Implemented | Snapshot test confirms new dataset versions do not affect old runs. |
| Exact match | Implemented | Unicode/whitespace normalization tests. |
| Embedding similarity | Implemented via live adapter | Cosine tests and mock HTTP tests; no paid live-provider verification. |
| Retrieval precision@K, recall@K, MRR | Implemented for supplied labeled/retrieved IDs | Deduplication, rank, and denominator tests. Running a real retriever is application-owned. |
| LLM-as-judge | Implemented and exercised against OpenAI | [100-case, two-prompt study](../studies/results/openai-2026-10-21/README.md): 200 actual generations and 200 judgments; full token/cost/latency evidence. Post hoc arithmetic/format checks exposed judge false acceptances. Independent human calibration remains pending. |
| Human labels and calibration | Review UI and calibration API implemented | Real independently reviewed dataset and agreement study remain to be collected. |
| Durable asynchronous runs | Implemented | SQLite and PostgreSQL integration tests. |
| Retry, timeout, cancellation, recovery | Implemented | Failure injection, stale lease tests, real SIGKILL/restart measurement. |
| Traces, tokens, latency, costs | Implemented | Metadata-only OTel spans and API projections; optional Collector/Jaeger deployment. Usage covers recorded stages and retries; uncertain or unpriced charges remain explicit. |
| Online observability | SDK and ingestion implemented | Idempotency, schema and privacy tests; traces visible in dashboard. SDK exports synchronously. |
| Comparisons and regressions | Implemented | Per-case changes, paired intervals, incompatible snapshot/config rejection. |
| CI quality gate and CLI | Implemented | Passing candidate and deliberate regression fixtures, persisted reports and exit codes. |
| React dashboard | Implemented | API-backed workflow and responsive browser tests. |
| Monitoring deployment | Compose profile and Grafana dashboard implemented | Runtime verification recorded in project documentation; no production monitoring claim. |
| 100/1,000/5,000-case performance measurements | Implemented and measured | Nine raw measurements checked in; one process, three concurrency settings. An additional PostgreSQL study measures one, three, and five separate processes and injected dependency failures. |
| Recovery within 60 seconds | Achieved in local test | 31.35 seconds with default lease; 20/20 cases persisted, zero duplicate logical results. |
| At least 100 human-labeled examples | Not claimed | Supplied 100-case dataset is synthetic. Human reviews must be performed independently. |
| Authentication and project permissions | Personal-token identities and project roles, plus a separate local developer mode | Personal-token identities, project memberships/roles, revocation, encrypted credentials, audit events, and an HTTPS gateway are implemented and locally verified. SSO/MFA and public rollout remain operator work. |
| Retention / production governance | Opt-in capture and documented limits | Configured content/trace retention, TLS, encrypted project credentials with separate key storage, and audit events are implemented. Backups, external stores, and compliance remain separate responsibilities. |
| Portfolio demo evidence | Screenshot, tests, benchmark JSON and documentation | No narrated video or resume impact figures based on unmeasured production use. |

## Outcome

The implementation covers the functional local MVP and the high-value additions of retrieval metrics, regression gates, CI integration, and application tracing. The remaining work is explicitly research, production hardening, or broader measurement; none is represented as completed evidence.

## Follow-up delivery

All six requested improvement areas now have executable support: HTTP application integration; a 100-question diverse corpus and blinded multi-reviewer calibration; complete stage/attempt usage accounting with explicit unknowns; isolated multi-process/dependency-failure tests; actual persistence spans with per-attempt history; and personal identities/project roles/encrypted credentials/retention/TLS. [Application contract](applications.md), [human reviews](human-review.md), and [deployment controls](security.md) describe how to use them.

The [real-provider study](../studies/results/openai-2026-10-21/README.md) now supplies measured OpenAI generation/judging evidence, with explicit limits and actual failure examples. Independent human judgments, embedding-provider validation and a public production rollout remain outstanding. No generated fixture or automated test label is represented as independent human research.

# Verification record

Verified on October 21, 2026. Local verification, hosted GitHub execution and the subsequently completed real-provider study are recorded separately. Independent human research remains pending.

## Real OpenAI execution

The [published 100-case prompt comparison](../studies/results/openai-2026-10-21/README.md) used the existing prepare/execute/collect workflow with actual GPT-4.1 mini generation and GPT-4.1 judging. Both runs completed 100/100 cases: 400 HTTP 200 provider responses, no retries, zero cached tokens and complete reconciled request/token ledgers. Mean judge scores were .9850 baseline and .9775 candidate; generation HTTP p95 was 1.086/1.014 seconds, while evaluation p95 including judging and limiter waits was 4.546/4.587 seconds. The standard-rate cost estimate was $0.1596628 for the study plus $0.0005252 for a disclosed two-request smoke test. Provider invoices were not accessed.

All 200 actual responses, judge reasons, usage events, request metadata and frozen configurations are published. Post hoc calendar/JSON checks reproduced mathematical and format defects missed by the judge, and are reported separately from the unchanged primary scores. No independent human labeling, human agreement or general accuracy guarantee is claimed. Core source commit `07cdd8d` also has a [successful hosted run](https://github.com/Mei0707/LLM-Evaluation-Observability-Platform/actions/runs/39674621664).

## Hosted GitHub Actions

[Run 39671039135](https://github.com/Mei0707/LLM-Evaluation-Observability-Platform/actions/runs/39671039135) passed for commit `42a71f3f150b8379899f9573e5aebf294de0c92c` on `main`, triggered by the successful push. It ran October 21, 2026, 20:31:26–20:33:31 UTC. The GitHub API job statuses and full decoded job logs were inspected, rather than inferring success from workflow YAML or local results. [Selected machine-readable evidence](evidence/github-ci-42a71f3.json) records job/step conclusions, log excerpts and artifact identifiers/digests.

| Hosted job | Verified result |
| --- | --- |
| [Backend](https://github.com/Mei0707/LLM-Evaluation-Observability-Platform/actions/runs/39671039135/job/119468664850) | SQLite: 49 passed, 1 Redis-only skip. PostgreSQL + Redis: 50 passed. Migration round trip passed. |
| [Dashboard and quality gate](https://github.com/Mei0707/LLM-Evaluation-Observability-Platform/actions/runs/39671039135/job/119468664388) | Production build passed. Baseline/candidate gate passed; intentional regression was correctly rejected. Chromium: 3 passed, 1 skipped, in 18.5 seconds. |
| [Resilience](https://github.com/Mei0707/LLM-Evaluation-Observability-Platform/actions/runs/39671039135/job/119468664886) | All eight scenarios passed: 1/3/5 workers, process crash, database disconnect/restart, Redis outage, and cancellation. Zero duplicate logical results in every scenario. |

The skipped hosted browser scenario is the optional HTTPS identity/permission workflow, whose separate secure deployment was not configured in that run. The three executed scenarios cover the main workflow, narrow-screen dashboard, and application/usage/blind-review flow. HTTPS remains locally verified below; it is not claimed as a hosted browser pass.

Hosted resilience wall times: throughput 5.02/2.20/2.20 seconds for 1/3/5 workers; crash 7.31; database disconnect 4.22; database restart 4.17; Redis outage 7.63; cancellation 2.94. These are single hosted measurements with five-second laboratory leases, not production availability guarantees. The run uploaded `evaluation-evidence` and `resilience-evidence`; GitHub reports expiration on January 19, 2027. Downloadable artifacts/full logs are available from the run while retained.

This record applies to the cited commit. Later local study/calibration changes require their own checks and do not inherit a hosted pass from this run.

## Prepared-study follow-up verification

The local study/calibration changes were checked separately: SQLite 56 passed / 1 Redis-only skip; PostgreSQL + Redis 57 passed; production dashboard build passed; Chromium 3 passed / 1 optional HTTPS skip. The browser downloaded the calibration JSON and verified that a single automated label produces neither human consensus nor paired judge evidence. The new integration test uses simulated HTTP generation/judging to exercise both 100-case runs and export 400 request-ledger events; it is explicitly not paid-provider validation. Further checks cover ambiguous dispatch without duplicate launch, frozen-snapshot tampering, separate token ceilings, per-pair kappa, retained disagreement examples, expiry, and the requirement to review both configurations before completing a campaign.

During the preparation stage, the offline study snapshot was generated under `artifacts/live-study/prepared.json` with placeholder model IDs and no execution state. No paid requests or independent human labels were collected at that stage. The preparation changes were subsequently committed as `07cdd8d`; the real OpenAI execution described above used a separate frozen study directory. Each hosted pass is scoped to its cited commit rather than being inherited by later changes.

## Local execution

| Check | Evidence |
| --- | --- |
| Python integration suite | SQLite: 49 passed, 1 Redis-specific test skipped. PostgreSQL + Redis: 50 passed. Redis-specific test uses isolated database 15. |
| TypeScript and production assets | `npm run build` passed; chart and vendor bundles are split. |
| Browser workflow | Four browser scenarios passed: original workflow, mobile layout, application/usage/blind review, and HTTPS personal-token project permissions. The HTTPS scenario is run against a separate secure deployment. |
| Mobile workflow | Chromium at 390×844: navigation and dataset page passed; no page overflow. |
| CLI passing gate | Same-snapshot deterministic candidate completed and returned exit 0 with PASS. |
| CLI regression | Deliberately regressed candidate completed and returned exit 1 with FAIL. |
| Database migrations | Upgrade → schema check → downgrade → upgrade passed on disposable SQLite. Compose migrated PostgreSQL before startup. |
| Docker stack | Built from source; API, PostgreSQL, and Redis healthy; separate worker completed demo/CLI evaluations. |
| Monitoring | Jaeger returned `evalscope` traces, both Prometheus targets were up, Grafana API was healthy and listed the provisioned system dashboard. |
| Throughput | Nine full measurements: 100/1,000/5,000 cases × concurrency 1/3/5. 18,300 completed logical results, zero duplicates. |
| Process crash | SIGKILL/replacement: 20/20 cases completed in 31.35 seconds with default lease; zero logical duplicates. |

Python 3.11.5, Apple arm64, macOS 26.5.2. Docker used PostgreSQL 16 and Redis 7. Local browser testing used installed Chromium with `PLAYWRIGHT_CHROMIUM_EXECUTABLE`; CI installs the browser matching its pinned Playwright package. One upstream Starlette/httpx TestClient deprecation warning is present; it does not affect the test outcomes.

Monitoring verification used host ports 9091 (Prometheus) and 3001 (Grafana) because default local ports were occupied. Application access is http://localhost:8000. Those ports are configurable in Compose.

Not verified: independent human/judge calibration research, live embedding-provider calls, provider invoices, public deployment, or highly available database failover. OpenAI generation/judging was exercised in the study above. Personal-token authorization, trusted HTTPS, one/three/five worker processes, PostgreSQL disconnect/restart, Redis outage, and in-flight cancellation were exercised locally. See the [acceptance matrix](proposal-review.md) and [benchmark limits](benchmarks.md).

## Follow-up checks

The additive migration preserves historical traces and passed SQLite upgrade/check/downgrade/upgrade. PostgreSQL was migrated in Docker without dropping application data. Expanded tests cover protected validation errors, secret encryption/rotation, revoked tokens, reader/reviewer restrictions, actual application retrieval, withheld gold labels, generation/embedding/judge costs after later failure, uncertain request recovery, actual persistence timing, immutable distinct-reviewer labels, and idempotent retention.

The separate HTTPS deployment used a protected secret volume, an unprivileged API/worker, and an unpublished backend port. Its certificate and localhost hostname were verified using the gateway CA (no TLS verification bypass in the verifier). The API returned 401 without a token and 200 for the administrator. The browser checked project membership and reader-write rejection; its isolated context allowed the local development CA. No host trust store was modified.

The reference application's browser workflow registered a target, dispatched a real HTTP evaluation, inspected retrieval/tool/persistence spans, observed unpriced usage as unknown, and submitted an explicitly automated review fixture. That fixture is not independent human evidence.

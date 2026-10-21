# Architecture

## Component boundaries

`backend/app/api.py` validates HTTP requests and projects, performs short transactions, and returns 202 for new runs. `schemas.py` rejects unknown configuration fields and invalid evaluator/provider combinations. `models.py` defines relational records; `services.py` owns immutable snapshots, aggregation, comparison, and release decisions.

`worker.py` claims cases, renews ownership, runs providers and evaluators outside API requests, and fences persistence. `providers.py` separates deterministic simulation from the live HTTP adapter. `evaluators.py` owns metric definitions and version identifiers. `telemetry.py` records spans without request content and exposes bounded metrics.

React uses TanStack Query for retrieval and progress polling. Navigation, selection, forms, import validation feedback, and gate reports use real API data; no frontend data store impersonates persisted backend results. Charts display completed run measurements only.

`cli/` communicates only with REST APIs; it does not bypass run state or read the database. `evalscope_sdk/` exports application trace metadata through the ingestion API.

## Lifecycle

1. Create a dataset, persist its first version and individual cases in one transaction.
2. Save an immutable prompt and experiment configuration referencing its IDs.
3. Start a run: freeze the prompt text, dataset fingerprint, evaluator versions, generation settings, retry policy, and content policy. Create one logical result per case.
4. Workers lock eligible run rows, recover expired case leases, enforce per-run concurrency, and atomically claim pending cases with unique lease tokens.
5. Execute generation and scoring with a deadline. Heartbeats renew ownership. Redis coordinates provider request slots for live calls.
6. Persist only if the ownership token still matches and its lease remains valid. Successful scores and the result share one database transaction.
7. When all cases are terminal, finalize the run as COMPLETED, PARTIAL, or FAILED. Cancellation closes remaining cases as CANCELED.
8. Compare compatible runs by case identity, retain missing/failed distinctions, report paired uncertainty, and save gate decisions.

## Tradeoffs

- **Database-backed scheduling:** fewer moving durability boundaries than Redis plus SQL dual writes. Polling and synchronous SQLAlchemy calls limit throughput; this is measured, not hidden.
- **Small Python worker:** evaluation-specific orchestration, not a general durable queue framework. PostgreSQL supports multi-process claims; SQLite is for one worker process. Slow DB calls can delay the event loop and heartbeat; expired owners are fenced.
- **Spans in two places:** OTel exports full metadata traces to Jaeger when configured. PostgreSQL stores a limited projection to make the local inspector work without Jaeger. The `results.persist` span wraps the actual database transaction and commit. Each attempt retains its own trace ID and completed span projection, and application stages are exported into the same trace.
- **Polling UI:** simple and robust for small local workloads; no WebSocket infrastructure. Overview aggregation loads results and is not intended for unbounded production history.
- **Explicit access modes:** local mode is a developer convenience. Users mode uses hashed personal tokens, per-project roles, revocation, and blinded-review restrictions; the HTTPS override terminates TLS and hides the backend port.
- **Registered targets and protected credentials:** model provider URLs are server-configured, application hostnames are allowlisted, and administrators register immutable endpoints. Credentials come from environment/secret files or an encrypted project vault. HTTP compatibility does not guarantee every model supports temperature, embeddings, or JSON mode.
- **Baseline compatibility:** model and prompt changes can be compared; evaluator meaning, dataset snapshot, and decision threshold must remain fixed.

## Primary references

- [SQLAlchemy SELECT and row locking](https://docs.sqlalchemy.org/en/20/core/selectable.html): PostgreSQL `FOR UPDATE SKIP LOCKED` behavior.
- [OpenTelemetry Python manual instrumentation](https://opentelemetry.io/docs/languages/python/instrumentation/): tracer providers and manual spans.
- [OpenAI chat completions](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create) and [embeddings](https://developers.openai.com/api/reference/resources/embeddings/methods/create): the live adapter's supported wire formats. Judge JSON mode is validated again in the application.

## Added control and evidence services

`security.py` resolves personal identities, enforces project roles, and encrypts/decrypts selected credentials. `management.py` exposes scoped project, member, credential, target, audit, usage, and retention APIs. `targets.py` executes the HTTP application contract without forwarding gold answers. `usage.py` records durable pre-dispatch intents and stage-specific usage, including uncertain charges after failure. `reviews.py` serves blinded queues and attributed labels, then calculates coordinator-only consensus/calibration. `retention.py` applies enabled policies and audits counts.

Usage intents are independent of logical result fencing: a stale request cannot overwrite the result, but late provider billing evidence is still useful and can settle its own uncertain usage record. Trace projections are archived after the root span ends so actual commit duration and complete parent/child timestamps are retained. A lost projection remains explicitly incomplete and does not erase the durable trace reference.

The optional reference RAG app uses its own knowledge source, retrieval, a filesystem tool, and extractive generation. It is a genuine HTTP integration target with clearly limited behavior; it does not masquerade as a live-model quality benchmark.

# Reproducible local benchmark report

Measured October 21, 2026. The first matrix describes the initial implementation before expanded usage/security features; current multi-process measurements follow below. Raw data: [throughput matrix](../benchmarks/results/local-baseline.json), [SIGKILL recovery](../benchmarks/results/recovery.json).

## Environment

- macOS 26.5.2, Apple arm64, 10 logical CPUs, Python 3.11.5.
- SQLite WAL on the local filesystem; one asyncio process. Concurrency denotes in-flight case slots, not separate workers.
- Deterministic mock provider with 5 ms configured latency, varied by stable case-ID hash (0.6–1.39×). Exact-match scoring, real SQL persistence, attempt records, lease claims, and local OpenTelemetry spans.
- Timings exclude dataset/experiment creation and remote trace export. Other local activity, including a Docker build, overlapped these runs. These are single observations, not repeated confidence estimates.

## Procedure

```sh
make setup
make benchmark
.venv/bin/python -m benchmarks.recovery
```

The throughput script creates a fresh temporary database for each combination, waits for every case task, and checks distinct persisted case identities. It reports queue waiting, p50/p95 completed-case latency, coverage, and duplicate counts. The recovery script SIGKILLs a separate worker after observing an active case, starts a replacement process, and waits up to 60 seconds. It uses the unmodified 30-second lease. Both scripts use isolated temporary databases and no paid model inference.

## Throughput

| Cases | Slots | Wall time (s) | Cases / s | p95 case latency (ms) | Mean queue wait (ms) | Persistence | Duplicates |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 100 | 1 | 1.02 | 97.6 | 8.73 | 573.2 | 100% | 0 |
| 100 | 3 | 0.38 | 261.9 | 9.85 | 221.0 | 100% | 0 |
| 100 | 5 | 0.35 | 286.8 | 13.39 | 188.8 | 100% | 0 |
| 1,000 | 1 | 10.66 | 93.8 | 8.54 | 5249.1 | 100% | 0 |
| 1,000 | 3 | 4.66 | 214.7 | 13.25 | 2427.3 | 100% | 0 |
| 1,000 | 5 | 5.28 | 189.5 | 28.63 | 2383.9 | 100% | 0 |
| 5,000 | 1 | 67.70 | 73.9 | 8.70 | 34039.2 | 100% | 0 |
| 5,000 | 3 | 33.13 | 150.9 | 16.20 | 16214.6 | 100% | 0 |
| 5,000 | 5 | 34.05 | 146.8 | 30.71 | 15978.7 | 100% | 0 |

All **18,300 of 18,300** logical results persisted successfully, with **zero** duplicate logical results in these nine runs. At 5,000 cases, three slots measured 150.9 cases/s versus 73.9 at one slot. Five slots did not improve the measured baseline: synchronous database work and local contention limit scaling. Do not infer linear multi-process throughput from these values.

## Actual process termination

| Measurement | Observed |
| --- | --- |
| Cases completed after worker replacement | 20/20 |
| Abandoned attempts recovered | 3 |
| Seconds from SIGKILL to full completion | 31.35 |
| Lease timeout | 30 seconds |
| Duplicate logical results | 0 |

The recovery result met the proposal’s local 60-second target in this test. It does not guarantee all deployment environments recover within the same time. External inference may have been issued more than once; the measured uniqueness concerns persisted logical results.

## Quality and regression evidence

The deterministic CI fixtures compare a precise baseline with an identical passing candidate and a deliberately regressed candidate. API tests verify per-case regressions, failed gates, compatible configuration enforcement, and inconclusive incomplete data. This tests orchestration and release logic, not real-model judgment accuracy.

## Limits and next measurements

- Repeat each benchmark on an otherwise idle documented machine and report variation.
- Repeat the new PostgreSQL multi-process measurements with larger corpora and multiple hardware configurations.
- Extend the tested disconnect/restart/Redis scenarios to highly available database failover and prolonged provider throttling.
- Collect an independent 100-case human-reviewed corpus and measure judge agreement and disagreement categories.
- Measure provider usage for generation, embeddings, judges, retries, and uncertain timeouts before treating costs as a billing ledger.

## PostgreSQL multi-process and fault laboratory

Run `make reliability`. This creates a separate `evalscope-fault-lab` Compose project, uses disposable PostgreSQL/Redis services and a controlled HTTP provider, and removes only those lab volumes afterward. It never restarts or drops the application's database. Raw results: [distributed.json](../benchmarks/results/distributed.json).

Each worker has five task slots; the run allows up to 32 claimed cases. The lab uses five-second renewable leases and a controlled 80 ms mock latency for throughput, longer simulated inference for crash/database/cancel tests, and a local 500 ms HTTP provider for Redis outage testing. No paid inference occurs. These are single observations, with other local processes active.

| Scenario | Processes | Cases | Outcome | Wall seconds | Logical duplicates |
| --- | ---: | ---: | --- | ---: | ---: |
| throughput | 1 | 100 | COMPLETED | 4.96 | 0 |
| throughput | 3 | 100 | COMPLETED | 2.32 | 0 |
| throughput | 5 | 100 | COMPLETED | 1.91 | 0 |
| worker-crash | 3 | 30 | COMPLETED | 7.40 | 0 |
| database-disconnect | 3 | 30 | COMPLETED | 4.54 | 0 |
| database-restart | 3 | 30 | COMPLETED | 4.50 | 0 |
| redis-outage | 3 | 30 | COMPLETED | 8.69 | 0 |
| cancel-in-flight | 3 | 30 | CANCELED | 3.28 | 0 |

The one/three/five-process throughput runs completed 100/100 cases in each configuration. Four recovery scenarios completed 30/30 cases each; in-flight cancellation preserved the canceled state and did not resurrect late results. All eight scenarios retained unique logical results. Wall times include the full scenario and fault orchestration, not just outage duration. The five-second lab lease is deliberately distinct from the earlier unmodified 30-second lease recovery measurement.

Connection-loss injection terminates worker PostgreSQL connections; the separate database-restart case restarts that lab database. Redis is stopped for three seconds, then restarted; live-provider calls fail closed and resume through persisted retry policy. Worker-crash injection SIGKILLs lab workers and restarts them. These measurements verify specific local recovery behaviors, not arbitrary production failover or exactly-once inference.

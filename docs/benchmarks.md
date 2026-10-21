# Reproducible local benchmark report

Measured October 21, 2026. Raw data: [throughput matrix](../benchmarks/results/local-baseline.json), [SIGKILL recovery](../benchmarks/results/recovery.json).

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
- Measure PostgreSQL with one, three, and five separate worker processes, real Redis provider coordination, and high-latency simulated requests.
- Measure database disconnect/failover, Redis outages, and prolonged provider throttling.
- Collect an independent 100-case human-reviewed corpus and measure judge agreement and disagreement categories.
- Measure provider usage for generation, embeddings, judges, retries, and uncertain timeouts before treating costs as a billing ledger.

# Reliability and failure handling

## Delivery and ownership

One result row exists for each run/test-case pair before inference starts. A PostgreSQL transaction locks an eligible run, reclaims expired work, checks the frozen per-run concurrency limit, conditionally claims one pending result, increments its attempt number, creates an attempt record, and assigns a random token with a 30-second lease. Workers heartbeat every ten seconds.

Final persistence takes the run lock before the result lock. It checks status, token, expiry, and run cancellation. Stale owners return without modifying results. Recovery marks expired attempts ABANDONED and reschedules work within its attempt budget. Exhausted leases fail explicitly; they cannot retry forever. SQL unique constraints on run/test-case, result/attempt, and result/evaluator supplement the ownership checks.

This provides idempotent logical persistence and **at-least-once external inference**. A worker can die after the provider accepts a request but before a local commit; a new owner may issue the request again. Exactly-once model execution is not claimed.

## Errors and retries

Rate limits, provider 5xx responses, network timeouts, and case deadlines are transient. The retry delay is `min(30, 2^(attempt-1)) + uniform(0,.25)` seconds. Invalid credentials, invalid requests, malformed generation/embedding/judge responses, and evaluator failures are permanent. The maximum attempt count is frozen per run, from one to five.

Backoff is persisted as an availability timestamp, not an in-memory sleep holding a task slot. A process restart preserves the delay. Provider errors are stored as bounded categories; raw HTTP responses and credentials are not persisted. Cancellation immediately closes pending/running logical cases, fences their tokens, and marks active attempts canceled. Already-accepted provider calls may still complete and incur cost; their late writes are discarded.

## Rate limits and backpressure

Live requests use a local semaphore and, when configured, Redis sorted-set leases for cross-process concurrency plus a minimum interval between request starts. Redis server time avoids worker clock differences for those slots. Each Redis request slot expires after 125 seconds, beyond the 120-second per-case maximum. Crashed workers can therefore temporarily reduce provider capacity. The limiter is conservative and fails closed on Redis errors, which become retryable case failures. Redis is not required for the synthetic provider.

Without Redis, live rate limits coordinate only a single process. All workers in a multi-process live deployment must share Redis. Worker slots bound in-process tasks; per-run limits are checked under the run lock. PostgreSQL is the supported multi-process backend. SQLite WAL is a one-process convenience mode, not a distributed locking test environment.

## Verification

Unit and integration tests simulate transient/permanent providers, malformed judges, duplicate persistence, expired owners, cancellation during work, and snapshot changes. The same suite runs against disposable SQLite and PostgreSQL databases. `benchmarks/recovery.py` performs a real SIGKILL during active inference, starts a new worker, and measures complete recovery under the default lease. Raw results are checked in.

Database connection pooling uses `pool_pre_ping`. A transient claim exception is logged and retried; no API connection waits for inference. A failure during persistence leaves the lease available for recovery. Severe database stalls can block the synchronous SQLAlchemy calls, delaying heartbeats; expired writes remain fenced. Whole-database disconnect/failover and Redis-outage integration studies are not yet measured.

The worker catches task exceptions so a single case does not stop its poll loop. Graceful shutdown cancels in-flight tasks and leaves their leases to recover. Completed attempts and scores remain transactional. Local API `--reload` can abandon work; this is expected and recovered by lease expiry, rather than pretending no request was repeated.

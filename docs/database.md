# Database and data integrity

PostgreSQL 16 is the Compose deployment database. SQLite WAL is an optional local mode. SQLAlchemy 2 models use UUID primary keys, enforced foreign keys, UTC Unix timestamps, and explicit unique constraints. JSON fields contain frozen configuration, case payloads, trace projections, or saved reports; relational ownership and uniqueness remain separate columns.

| Table | Purpose / key constraints |
| --- | --- |
| projects | Local workspace partitions |
| datasets | Dataset identity and project ownership |
| dataset_versions | Dataset FK; unique dataset + version number; SHA-256 content fingerprint |
| test_cases | Version FK; unique version + case_id |
| prompt_versions | Immutable prompt text and project ownership |
| experiments | Named configuration referencing dataset/prompt versions |
| evaluation_runs | Frozen configuration, dataset version FK, lifecycle and timestamps |
| evaluation_results | Unique run + test_case; current logical state, lease, score, captured response policy |
| execution_attempts | Unique result + attempt number; explicit completed, failed, abandoned, canceled states |
| evaluator_scores | Unique result + evaluator; version, normalized value, explanation and metric details |
| baselines | Unique project + baseline name; completed run reference |
| regression_reports | Baseline/candidate references and immutable decision report |
| online_traces | Unique project + trace ID; allowlisted metadata only |

## Migrations

```sh
.venv/bin/alembic upgrade head
.venv/bin/alembic check
```

Compose runs migrations in a one-shot service before starting the API. Local SQLite startup creates missing tables for convenience. Schema changes still require migrations; `create_all` does not alter existing tables. Existing datasets, prompt versions, and run configurations have no update endpoints. Baseline names can intentionally move to another completed run. Human review labels can be updated independently of immutable machine scores.

The API records result state, attempt state, and scores transactionally. PostgreSQL run-row locks serialize concurrency accounting, recovery, cancellation, and finalization. Claim updates are conditional on the pending state; final writes require an unexpired lease and matching unique token. Unique constraints are a final backstop against duplicate logical results and score records.

`X-Project-ID` filters every application read/write and related-object validation. It is a partition selector, not proof of user membership. The local token authorizes the entire service. Do not expose this prototype as a multi-user service without authenticated identities and membership checks.

## Retention

Dataset inputs and references are deliberately persisted. Generated output is omitted unless content capture was enabled on the frozen run. Human review requires captured output. Trace spans exclude content. Captured responses, explanations, and review notes have no automated expiration; a production deployment must implement a retention policy, protected administrative deletion, backup handling, and audit requirements before handling sensitive data.

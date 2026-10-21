# Local verification record

Verified on October 21, 2026. These results describe local execution; the supplied GitHub Actions workflow has not been pushed or run on GitHub.

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

Not verified: paid live-model calls, independent human/judge calibration research, provider invoices, public deployment, or highly available database failover. Personal-token authorization, trusted HTTPS, one/three/five worker processes, PostgreSQL disconnect/restart, Redis outage, and in-flight cancellation were exercised locally. See the [acceptance matrix](proposal-review.md) and [benchmark limits](benchmarks.md).

## Follow-up checks

The additive migration preserves historical traces and passed SQLite upgrade/check/downgrade/upgrade. PostgreSQL was migrated in Docker without dropping application data. Expanded tests cover protected validation errors, secret encryption/rotation, revoked tokens, reader/reviewer restrictions, actual application retrieval, withheld gold labels, generation/embedding/judge costs after later failure, uncertain request recovery, actual persistence timing, immutable distinct-reviewer labels, and idempotent retention.

The separate HTTPS deployment used a protected secret volume, an unprivileged API/worker, and an unpublished backend port. Its certificate and localhost hostname were verified using the gateway CA (no TLS verification bypass in the verifier). The API returned 401 without a token and 200 for the administrator. The browser checked project membership and reader-write rejection; its isolated context allowed the local development CA. No host trust store was modified.

The reference application's browser workflow registered a target, dispatched a real HTTP evaluation, inspected retrieval/tool/persistence spans, observed unpriced usage as unknown, and submitted an explicitly automated review fixture. That fixture is not independent human evidence.

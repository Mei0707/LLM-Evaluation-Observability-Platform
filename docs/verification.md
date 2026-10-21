# Local verification record

Verified on October 21, 2026. These results describe local execution; the supplied GitHub Actions workflow has not been pushed or run on GitHub.

| Check | Evidence |
| --- | --- |
| Python integration suite | SQLite: 38 passed, 1 Redis-specific test skipped. PostgreSQL + Redis: 39 passed. Redis-specific test uses isolated database 15. |
| TypeScript and production assets | `npm run build` passed; chart and vendor bundles are split. |
| Browser workflow | Two Playwright tests passed: import/version → prompt → two runs → case trace → failed regression gate, plus the mobile workflow. |
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

Not verified: paid live-model calls, human/judge calibration agreement, live-provider billing completeness, a public deployment, per-user authorization, full database/Redis failover, or multi-process throughput scaling. See the [acceptance matrix](proposal-review.md) and [benchmark limits](benchmarks.md).

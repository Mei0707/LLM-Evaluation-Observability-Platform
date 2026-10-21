# Identity, access, credentials, and retention

## Two explicit operating modes

`EVALSCOPE_AUTH_MODE=local` preserves the loopback development experience, with one local developer identity and an optional shared access token. It is not a shared-user deployment. `users` mode requires a personal bearer token on every API request. Tokens are generated with 256 bits of randomness and stored only as SHA-256 hashes; plaintext is returned once. Disabling a user revokes their access, and rotating a token immediately revokes the previous token.

First users-mode startup provisions an administrator from `EVALSCOPE_BOOTSTRAP_TOKEN` or its `_FILE` secret. The value must contain at least 32 characters. Restarts do not reset an existing identity's token. System administrators create identities; project administrators manage memberships. Project roles are enforced on every request:

| Role | Allowed operations |
| --- | --- |
| reader | Read project data and calculate comparisons; no persisted writes |
| reviewer | Blinded campaign lists/queues and submission of their own labels; cannot access machine runs, scores, datasets, or calibration |
| editor | Dataset/prompt/experiment/run management and review campaigns |
| admin | Editor access plus memberships, application targets, encrypted credentials, and retention policy |

System administrator tokens can administer every project; project-admin membership is not system administration. Project headers select a partition and never grant access by themselves. Project creation grants the creator its admin membership. Membership mutations lock the project row to preserve the last-admin rule under concurrent changes.

## Run the HTTPS deployment

```sh
make secure-setup
docker compose -p evalscope-secure -f docker-compose.yml -f docker-compose.secure.yml up --build -d
```

Open `https://localhost:8443`. Copy the protected `.secrets/admin-token` value into the dashboard's access-token field. Do not commit or share this file. Settings provides identity issuance, project role assignment, revocation, project selection, encrypted credential creation/rotation, and retention management.

The setup helper creates ignored files with directory mode 0700 and file mode 0600, without printing values or replacing existing files. A one-shot root initializer copies Docker secret mounts into a volume readable only by UID 10001. API and worker processes remain unprivileged; the gateway has no application credentials. Back up the master key separately from the database: loss of that key prevents credential decryption.

Caddy terminates TLS, adds HSTS and common response protections, and forwards requests to an API with no published HTTP port. Proxy headers are trusted only in this override, where the API is reachable through its Docker network. That network is a trusted deployment boundary; do not attach untrusted containers to it. The API rejects non-HTTPS application requests based on the proxy-established request scheme.

For localhost, Caddy uses its development CA. This project does not install trust into the host/browser. Verify with:

```sh
.venv/bin/python scripts/verify_secure.py --project evalscope-secure
```

The verifier explicitly trusts the gateway CA and verifies the localhost hostname; it does not disable TLS checks. Browser QA permits the local untrusted CA in its isolated test context. For a real domain, configure `EVALSCOPE_DOMAIN`, appropriate network ports, DNS, and a trusted certificate. Public exposure and organization-specific identity setup are not performed automatically.

Authenticated Prometheus scraping must use a protected administrator/service credential and the TLS gateway with its trusted CA. The default development scrape configuration does not bypass secure-mode HTTPS/authentication. Configure those scrape credentials before combining the secure and monitoring deployments.

## Credential protection

API/provider secrets can be loaded from environment or `_FILE` mounts. Project credentials use Fernet authenticated encryption with a separately supplied master key. Values and ciphertext are excluded from list/create responses; rotation increments the recorded credential version, and disabling a credential prevents future use. Validation errors omit submitted input values. Audit events contain action/actor/object identifiers and bounded metadata, never secret values.

Targets are administrator-registered and restricted to allowed hostnames. URLs cannot contain userinfo, query strings, or fragments; redirects are rejected. HTTPS mode also requires HTTPS targets. Provider URLs are server-configured, not arbitrary experiment parameters. Administrators and their configured application hosts are trusted to receive the explicitly selected credentials.

## Retention

Project policies are off until an administrator enables them. Enabled policies run every five minutes. They expire captured output/retrieval evidence, judge explanations, human free-text notes/rationales, and attempt/online trace content. Numeric machine scores, attributed human scores/categories, usage records, and audit metadata remain. Dataset inputs/reference labels and prompt snapshots remain versioned data with a separate lifecycle; this policy is not a blanket deletion or erasure claim.

The cleanup endpoint defaults to a dry run. Retention and review submission lock result rows so an expired response cannot receive a newly stored review rationale after cleanup. Sweep audit events record counts. Database backups, Jaeger storage, external provider retention, and exported reports need their own operator-configured lifetimes.

## Boundaries

Personal-token identities are developer authentication, not OIDC/SSO, email verification, MFA, or an independent security audit. There is no compliance certification. The deployment controls are implemented and locally verified; production rollout still requires appropriate operational identity provisioning, backups, network policy, certificate ownership, and monitoring credentials.

References: [Fernet authenticated encryption](https://cryptography.io/en/stable/fernet/), [HTTPX transport behavior](https://www.python-httpx.org/advanced/transports/).

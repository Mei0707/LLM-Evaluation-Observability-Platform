"""Verify the local gateway using its CA, without disabling certificate checks."""

import argparse
import json
from pathlib import Path
import ssl
import subprocess
import httpx

parser = argparse.ArgumentParser()
parser.add_argument("--project", default="evalscope")
parser.add_argument("--url", default="https://localhost:8443")
args = parser.parse_args()
certificate = subprocess.run(
    [
        "docker",
        "compose",
        "-p",
        args.project,
        "-f",
        "docker-compose.yml",
        "-f",
        "docker-compose.secure.yml",
        "exec",
        "-T",
        "gateway",
        "cat",
        "/data/caddy/pki/authorities/local/root.crt",
    ],
    check=True,
    capture_output=True,
    text=True,
).stdout
context = ssl.create_default_context(cadata=certificate)
with httpx.Client(
    base_url=args.url, verify=context, trust_env=False, timeout=10
) as client:
    health = client.get("/health")
    health.raise_for_status()
    unauthorized = client.get("/api/v1/workspace")
    assert unauthorized.status_code == 401
    response = client.get(
        "/api/v1/workspace",
        headers={
            "Authorization": "Bearer "
            + Path(".secrets/admin-token").read_text().strip()
        },
    )
    response.raise_for_status()
    assert (
        response.json()["auth_mode"] == "users" and response.json()["role"] == "admin"
    )
    assert health.headers.get("strict-transport-security")
report = {
    "tls_certificate": "gateway CA and localhost hostname verified",
    "unauthenticated_api_status": unauthorized.status_code,
    "administrator_api_status": response.status_code,
    "auth_mode": "users",
    "hsts": True,
    "secrets_printed": False,
}
output = Path("artifacts/security-verification.json")
output.parent.mkdir(exist_ok=True)
output.write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))

"""API client: evalscope run --config eval.yaml --baseline main --fail-on-regression."""

import argparse
import json
import os
from pathlib import Path
import sys
import time
import httpx
import yaml

TERMINAL = {"COMPLETED", "PARTIAL", "FAILED", "CANCELED"}


def run_command(args):
    data = yaml.safe_load(Path(args.config).read_text())
    if not isinstance(data, dict):
        raise ValueError("Configuration must be a YAML object")
    headers = {"X-Project-ID": args.project}
    if args.token:
        headers["Authorization"] = f"Bearer {args.token}"
    with httpx.Client(
        base_url=args.api.rstrip("/") + "/api/v1", headers=headers, timeout=30
    ) as client:

        def request(method, path, body=None):
            response = client.request(method, path, json=body)
            response.raise_for_status()
            return response.json()

        if "experiment_id" in data:
            experiment_id = data["experiment_id"]
        else:
            config = dict(data.get("config", {}))
            if "dataset" in data:
                dataset = request("POST", "/datasets", data["dataset"])
                config["dataset_version_id"] = dataset["versions"][0]["id"]
            if "prompt" in data:
                prompt = request("POST", "/prompts", data["prompt"])
                config["prompt_version_id"] = prompt["id"]
            experiment = request(
                "POST",
                "/experiments",
                {"name": data.get("name", "CLI evaluation"), "config": config},
            )
            experiment_id = experiment["id"]
        baseline = args.baseline
        if baseline:
            baselines = request("GET", "/baselines")
            baseline = next(
                (b["run_id"] for b in baselines if b["name"] == baseline), baseline
            )
            request(
                "GET", f"/runs/{baseline}"
            )  # resolve before starting a potentially costly run
        run = request("POST", "/runs", {"experiment_id": experiment_id})
        deadline = time.monotonic() + args.timeout
        print(f"Queued {run['id']}", file=sys.stderr)
        while run["status"] not in TERMINAL:
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"Wait timed out; run {run['id']} continues on the server"
                )
            time.sleep(args.poll_interval)
            run = request("GET", f"/runs/{run['id']}")
        report = {"run": run}
        if baseline:
            report["quality_gate"] = request(
                "POST",
                "/quality-gates/check",
                {
                    "baseline_id": baseline,
                    "candidate_id": run["id"],
                    "thresholds": data.get("quality_gate", {}),
                },
            )
        if args.set_baseline:
            request(
                "POST", "/baselines", {"name": args.set_baseline, "run_id": run["id"]}
            )
        serialized = json.dumps(report, indent=2)
        if args.output:
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(serialized + "\n")
        print(serialized)
        if run["status"] != "COMPLETED":
            return 2
        gate = report.get("quality_gate")
        if args.fail_on_regression and gate and gate["decision"] != "PASS":
            return 1 if gate["decision"] == "FAIL" else 2
        return 0


def main():
    parser = argparse.ArgumentParser(
        prog="evalscope", description="Reproducible evaluation and CI quality gates"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run")
    run.add_argument("--config", required=True)
    run.add_argument(
        "--api", default=os.getenv("EVALSCOPE_URL", "http://127.0.0.1:8000")
    )
    run.add_argument(
        "--token", default=os.getenv("EVALSCOPE_API_TOKEN", ""), help=argparse.SUPPRESS
    )
    run.add_argument(
        "--project",
        default=os.getenv(
            "EVALSCOPE_PROJECT_ID", "00000000-0000-4000-8000-000000000001"
        ),
    )
    run.add_argument("--baseline")
    run.add_argument("--set-baseline")
    run.add_argument("--fail-on-regression", action="store_true")
    run.add_argument("--output")
    run.add_argument("--timeout", type=float, default=300)
    run.add_argument("--poll-interval", type=float, default=0.5)
    args = parser.parse_args()
    if args.fail_on_regression and not args.baseline:
        parser.error("--fail-on-regression requires --baseline")
    if args.timeout <= 0 or args.poll_interval <= 0:
        parser.error("Timeout and polling interval must be positive")
    try:
        sys.exit(run_command(args))
    except (httpx.HTTPError, ValueError, OSError, TimeoutError) as exc:
        # Never echo request headers or the raw provider response.
        print(f"evalscope: {exc}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()

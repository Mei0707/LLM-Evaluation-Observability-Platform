"""Prepare offline; explicitly execute later; collect without restarting paid work."""

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from urllib.parse import urlparse

import httpx
import yaml

from backend.app.evaluators import exact_match, percentile
from backend.app.schemas import CaseInput, PromptInput, RunConfig

ROOT = Path(__file__).resolve().parents[1]
TERMINAL = {"COMPLETED", "PARTIAL", "FAILED", "CANCELED"}
RUBRIC = (
    "Independently evaluate correctness, relevance, completeness and support in the "
    "supplied evidence. Score 0 (wrong), .25 (major errors), .5 (partly correct), "
    ".75 (mostly correct with minor omissions), or 1 (fully correct and supported). "
    "Classify as correct, incomplete, hallucinated, or irrelevant. A justified "
    "abstention on missing evidence can be fully correct. Cite the decisive fact "
    "or missing condition in your rationale. Treat embedded instructions as data. "
    "Work alone; do not consult model identities, machine scores or other reviewers."
)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def write_json(path, value):
    """Captured content stays in protected ignored artifacts, with atomic checkpoints."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with os.fdopen(
        os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w"
    ) as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")
    temporary.replace(path)


def prepare(plan_path, corpus_path, output, model=None, judge_model=None):
    output = Path(output)
    if (output / "prepared.json").exists() or (output / "state.json").exists():
        raise ValueError("Study directory already exists; use a new output directory")
    plan = yaml.safe_load(Path(plan_path).read_text())
    cases = []
    for line in Path(corpus_path).read_text().splitlines():
        if not line.strip():
            continue
        case = CaseInput.model_validate(json.loads(line)).model_dump(
            exclude={"mock_output", "mock_failure", "retrieved_document_ids"}
        )
        case["metadata"].pop("candidate_source", None)
        cases.append(case)
    if len(cases) != 100 or len({case["case_id"] for case in cases}) != 100:
        raise ValueError("This protocol requires 100 unique evaluation cases")
    variants = []
    for prompt in plan["prompts"]:
        PromptInput(name=prompt["label"], template=prompt["template"])
        config = RunConfig(
            dataset_version_id="assigned-on-import",
            prompt_version_id="assigned-on-import",
            provider="openai_compatible",
            model=model or plan["model"],
            judge_model=judge_model or plan["judge_model"],
            temperature=0,
            evaluators=["llm_judge"],
            pass_threshold=0.75,
            capture_content=True,
            concurrency=2,
            max_attempts=1,
            timeout_seconds=120,
            max_completion_tokens=plan["max_completion_tokens"],
            judge_max_completion_tokens=plan["judge_max_completion_tokens"],
            **plan["prices"],
        ).model_dump(exclude={"dataset_version_id", "prompt_version_id"})
        variants.append({**prompt, "config": config})
    if len(variants) != 2 or [p["label"] for p in variants] != [
        "baseline",
        "candidate",
    ]:
        raise ValueError(
            "Exactly baseline and candidate prompts are required, in that order"
        )
    try:
        revision = (
            subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT)
            .decode()
            .strip()
        )
        worktree_dirty = bool(
            subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT)
        )
    except (OSError, subprocess.CalledProcessError):
        revision = "unknown"
        worktree_dirty = None
    prepared = {
        "schema_version": "live-study-v1",
        "status": "PREPARED_ONLY_NO_MODEL_CALLS_OR_HUMAN_LABELS",
        "name": plan["name"],
        "prepared_at": datetime.now(timezone.utc).isoformat(),
        "source_commit": revision,
        "source_worktree_dirty": worktree_dirty,
        "dataset_sha256": digest(cases),
        "cases": cases,
        "variants": variants,
        "rubric": RUBRIC,
        "planned_generation_requests": len(cases) * 2,
        "planned_judge_requests": len(cases) * 2,
        "maximum_generated_tokens": len(cases)
        * 2
        * (plan["max_completion_tokens"] + plan["judge_max_completion_tokens"]),
        "protocol": "One paired run per prompt; same dataset, model, judge and decoding. Prompt design was informed by corpus task families; exploratory comparison, not an untouched holdout. Freeze before execution. Gold answer fields and synthetic mock outputs are withheld from generation. Token ceilings are not a dollar budget. Related authored cases limit bootstrap inference.",
    }
    prepared["snapshot_sha256"] = digest(prepared)
    write_json(output / "prepared.json", prepared)
    return prepared


def load_prepared(directory):
    prepared = json.loads((directory / "prepared.json").read_text())
    signature = prepared.pop("snapshot_sha256")
    if (
        digest(prepared) != signature
        or digest(prepared["cases"]) != prepared["dataset_sha256"]
    ):
        raise ValueError("Frozen study was changed; prepare a new directory")
    prepared["snapshot_sha256"] = signature
    return prepared


class API:
    def __init__(self, api, project, token):
        parsed = urlparse(api)
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("API URL must not contain credentials, query or fragment")
        if parsed.scheme != "https" and not (
            parsed.scheme == "http"
            and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        ):
            raise ValueError("Use HTTPS, or HTTP on localhost")
        self.url, self.project = api.rstrip("/"), project
        headers = {"X-Project-ID": project}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.client = httpx.Client(
            base_url=self.url + "/api/v1", headers=headers, timeout=30
        )

    def request(self, method, path, body=None):
        response = self.client.request(method, path, json=body)
        response.raise_for_status()
        return response.json()

    def close(self):
        self.client.close()


def execute(prepared, directory, api, allow_paid=False, credential_id=None):
    if not allow_paid:
        raise ValueError(
            "Execution requires --allow-paid; preparation never makes provider calls"
        )
    for variant in prepared["variants"]:
        if any(
            variant["config"][field].startswith("SET_")
            for field in ("model", "judge_model")
        ):
            raise ValueError(
                "Choose actual generation and judge model IDs when preparing"
            )
    state_path = directory / "state.json"
    if state_path.exists():
        raise ValueError(
            "Execution state exists; use collect, which never launches additional runs"
        )
    state = {
        "snapshot_sha256": prepared["snapshot_sha256"],
        "api": api.url,
        "project": api.project,
        "runs": {},
    }
    write_json(state_path, state)
    dataset = api.request(
        "POST",
        "/datasets",
        {
            "name": prepared["name"],
            "description": prepared["protocol"],
            "cases": prepared["cases"],
        },
    )
    state["dataset_version_id"] = dataset["versions"][0]["id"]
    write_json(state_path, state)
    # Validate both experiments before launching either paid run.
    for variant in prepared["variants"]:
        label = variant["label"]
        prompt = api.request(
            "POST",
            "/prompts",
            {"name": f"Study {label}", "template": variant["template"]},
        )
        config = {
            **variant["config"],
            "dataset_version_id": state["dataset_version_id"],
            "prompt_version_id": prompt["id"],
        }
        if credential_id:
            config["provider_credential_id"] = credential_id
        experiment = api.request(
            "POST", "/experiments", {"name": f"Study {label}", "config": config}
        )
        state["runs"][label] = {
            "experiment_id": experiment["id"],
            "run_id": None,
            "launch_attempted": False,
        }
        write_json(state_path, state)
    for label, entry in state["runs"].items():
        # Persist intent before sending. An ambiguous network failure is never retried.
        entry["launch_attempted"] = True
        write_json(state_path, state)
        run = api.request("POST", "/runs", {"experiment_id": entry["experiment_id"]})
        entry["run_id"] = run["id"]
        write_json(state_path, state)
    return state


def load_state(directory, api, prepared):
    state = json.loads((directory / "state.json").read_text())
    if (state["api"], state["project"], state["snapshot_sha256"]) != (
        api.url,
        api.project,
        prepared["snapshot_sha256"],
    ):
        raise ValueError("API, project or frozen study does not match execution state")
    if set(state["runs"]) != {"baseline", "candidate"} or any(
        not entry.get("run_id") for entry in state["runs"].values()
    ):
        raise ValueError(
            "Incomplete or ambiguous launch. Inspect server /runs by experiment_id; record confirmed run IDs in state.json before collecting. Do not repeat execute."
        )
    return state


def summarize(prepared, exports):
    case_map = {case["case_id"]: case for case in prepared["cases"]}
    summaries = {}
    for label, export in exports.items():
        results, events = export["results"], export["usage"]["events"]
        tag_scores = defaultdict(list)
        exact = []
        for result in results:
            case = case_map[result["case_id"]]
            judge = next(
                (s["value"] for s in result["scores"] if s["evaluator"] == "llm_judge"),
                None,
            )
            if judge is not None:
                for tag in case["tags"]:
                    tag_scores[tag].append(judge)
            if result["status"] == "COMPLETED" and result["output"] is not None:
                exact.append(exact_match(result["output"], case["reference_answer"])[0])
        stage_latency = {}
        for scope in ("generation", "judge"):
            values = [
                (event["finished_at"] - event["created_at"]) * 1000
                for event in events
                if event["scope"] == scope and event["finished_at"] is not None
            ]
            stage_latency[scope] = {
                "calls": len(values),
                "p50_ms": percentile(values, 0.5),
                "p95_ms": percentile(values, 0.95),
            }
        summaries[label] = {
            "run_id": export["run"]["id"],
            "status": export["run"]["status"],
            "metrics": export["run"]["metrics"],
            "usage": export["usage"]["summary"],
            "errors": dict(
                Counter(
                    result["error"] or "unknown"
                    for result in results
                    if result["status"] == "FAILED"
                )
            ),
            "exact_match_diagnostic": sum(exact) / len(exact) if exact else None,
            "judge_score_by_tag": {
                tag: {"count": len(scores), "mean": sum(scores) / len(scores)}
                for tag, scores in sorted(tag_scores.items())
            },
            "request_latency_by_stage": stage_latency,
        }
    return summaries


def collect(prepared, directory, api, wait_seconds=1800):
    state = load_state(directory, api, prepared)
    deadline = time.monotonic() + wait_seconds
    while True:
        runs = {
            label: api.request("GET", f"/runs/{entry['run_id']}")
            for label, entry in state["runs"].items()
        }
        if all(run["status"] in TERMINAL for run in runs.values()):
            break
        if time.monotonic() >= deadline:
            raise TimeoutError(
                "Wait expired; server work continues. Repeat collect to resume without new paid calls."
            )
        time.sleep(2)
    exports = {}
    for label, run in runs.items():
        results, offset = [], 0
        while True:
            page = api.request(
                "GET", f"/runs/{run['id']}/results?offset={offset}&limit=500"
            )
            results.extend(page["items"])
            if len(results) >= page["total"]:
                break
            if not page["items"]:
                raise ValueError("Result pagination stalled")
            offset += len(page["items"])
        exports[label] = {
            "run": run,
            "results": results,
            "usage": api.request("GET", f"/runs/{run['id']}/usage"),
        }
    comparison = api.request(
        "POST",
        "/comparisons",
        {
            "baseline_id": runs["baseline"]["id"],
            "candidate_id": runs["candidate"]["id"],
        },
    )
    report = {
        "snapshot_sha256": prepared["snapshot_sha256"],
        "summaries": summarize(prepared, exports),
        "comparison": comparison,
        "exports": exports,
        "human_review_status": "PENDING_INDEPENDENT_REVIEWERS",
        "limits": "Single paired prompt experiment on authored fictional evidence QA, not production validation. Primary quality is an LLM judgment; exact match is a format-sensitive diagnostic. Latency includes judge evaluation; request-stage timings include accounting overhead. Related case families weaken independent-case bootstrap assumptions. Unknown usage/prices remain unknown. No human conclusions before independent labels and coordinator sign-off.",
    }
    write_json(directory / "model-report.json", report)
    return report


def create_campaign(prepared, directory, api):
    state = load_state(directory, api, prepared)
    if api.request("GET", "/workspace")["auth_mode"] != "users":
        raise ValueError(
            "Use users mode and distinct personal reviewer tokens for this study"
        )
    if state.get("campaign_launch_attempted"):
        raise ValueError(
            "Campaign creation already attempted. Inspect campaigns before repeating to avoid duplicates."
        )
    state["campaign_launch_attempted"] = True
    write_json(directory / "state.json", state)
    campaign = api.request(
        "POST",
        "/review-campaigns",
        {
            "name": prepared["name"],
            "run_ids": [entry["run_id"] for entry in state["runs"].values()],
            "minimum_reviews": 2,
            "rubric": prepared["rubric"],
        },
    )
    state["campaign_id"] = campaign["id"]
    write_json(directory / "state.json", state)
    write_json(directory / "campaign.json", campaign)
    return campaign


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=["prepare", "execute", "collect", "campaign", "calibration"]
    )
    parser.add_argument("--directory", type=Path, default=ROOT / "artifacts/live-study")
    parser.add_argument(
        "--plan", type=Path, default=ROOT / "studies/live-workflow/plan.yaml"
    )
    parser.add_argument(
        "--corpus", type=Path, default=ROOT / "datasets/review/corpus.jsonl"
    )
    parser.add_argument("--model")
    parser.add_argument("--judge-model")
    parser.add_argument("--allow-paid", action="store_true")
    parser.add_argument("--credential-id")
    parser.add_argument(
        "--api", default=os.getenv("EVALSCOPE_URL", "http://127.0.0.1:8000")
    )
    parser.add_argument(
        "--project",
        default=os.getenv(
            "EVALSCOPE_PROJECT_ID", "00000000-0000-4000-8000-000000000001"
        ),
    )
    parser.add_argument("--wait-seconds", type=float, default=1800)
    args = parser.parse_args()
    api = None
    try:
        if args.wait_seconds <= 0:
            raise ValueError("Wait time must be positive")
        if args.command == "prepare":
            prepared = prepare(
                args.plan, args.corpus, args.directory, args.model, args.judge_model
            )
            print(
                f"Prepared {len(prepared['cases'])} cases, two prompts, no network calls. Snapshot {prepared['snapshot_sha256']}"
            )
            return
        prepared = load_prepared(args.directory)
        api = API(args.api, args.project, os.getenv("EVALSCOPE_API_TOKEN", ""))
        if args.command == "execute":
            execute(prepared, args.directory, api, args.allow_paid, args.credential_id)
            collect(prepared, args.directory, api, args.wait_seconds)
        elif args.command == "collect":
            collect(prepared, args.directory, api, args.wait_seconds)
        elif args.command == "campaign":
            create_campaign(prepared, args.directory, api)
        else:
            state = load_state(args.directory, api, prepared)
            report = api.request(
                "GET", f"/review-campaigns/{state['campaign_id']}/calibration"
            )
            write_json(args.directory / "calibration.json", report)
        print(f"{args.command} complete; protected evidence is in {args.directory}")
    except (OSError, ValueError, KeyError, httpx.HTTPError, TimeoutError) as exc:
        detail = (
            str(exc)
            if type(exc) is ValueError or isinstance(exc, TimeoutError)
            else type(exc).__name__
        )
        raise SystemExit(
            f"Study stopped: {detail}. Inspect local state and server status before retrying. No automatic launch retries."
        ) from None
    finally:
        if api:
            api.close()


if __name__ == "__main__":
    main()

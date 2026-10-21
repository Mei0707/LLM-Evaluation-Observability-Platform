"""Export the completed OpenAI study, reconciling provider evidence with the ledger."""

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import platform
import random
import re
import shutil
import statistics

from backend.app.evaluators import percentile
from cli.study import load_prepared

CACHED_INPUT_RATES = {
    "gpt-4.1-mini-2025-04-14": 0.10,
    "gpt-4.1-2025-04-14": 0.50,
}


def export(source, destination):
    prepared = load_prepared(source)
    report = json.loads((source / "model-report.json").read_text())
    audit = [
        json.loads(line)
        for line in (source / "provider-audit.jsonl").read_text().splitlines()
    ]
    if report["snapshot_sha256"] != prepared["snapshot_sha256"]:
        raise ValueError("Report does not match the frozen study")
    if any(
        e["run"]["status"] not in {"COMPLETED", "PARTIAL", "FAILED", "CANCELED"}
        for e in report["exports"].values()
    ):
        raise ValueError("Study is not terminal")
    cases = {case["case_id"]: case for case in prepared["cases"]}
    destination.mkdir(parents=True, exist_ok=True)
    variants = {variant["label"]: variant for variant in prepared["variants"]}
    summaries, flat, failures, mechanical = {}, [], [], []
    for label, exported in report["exports"].items():
        run = exported["run"]
        requests = [entry for entry in audit if entry["run_id"] == run["id"]]
        ledger = exported["usage"]["events"]
        observed_ids = [
            entry["request_id"] for entry in requests if entry["request_id"]
        ]
        ledger_ids = [entry["request_id"] for entry in ledger if entry["request_id"]]
        if len(observed_ids) != len(set(observed_ids)) or set(observed_ids) != set(
            ledger_ids
        ):
            raise ValueError(
                "Provider request identities do not reconcile with the ledger"
            )
        config = variants[label]["config"]
        stages = {}
        for scope, model, input_rate, output_rate in [
            (
                "generation",
                config["model"],
                config["input_cost_per_million"],
                config["output_cost_per_million"],
            ),
            (
                "judge",
                config["judge_model"],
                config["judge_input_cost_per_million"],
                config["judge_output_cost_per_million"],
            ),
        ]:
            rows = [entry for entry in requests if entry["requested_model"] == model]
            if any(
                entry["http_status"] == 200 and entry["response_model"] != model
                for entry in rows
            ):
                raise ValueError("Provider returned a different model snapshot")
            costs, prompt, completion, cached = [], 0, 0, 0
            for entry in rows:
                tokens = entry["usage"]
                if not tokens:
                    costs.append(None)
                    continue
                incoming, outgoing = (
                    tokens["prompt_tokens"],
                    tokens["completion_tokens"],
                )
                hits = tokens.get("prompt_tokens_details", {}).get("cached_tokens", 0)
                prompt += incoming
                completion += outgoing
                cached += hits
                costs.append(
                    (
                        (incoming - hits) * input_rate
                        + hits * CACHED_INPUT_RATES[model]
                        + outgoing * output_rate
                    )
                    / 1_000_000
                )
            timings = [entry["http_duration_ms"] for entry in rows]
            stages[scope] = {
                "model": model,
                "requests": len(rows),
                "input_tokens": prompt,
                "output_tokens": completion,
                "cached_input_tokens": cached,
                "estimated_cost_usd": (
                    sum(costs) if all(value is not None for value in costs) else None
                ),
                "http_p50_ms": percentile(timings, 0.5),
                "http_p95_ms": percentile(timings, 0.95),
                "finish_reasons": dict(
                    Counter(entry["finish_reason"] for entry in rows)
                ),
            }
        totals = {
            field: sum(stage[field] for stage in stages.values())
            for field in (
                "requests",
                "input_tokens",
                "output_tokens",
                "cached_input_tokens",
            )
        }
        totals["estimated_cost_usd"] = (
            sum(stage["estimated_cost_usd"] for stage in stages.values())
            if all(stage["estimated_cost_usd"] is not None for stage in stages.values())
            else None
        )
        if (totals["input_tokens"], totals["output_tokens"], totals["requests"]) != (
            exported["usage"]["summary"]["input_tokens"],
            exported["usage"]["summary"]["output_tokens"],
            exported["usage"]["summary"]["calls"],
        ):
            raise ValueError(
                "Provider tokens/call counts do not reconcile with the ledger"
            )
        summaries[label] = {
            "run_id": run["id"],
            "status": run["status"],
            "metrics": run["metrics"],
            "stages": stages,
            "totals": totals,
            "ledger_complete": exported["usage"]["summary"]["complete"],
            "ledger_nominal_cost_usd": exported["usage"]["summary"]["known_cost"],
            "judge_score_by_tag": report["summaries"][label]["judge_score_by_tag"],
        }
        for result in exported["results"]:
            case = cases[result["case_id"]]
            tag = next(
                tag
                for tag in case["tags"]
                if tag not in {"unreviewed", "authored-fixture"}
            )
            judge = next(
                (s for s in result["scores"] if s["evaluator"] == "llm_judge"), None
            )
            entry = {
                "configuration": label,
                "case_id": result["case_id"],
                "task_family": tag,
                "result_id": result["id"],
                "status": result["status"],
                "question": case["input"],
                "reference_answer": case["reference_answer"],
                "output": result["output"],
                "judge_score": judge["value"] if judge else None,
                "judge_reason": judge["reason"] if judge else None,
                "passed": result["passed"],
                "evaluation_latency_ms": result["latency_ms"],
                "error": result["error"],
            }
            flat.append(entry)
            if tag in {"temporal", "structured-output"}:
                issue = None
                if tag == "temporal":
                    match = re.search(
                        r"opened at (\S+)\. Its SLA is (\d+) hours\.", case["input"]
                    )
                    expected = datetime.fromisoformat(match[1]) + timedelta(
                        hours=int(match[2])
                    )
                    if expected != datetime.fromisoformat(case["reference_answer"]):
                        raise ValueError(
                            "Authored temporal reference disagrees with calendar arithmetic"
                        )
                    try:
                        actual = datetime.fromisoformat(
                            (result["output"] or "").strip()
                        )
                        if actual != expected or actual.utcoffset() != timedelta(0):
                            issue = "wrong_utc_instant"
                    except ValueError:
                        issue = "not_a_single_python_parseable_iso_datetime"
                else:
                    expected = json.loads(case["reference_answer"])
                    try:
                        actual = json.loads(result["output"] or "")
                        if (
                            not isinstance(actual, dict)
                            or actual != expected
                            or set(actual) != {"name", "quota"}
                            or type(actual["quota"]) is not int
                            or type(actual["name"]) is not str
                        ):
                            issue = "incorrect_json_fields_values_or_types"
                    except ValueError:
                        issue = "not_bare_json"
                mechanical.append(
                    {
                        **entry,
                        "mechanical_pass": issue is None,
                        "mechanical_issue": issue,
                    }
                )
            if (
                result["status"] != "COMPLETED"
                or judge
                and judge["value"] < config["pass_threshold"]
            ):
                failures.append(entry)
        summaries[label]["below_threshold_or_error_cases"] = sum(
            entry["configuration"] == label for entry in failures
        )
        summaries[label]["post_hoc_mechanical_checks"] = {
            family: {
                "tested": sum(
                    entry["configuration"] == label and entry["task_family"] == family
                    for entry in mechanical
                ),
                "passed": sum(
                    entry["configuration"] == label
                    and entry["task_family"] == family
                    and entry["mechanical_pass"]
                    for entry in mechanical
                ),
                "failed_with_judge_full_score": sum(
                    entry["configuration"] == label
                    and entry["task_family"] == family
                    and not entry["mechanical_pass"]
                    and entry["judge_score"] == 1
                    for entry in mechanical
                ),
            }
            for family in ("temporal", "structured-output")
        }
    cluster = defaultdict(list)
    for pair in report["comparison"]["cases"]:
        if pair["delta"] is not None:
            family = next(
                tag
                for tag in cases[pair["case_id"]]["tags"]
                if tag not in {"unreviewed", "authored-fixture"}
            )
            cluster[family].append(pair["delta"])
    rng = random.Random(42)
    families = sorted(cluster)
    samples = []
    for _ in range(10000):
        sample = [
            value
            for family in rng.choices(families, k=len(families))
            for value in cluster[family]
        ]
        samples.append(statistics.mean(sample))
    summary = {
        "study_snapshot_sha256": prepared["snapshot_sha256"],
        "dataset_sha256": prepared["dataset_sha256"],
        "configurations": summaries,
        "mean_score_delta": report["comparison"]["mean_score_delta"],
        "case_bootstrap_95_interval": report["comparison"]["score_delta_95_ci"],
        "family_cluster_bootstrap_95_interval": [
            percentile(samples, 0.025),
            percentile(samples, 0.975),
        ],
        "family_cluster_bootstrap_method": "Resample the ten authored task families with replacement, retaining their paired case deltas; 10000 percentile resamples, seed 42. Exploratory sensitivity analysis, ten clusters and no independent human calibration.",
        "paired_case_changes": report["comparison"]["counts"],
        "http_status_counts": dict(Counter(entry["http_status"] for entry in audit)),
        "rates_usd_per_million": {
            label: {
                k: v for k, v in variant["config"].items() if "cost_per_million" in k
            }
            for label, variant in variants.items()
        },
        "cached_input_rates_usd_per_million": CACHED_INPUT_RATES,
        "billing_note": "Standard-rate token-based estimates, accounting for observed cached tokens. Provider invoices, credits, discounts and taxes were not accessed.",
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "database": "isolated SQLite WAL",
            "provider_concurrency": 2,
            "provider_requests_per_second": 2,
            "embedded_worker": True,
        },
        "human_review_status": "NOT_CONDUCTED",
        "mechanical_check_method": "Post hoc diagnostics on all ten temporal and all ten structured-output cases per configuration, chosen after inspecting outputs. Temporal references are independently recomputed from the question with datetime + timedelta; a single Python-parseable ISO datetime must equal that UTC instant. JSON is parsed directly without stripping Markdown and compared for exact keys, values and field types. These checks do not replace the frozen judge scores or measure overall 100-case accuracy.",
    }
    for name, value in [
        ("summary.json", summary),
        ("quality-failures.json", failures),
        ("mechanical-checks.json", mechanical),
    ]:
        (destination / name).write_text(json.dumps(value, indent=2) + "\n")
    with (destination / "cases.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(flat[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(flat)
    for name in ["prepared.json", "model-report.json", "provider-audit.jsonl"]:
        shutil.copyfile(source / name, destination / name)
    smoke = source.parent / "openai-study-2026-10-21-smoke.json"
    shutil.copyfile(smoke, destination / "smoke.json")
    smoke_data = json.loads(smoke.read_text())
    smoke_cost = 0
    for entry in smoke_data["requests"]:
        rates = (0.4, 1.6) if entry["model"] == "gpt-4.1-mini-2025-04-14" else (2, 8)
        smoke_cost += (
            entry["usage"]["prompt_tokens"] * rates[0]
            + entry["usage"]["completion_tokens"] * rates[1]
        ) / 1_000_000
    summary["excluded_smoke_estimated_cost_usd"] = smoke_cost
    (destination / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    hashes = [
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}"
        for path in sorted(destination.iterdir())
        if path.is_file() and path.name != "SHA256SUMS"
    ]
    (destination / "SHA256SUMS").write_text("\n".join(hashes) + "\n")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", type=Path, default=Path("artifacts/openai-study-2026-10-21")
    )
    parser.add_argument(
        "--output", type=Path, default=Path("studies/results/openai-2026-10-21")
    )
    args = parser.parse_args()
    summary = export(args.source, args.output)
    print(
        json.dumps(
            {
                "configurations": summary["configurations"],
                "mean_score_delta": summary["mean_score_delta"],
                "family_cluster_bootstrap_95_interval": summary[
                    "family_cluster_bootstrap_95_interval"
                ],
            },
            indent=2,
        )
    )

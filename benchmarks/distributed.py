"""Host orchestrator: all faults target a separate named Compose project."""

import json
from pathlib import Path
import platform
import subprocess
import time

COMMAND = [
    "docker",
    "compose",
    "-p",
    "evalscope-fault-lab",
    "-f",
    "benchmarks/docker-compose.lab.yml",
]


def compose(*args):
    subprocess.run([*COMMAND, *args], check=True, stdout=subprocess.DEVNULL)


def measure(scenario, processes):
    compose("up", "-d", "--scale", f"worker={processes}", "worker", "api", "provider")
    process = subprocess.Popen(
        [
            *COMMAND,
            "run",
            "--rm",
            "--no-deps",
            "-T",
            "runner",
            "python",
            "-u",
            "-m",
            "benchmarks.lab_scenarios",
            "run",
            "--scenario",
            scenario,
            "--processes",
            str(processes),
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    report = None
    try:
        for line in process.stdout:
            if line.startswith("READY "):
                run_id = line.split()[1]
                if scenario == "worker-crash":
                    compose("kill", "-s", "SIGKILL", "worker")
                    compose("up", "-d", "--scale", f"worker={processes}", "worker")
                elif scenario == "database-disconnect":
                    compose(
                        "exec",
                        "-T",
                        "postgres",
                        "psql",
                        "-U",
                        "evalscope",
                        "-d",
                        "evalscope_lab",
                        "-c",
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE application_name='evalscope-worker' AND pid<>pg_backend_pid()",
                    )
                elif scenario == "database-restart":
                    compose("restart", "postgres")
                elif scenario == "redis-outage":
                    compose("stop", "redis")
                    time.sleep(3)
                    compose("start", "redis")
                elif scenario == "cancel-in-flight":
                    compose(
                        "run",
                        "--rm",
                        "--no-deps",
                        "-T",
                        "runner",
                        "python",
                        "-m",
                        "benchmarks.lab_scenarios",
                        "cancel",
                        "--run-id",
                        run_id,
                    )
            elif line.startswith("REPORT "):
                report = json.loads(line[7:])
        if process.wait() != 0 or report is None:
            raise RuntimeError(f"{scenario} failed")
        print(
            f"{scenario} / {processes} processes: {report['status']}, {report['wall_seconds']:.2f}s, duplicates {report['duplicate_logical_results']}",
            flush=True,
        )
        return report
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)


def main():
    result = {
        "environment": {
            "host": platform.platform(),
            "database": "PostgreSQL 16",
            "redis": "Redis 7",
            "provider": "controlled local HTTP / deterministic mock; no paid inference",
            "notes": "Disposable Compose project; five slots per worker, five-second renewable leases. Single measurements with other local processes active.",
        },
        "measurements": [],
    }
    try:
        compose("up", "-d", "postgres", "redis", "provider")
        compose("run", "--rm", "-T", "init")
        for processes in [1, 3, 5]:
            result["measurements"].append(measure("throughput", processes))
        for scenario in [
            "worker-crash",
            "database-disconnect",
            "database-restart",
            "redis-outage",
            "cancel-in-flight",
        ]:
            result["measurements"].append(measure(scenario, 3))
            output = Path("benchmarks/results/distributed.json")
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(result, indent=2) + "\n")
    finally:
        compose("down", "-v", "--remove-orphans")


if __name__ == "__main__":
    main()

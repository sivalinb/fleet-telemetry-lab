"""Run the complete Python demo and native observability tools. Ctrl-C stops children."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".runtime"


def native_config():
    out = RUNTIME / "config"
    out.mkdir(parents=True, exist_ok=True)
    for directory in ["collector", "prometheus", "loki/chunks", "loki/rules"]:
        (RUNTIME / directory).mkdir(parents=True, exist_ok=True)
    for name in ["collector", "prometheus", "loki", "jaeger"]:
        content = (ROOT / "observability" / f"{name}.yaml").read_text()
        content = content.replace("0.0.0.0", "127.0.0.1").replace(
            "/var/lib/fleetlab", str(RUNTIME)
        )
        for service in ["relay", "collector"]:
            content = (
                content.replace(service + ":", "127.0.0.1:")
                if service == "relay"
                else content.replace("collector:888", "127.0.0.1:888")
            )
        (out / f"{name}.yaml").write_text(content)
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--catalog-only",
        action="store_true",
        help="Run the catalog and UI; telemetry is visibly unavailable",
    )
    parser.add_argument("--no-ui", action="store_true")
    args = parser.parse_args()
    os.chdir(ROOT)
    config = native_config()
    py = sys.executable
    commands = [
        (
            "api",
            [
                py,
                "-m",
                "uvicorn",
                "fleetlab.api:app_factory",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                "8001",
            ],
            {},
        )
    ]
    if not args.catalog_only:
        for tool in ["collector", "prometheus", "loki", "jaeger"]:
            if not (RUNTIME / "bin" / tool).exists():
                raise SystemExit(
                    "Run python scripts/install_tools.py first, or use --catalog-only."
                )
        commands += [
            (
                "loki",
                [
                    str(RUNTIME / "bin/loki"),
                    "-config.file=" + str(config / "loki.yaml"),
                ],
                {},
            ),
            (
                "jaeger",
                [
                    str(RUNTIME / "bin/jaeger"),
                    "--config=" + str(config / "jaeger.yaml"),
                ],
                {},
            ),
            (
                "prometheus",
                [
                    str(RUNTIME / "bin/prometheus"),
                    "--config.file=" + str(config / "prometheus.yaml"),
                    "--storage.tsdb.path=" + str(RUNTIME / "prometheus"),
                    "--web.listen-address=127.0.0.1:9090",
                    "--storage.tsdb.retention.time=2h",
                ],
                {},
            ),
            (
                "relay",
                [
                    py,
                    "-m",
                    "uvicorn",
                    "fleetlab.relay:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "8200",
                ],
                {},
            ),
            (
                "collector",
                [
                    str(RUNTIME / "bin/collector"),
                    "--config=" + str(config / "collector.yaml"),
                ],
                {},
            ),
        ]
        for name, port in [("worker", 8103), ("scheduler", 8102), ("gateway", 8101)]:
            commands.append(
                (
                    name,
                    [
                        py,
                        "-m",
                        "uvicorn",
                        "fleetlab.workload:app",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(port),
                    ],
                    {"SERVICE_NAME": name},
                )
            )
    if not args.no_ui:
        commands.append(
            (
                "streamlit",
                [
                    py,
                    "-m",
                    "streamlit",
                    "run",
                    "streamlit_app.py",
                    "--server.address=127.0.0.1",
                    "--server.port=8501",
                    "--server.headless=true",
                    "--browser.gatherUsageStats=false",
                ],
                {},
            )
        )
    processes, handles = [], []
    (RUNTIME / "logs").mkdir(exist_ok=True)
    try:
        for name, command, overrides in commands:
            log = (RUNTIME / "logs" / f"{name}.log").open("a")
            handles.append(log)
            process = subprocess.Popen(
                command,
                env={**os.environ, **overrides},
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            processes.append((name, process))
        (RUNTIME / "processes.json").write_text(
            json.dumps({n: p.pid for n, p in processes}, indent=2)
        )
        print("Fleet Atlas: http://127.0.0.1:8501", flush=True)
        print("API: http://127.0.0.1:8001/docs · Logs: .runtime/logs", flush=True)
        while True:
            for name, process in processes:
                if process.poll() is not None:
                    raise RuntimeError(
                        f"{name} exited ({process.returncode}). See .runtime/logs/{name}.log"
                    )
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for _, process in reversed(processes):
            if process.poll() is None:
                process.terminate()
        for _, process in reversed(processes):
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        for handle in handles:
            handle.close()


if __name__ == "__main__":
    main()

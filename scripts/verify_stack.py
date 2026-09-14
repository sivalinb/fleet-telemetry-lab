"""Exercise real services. Start scripts/run_stack.py first. Evidence is reproducible."""

import argparse
import json
import os
from pathlib import Path
import sys
import time
import httpx

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--api", default=os.getenv("FLEET_API_URL", "http://127.0.0.1:8001")
    )
    parser.add_argument(
        "--output", default=str(ROOT / "evidence/live-experiments.json")
    )
    args = parser.parse_args()
    token = os.getenv("LAB_API_TOKEN")
    headers = {"Authorization": "Bearer " + token} if token else {}
    with httpx.Client(timeout=90, headers=headers) as client:
        for _ in range(90):
            try:
                health = (
                    client.get(args.api + "/api/pipeline").raise_for_status().json()
                )
                if all(s["status"] == "ready" for s in health["services"]):
                    break
            except httpx.HTTPError:
                pass
            time.sleep(1)
        else:
            raise SystemExit("Stack did not become ready in 90 seconds")
        runs = []
        for name in [
            "baseline",
            "label-growth",
            "contract-gate",
            "slow-worker",
            "backend-outage",
        ]:
            run = (
                client.post(
                    args.api + "/api/experiments", json={"name": name, "count": 12}
                )
                .raise_for_status()
                .json()
            )
            runs.append(run)
            print(name, run["state"], run.get("assertions"), flush=True)
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        evidence = {
            "description": "Measured synthetic CPU workload against real observability backends",
            "source_paths": "Local source paths normalized to repository-relative paths for sharing",
            "runs": runs,
        }
        output.write_text(
            json.dumps(evidence, indent=2).replace(str(ROOT) + "/", "") + "\n"
        )
    return 0 if all(r.get("passed") for r in runs) else 1


if __name__ == "__main__":
    sys.exit(main())

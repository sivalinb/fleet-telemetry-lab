"""Exercise all nine real experiments, cancellation, and the Gradio API."""

import json
import os
from pathlib import Path
import time
import httpx
from gradio_client import Client
from fleetlab.contracts import resource_for
from fleetlab.runs import SCENARIO_CATALOG, TERMINAL
from fleetlab.reports import public_result
from fleetlab.telemetry import auth_headers

ROOT = Path(__file__).resolve().parents[1]


def save_evidence(payload):
    directory = ROOT / "evidence/reliability"
    directory.mkdir(parents=True, exist_ok=True)
    summary = {**payload, "runs": []}
    for run in payload["runs"]:
        name = run["name"]
        path = directory / (name + ".json")
        path.write_text(json.dumps(public_result(run), separators=(",", ":")) + "\n")
        keys = [
            "id",
            "name",
            "state",
            "requested",
            "completed",
            "duration_s",
            "verified_chains",
            "delivery",
            "ingress",
            "assertions",
            "cleanup",
        ]
        summary["runs"].append(
            {
                **{k: run[k] for k in keys if k in run},
                "evidence_file": "reliability/" + path.name,
            }
        )
    (ROOT / "evidence/reliability-suite.json").write_text(
        json.dumps(summary, separators=(",", ":")) + "\n"
    )


def main():
    address = os.getenv("FLEET_API_URL", "http://127.0.0.1:8001")
    results = []
    with httpx.Client(base_url=address, timeout=20, headers=auth_headers()) as client:

        def request(method, path, **kwargs):
            response = client.request(method, path, **kwargs)
            response.raise_for_status()
            return response.json()

        for _ in range(90):
            try:
                health = request("GET", "/api/pipeline")
                if all(s["status"] == "ready" for s in health["services"]):
                    break
            except httpx.HTTPError:
                pass
            time.sleep(1)
        else:
            raise RuntimeError("Stack did not become ready")

        for scenario in SCENARIO_CATALOG:
            record = request(
                "POST", "/api/runs", json={"name": scenario["id"], "count": 12}
            )
            deadline = time.monotonic() + 110
            while record["state"] not in TERMINAL and time.monotonic() < deadline:
                time.sleep(0.5)
                record = request("GET", "/api/runs/" + record["id"])
            results.append(public_result(record["results"]))
            save_evidence(
                {"origin": "Real local OTLP/backend integration", "runs": results}
            )
            print(scenario["id"] + ": " + record["state"], flush=True)
            assert record["state"] == "passed", record["results"]
            assert all(record["results"]["assertions"].values())
            for extension in ["html", "json"]:
                report = client.get(
                    "/api/runs/" + record["id"] + "/report",
                    params={"format": extension},
                )
                report.raise_for_status()
                assert "attachment" in report.headers["content-disposition"]

        record = request(
            "POST", "/api/runs", json={"name": "durable-crash", "count": 40}
        )
        run_id = record["id"]
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            record = request("GET", "/api/runs/" + run_id)
            if record["results"].get("samples"):
                break
            time.sleep(0.05)
        assert record["state"] == "running", record
        cancelled = request("POST", "/api/runs/" + run_id + "/cancel")
        assert cancelled["state"] == "cancelled", cancelled
        assert cancelled["results"]["cleanup"]["all_exited"]
        assert cancelled["results"]["cleanup"]["owned_processes"] >= 2
        print("Cancellation: owned processes exited", flush=True)

    demo = Client(os.getenv("GRADIO_URL", "http://127.0.0.1:7860"), verbose=False)
    invalid = demo.predict(
        json.dumps(resource_for("gateway")),
        json.dumps({"request_id": "bad"}),
        api_name="/validate_contract",
    )
    valid = demo.predict(
        json.dumps(resource_for("gateway")),
        json.dumps({"profile": "bounded"}),
        api_name="/validate_contract",
    )
    assert not invalid["valid"] and valid["valid"]
    output = demo.predict("baseline", 8, api_name="/run_experiment")
    assert "Hypothesis verified" in output[0]
    assert output[-2]["verified_chains"] == 8
    assert len(output[-1]) == 2 and all(Path(p).is_file() for p in output[-1])
    save_evidence(
        {
            "origin": "Real local OTLP/backend integration",
            "runs": results,
            "cancellation": public_result(cancelled["results"]),
            "gradio": {
                "contract_rejects_unbounded_label": True,
                "contract_accepts_bounded_label": True,
                "run": public_result(output[-2]),
                "report_downloads": 2,
            },
        }
    )
    print(
        "Gradio: contract validation, streamed run, both report downloads passed",
        flush=True,
    )
    print("Nine scenarios passed; evidence/reliability-suite.json", flush=True)


if __name__ == "__main__":
    main()

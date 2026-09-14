"""Publish aggregate verification results without raw execution metadata."""

import json
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]


def main():
    evidence = ROOT / "evidence"
    result = {"scope": "Synthetic local workload verification; aggregate results only"}
    junit = evidence / "unit-tests.xml"
    if junit.exists():
        suites = list(ElementTree.parse(junit).iter("testsuite"))
        result["python_tests"] = {key: sum(int(s.attrib.get(key, 0)) for s in suites) for key in ["tests", "failures", "errors", "skipped"]}
    suite = evidence / "reliability-suite.json"
    if suite.exists():
        result["scenarios"] = [{"name": run["name"], "state": run["state"], "assertions_passed": bool(run.get("assertions")) and all(run["assertions"].values())} for run in json.loads(suite.read_text())["runs"]]
    recovery = evidence / "collector-recovery.json"
    if recovery.exists():
        run = json.loads(recovery.read_text())
        result["persistent_recovery"] = {key: run[key] for key in ["requests", "traces_recovered", "unique_logs_recovered", "passed"]}
    (evidence / "verification-summary.json").write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()

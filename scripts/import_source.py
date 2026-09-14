"""Read a native JSON snapshot, normalize it, then sync it into the local catalog.

File input is the safe default. HTTPS input requires explicit URL and optional bearer
token in SOURCE_BEARER_TOKEN. Pagination/member expansion must be done by the caller.
Imports are incremental by default; --full-snapshot explicitly marks omitted records absent.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
import httpx
from fleetlab.adapters import kubernetes_records, redfish_records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=["kubernetes", "redfish"])
    parser.add_argument(
        "input", help="Native JSON file or HTTPS URL returning a complete JSON document"
    )
    parser.add_argument("--api", default="http://127.0.0.1:8001")
    parser.add_argument(
        "--batch-id",
        help="Reuse to verify idempotency with identical input and --observed-at",
    )
    parser.add_argument(
        "--observed-at", help="ISO 8601 timezone-aware source snapshot timestamp"
    )
    parser.add_argument("--full-snapshot", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if "://" in args.input:
        if urlsplit(args.input).scheme != "https":
            raise SystemExit(
                "Remote imports require HTTPS with certificate verification"
            )
        token = os.getenv("SOURCE_BEARER_TOKEN")
        headers = {"Authorization": "Bearer " + token} if token else {}
        with httpx.Client(
            timeout=15, follow_redirects=False, headers=headers
        ) as client:
            with client.stream("GET", args.input) as r:
                r.raise_for_status()
                raw = bytearray()
                for chunk in r.iter_bytes():
                    raw.extend(chunk)
                    if len(raw) > 4 * 1024 * 1024:
                        raise SystemExit("Source document exceeds 4 MB")
    else:
        raw = Path(args.input).read_bytes()
    if len(raw) > 4 * 1024 * 1024:
        raise SystemExit("Source document exceeds 4 MB")
    doc = json.loads(raw)
    records = (kubernetes_records if args.kind == "kubernetes" else redfish_records)(
        doc
    )
    observed = args.observed_at or datetime.now(timezone.utc).isoformat()
    payload = {
        "batch_id": args.batch_id
        or hashlib.sha256(raw + observed.encode()).hexdigest()[:24],
        "observed_at": observed,
        "full_snapshot": args.full_snapshot,
        "records": [r.model_dump() for r in records],
    }
    if args.dry_run:
        print(json.dumps(payload, indent=2))
        return
    token = os.getenv("LAB_API_TOKEN")
    headers = {"Authorization": "Bearer " + token} if token else {}
    source = "kubernetes" if args.kind == "kubernetes" else "redfish-bmc"
    r = httpx.post(
        args.api + "/api/sources/" + source + "/sync",
        json=payload,
        headers=headers,
        timeout=30,
    )
    r.raise_for_status()
    print(json.dumps(r.json(), indent=2))


if __name__ == "__main__":
    main()

"""Read-only parsers for native Kubernetes lists and Redfish ComputerSystem data."""

from .catalog import Record


def kubernetes_records(document):
    records = []
    for item in document.get("items", []):
        metadata = item.get("metadata", {})
        annotations = metadata.get("annotations", {})
        if item.get("kind") == "Node":
            serial = annotations.get("fleetlab/serial")
            if not serial:
                raise ValueError(
                    "Node is missing fleetlab/serial; hostnames are not physical identifiers"
                )
            fields = {"name": metadata["name"], "serial": serial}
            if annotations.get("fleetlab/owner"):
                fields["owner"] = annotations["fleetlab/owner"]
            if annotations.get("fleetlab/cluster"):
                fields["cluster"] = annotations["fleetlab/cluster"]
            ready = next(
                (
                    c
                    for c in item.get("status", {}).get("conditions", [])
                    if c.get("type") == "Ready"
                ),
                {},
            )
            fields["health"] = "healthy" if ready.get("status") == "True" else "unknown"
            records.append(
                Record(
                    external_id=metadata["name"],
                    entity_id="node:" + serial,
                    kind="node",
                    fields=fields,
                )
            )
        elif item.get("kind") == "Deployment":
            service = annotations.get("fleetlab/service")
            if not service:
                raise ValueError("Deployment is missing fleetlab/service")
            fields = {"name": metadata["name"]}
            if annotations.get("fleetlab/owner"):
                fields["owner"] = annotations["fleetlab/owner"]
            records.append(
                Record(
                    external_id=metadata.get("namespace", "default")
                    + "/"
                    + metadata["name"],
                    entity_id=service,
                    kind="service",
                    fields=fields,
                )
            )
    return records


def redfish_records(document):
    items = document.get("systems", [document])
    records = []
    for item in items:
        serial = item.get("SerialNumber")
        if not serial:
            raise ValueError("Redfish ComputerSystem requires SerialNumber")
        if "@odata.id" in item and "SerialNumber" not in item:
            raise ValueError("Resolve Redfish member links before parsing")
        fields = {
            "serial": serial,
            "name": item.get("Name", serial),
            "model": item.get("Model", "unknown"),
            "health": {
                "OK": "healthy",
                "Warning": "degraded",
                "Critical": "critical",
            }.get(item.get("Status", {}).get("Health"), "unknown"),
        }
        extra = item.get("Oem", {}).get("FleetLab", {})
        for key in ["rack", "cluster", "gpus"]:
            if key in extra:
                fields[key] = extra[key]
        records.append(
            Record(
                external_id=item.get("Id", serial),
                entity_id="node:" + serial,
                kind="node",
                fields=fields,
            )
        )
    return records

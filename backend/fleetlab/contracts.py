"""Small, explicit instrumentation contract used by workloads and release checks."""

REQUIRED_RESOURCE = {
    "service.name",
    "service.namespace",
    "deployment.environment.name",
    "k8s.cluster.name",
    "team.owner",
}
UNBOUNDED = {"request_id", "user_id", "session_id", "email", "prompt"}


def validate_telemetry(resource, metric_attributes):
    errors = []
    for field in sorted(REQUIRED_RESOURCE):
        if not isinstance(resource.get(field), str) or not resource[field].strip():
            errors.append(
                {
                    "code": "missing_resource",
                    "field": field,
                    "message": f"Missing required resource attribute: {field}",
                }
            )
    for field in sorted(set(metric_attributes) & UNBOUNDED):
        errors.append(
            {
                "code": "unbounded_label",
                "field": field,
                "message": f"{field} belongs in logs/traces, not metric labels",
            }
        )
    if len(metric_attributes) > 12:
        errors.append(
            {
                "code": "label_budget",
                "field": "*",
                "message": "Metric attribute budget exceeded (12)",
            }
        )
    return {"valid": not errors, "errors": errors}


def resource_for(service, owner="team:inference"):
    return {
        "service.name": service,
        "service.namespace": "fleetlab",
        "deployment.environment.name": "lab",
        "k8s.cluster.name": "alpine",
        "team.owner": owner,
    }

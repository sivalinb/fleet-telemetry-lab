# Source examples

These documents are invented, small examples in native Kubernetes and Redfish shapes. They contain no employer data. The `Oem.FleetLab` Redfish capacity and location fields are a lab convention; an actual integration must map its vendor schema. The Kubernetes annotations are an explicit identity/ownership contract, not fields Kubernetes discovers automatically.

The importer is incremental by default. Only use `--full-snapshot` for a complete, paginated source snapshot. A partial page must never withdraw the rest of the fleet.

```sh
python scripts/import_source.py redfish fixtures/redfish.json --dry-run
python scripts/import_source.py redfish fixtures/redfish.json
python scripts/import_source.py kubernetes fixtures/kubernetes.json
```

Remote input accepts an explicit HTTPS URL returning a resolved document. `SOURCE_BEARER_TOKEN` is optional and scoped to that read. Redirects are disabled and TLS is verified. Kubernetes continuation tokens and Redfish member links are not followed automatically in this version.

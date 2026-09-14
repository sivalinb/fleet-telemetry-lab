"""Three real HTTP services generate correlated OTLP metrics, logs, and traces.

The workload is deterministic CPU work, not an LLM or GPU inference benchmark.
"""

import asyncio
import hashlib
import logging
import os
import time
from contextlib import asynccontextmanager
from uuid import uuid4

import httpx
from fastapi import FastAPI, Request
from opentelemetry import metrics, propagate, trace
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from pydantic import BaseModel, Field

from .contracts import resource_for, validate_telemetry

SERVICE = os.environ.get("SERVICE_NAME", "gateway")
COLLECTOR = os.environ.get("COLLECTOR_URL", "http://127.0.0.1:4318").rstrip("/")
INSTANCE_ID = uuid4().hex
resource = Resource.create(
    {
        **resource_for(
            SERVICE, "team:platform" if SERVICE == "scheduler" else "team:inference"
        ),
        "service.instance.id": INSTANCE_ID,
    }
)
traces = TracerProvider(resource=resource)
traces.add_span_processor(
    BatchSpanProcessor(
        OTLPSpanExporter(endpoint=COLLECTOR + "/v1/traces"), schedule_delay_millis=300
    )
)
trace.set_tracer_provider(traces)
reader = PeriodicExportingMetricReader(
    OTLPMetricExporter(endpoint=COLLECTOR + "/v1/metrics"), export_interval_millis=1000
)
meters = MeterProvider(resource=resource, metric_readers=[reader])
metrics.set_meter_provider(meters)
logs = LoggerProvider(resource=resource)
logs.add_log_record_processor(
    BatchLogRecordProcessor(
        OTLPLogExporter(endpoint=COLLECTOR + "/v1/logs"), schedule_delay_millis=300
    )
)
logger = logging.getLogger("fleetlab." + SERVICE)
logger.setLevel(logging.INFO)
logger.propagate = False
logger.addHandler(LoggingHandler(logger_provider=logs))
tracer = trace.get_tracer("fleetlab.workload")
meter = metrics.get_meter("fleetlab.workload")
counter = meter.create_counter(
    "fleetlab_requests", description="Completed lab HTTP requests"
)
latency = meter.create_histogram(
    "fleetlab_request_duration", unit="s", description="Lab service request duration"
)


class Work(BaseModel):
    experiment_id: str = Field(default="manual", max_length=80)
    request_id: str = Field(default_factory=lambda: uuid4().hex, max_length=80)
    profile: str = Field(default="bounded", pattern="^(bounded|unbounded|guarded)$")
    delay_ms: int = Field(default=0, ge=0, le=1000)


@asynccontextmanager
async def lifespan(app):
    yield
    traces.shutdown()
    meters.shutdown()
    logs.shutdown()


app = FastAPI(title=f"FleetLab {SERVICE}", lifespan=lifespan)


@app.get("/health")
def health():
    return {
        "service": SERVICE,
        "status": "ready",
        "instance_id": INSTANCE_ID,
        "workload": "CPU hash exercise",
    }


@app.post("/work")
async def work(body: Work, request: Request):
    attrs = {"profile": body.profile, "operation": "work"}
    if body.profile in {"unbounded", "guarded"}:
        attrs["request_id"] = body.request_id
    contract = validate_telemetry(resource.attributes, attrs)
    if body.profile == "guarded" and not contract["valid"]:
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=422, content={"contract": contract, "emitted": False}
        )
    start = time.perf_counter()
    context = propagate.extract(dict(request.headers))
    with tracer.start_as_current_span(
        SERVICE + ".work",
        context=context,
        attributes={
            "experiment.id": body.experiment_id,
            "request.id": body.request_id,
            "fleet.node.id": "node:FTL-A11",
        },
    ) as span:
        trace_id = format(span.get_span_context().trace_id, "032x")
        logger.info(
            "work.started",
            extra={
                "experiment.id": body.experiment_id,
                "request.id": body.request_id,
                "event.name": "work.started",
            },
        )
        next_service = {"gateway": "scheduler", "scheduler": "worker"}.get(SERVICE)
        if next_service:
            headers = {}
            propagate.inject(headers)
            endpoint = os.environ.get(
                "DOWNSTREAM_URL",
                "http://127.0.0.1:"
                + ("8102" if next_service == "scheduler" else "8103"),
            )
            async with httpx.AsyncClient(timeout=10) as client:
                result = await client.post(
                    endpoint + "/work", json=body.model_dump(), headers=headers
                )
                result.raise_for_status()
        else:
            payload = body.request_id.encode()
            for _ in range(2000):
                payload = hashlib.sha256(payload).digest()
            await asyncio.sleep(body.delay_ms / 1000)
        duration = time.perf_counter() - start
        counter.add(1, attrs)
        latency.record(duration, attrs)
        logger.info(
            "work.completed",
            extra={
                "experiment.id": body.experiment_id,
                "request.id": body.request_id,
                "event.name": "work.completed",
                "duration_ms": round(duration * 1000, 3),
            },
        )
    return {
        "service": SERVICE,
        "trace_id": trace_id,
        "request_id": body.request_id,
        "duration_ms": round(duration * 1000, 3),
        "contract": contract,
    }

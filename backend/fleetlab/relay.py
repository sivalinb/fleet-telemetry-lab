"""A bounded fault relay: deliberately return 503 to exercise Collector retry queues."""

import os
import time
import secrets
import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

app = FastAPI(title="FleetLab telemetry fault relay")
state = {"fail_until": 0.0, "attempts": 0, "rejected": 0, "forwarded": 0}


class Fault(BaseModel):
    seconds: int = Field(ge=0, le=45)


@app.get("/health")
def health():
    return {
        **state,
        "remaining_seconds": max(0, round(state["fail_until"] - time.time(), 1)),
    }


@app.post("/control")
def control(body: Fault, request: Request):
    token = os.environ.get("LAB_API_TOKEN", "")
    if token and not secrets.compare_digest(
        request.headers.get("authorization", ""), "Bearer " + token
    ):
        raise HTTPException(401, "Invalid API token")
    state["fail_until"] = time.time() + body.seconds
    return health()


@app.post("/v1/{signal}")
async def forward(signal: str, request: Request):
    endpoints = {
        "traces": os.environ.get("JAEGER_OTLP_URL", "http://127.0.0.1:4319")
        + "/v1/traces",
        "logs": os.environ.get("LOKI_URL", "http://127.0.0.1:3100") + "/otlp/v1/logs",
    }
    if signal not in endpoints:
        raise HTTPException(404, "Unsupported signal")
    body = await request.body()
    if len(body) > 4 * 1024 * 1024:
        raise HTTPException(413, "Batch exceeds relay limit")
    state["attempts"] += 1
    if time.time() < state["fail_until"]:
        state["rejected"] += 1
        return Response("Injected backend outage", status_code=503)
    headers = {
        k: v
        for k, v in request.headers.items()
        if k.lower() in {"content-type", "content-encoding"}
    }
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.post(endpoints[signal], content=body, headers=headers)
        if r.is_success:
            state["forwarded"] += 1
        return Response(
            r.content,
            status_code=r.status_code,
            media_type=r.headers.get("content-type", "application/octet-stream"),
        )
    except httpx.HTTPError:
        return Response("Telemetry backend unavailable", status_code=503)

import asyncio
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import select

from .contracts import validate_telemetry
from .jobs import BusyError, ExperimentManager
from .models import Experiment, make_database
from .reports import html_report, public_result
from .runs import SCENARIO_CATALOG
from .telemetry import pipeline_status

ROOT = Path(__file__).resolve().parents[2]


def create_app(database_url=None):
    engine, factory = make_database(database_url)
    manager = ExperimentManager(factory)

    @asynccontextmanager
    async def lifespan(app):
        yield
        await manager.close()
        engine.dispose()

    app = FastAPI(
        title="Telemetry Reliability Lab API", version="1.0.0", lifespan=lifespan
    )
    app.state.factory = factory
    app.state.experiments = manager

    @app.middleware("http")
    async def protect(request, call_next):
        token = os.getenv("LAB_API_TOKEN", "")
        if (
            request.url.path.startswith("/api/")
            and token
            and not secrets.compare_digest(
                request.headers.get("authorization", ""), "Bearer " + token
            )
        ):
            from fastapi.responses import JSONResponse

            return JSONResponse(
                status_code=401, content={"detail": "Invalid API token"}
            )
        try:
            length = int(request.headers.get("content-length", "0") or "0")
        except ValueError:
            from fastapi.responses import JSONResponse

            return JSONResponse(
                status_code=400, content={"detail": "Invalid content length"}
            )
        if length > 4 * 1024 * 1024:
            from fastapi.responses import JSONResponse

            return JSONResponse(
                status_code=413, content={"detail": "Request exceeds 4 MB"}
            )
        if request.method == "POST" and len(await request.body()) > 4 * 1024 * 1024:
            from fastapi.responses import JSONResponse

            return JSONResponse(
                status_code=413, content={"detail": "Request exceeds 4 MB"}
            )
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.get("/health")
    def health():
        return {"status": "ready", "database": engine.dialect.name, "version": "1.0.0"}

    @app.get("/api/pipeline")
    async def pipeline():
        return await pipeline_status()

    class Run(BaseModel):
        name: str
        count: int = Field(default=12, ge=1, le=40)

    @app.post("/api/experiments")
    async def experiment(body: Run):
        try:
            record = await manager.start(body.name, body.count)
            await asyncio.shield(manager.tasks[record["id"]])
            return manager.get(record["id"])["results"]
        except ValueError as e:
            raise HTTPException(422, str(e))
        except BusyError as e:
            raise HTTPException(409, str(e))

    @app.get("/api/scenarios")
    def scenarios():
        return SCENARIO_CATALOG

    @app.post("/api/runs", status_code=202)
    async def start_run(body: Run):
        try:
            return await manager.start(body.name, body.count)
        except ValueError as e:
            raise HTTPException(422, str(e))
        except BusyError as e:
            raise HTTPException(409, str(e))

    @app.get("/api/runs/{run_id}")
    def read_run(run_id: str):
        try:
            return manager.get(run_id)
        except KeyError as e:
            raise HTTPException(404, str(e))

    @app.post("/api/runs/{run_id}/cancel")
    async def cancel_run(run_id: str):
        try:
            return await manager.cancel(run_id)
        except KeyError as e:
            raise HTTPException(404, str(e))

    @app.get("/api/runs/{run_id}/report")
    def report(run_id: str, format: Literal["json", "html"] = "html"):
        import json

        try:
            result = manager.get(run_id)["results"]
        except KeyError as e:
            raise HTTPException(404, str(e))
        body = (
            html_report(result)
            if format == "html"
            else json.dumps(public_result(result), indent=2)
        )
        return Response(
            body,
            media_type="text/html" if format == "html" else "application/json",
            headers={
                "Content-Disposition": f'attachment; filename="experiment-{run_id}.{format}"'
            },
        )

    @app.get("/api/experiments")
    def experiments():
        with factory() as db:
            return [
                {
                    "id": e.id,
                    "name": e.name,
                    "state": e.state,
                    "created_at": e.created_at.isoformat(),
                    "results": e.results,
                }
                for e in db.scalars(
                    select(Experiment).order_by(Experiment.created_at.desc()).limit(30)
                )
            ]

    @app.post("/api/contract")
    def contract(body: dict):
        return validate_telemetry(body.get("resource", {}), body.get("attributes", {}))

    app.mount(
        "/docs-guide", StaticFiles(directory=ROOT / "docs", html=True), name="guide"
    )
    return app


def app_factory():
    return create_app()

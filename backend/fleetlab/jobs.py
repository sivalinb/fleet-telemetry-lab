"""Single-worker experiment coordination with persisted state and cancellation."""

import asyncio
from uuid import uuid4
from sqlalchemy import select
from .models import Experiment
from .runs import TERMINAL, save_run, run_record, validate_run
from .isolation import ISOLATED, run_isolated
from .telemetry import run_experiment


class BusyError(Exception):
    pass


class ExperimentManager:
    def __init__(self, factory):
        self.factory = factory
        self.lock = asyncio.Lock()
        self.tasks = {}
        # This lab explicitly supports one API process. A restart interrupts old jobs.
        with factory.begin() as db:
            for run in db.scalars(
                select(Experiment).where(Experiment.state.in_(["queued", "running"]))
            ):
                run.state = "interrupted"
                run.results = {
                    **run.results,
                    "state": "interrupted",
                    "passed": False,
                    "phase": "API restarted",
                    "errors": [
                        *run.results.get("errors", []),
                        "The API restarted before this run completed; no success is inferred.",
                    ],
                }

    def get(self, run_id):
        with self.factory() as db:
            item = db.get(Experiment, run_id)
            if item is None:
                raise KeyError("Experiment not found")
            return run_record(item)

    async def dispatch(self, name, count, run_id):
        function = run_isolated if name in ISOLATED else run_experiment
        return await function(self.factory, name, count, run_id=run_id)

    async def execute(self, name, count, run_id):
        async with asyncio.timeout(90) as deadline:
            result = await self.dispatch(name, count, run_id)
        if deadline.expired():
            result.update(state="failed", passed=False)
            result.setdefault("errors", []).append(
                "Experiment exceeded its 90-second execution limit."
            )
            save_run(self.factory, result, "Execution deadline exceeded")
        return result

    def finished(self, run_id, task):
        record = self.get(run_id)["results"]
        if task.cancelled() and record.get("state") not in TERMINAL:
            record.update(state="cancelled", passed=False)
            save_run(self.factory, record, "Cancelled before execution")
        elif not task.cancelled() and task.exception() is not None:
            record.update(state="failed", passed=False)
            record.setdefault("errors", []).append(
                type(task.exception()).__name__ + ": experiment execution failed"
            )
            save_run(self.factory, record, "Execution failed")
        self.tasks.pop(run_id, None)
        self.lock.release()

    async def start(self, name, count):
        validate_run(name, count)
        if self.lock.locked():
            raise BusyError(
                "An experiment is running. Wait or cancel it before starting another."
            )
        await self.lock.acquire()
        run_id = uuid4().hex
        try:
            save_run(
                self.factory,
                {
                    "id": run_id,
                    "name": name,
                    "state": "queued",
                    "requested": count,
                    "completed": 0,
                    "samples": [],
                    "errors": [],
                },
                "Queued",
            )
            task = asyncio.create_task(self.execute(name, count, run_id))
            self.tasks[run_id] = task
            task.add_done_callback(lambda done: self.finished(run_id, done))
        except BaseException:
            self.lock.release()
            raise
        return self.get(run_id)

    async def cancel(self, run_id):
        self.get(run_id)  # A nonexistent ID must not report success.
        task = self.tasks.get(run_id)
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        return self.get(run_id)

    async def close(self):
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

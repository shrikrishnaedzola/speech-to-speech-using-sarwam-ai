"""Connects the shared post-call report module (../report_module) to this tester.

- report_service: builds reports from this tester's database (via the Sarvam adapter)
- schedule_report(call_id): generate in the background, then tell the UI "report ready"

Called when complete_form succeeds and when a call (live or simulated) ends.
"""

import asyncio

from fastapi.concurrency import run_in_threadpool
from loguru import logger
from report_module.adapters.base import SAMPLE_DATA_DIR, first_of, json_file_adapter
from report_module.adapters.sarvam import sarvam_adapter
from report_module.service import ReportService

from app.config import BACKEND_DIR
from app.db import engine
from app.services.events import bus

DATA_DIR = BACKEND_DIR / "data"
RECORDINGS_DIR = DATA_DIR / "recordings"  # agent audio, dummy test calls only (git-ignored)
SCENARIOS_DIR = DATA_DIR / "scenarios"  # optional expected scripts: <call_id>.json

report_service = ReportService(
    # This tester's calls first; then the 4 fake sample calls (/report/sample-openai-01 etc.)
    adapter=first_of(
        sarvam_adapter(engine, recordings_dir=RECORDINGS_DIR, scripts_dir=SCENARIOS_DIR),
        json_file_adapter(SAMPLE_DATA_DIR),
    ),
    engine=engine,
    settings_path=DATA_DIR / "report_settings.json",
)

_tasks: set[asyncio.Task] = set()


async def _generate(call_id: str, reason: str):
    try:
        report = await run_in_threadpool(report_service.generate, call_id)
        if report is not None:
            bus.publish(call_id, "report_ready", {"url": f"/report/{call_id}", "reason": reason,
                                                  "score": report.summary.overall_score,
                                                  "verdict": report.summary.verdict})
    except Exception as e:  # a report problem must never break the call
        logger.exception(f"Report generation failed for {call_id}")
        bus.publish(call_id, "error", {"message": f"Report generation failed: {e}"})


def schedule_report(call_id: str, reason: str):
    """Generate the report in the background (needs a running event loop)."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return  # no event loop (e.g. a plain script): the tester can POST /report instead
    task = loop.create_task(_generate(call_id, reason))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)

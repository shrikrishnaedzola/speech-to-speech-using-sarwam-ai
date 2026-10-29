"""ReportService: the object a tester app creates once and uses everywhere.

    service = ReportService(adapter=my_adapter, engine=my_engine, settings_path="data/report_settings.json")
    app.include_router(make_report_router(service))      # the API
    service.generate(call_id)                            # e.g. when a call ends

`adapter` is a function call_id -> CallData (or None if the call does not exist).
"""

import re
from collections.abc import Callable
from pathlib import Path

from sqlalchemy.engine import Engine

from report_module.report_builder import build_report
from report_module.schema import CallData, Ratings, Report
from report_module.settings import load_settings, save_settings
from report_module.storage import ReportStore

Adapter = Callable[[str], CallData | None]


class ReportService:
    def __init__(self, adapter: Adapter, engine: Engine, settings_path: str | Path):
        self.adapter = adapter
        self.store = ReportStore(engine)
        self.settings_path = Path(settings_path)

    # --- settings -------------------------------------------------------
    def settings(self) -> dict:
        return load_settings(self.settings_path)

    def update_settings(self, new: dict) -> dict:
        return save_settings(self.settings_path, new)

    # --- reports --------------------------------------------------------
    def generate(self, call_id: str, with_ai_summary: bool = True) -> Report | None:
        """Build (or rebuild) the report for a call and store it. None if the call is unknown."""
        data = self.adapter(call_id)
        if data is None:
            return None
        report = build_report(data, self.store.get_ratings(call_id), self.settings(), with_ai_summary=with_ai_summary)
        self.store.save_report(report)
        return report

    def get(self, call_id: str) -> Report | None:
        return self.store.get_report(call_id)

    def save_ratings(self, call_id: str, ratings: Ratings):
        self.store.save_ratings(call_id, ratings)

    def get_ratings(self, call_id: str) -> Ratings:
        return self.store.get_ratings(call_id) or Ratings()


def export_filename(report: Report, extension: str) -> str:
    """report_{provider}_{model}_{language}_{date}_{call_id}.{ext}, safe for every OS."""
    call = report.call
    parts = [call.provider, call.model, call.language_selected, call.started_at.strftime("%Y-%m-%d"), call.call_id]
    safe = "_".join(re.sub(r"[^A-Za-z0-9.-]+", "-", p).strip("-") for p in parts)
    return f"report_{safe}.{extension}"

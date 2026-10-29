"""Helpers shared by the adapters (tester database -> CallData)."""

from datetime import datetime, timezone
from pathlib import Path

from report_module.schema import CallData, ExpectedScript


def as_utc(value) -> datetime | None:
    """SQLite drops time zones; tester apps store UTC. Accepts datetime or ISO text."""
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def seconds_since(start: datetime, moment) -> float | None:
    moment = as_utc(moment)
    return round((moment - start).total_seconds(), 2) if moment else None


def load_expected_script(folder: str | Path | None, call_id: str) -> ExpectedScript | None:
    """Optional test scenario for a call: <folder>/<call_id>.json in the ExpectedScript shape."""
    if not folder:
        return None
    path = Path(folder) / f"{call_id}.json"
    return ExpectedScript.model_validate_json(path.read_text(encoding="utf-8")) if path.exists() else None


SAMPLE_DATA_DIR = Path(__file__).resolve().parent.parent / "sample_data"


def first_of(*adapters):
    """Combine adapters: use the first one that knows the call id.

    Example: first_of(sarvam_adapter(engine), json_file_adapter(SAMPLE_DATA_DIR))
    lets a tester also open the sample reports (/report/sample-openai-01 ...).
    """

    def adapter(call_id: str) -> CallData | None:
        for a in adapters:
            data = a(call_id)
            if data is not None:
                return data
        return None

    return adapter


def json_file_adapter(folder: str | Path):
    """Adapter for testers that export CallData JSON files (<folder>/<call_id>.json).

    Also used for the sample data: json_file_adapter(".../sample_data") with ids like "sarvam".
    """
    folder = Path(folder)

    def adapter(call_id: str) -> CallData | None:
        path = folder / f"{call_id}.json"
        if not path.exists():
            return None
        return CallData.model_validate_json(path.read_text(encoding="utf-8"))

    return adapter

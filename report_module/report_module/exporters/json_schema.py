"""JSON export + the fixed JSON schema the comparison tool imports.

Every provider's report has exactly the same shape (schema_version "1.0").
Regenerate the schema file after changing schema.py:
    python -m report_module.exporters.json_schema
"""

import json
from pathlib import Path

from report_module.schema import Report

SCHEMA_FILE = Path(__file__).resolve().parent.parent / "report.schema.json"


def to_json(report: Report) -> str:
    return report.model_dump_json(indent=2)


def report_json_schema() -> dict:
    schema = Report.model_json_schema()
    schema["$id"] = "https://edzola.com/zolabs/voice-tester/report.schema.json"
    schema["title"] = "Zolabs voice tester post-call report"
    return schema


if __name__ == "__main__":
    SCHEMA_FILE.write_text(json.dumps(report_json_schema(), indent=2), encoding="utf-8")
    print(f"wrote {SCHEMA_FILE}")

"""Two small tables the report module adds to each tester's SQLite database.

- report_ratings: the tester's 1-5 voice ratings for a call
- reports:        the latest generated report JSON for a call

They use their own MetaData, so the tester's own tables are never touched.
"""

from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, MetaData, String, Table, select
from sqlalchemy.engine import Engine

from report_module.schema import Ratings, Report

metadata = MetaData()

ratings_table = Table(
    "report_ratings", metadata,
    Column("call_id", String(64), primary_key=True),
    Column("ratings", JSON, nullable=False),
    Column("updated_at", DateTime(timezone=True)),
)

reports_table = Table(
    "reports", metadata,
    Column("call_id", String(64), primary_key=True),
    Column("report", JSON, nullable=False),
    Column("generated_at", DateTime(timezone=True)),
)


class ReportStore:
    def __init__(self, engine: Engine):
        self.engine = engine
        metadata.create_all(engine)

    def _upsert(self, table: Table, call_id: str, values: dict):
        with self.engine.begin() as conn:
            exists = conn.execute(select(table.c.call_id).where(table.c.call_id == call_id)).first()
            if exists:
                conn.execute(table.update().where(table.c.call_id == call_id).values(**values))
            else:
                conn.execute(table.insert().values(call_id=call_id, **values))

    def get_ratings(self, call_id: str) -> Ratings | None:
        with self.engine.connect() as conn:
            row = conn.execute(select(ratings_table.c.ratings).where(ratings_table.c.call_id == call_id)).first()
        return Ratings.model_validate(row[0]) if row else None

    def save_ratings(self, call_id: str, ratings: Ratings):
        self._upsert(ratings_table, call_id, {"ratings": ratings.model_dump(), "updated_at": datetime.now(timezone.utc)})

    def get_report(self, call_id: str) -> Report | None:
        with self.engine.connect() as conn:
            row = conn.execute(select(reports_table.c.report).where(reports_table.c.call_id == call_id)).first()
        return Report.model_validate(row[0]) if row else None

    def save_report(self, report: Report):
        self._upsert(reports_table, report.call.call_id,
                     {"report": report.model_dump(mode="json"), "generated_at": report.generated_at})

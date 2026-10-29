"""FastAPI endpoints for reports. Mount in any tester app:

    app.include_router(make_report_router(service))

POST /api/calls/{call_id}/report                    generate / regenerate
GET  /api/calls/{call_id}/report                    report JSON (404 if not generated yet)
GET  /api/calls/{call_id}/ratings                   tester ratings
POST /api/calls/{call_id}/ratings                   save tester 1-5 ratings
GET  /api/calls/{call_id}/report/export?format=pdf|md|json
GET  /api/report/settings, PUT /api/report/settings weights, rates, options
GET  /api/report/schema                             JSON schema of the report (for the comparison tool)
"""

from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

from report_module.schema import Ratings
from report_module.service import ReportService, export_filename


def make_report_router(service: ReportService) -> APIRouter:
    router = APIRouter()

    @router.post("/api/calls/{call_id}/report")
    async def generate(call_id: str):
        # Runs in a thread: the optional AI summary and MOS scorer can take a few seconds.
        report = await run_in_threadpool(service.generate, call_id)
        if report is None:
            raise HTTPException(404, "Call not found")
        return report.model_dump(mode="json")

    @router.get("/api/calls/{call_id}/report")
    def get_report(call_id: str):
        report = service.get(call_id)
        if report is None:
            raise HTTPException(404, "Report not generated yet")
        return report.model_dump(mode="json")

    @router.get("/api/calls/{call_id}/ratings")
    def get_ratings(call_id: str):
        return service.get_ratings(call_id).model_dump()

    @router.post("/api/calls/{call_id}/ratings")
    def save_ratings(call_id: str, ratings: Ratings):
        service.save_ratings(call_id, ratings)
        return ratings.model_dump()

    @router.get("/api/calls/{call_id}/report/export")
    def export(call_id: str, format: str = Query("json", pattern="^(pdf|md|json)$")):
        report = service.get(call_id)
        if report is None:
            raise HTTPException(404, "Report not generated yet")
        if format == "pdf":
            from report_module.exporters.pdf import to_pdf

            body, media = to_pdf(report), "application/pdf"
        elif format == "md":
            from report_module.exporters.markdown import to_markdown

            body, media = to_markdown(report).encode("utf-8"), "text/markdown; charset=utf-8"
        else:
            from report_module.exporters.json_schema import to_json

            body, media = to_json(report).encode("utf-8"), "application/json"
        name = export_filename(report, format)
        return Response(body, media_type=media, headers={"Content-Disposition": f'attachment; filename="{name}"'})

    @router.get("/api/report/settings")
    def get_settings():
        return service.settings()

    @router.put("/api/report/settings")
    def put_settings(new: dict):
        return service.update_settings(new)

    @router.get("/api/report/schema")
    def schema():
        from report_module.exporters.json_schema import report_json_schema

        return report_json_schema()

    return router

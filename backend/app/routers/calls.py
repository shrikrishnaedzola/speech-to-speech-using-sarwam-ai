"""Call results.

GET  /api/calls                          recent calls
GET  /api/calls/{id}                     answers, metrics, transcript
POST /api/calls/{id}/review              tester Correct/Wrong marks
GET  /api/calls/{id}/export?format=json|csv[&section=turns]
WS   /api/calls/{id}/events              live events for the UI
"""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Call, Review, utcnow
from app.schemas import ReviewRequest
from app.services.events import bus
from app.services.export import to_csv, to_json
from app.services.report import build_report
from app.services.tools import form_state

router = APIRouter(prefix="/api")


@router.get("/calls")
def list_calls(limit: int = 20, db: Session = Depends(get_db)):
    calls = db.scalars(select(Call).order_by(Call.started_at.desc()).limit(limit)).all()
    return [
        {"call_id": c.id, "form_id": c.form_id, "mode": c.mode, "status": c.status,
         "started_at": c.started_at.isoformat(), "form_completed": c.form_completed}
        for c in calls
    ]


@router.get("/calls/{call_id}")
def get_call(call_id: str, db: Session = Depends(get_db)):
    report = build_report(db, call_id)
    if report is None:
        raise HTTPException(404, "Call not found")
    return report


@router.post("/calls/{call_id}/review")
async def save_review(call_id: str, body: ReviewRequest, db: Session = Depends(get_db)):
    if db.get(Call, call_id) is None:
        raise HTTPException(404, "Call not found")
    for item in body.reviews:
        row = db.scalars(select(Review).where(Review.call_id == call_id, Review.field_id == item.field_id)).first()
        if item.verdict is None:
            if row:
                db.delete(row)
            continue
        if row is None:
            row = Review(call_id=call_id, field_id=item.field_id, verdict=item.verdict)
            db.add(row)
        row.verdict, row.expected_value, row.updated_at = item.verdict, item.expected_value, utcnow()
    db.commit()
    state = form_state(db, call_id)
    bus.publish(call_id, "form_state", state)
    return state


@router.get("/calls/{call_id}/export")
def export_call(
    call_id: str,
    format: str = Query("json", pattern="^(json|csv)$"),
    section: str = Query("fields", pattern="^(fields|turns)$"),
    db: Session = Depends(get_db),
):
    report = build_report(db, call_id)
    if report is None:
        raise HTTPException(404, "Call not found")
    if format == "csv":
        name = f"sarvam_test_{call_id}_{section}.csv"
        # utf-8-sig adds a BOM so Excel shows Hindi/Tamil/Telugu text correctly.
        return Response(to_csv(report, section).encode("utf-8-sig"), media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})
    return Response(to_json(report), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="sarvam_test_{call_id}.json"'})


@router.websocket("/calls/{call_id}/events")
async def call_events(websocket: WebSocket, call_id: str):
    await websocket.accept()
    queue = bus.subscribe(call_id)
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=20)
            except asyncio.TimeoutError:
                event = {"type": "ping", "data": {}}  # keeps proxies from closing the socket
            await websocket.send_json(event)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        bus.unsubscribe(call_id, queue)

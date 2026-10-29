"""Start / end calls.

POST /api/session                 create a call, return connection details
POST /api/webrtc/offer?call_id=   WebRTC offer -> answer (starts the pipeline)
POST /api/session/{id}/end        stop a running call
POST /api/simulate                start a Simulate-mode call (no mic, no Sarvam)
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.config import ICE_SERVERS, has_api_key
from app.db import get_db
from app.models import Call, Form
from app.schemas import SessionRequest, SimulateRequest
from app.services.events import bus
from app.services.simulate import start_simulation
from app.services.tools import form_state

router = APIRouter(prefix="/api")

# Live calls need pipecat, which is left out of the slim Vercel build (serverless
# cannot hold a WebRTC session anyway). Import it on first use.
_webrtc_handler = None


def _live_unavailable() -> HTTPException:
    return HTTPException(503, "Live calls are not available on this deployment. Use Simulate mode.")


def get_webrtc_handler():
    global _webrtc_handler
    if _webrtc_handler is None:
        try:
            from pipecat.transports.smallwebrtc.connection import IceServer
            from pipecat.transports.smallwebrtc.request_handler import SmallWebRTCRequestHandler
        except ImportError:
            raise _live_unavailable()
        _webrtc_handler = SmallWebRTCRequestHandler(ice_servers=[IceServer(urls=ICE_SERVERS)])
    return _webrtc_handler


async def close_webrtc_handler():
    if _webrtc_handler is not None:
        await _webrtc_handler.close()


def _create_call(db: Session, form_id: str, settings: dict, mode: str) -> Call:
    if db.get(Form, form_id) is None:
        raise HTTPException(404, "Form not found")
    call = Call(id=uuid.uuid4().hex[:12], form_id=form_id, mode=mode, status="connecting", settings=settings,
                transcript=[], errors=[])
    db.add(call)
    db.commit()
    return call


@router.post("/session")
async def create_session(body: SessionRequest, db: Session = Depends(get_db)):
    if not has_api_key():
        raise HTTPException(400, "SARVAM_API_KEY is not set in backend/.env. Use Simulate mode or add the key.")
    call = _create_call(db, body.form_id, body.settings.model_dump(), "live")
    bus.publish(call.id, "status", {"status": "connecting"})
    bus.publish(call.id, "form_state", form_state(db, call.id))
    return {
        "call_id": call.id,
        "webrtc_offer_url": f"/api/webrtc/offer?call_id={call.id}",
        "ice_servers": ICE_SERVERS,
        "events_url": f"/api/calls/{call.id}/events",
    }


@router.post("/webrtc/offer")
async def webrtc_offer(request: Request, call_id: str = Query(...), db: Session = Depends(get_db)):
    """Browser sends its SDP offer; we answer and start the voice pipeline for this call."""
    handler = get_webrtc_handler()
    from pipecat.transports.smallwebrtc.request_handler import SmallWebRTCRequest

    from app.pipeline.runner import start_call_task

    call = db.get(Call, call_id)
    if call is None or call.mode != "live":
        raise HTTPException(404, "Call not found")
    body = await request.json()
    offer = SmallWebRTCRequest(sdp=body["sdp"], type=body["type"], pc_id=body.get("pc_id"))

    async def on_connection(connection):
        start_call_task(connection, call_id)

    return await handler.handle_web_request(offer, on_connection)


@router.post("/session/{call_id}/end")
async def end_session(call_id: str):
    try:
        from app.pipeline.runner import end_call
    except ImportError:
        raise _live_unavailable()
    stopped = await end_call(call_id)
    return {"stopped": stopped}


@router.post("/simulate")
async def simulate(body: SimulateRequest, db: Session = Depends(get_db)):
    call = _create_call(db, body.form_id, body.settings.model_dump(), "simulate")
    bus.publish(call.id, "form_state", form_state(db, call.id))
    start_simulation(call.id, body.speed)
    return {"call_id": call.id, "events_url": f"/api/calls/{call.id}/events"}

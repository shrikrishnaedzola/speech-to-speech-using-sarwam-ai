"""POST /api/tools/{tool_name} - run a tool call outside the voice pipeline.

Same code path as the live LLM tool calls (services/tools.py). Used by
Simulate mode, tests, and for manual checks with curl.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Call
from app.schemas import ToolRequest
from app.services.tools import TOOL_NAMES, handle_tool_call

router = APIRouter(prefix="/api")


@router.post("/tools/{tool_name}")
async def run_tool(tool_name: str, body: ToolRequest, db: Session = Depends(get_db)):
    if tool_name not in TOOL_NAMES:
        raise HTTPException(404, f"Unknown tool. Valid tools: {', '.join(TOOL_NAMES)}")
    if db.get(Call, body.call_id) is None:
        raise HTTPException(404, "Call not found")
    return handle_tool_call(db, body.call_id, tool_name, body.arguments)

"""Read models for the dashboard and flight recorder. Writes still go through voice tools."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.api.patients import fail, get_db, ok
from app.db.models import CallLog
from app.realtime.hub import hub
from app.services.sessions import active_calls, get_session, list_events, recent_calls

router = APIRouter(tags=["calls"])


def _session_dict(session, db: Session) -> dict:
    log = db.get(CallLog, session.call_id)
    return {
        "call_id": session.call_id,
        "caller_number": session.caller_number,
        "status": session.status,
        "patient_id": session.patient_id,
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "ended_at": session.ended_at.isoformat() if session.ended_at else None,
        "language": session.language,
        "registering_for_other": session.registering_for_other,
        "relationship": session.relationship,
        "draft": session.draft_json,
        "summary": log.summary if log else None,
        "duration_seconds": log.duration_seconds if log else None,
    }


@router.get("/calls")
def calls(db: Session = Depends(get_db)) -> JSONResponse:
    return ok([_session_dict(row, db) for row in recent_calls(db)])


@router.get("/calls/active")
def calls_active(db: Session = Depends(get_db)) -> JSONResponse:
    return ok([_session_dict(row, db) for row in active_calls(db)])


@router.get("/calls/{call_id}")
def call_detail(call_id: str, db: Session = Depends(get_db)) -> JSONResponse:
    row = get_session(db, call_id)
    if row is None:
        return fail(404, "NOT_FOUND", "Call not found.")
    events = [
        {"id": event.id, "ts": event.ts.isoformat(), "type": event.type, "payload": event.payload_json}
        for event in list_events(db, call_id)
    ]
    log = db.get(CallLog, call_id)
    body = _session_dict(row, db)
    body["events"] = events
    body["transcript"] = log.transcript_json if log else None
    return ok(body)


@router.get("/events")
async def events() -> StreamingResponse:
    queue = hub.subscribe()

    async def stream():
        try:
            for event in list(hub.recent):
                yield f"data: {json.dumps(event, default=str)}\n\n"
            while True:
                event = await queue.get()
                yield f"data: {json.dumps(event, default=str)}\n\n"
        finally:
            hub.unsubscribe(queue)

    return StreamingResponse(stream(), media_type="text/event-stream")


# Imported so the route module has a named async dependency for tests that inspect it.
_ = asyncio

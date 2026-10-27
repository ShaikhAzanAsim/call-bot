"""Vapi webhook routes. Parsing stays in the adapter; rules stay in the tools."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.session import get_session_factory
from app.services.sessions import cached_tool_result, finish_call, start_call, store_tool_result
from app.voice.assistant import assistant_payload
from app.voice.tools import dispatch_tool
from app.voice.vapi_adapter import (
    authorized,
    call_id_of,
    caller_number_of,
    duration_of,
    ended_reason_of,
    message_type,
    summary_of,
    tool_calls_of,
    tool_results_response,
    transcript_of,
)

logger = logging.getLogger("voice")
router = APIRouter(prefix="/voice", tags=["voice"])


def _db() -> Session:
    return get_session_factory()()


@router.post("/webhook")
async def vapi_webhook(request: Request, token: str | None = None) -> JSONResponse:
    settings = get_settings()
    if not authorized(dict(request.headers), token, settings):
        logger.warning("rejected voice webhook: missing or wrong secret")
        return JSONResponse(status_code=401, content={"error": "unauthorized"})
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "bad json"})
    if not isinstance(payload, dict):
        return JSONResponse(status_code=400, content={"error": "bad json"})

    kind = message_type(payload)
    if kind == "assistant-request":
        return JSONResponse(content=_assistant_request(payload, settings))
    if kind == "tool-calls":
        return JSONResponse(content=_tool_calls(payload, settings))
    if kind in {"end-of-call-report", "status-update", "hang"}:
        _lifecycle(payload, settings, kind)
        return JSONResponse(content={"ok": True})
    return JSONResponse(content={"ok": True})


def _assistant_request(payload: dict, settings: Settings) -> dict:
    db = _db()
    try:
        _session, context = start_call(db, call_id_of(payload), caller_number_of(payload), settings)
        return assistant_payload(settings, context)
    finally:
        db.close()


def _tool_calls(payload: dict, settings: Settings) -> dict:
    db = _db()
    try:
        call_id = call_id_of(payload)
        caller = caller_number_of(payload)
        session, _context = start_call(db, call_id, caller, settings)
        results = []
        for call in tool_calls_of(payload):
            cached = cached_tool_result(session, call["id"])
            if cached is not None:
                results.append((call["id"], cached))
                continue
            result = dispatch_tool(db, call_id, caller, settings, call["name"], call["arguments"])
            session = db.get(type(session), call_id) or session
            store_tool_result(session, call["id"], result)
            db.commit()
            results.append((call["id"], result))
            logger.info(
                "tool %s call=%s ok=%s",
                call["name"],
                call_id,
                result.get("ok"),
            )
        return tool_results_response(results)
    finally:
        db.close()


def _lifecycle(payload: dict, settings: Settings, kind: str) -> None:
    message_status = ""
    message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
    if kind == "status-update":
        message_status = str(message.get("status") or "")
        if message_status not in {"ended", "in-progress"}:
            return
        if message_status == "in-progress":
            db = _db()
            try:
                start_call(db, call_id_of(payload), caller_number_of(payload), settings)
            finally:
                db.close()
            return
    db = _db()
    try:
        report = finish_call(
            db,
            call_id_of(payload),
            transcript=transcript_of(payload),
            summary=summary_of(payload),
            duration_seconds=duration_of(payload),
            ended_reason=ended_reason_of(payload) or message_status or kind,
        )
    finally:
        db.close()
    print(json.dumps(report, default=str), flush=True)
    logger.info("call_ended %s", report.get("call_id"))

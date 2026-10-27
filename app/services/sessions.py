"""Call drafts, resume, and the flight-recorder event log."""

from __future__ import annotations

import re
from copy import deepcopy
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.config import Settings
from app.db.models import CallEvent, CallLog, CallSession, utcnow
from app.services.readback import collected_summary, missing_required
from app.services.validation import REQUIRED_FIELDS

RESUMABLE = ("in_progress", "abandoned")


def empty_draft() -> dict:
    return {
        "fields": {},
        "meta": {
            "confirmed": False,
            "readback_done": False,
            "mode": "create",
            "update_patient_id": None,
            "failures": {},
            "saved_patient_id": None,
            "save_attempts": 0,
            "simulate_db_failure": False,
            "resumed_from": None,
            "ignore_duplicate": False,
            "tool_cache": {},
        },
    }


def caller_digits(number: str | None) -> str | None:
    if not number:
        return None
    digits = re.sub(r"\D", "", number)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits or None


def _touch(session: CallSession) -> None:
    flag_modified(session, "draft_json")


def add_event(db: Session, call_id: str, event_type: str, payload: dict) -> None:
    db.add(CallEvent(call_id=call_id, ts=utcnow(), type=event_type, payload_json=payload))


def get_session(db: Session, call_id: str) -> CallSession | None:
    return db.get(CallSession, call_id)


def find_resumable(db: Session, caller_number: str | None, settings: Settings, exclude: str | None = None) -> CallSession | None:
    digits = caller_digits(caller_number)
    if not digits:
        return None
    cutoff = utcnow() - timedelta(hours=settings.draft_resume_hours)
    rows = db.scalars(
        select(CallSession)
        .where(CallSession.caller_number == digits, CallSession.status.in_(RESUMABLE))
        .order_by(CallSession.started_at.desc())
    ).all()
    for row in rows:
        if exclude and row.call_id == exclude:
            continue
        started = row.started_at
        if started.tzinfo is None:
            started = started.replace(tzinfo=cutoff.tzinfo)
        if started < cutoff:
            if row.status != "abandoned":
                row.status = "abandoned"
                row.ended_at = row.ended_at or utcnow()
            continue
        fields = (row.draft_json or {}).get("fields") or {}
        saved = (row.draft_json or {}).get("meta", {}).get("saved_patient_id")
        if fields and not saved:
            return row
    return None


def start_call(db: Session, call_id: str, caller_number: str | None, settings: Settings) -> tuple[CallSession, dict]:
    existing = get_session(db, call_id)
    if existing is not None:
        return existing, _caller_context(db, existing, settings)

    digits = caller_digits(caller_number)
    draft = empty_draft()
    prior = find_resumable(db, digits, settings, exclude=call_id)
    if prior is not None:
        draft["fields"] = deepcopy(prior.draft_json.get("fields") or {})
        draft["meta"]["resumed_from"] = prior.call_id
        draft["meta"]["readback_done"] = False
        draft["meta"]["confirmed"] = False
        if prior.status == "in_progress":
            prior.status = "abandoned"
            prior.ended_at = utcnow()

    session = CallSession(
        call_id=call_id,
        caller_number=digits,
        status="in_progress",
        draft_json=draft,
        patient_id=None,
        started_at=utcnow(),
        ended_at=None,
        language="English",
        registering_for_other=False,
        relationship=None,
    )
    db.add(session)
    add_event(db, call_id, "call_started", {"caller_number": digits, "resumed_from": draft["meta"]["resumed_from"]})
    db.commit()
    db.refresh(session)
    return session, _caller_context(db, session, settings)


def _caller_context(db: Session, session: CallSession, settings: Settings) -> dict:
    from app.services.patients import find_by_phone

    fields = session.draft_json.get("fields") or {}
    existing = find_by_phone(db, session.caller_number) if session.caller_number else None
    context = {
        "caller_number": session.caller_number,
        "existing_patient": None,
        "resume": None,
        "greeting": (
            "Thanks for calling. I'm the virtual intake assistant. "
            "I'll get you registered; it takes about three minutes. Who am I registering today?"
        ),
    }
    if existing is not None:
        context["existing_patient"] = {
            "patient_id": existing.patient_id,
            "first_name": existing.first_name,
            "last_initial": existing.last_name[:1],
        }
        context["greeting"] = f"Hi, is this {existing.first_name}? Welcome back."
    if session.draft_json.get("meta", {}).get("resumed_from") and fields:
        missing = missing_required(fields)
        nxt = missing[0].replace("_", " ") if missing else "a quick confirmation"
        context["resume"] = {
            "collected": collected_summary(fields),
            "next": nxt,
        }
        context["greeting"] = (
            f"Welcome back. You'd given me your {collected_summary(fields)}. "
            f"Shall we continue from your {nxt}?"
        )
    return context


def invalidate_confirmation(session: CallSession) -> None:
    meta = session.draft_json.setdefault("meta", {})
    meta["confirmed"] = False
    meta["readback_done"] = False
    _touch(session)


def mark_readback(session: CallSession) -> None:
    fields = session.draft_json.get("fields") or {}
    meta = session.draft_json.setdefault("meta", {})
    if not missing_required(fields):
        meta["readback_done"] = True
    _touch(session)


def cached_tool_result(session: CallSession, tool_call_id: str | None) -> dict | None:
    if not tool_call_id:
        return None
    return session.draft_json.get("meta", {}).get("tool_cache", {}).get(tool_call_id)


def store_tool_result(session: CallSession, tool_call_id: str | None, result: dict) -> None:
    if not tool_call_id:
        return
    meta = session.draft_json.setdefault("meta", {})
    cache = meta.setdefault("tool_cache", {})
    cache[tool_call_id] = result
    # Keep the row small if Vapi retries a long call.
    if len(cache) > 40:
        for key in list(cache)[:-40]:
            cache.pop(key, None)
    _touch(session)


def finish_call(
    db: Session,
    call_id: str,
    *,
    transcript: list | dict | str | None,
    summary: str | None,
    duration_seconds: int | None,
    ended_reason: str | None,
) -> dict:
    session = get_session(db, call_id)
    if session is None:
        session, _ = start_call(db, call_id, None, _fallback_settings())
    meta = session.draft_json.get("meta") or {}
    saved_id = meta.get("saved_patient_id")
    if session.status == "in_progress":
        if saved_id:
            session.status = "completed"
        elif meta.get("save_attempts", 0) >= 2 or (ended_reason and "error" in ended_reason.lower()):
            session.status = "failed"
        else:
            session.status = "abandoned"
    session.ended_at = utcnow()
    if saved_id:
        session.patient_id = saved_id
    fields = session.draft_json.get("fields") or {}
    if not summary:
        if saved_id:
            summary = f"Registration completed for {fields.get('first_name', 'the patient')}."
        elif session.status == "failed":
            summary = "Registration could not be saved. The draft was kept for staff follow-up."
        else:
            summary = f"Call ended before save. Collected: {collected_summary(fields)}."
    log = db.get(CallLog, call_id)
    if log is None:
        log = CallLog(
            call_id=call_id,
            transcript_json={"text": transcript} if isinstance(transcript, str) else transcript,
            summary=summary,
            patient_id=saved_id,
            duration_seconds=duration_seconds,
            created_at=utcnow(),
        )
        db.add(log)
    else:
        log.transcript_json = {"text": transcript} if isinstance(transcript, str) else transcript
        log.summary = summary
        log.patient_id = saved_id
        log.duration_seconds = duration_seconds
    add_event(db, call_id, "call_ended", {"status": session.status, "ended_reason": ended_reason})
    db.commit()
    payload = {
        "event": "call_completed" if session.status == "completed" else "call_ended",
        "call_id": call_id,
        "status": session.status,
        "patient_id": saved_id,
        "duration_seconds": duration_seconds,
        "summary": summary,
        "payload": fields,
        "relationship": session.relationship,
        "language": session.language,
    }
    return payload


def _fallback_settings() -> Settings:
    from app.config import get_settings

    return get_settings()


def list_events(db: Session, call_id: str) -> list[CallEvent]:
    return list(
        db.scalars(select(CallEvent).where(CallEvent.call_id == call_id).order_by(CallEvent.id.asc())).all()
    )


def recent_calls(db: Session, limit: int = 20) -> list[CallSession]:
    return list(db.scalars(select(CallSession).order_by(CallSession.started_at.desc()).limit(limit)).all())


def active_calls(db: Session) -> list[CallSession]:
    return list(
        db.scalars(
            select(CallSession).where(CallSession.status == "in_progress").order_by(CallSession.started_at.desc())
        ).all()
    )

"""Tool implementations. They call the service layer and never touch SQL themselves."""

from __future__ import annotations

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.config import Settings
from app.db.models import utcnow
from app.realtime.hub import hub
from app.services.address import check_address
from app.services.patients import (
    StorageError,
    create_patient,
    find_by_phone,
    get_patient,
    patient_to_dict,
    update_patient,
)
from app.services.readback import collected_summary, missing_required, readback_script, speak_value
from app.services.sessions import (
    add_event,
    invalidate_confirmation,
    mark_readback,
    start_call,
)
from app.services.validation import OPTIONAL_FIELDS, REQUIRED_FIELDS, canonical_field, validate_field

SKIP_WORDS = {
    "skip", "no", "nope", "none", "nothing", "no thanks", "nah",
    "i don't have one", "dont have one", "don't have one", "i dont have one",
}


def _say_failure(reason: str, step: int, optional: bool) -> str:
    if step <= 1:
        return reason
    if step == 2:
        return f"{reason} Let's try it in smaller pieces."
    if optional:
        return f"{reason} We can skip this one if you want."
    return f"{reason} We can come back to it. Let's keep going and return to this before I save."


def _save(db: Session, session) -> None:
    flag_modified(session, "draft_json")
    db.commit()


def _publish(call_id: str, event_type: str, payload: dict) -> None:
    hub.publish({"type": event_type, "call_id": call_id, "ts": utcnow().isoformat(), **payload})


def _session(db: Session, call_id: str, caller_number: str | None, settings: Settings):
    session, _context = start_call(db, call_id, caller_number, settings)
    return session


def lookup_caller(db: Session, call_id: str, caller_number: str | None, settings: Settings) -> dict:
    session = _session(db, call_id, caller_number, settings)
    from app.services.sessions import _caller_context

    context = _caller_context(db, session, settings)
    existing = context.get("existing_patient")
    resume = context.get("resume")
    return {
        "ok": True,
        "say": context["greeting"],
        "caller_number": context.get("caller_number"),
        "existing_patient": existing,
        "resume": resume,
        "masked": True,
    }


def record_field(
    db: Session,
    call_id: str,
    caller_number: str | None,
    settings: Settings,
    field: str,
    spoken_value: str,
) -> dict:
    session = _session(db, call_id, caller_number, settings)
    name = canonical_field(field)
    if name is None:
        return {"ok": False, "say": f"I can't store {field}.", "reason": "unknown field"}

    spoken = "" if spoken_value is None else str(spoken_value).strip()
    optional = name in OPTIONAL_FIELDS
    if optional and spoken.lower() in SKIP_WORDS:
        session.draft_json["fields"].pop(name, None)
        invalidate_confirmation(session)
        add_event(db, call_id, "field_recorded", {"field": name, "skipped": True})
        _save(db, session)
        _publish(call_id, "field_recorded", {"field": name, "ok": True, "skipped": True})
        return {"ok": True, "skipped": True, "field": name, "say": "Okay, we'll skip that."}

    verdict = validate_field(name, spoken)
    meta = session.draft_json.setdefault("meta", {})
    failures = meta.setdefault("failures", {})
    if not verdict.ok:
        failures[name] = int(failures.get(name, 0)) + 1
        step = min(failures[name], 3)
        reason = verdict.reason or "That didn't look right."
        say = _say_failure(reason, step, optional)
        add_event(
            db,
            call_id,
            "validation_failed",
            {"field": name, "reason": reason, "repair_step": step, "spoken": spoken[:120]},
        )
        add_event(db, call_id, "repair_strategy", {"field": name, "repair_step": step})
        _save(db, session)
        _publish(call_id, "validation_failed", {"field": name, "ok": False, "reason": reason, "repair_step": step})
        return {
            "ok": False,
            "field": name,
            "reason": reason,
            "repair_step": step,
            "repair_hint": say,
            "say": say,
        }

    session.draft_json["fields"][name] = verdict.value
    failures[name] = 0
    invalidate_confirmation(session)
    if name == "preferred_language" and verdict.value:
        session.language = verdict.value
    add_event(db, call_id, "field_recorded", {"field": name, "value": verdict.value})
    result = {
        "ok": True,
        "field": name,
        "normalized_value": verdict.value,
        "say": f"Got it. {speak_value(name, verdict.value)}.",
    }
    if name == "phone_number" and verdict.value and not meta.get("ignore_duplicate"):
        existing = find_by_phone(db, verdict.value)
        current_target = meta.get("update_patient_id")
        if existing is not None and existing.patient_id != current_target:
            result["existing_patient"] = {
                "patient_id": existing.patient_id,
                "first_name": existing.first_name,
                "last_name": existing.last_name,
            }
            result["say"] = (
                f"It looks like we already have a record for {existing.first_name} {existing.last_name}. "
                "Would you like to update that information instead?"
            )
    _save(db, session)
    _publish(call_id, "field_recorded", {"field": name, "ok": True, "value": verdict.value, "repair_step": None})
    return result


def get_draft(db: Session, call_id: str, caller_number: str | None, settings: Settings) -> dict:
    session = _session(db, call_id, caller_number, settings)
    fields = session.draft_json.get("fields") or {}
    missing = missing_required(fields)
    mark_readback(session)
    _save(db, session)
    script = readback_script(fields) if not missing else ""
    nxt = missing[0] if missing else None
    if missing:
        say = f"I still need the {nxt.replace('_', ' ')}."
    else:
        say = script
    return {
        "ok": True,
        "collected": fields,
        "missing_required": missing,
        "ready_to_confirm": not missing,
        "readback": script,
        "say": say,
    }


def reset_draft(
    db: Session,
    call_id: str,
    caller_number: str | None,
    settings: Settings,
    scope: str,
    field: str | None = None,
) -> dict:
    session = _session(db, call_id, caller_number, settings)
    scope_name = (scope or "").strip().lower()
    if scope_name == "all":
        kept_failure_flag = session.draft_json.get("meta", {}).get("simulate_db_failure", False)
        session.draft_json["fields"] = {}
        meta = session.draft_json["meta"]
        meta.update(
            {
                "confirmed": False,
                "readback_done": False,
                "mode": "create",
                "update_patient_id": None,
                "failures": {},
                "saved_patient_id": None,
                "ignore_duplicate": False,
                "simulate_db_failure": kept_failure_flag,
            }
        )
        session.registering_for_other = False
        session.relationship = None
        add_event(db, call_id, "draft_reset", {"scope": "all"})
        _save(db, session)
        _publish(call_id, "draft_reset", {"scope": "all"})
        return {"ok": True, "say": "No problem. Let's start fresh. Who am I registering?"}
    if scope_name == "field":
        name = canonical_field(field or "")
        if name is None:
            return {"ok": False, "say": "Tell me which detail to clear."}
        session.draft_json["fields"].pop(name, None)
        invalidate_confirmation(session)
        add_event(db, call_id, "draft_reset", {"scope": "field", "field": name})
        _save(db, session)
        _publish(call_id, "draft_reset", {"scope": "field", "field": name})
        return {"ok": True, "field": name, "say": f"Okay, let's redo the {name.replace('_', ' ')}."}
    return {"ok": False, "say": "I can start over completely, or clear one field."}


def set_proxy_registration(
    db: Session,
    call_id: str,
    caller_number: str | None,
    settings: Settings,
    relationship: str,
) -> dict:
    session = _session(db, call_id, caller_number, settings)
    relation = (relationship or "").strip()[:50] or "someone else"
    session.registering_for_other = True
    session.relationship = relation
    session.draft_json["fields"] = {}
    invalidate_confirmation(session)
    add_event(db, call_id, "proxy_set", {"relationship": relation})
    _save(db, session)
    _publish(call_id, "proxy_set", {"relationship": relation})
    return {
        "ok": True,
        "relationship": relation,
        "say": f"Of course. I'll register your {relation}. What is their first name?",
    }


def confirm_registration(db: Session, call_id: str, caller_number: str | None, settings: Settings) -> dict:
    session = _session(db, call_id, caller_number, settings)
    fields = session.draft_json.get("fields") or {}
    missing = missing_required(fields)
    meta = session.draft_json.setdefault("meta", {})
    if missing:
        return {"ok": False, "say": f"I still need the {missing[0].replace('_', ' ')} before confirming."}
    if not meta.get("readback_done"):
        return {"ok": False, "say": "Read every field back, then ask if it is correct, before confirming."}
    meta["confirmed"] = True
    add_event(db, call_id, "confirm", {"fields": list(fields)})
    _save(db, session)
    return {"ok": True, "say": "Confirmed. Saving now."}


def save_patient(db: Session, call_id: str, caller_number: str | None, settings: Settings) -> dict:
    session = _session(db, call_id, caller_number, settings)
    meta = session.draft_json.setdefault("meta", {})
    fields = dict(session.draft_json.get("fields") or {})
    if meta.get("saved_patient_id"):
        patient = get_patient(db, meta["saved_patient_id"])
        first = fields.get("first_name") or (patient.first_name if patient else "there")
        return {
            "ok": True,
            "idempotent": True,
            "patient_id": meta["saved_patient_id"],
            "say": f"You're all set, {first}.",
        }
    missing = missing_required(fields)
    if missing:
        return {"ok": False, "say": f"I still need the {missing[0].replace('_', ' ')} before I can save."}
    if not meta.get("confirmed"):
        return {
            "ok": False,
            "say": "I need to read everything back and hear a clear yes before I save.",
        }
    fields.setdefault("preferred_language", session.language or "English")
    force = bool(meta.get("simulate_db_failure")) or settings.simulate_db_write_failure
    add_event(db, call_id, "save_attempt", {"mode": meta.get("mode"), "force_failure": force})
    try:
        if force:
            raise StorageError("simulated database write failure")
        if meta.get("mode") == "update" and meta.get("update_patient_id"):
            patient = update_patient(
                db,
                meta["update_patient_id"],
                fields,
                settings=settings,
                already_clean=True,
            )
            if patient is None:
                raise StorageError("patient to update was not found")
        else:
            patient = create_patient(db, fields, settings=settings, already_clean=True)
    except StorageError as exc:
        attempts = int(meta.get("save_attempts", 0)) + 1
        meta["save_attempts"] = attempts
        add_event(db, call_id, "save_failed", {"attempt": attempts, "error": str(exc)})
        _publish(call_id, "save_failed", {"attempt": attempts})
        if attempts >= 2:
            session.status = "failed"
            _save(db, session)
            return {
                "ok": False,
                "attempt": attempts,
                "draft_retained": True,
                "say": (
                    "I'm sorry, I still can't save this. I've kept everything you told me "
                    "for a staff member to finish. You're welcome to call back."
                ),
            }
        _save(db, session)
        return {
            "ok": False,
            "attempt": attempts,
            "draft_retained": True,
            "retry": True,
            "say": "I'm sorry, I couldn't save that just now. I'll try once more.",
        }
    except Exception as exc:  # unexpected write error, still spoken
        attempts = int(meta.get("save_attempts", 0)) + 1
        meta["save_attempts"] = attempts
        add_event(db, call_id, "tool_error", {"error": type(exc).__name__, "attempt": attempts})
        _save(db, session)
        if attempts >= 2:
            session.status = "failed"
            _save(db, session)
            return {
                "ok": False,
                "draft_retained": True,
                "say": (
                    "I'm sorry, saving failed again. I've held onto your information for a staff member."
                ),
            }
        return {
            "ok": False,
            "retry": True,
            "draft_retained": True,
            "say": "Something went wrong saving that. I'll try once more.",
        }

    meta["saved_patient_id"] = patient.patient_id
    meta["save_attempts"] = 0
    session.patient_id = patient.patient_id
    add_event(db, call_id, "save_success", {"patient_id": patient.patient_id})
    _save(db, session)
    _publish(
        call_id,
        "save_success",
        {"patient_id": patient.patient_id, "patient": patient_to_dict(patient)},
    )
    return {
        "ok": True,
        "patient_id": patient.patient_id,
        "say": f"You're all set, {patient.first_name}.",
    }


def find_existing_by_phone(
    db: Session,
    call_id: str,
    caller_number: str | None,
    settings: Settings,
    phone: str,
) -> dict:
    _session(db, call_id, caller_number, settings)
    existing = find_by_phone(db, phone)
    if existing is None:
        return {"ok": True, "found": False, "say": "I don't see an existing record for that number."}
    return {
        "ok": True,
        "found": True,
        "patient_id": existing.patient_id,
        "first_name": existing.first_name,
        "last_name": existing.last_name,
        "say": (
            f"It looks like we already have a record for {existing.first_name} {existing.last_name}. "
            "Would you like to update your information instead?"
        ),
    }


def choose_duplicate_action(
    db: Session,
    call_id: str,
    caller_number: str | None,
    settings: Settings,
    action: str,
    patient_id: str | None = None,
) -> dict:
    session = _session(db, call_id, caller_number, settings)
    choice = (action or "").strip().lower()
    meta = session.draft_json.setdefault("meta", {})
    if choice in {"update", "yes"}:
        target = patient_id or (meta.get("update_patient_id"))
        if target is None:
            phone = session.draft_json.get("fields", {}).get("phone_number") or session.caller_number
            existing = find_by_phone(db, phone) if phone else None
            target = existing.patient_id if existing else None
        patient = get_patient(db, target) if target else None
        if patient is None:
            return {"ok": False, "say": "I couldn't open that existing record. We can continue a new registration."}
        prefill = patient_to_dict(patient)
        kept = {
            key: prefill[key]
            for key in list(REQUIRED_FIELDS) + list(OPTIONAL_FIELDS)
            if prefill.get(key)
        }
        # Keep anything the caller already said on this call.
        kept.update({key: value for key, value in session.draft_json.get("fields", {}).items() if value})
        session.draft_json["fields"] = kept
        meta["mode"] = "update"
        meta["update_patient_id"] = patient.patient_id
        meta["confirmed"] = False
        meta["readback_done"] = False
        _save(db, session)
        return {
            "ok": True,
            "mode": "update",
            "patient_id": patient.patient_id,
            "say": f"We'll update {patient.first_name}'s record. What should I change?",
        }
    meta["mode"] = "create"
    meta["ignore_duplicate"] = True
    meta["update_patient_id"] = None
    _save(db, session)
    return {"ok": True, "mode": "create", "say": "Okay. I'll create a separate registration."}


def check_address_tool(
    db: Session,
    call_id: str,
    caller_number: str | None,
    settings: Settings,
    line1: str,
    city: str,
    state: str,
    zip_code: str,
) -> dict:
    session = _session(db, call_id, caller_number, settings)
    result = check_address(line1, city, state, zip_code, settings)
    add_event(db, call_id, "address_check", {"ok": result.get("ok"), "source": result.get("source"), "say": result.get("say")})
    _save(db, session)
    _publish(call_id, "address_check", {"ok": result.get("ok"), "source": result.get("source"), "say": result.get("say")})
    result.setdefault("ok", False)
    return result


def end_call(db: Session, call_id: str, caller_number: str | None, settings: Settings) -> dict:
    session = _session(db, call_id, caller_number, settings)
    add_event(db, call_id, "end_requested", {})
    _save(db, session)
    first = (session.draft_json.get("fields") or {}).get("first_name")
    goodbye = f"You're all set, {first}. Thanks for calling. Goodbye." if first else "Thanks for calling. Goodbye."
    return {"ok": True, "say": goodbye, "end_call": True}


def arm_db_failure(db: Session, call_id: str, caller_number: str | None, settings: Settings) -> dict:
    """Test and eval hook. Refused in production."""
    if settings.is_production:
        return {"ok": False, "say": "That action isn't available."}
    session = _session(db, call_id, caller_number, settings)
    session.draft_json.setdefault("meta", {})["simulate_db_failure"] = True
    _save(db, session)
    return {"ok": True, "say": "The next save will fail on purpose."}


TOOL_HANDLERS = {
    "lookup_caller": lambda db, call_id, caller, settings, args: lookup_caller(db, call_id, caller, settings),
    "record_field": lambda db, call_id, caller, settings, args: record_field(
        db, call_id, caller, settings, args.get("field", ""), args.get("spoken_value", "")
    ),
    "check_address": lambda db, call_id, caller, settings, args: check_address_tool(
        db,
        call_id,
        caller,
        settings,
        args.get("line1") or args.get("address_line_1") or "",
        args.get("city") or "",
        args.get("state") or "",
        args.get("zip") or args.get("zip_code") or "",
    ),
    "get_draft": lambda db, call_id, caller, settings, args: get_draft(db, call_id, caller, settings),
    "reset_draft": lambda db, call_id, caller, settings, args: reset_draft(
        db, call_id, caller, settings, args.get("scope", ""), args.get("field")
    ),
    "set_proxy_registration": lambda db, call_id, caller, settings, args: set_proxy_registration(
        db, call_id, caller, settings, args.get("relationship", "")
    ),
    "confirm_registration": lambda db, call_id, caller, settings, args: confirm_registration(
        db, call_id, caller, settings
    ),
    "save_patient": lambda db, call_id, caller, settings, args: save_patient(db, call_id, caller, settings),
    "find_existing_by_phone": lambda db, call_id, caller, settings, args: find_existing_by_phone(
        db, call_id, caller, settings, args.get("phone") or args.get("phone_number") or ""
    ),
    "choose_duplicate_action": lambda db, call_id, caller, settings, args: choose_duplicate_action(
        db, call_id, caller, settings, args.get("action", ""), args.get("patient_id")
    ),
    "end_call": lambda db, call_id, caller, settings, args: end_call(db, call_id, caller, settings),
    "arm_db_failure": lambda db, call_id, caller, settings, args: arm_db_failure(db, call_id, caller, settings),
}


def dispatch_tool(
    db: Session,
    call_id: str,
    caller_number: str | None,
    settings: Settings,
    name: str,
    arguments: dict,
) -> dict:
    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        return {"ok": False, "say": "I can't do that from this call. Let's keep going with registration."}
    try:
        return handler(db, call_id, caller_number, settings, arguments or {})
    except Exception as exc:
        add_event(db, call_id, "tool_error", {"tool": name, "error": type(exc).__name__})
        db.commit()
        return {"ok": False, "say": "Something went wrong on my side. Let's try that once more."}

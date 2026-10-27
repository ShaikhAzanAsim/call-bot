"""Deterministic checks. Soft scores, when an LLM key is present, are labeled separately."""

from __future__ import annotations

from app.voice.assistant import assistant_payload


def expect_ok(result: dict, expect: dict) -> list[str]:
    notes = []
    for key, wanted in expect.items():
        if key == "contains":
            blob = f"{result.get('say', '')} {result.get('reason', '')}".lower()
            if str(wanted).lower() not in blob:
                notes.append(f"expected text {wanted!r} in {blob!r}")
            continue
        actual = result.get(key)
        if actual != wanted:
            notes.append(f"{key}: expected {wanted!r}, got {actual!r}")
    return notes


def score_scenario(scenario: dict, session, patient: dict | None, results: list[dict], settings) -> dict:
    notes: list[str] = []
    checks = scenario.get("checks") or []
    fields = (session.draft_json or {}).get("fields", {}) if session is not None else {}
    meta = (session.draft_json or {}).get("meta", {}) if session is not None else {}
    ground = scenario.get("ground_truth") or {}

    if "saved" in checks and not meta.get("saved_patient_id"):
        notes.append("registration was not saved")
    if "not_saved" in checks and meta.get("saved_patient_id"):
        notes.append("a patient was saved and should not have been")
    if "matches_ground_truth" in checks:
        if patient is None:
            notes.append("no patient row to compare")
        else:
            for key, wanted in ground.items():
                if patient.get(key) != wanted:
                    notes.append(f"{key}: saved {patient.get(key)!r}, ground truth {wanted!r}")
    if "no_save_before_confirm" in checks:
        confirmed = False
        for item in results:
            if item["tool"] == "confirm_registration" and item["result"].get("ok"):
                confirmed = True
            if item["tool"] == "save_patient" and item["result"].get("ok") and not confirmed:
                notes.append("save_patient succeeded before confirm_registration")
    if "reprompted_date_of_birth" in checks:
        failures = [item for item in results if item["tool"] == "record_field" and item["result"].get("field") == "date_of_birth" and not item["result"].get("ok")]
        if not failures:
            notes.append("date of birth was never rejected")
    if "reprompted_phone_number" in checks:
        failures = [item for item in results if item["tool"] == "record_field" and item["result"].get("field") == "phone_number" and not item["result"].get("ok")]
        if len(failures) < 2:
            notes.append("phone number was not re-prompted")
    if "repair_escalated" in checks:
        steps = [item["result"].get("repair_step") for item in results if item["result"].get("repair_step")]
        if steps != [1, 2, 3]:
            notes.append(f"repair steps were {steps}, expected 1 then 2 then 3")
    if "corrections_applied" in checks:
        writes = [
            item for item in results
            if item["tool"] == "record_field"
            and item["args"].get("field") == "last_name"
            and item["result"].get("ok")
        ]
        if len(writes) < 3:
            notes.append("expected three last-name writes")
        elif patient and patient.get("last_name") != ground.get("last_name"):
            notes.append("final last name does not match the last correction")
    if "updated_not_duplicated" in checks:
        if patient is None:
            notes.append("update did not return a patient")
        elif patient.get("city") != ground.get("city"):
            notes.append(f"city is {patient.get('city')!r}")
    if "resumed_fields" in checks:
        prior = (scenario.get("prior_call") or {}).get("fields") or {}
        for key, value in prior.items():
            if fields.get(key) != value:
                notes.append(f"resume missing {key}")
        say = " ".join(item["result"].get("say", "") for item in results if item["tool"] == "lookup_caller")
        if "continue" not in say.lower() and "given" not in say.lower() and "welcome back" not in say.lower():
            notes.append("lookup did not offer to resume")
    if "abandoned" in checks and (session is None or session.status != "abandoned"):
        notes.append(f"status is {getattr(session, 'status', None)}")
    if "save_failed_twice" in checks:
        saves = [item for item in results if item["tool"] == "save_patient"]
        if len(saves) < 2 or any(item["result"].get("ok") for item in saves):
            notes.append("expected two failed saves")
        elif "staff" not in (saves[-1]["result"].get("say") or "").lower():
            notes.append("the second failure did not mention staff follow-up")
    if "draft_retained" in checks and fields.get("first_name") != "Nora":
        notes.append("draft was not retained")
    if "email_empty" in checks and patient and patient.get("email"):
        notes.append("email should be empty")
    if "proxy_not_on_patient" in checks:
        if session is None or session.relationship != "mother":
            notes.append("relationship was not stored on the call")
        if patient and "relationship" in patient:
            notes.append("relationship leaked onto the patient record")
    if "silence_contract" in checks:
        assistant = assistant_payload(settings, {"greeting": "hello"}).get("assistant") or {}
        if assistant.get("silenceTimeoutSeconds", 0) < 10:
            notes.append("assistant has no silence timeout")

    for item in results:
        notes.extend(f"step {item['index']} {item['tool']}: {note}" for note in item.get("notes") or [])

    return {
        "id": scenario["id"],
        "description": scenario.get("description", ""),
        "passed": not notes,
        "turns": len(results),
        "notes": notes,
    }

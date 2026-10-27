from patient_samples import VALID_PATIENT


def _tool(client, call_id, name, arguments, tool_id="t1"):
    response = client.post(
        "/voice/webhook",
        headers={"X-Vapi-Secret": "test-secret"},
        json={
            "message": {
                "type": "tool-calls",
                "call": {"id": call_id, "customer": {"number": "+12065550142"}},
                "toolCallList": [
                    {
                        "id": tool_id,
                        "type": "function",
                        "function": {"name": name, "arguments": arguments},
                    }
                ],
            }
        },
    )
    assert response.status_code == 200, response.text
    import json

    return json.loads(response.json()["results"][0]["result"])


def _register(client, call_id, phone="2065550142"):
    fields = {
        "first_name": "Maria",
        "last_name": "Lopez",
        "date_of_birth": "March fifth, nineteen ninety-two",
        "sex": "woman",
        "phone_number": phone,
        "address_line_1": "410 Pike Street",
        "city": "Seattle",
        "state": "Washington",
        "zip_code": "nine eight one oh one",
    }
    for index, (field, spoken) in enumerate(fields.items(), start=1):
        result = _tool(client, call_id, "record_field", {"field": field, "spoken_value": spoken}, f"f{index}")
        assert result["ok"], result
    draft = _tool(client, call_id, "get_draft", {}, "draft")
    assert draft["ready_to_confirm"]
    confirmed = _tool(client, call_id, "confirm_registration", {}, "yes")
    assert confirmed["ok"]
    return _tool(client, call_id, "save_patient", {}, "save")


def test_webhook_rejects_missing_secret(client):
    response = client.post("/voice/webhook", json={"message": {"type": "status-update", "status": "ringing"}})
    assert response.status_code == 401


def test_record_failure_then_save(client):
    bad = _tool(
        client,
        "call-1",
        "record_field",
        {"field": "date_of_birth", "spoken_value": "March 5, 2030"},
        "dob-bad",
    )
    assert bad["ok"] is False
    assert bad["repair_step"] == 1
    assert "future" in bad["reason"].lower()
    saved = _register(client, "call-1")
    assert saved["ok"] is True
    patient_id = saved["patient_id"]
    listed = client.get("/patients", params={"last_name": "Lopez"})
    assert listed.json()["data"][0]["patient_id"] == patient_id

    again = _tool(client, "call-1", "save_patient", {}, "save-again")
    assert again["idempotent"] is True
    assert again["patient_id"] == patient_id
    assert len(client.get("/patients").json()["data"]) == 1


def test_save_blocked_until_yes(client):
    fields = {
        "first_name": "Mia",
        "last_name": "Cole",
        "date_of_birth": "01/02/1991",
        "sex": "female",
        "phone_number": "5035550133",
        "address_line_1": "1 Main Street",
        "city": "Portland",
        "state": "OR",
        "zip_code": "97201",
    }
    for index, (field, spoken) in enumerate(fields.items(), start=1):
        assert _tool(client, "call-gate", "record_field", {"field": field, "spoken_value": spoken}, f"g{index}")["ok"]
    assert _tool(client, "call-gate", "get_draft", {}, "gd")["ready_to_confirm"]
    blocked = _tool(client, "call-gate", "save_patient", {}, "early")
    assert blocked["ok"] is False
    assert "yes" in blocked["say"].lower() or "read" in blocked["say"].lower()


def test_save_failure_keeps_draft(client):
    _register_fields = _tool
    call_id = "call-fail"
    for index, (field, spoken) in enumerate(
        {
            "first_name": "Nora",
            "last_name": "Kim",
            "date_of_birth": "01/02/1991",
            "sex": "female",
            "phone_number": "4155550166",
            "address_line_1": "1 Market Street",
            "city": "San Francisco",
            "state": "CA",
            "zip_code": "94105",
        }.items(),
        start=1,
    ):
        assert _register_fields(client, call_id, "record_field", {"field": field, "spoken_value": spoken}, f"p{index}")["ok"]
    assert _tool(client, call_id, "get_draft", {}, "d")["ready_to_confirm"]
    assert _tool(client, call_id, "confirm_registration", {}, "c")["ok"]
    assert _tool(client, call_id, "arm_db_failure", {}, "arm")["ok"]
    first = _tool(client, call_id, "save_patient", {}, "s1")
    assert first["ok"] is False
    assert first["retry"] is True
    second = _tool(client, call_id, "save_patient", {}, "s2")
    assert second["ok"] is False
    assert "staff" in second["say"].lower()
    assert client.get("/patients", params={"last_name": "Kim"}).json()["data"] == []
    detail = client.get(f"/calls/{call_id}").json()["data"]
    assert detail["draft"]["fields"]["first_name"] == "Nora"
    assert detail["status"] == "failed"


def test_resume_after_drop(client):
    _tool(client, "drop-1", "record_field", {"field": "first_name", "spoken_value": "Ada"}, "a")
    _tool(client, "drop-1", "record_field", {"field": "last_name", "spoken_value": "Lovelace"}, "b")
    ended = client.post(
        "/voice/webhook",
        headers={"X-Vapi-Secret": "test-secret"},
        json={
            "message": {
                "type": "end-of-call-report",
                "endedReason": "customer-ended-call",
                "call": {"id": "drop-1", "customer": {"number": "+12065550142"}},
                "artifact": {"transcript": "AI: name? User: Ada Lovelace"},
            }
        },
    )
    assert ended.status_code == 200
    lookup = _tool(client, "drop-2", "lookup_caller", {}, "look")
    assert lookup["resume"]["collected"]
    draft = _tool(client, "drop-2", "get_draft", {}, "back")
    assert draft["collected"]["first_name"] == "Ada"
    assert "last_name" not in draft["missing_required"]


def test_duplicate_phone_offers_update(client):
    created = client.post("/patients", json=VALID_PATIENT)
    assert created.status_code == 201
    heard = _tool(
        client,
        "dup-1",
        "record_field",
        {"field": "phone_number", "spoken_value": "2065550142"},
        "phone",
    )
    assert heard["existing_patient"]["first_name"] == "Maria"
    choice = _tool(
        client,
        "dup-1",
        "choose_duplicate_action",
        {"action": "update", "patient_id": heard["existing_patient"]["patient_id"]},
        "upd",
    )
    assert choice["mode"] == "update"


def test_start_over_and_proxy(client):
    _tool(client, "reset-1", "record_field", {"field": "first_name", "spoken_value": "Sam"}, "s")
    cleared = _tool(client, "reset-1", "reset_draft", {"scope": "all"}, "r")
    assert cleared["ok"]
    draft = _tool(client, "reset-1", "get_draft", {}, "g")
    assert draft["collected"] == {}
    proxy = _tool(client, "reset-1", "set_proxy_registration", {"relationship": "mother"}, "p")
    assert proxy["ok"]
    detail = client.get("/calls/reset-1").json()["data"]
    assert detail["relationship"] == "mother"
    assert detail["registering_for_other"] is True

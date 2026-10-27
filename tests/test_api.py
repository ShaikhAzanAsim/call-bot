from datetime import datetime, timezone

from patient_samples import VALID_PATIENT


def test_health_and_envelope(client):
    health = client.get("/health")
    assert health.status_code == 200
    body = health.json()
    assert body["error"] is None
    assert body["data"]["database"] == "ok"
    assert client.get("/").json()["data"]["dashboard"] == "/dashboard"


def test_create_get_list_update_delete(client, monkeypatch):
    stamps = [
        datetime(2020, 1, 1, tzinfo=timezone.utc),
        datetime(2020, 1, 2, tzinfo=timezone.utc),
    ]

    def fake_now():
        return stamps.pop(0) if stamps else datetime(2020, 1, 3, tzinfo=timezone.utc)

    monkeypatch.setattr("app.services.patients.utcnow", fake_now)
    created = client.post("/patients", json=VALID_PATIENT)
    assert created.status_code == 201
    body = created.json()
    assert body["error"] is None
    patient = body["data"]
    assert patient["patient_id"]
    assert patient["date_of_birth"] == "03/05/1992"
    assert patient["phone_number"] == "2065550142"
    patient_id = patient["patient_id"]

    fetched = client.get(f"/patients/{patient_id}")
    assert fetched.status_code == 200
    assert fetched.json()["data"]["last_name"] == "Lopez"

    listed = client.get("/patients", params={"last_name": "lopez", "date_of_birth": "03/05/1992"})
    assert listed.status_code == 200
    assert len(listed.json()["data"]) == 1

    by_phone = client.get("/patients", params={"phone_number": "(206) 555-0142"})
    assert len(by_phone.json()["data"]) == 1

    updated = client.put(f"/patients/{patient_id}", json={"city": "Tacoma"})
    assert updated.status_code == 200
    assert updated.json()["data"]["city"] == "Tacoma"
    assert updated.json()["data"]["last_name"] == "Lopez"
    assert updated.json()["data"]["updated_at"] != patient["updated_at"]

    removed = client.delete(f"/patients/{patient_id}")
    assert removed.status_code == 200
    assert removed.json()["data"]["deleted_at"]
    assert client.get(f"/patients/{patient_id}").status_code == 404
    assert client.get("/patients").json()["data"] == []

    again = client.post("/patients", json=VALID_PATIENT)
    assert again.status_code == 201


def test_status_codes(client, monkeypatch):
    assert client.get("/patients/not-a-uuid").status_code == 400
    missing = "00000000-0000-4000-8000-000000000000"
    assert client.get(f"/patients/{missing}").status_code == 404
    assert client.get("/patients", params={"date_of_birth": "March 5"}).status_code == 400
    assert client.get("/patients", params={"phone_number": "123"}).status_code == 400

    bad = client.post("/patients", json={"first_name": "Maria"})
    assert bad.status_code == 422
    assert bad.json()["data"] is None
    assert "last_name" in bad.json()["error"]["fields"]

    invalid = dict(VALID_PATIENT)
    invalid["date_of_birth"] = "02/30/1992"
    rejected = client.post("/patients", json=invalid)
    assert rejected.status_code == 422
    assert "date_of_birth" in rejected.json()["error"]["fields"]

    not_json = client.post("/patients", content=b"nope", headers={"content-type": "application/json"})
    assert not_json.status_code == 400

    def boom(*_args, **_kwargs):
        raise RuntimeError("db down secret")

    monkeypatch.setattr("app.api.patients.list_patients", boom)
    crashed = client.get("/patients")
    assert crashed.status_code == 500
    text = crashed.text
    assert "db down" not in text
    assert crashed.json()["error"]["code"] == "INTERNAL_ERROR"

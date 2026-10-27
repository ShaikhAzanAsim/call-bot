"""Hit a running server: health, create, get, list, update, delete.

Usage: python scripts/smoke_test.py https://your-host.example
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")
PATIENT = {
    "first_name": "Smoke",
    "last_name": "Test",
    "date_of_birth": "01/15/1990",
    "sex": "Other",
    "phone_number": "2065550198",
    "address_line_1": "1 Test Street",
    "city": "Seattle",
    "state": "WA",
    "zip_code": "98101",
}


def request(method: str, path: str, body: dict | None = None, ok: tuple[int, ...] = (200,)) -> dict:
    data = None if body is None else json.dumps(body).encode()
    headers = {"content-type": "application/json"} if data else {}
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            status = response.status
            payload = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        status = exc.code
        payload = json.loads(exc.read().decode())
    if status not in ok:
        raise SystemExit(f"FAIL {method} {path} -> {status} {payload}")
    if "data" not in payload or "error" not in payload:
        raise SystemExit(f"FAIL {method} {path} missing envelope")
    print(f"PASS {method} {path} -> {status}")
    return payload


def main() -> None:
    request("GET", "/health")
    created = request("POST", "/patients", PATIENT, ok=(201,))
    patient_id = created["data"]["patient_id"]
    request("GET", f"/patients/{patient_id}")
    listed = request("GET", "/patients?last_name=Test")
    if not any(row["patient_id"] == patient_id for row in listed["data"]):
        raise SystemExit("FAIL list filter missed the new patient")
    print("PASS GET /patients?last_name=Test")
    request("PUT", f"/patients/{patient_id}", {"city": "Tacoma"})
    request("DELETE", f"/patients/{patient_id}")
    missing = request("GET", f"/patients/{patient_id}", ok=(404,))
    if missing["data"] is not None:
        raise SystemExit("FAIL soft-deleted patient still returned")
    print("PASS soft-deleted patient is hidden")
    print("ALL PASSED")


if __name__ == "__main__":
    main()

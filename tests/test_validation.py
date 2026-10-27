from datetime import date

from app.services.validation import validate_field

TODAY = date(2026, 10, 27)


def test_future_dob_and_implausible_age():
    future = validate_field("date_of_birth", "April 12, 2030", today=TODAY)
    assert not future.ok
    assert "future" in (future.reason or "").lower()
    old = validate_field("date_of_birth", "January 1, 1800", today=TODAY)
    assert not old.ok
    assert "120" in (old.reason or "")


def test_validators_accept_canonical_api_values():
    assert validate_field("state", "WA").value == "WA"
    assert validate_field("sex", "Decline to Answer").value == "Decline to Answer"
    assert validate_field("zip_code", "98101").value == "98101"
    assert validate_field("phone_number", "(206) 555-0142").value == "2065550142"

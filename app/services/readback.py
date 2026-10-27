"""Spoken read-back. Phone numbers are grouped, dates are words, emails are spelled."""

from __future__ import annotations

from datetime import datetime

from app.services.normalization import speak_date, speak_email, speak_phone
from app.services.validation import OPTIONAL_FIELDS, REQUIRED_FIELDS

LABELS = {
    "first_name": "first name",
    "last_name": "last name",
    "date_of_birth": "date of birth",
    "sex": "sex",
    "phone_number": "phone number",
    "email": "email",
    "address_line_1": "street",
    "address_line_2": "apartment",
    "city": "city",
    "state": "state",
    "zip_code": "ZIP code",
    "insurance_provider": "insurance",
    "insurance_member_id": "member ID",
    "preferred_language": "preferred language",
    "emergency_contact_name": "emergency contact",
    "emergency_contact_phone": "emergency phone",
}


def speak_value(field: str, value: str) -> str:
    if field == "date_of_birth":
        born = datetime.strptime(value, "%m/%d/%Y").date()
        return speak_date(born)
    if field in {"phone_number", "emergency_contact_phone"}:
        return speak_phone(value)
    if field == "email":
        return speak_email(value)
    return value


def missing_required(fields: dict) -> list[str]:
    return [name for name in REQUIRED_FIELDS if not fields.get(name)]


def readback_script(fields: dict) -> str:
    parts = []
    ordered = [name for name in REQUIRED_FIELDS + OPTIONAL_FIELDS if fields.get(name)]
    for name in ordered:
        parts.append(f"{LABELS[name]} {speak_value(name, fields[name])}")
    if not parts:
        return "I don't have any details yet."
    joined = ". ".join(parts)
    return f"Here is what I have. {joined}. Is all of that correct?"


def collected_summary(fields: dict) -> str:
    labels = [LABELS[name] for name in REQUIRED_FIELDS + OPTIONAL_FIELDS if fields.get(name)]
    if not labels:
        return "nothing yet"
    if len(labels) == 1:
        return labels[0]
    return ", ".join(labels[:-1]) + f" and {labels[-1]}"

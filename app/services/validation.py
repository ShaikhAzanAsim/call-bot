"""Single source of truth for patient field rules.

The REST API, the voice tools, and the Eval Lab scorer all call this module.
Each field returns a canonical value or a sentence the agent can say aloud.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

from app.db.models import SEX_VALUES, STATE_CODES
from app.services.normalization import (
    parse_address_line,
    parse_city,
    parse_date,
    parse_email,
    parse_free_text,
    parse_language,
    parse_member_id,
    parse_name,
    parse_phone,
    parse_sex,
    parse_state,
    parse_zip,
    sanitize_text,
)

MAX_AGE_YEARS = 120

REQUIRED_FIELDS = (
    "first_name",
    "last_name",
    "date_of_birth",
    "sex",
    "phone_number",
    "address_line_1",
    "city",
    "state",
    "zip_code",
)
OPTIONAL_FIELDS = (
    "email",
    "address_line_2",
    "insurance_provider",
    "insurance_member_id",
    "preferred_language",
    "emergency_contact_name",
    "emergency_contact_phone",
)
ALL_FIELDS = REQUIRED_FIELDS + OPTIONAL_FIELDS

FIELD_ALIASES = {
    "firstname": "first_name",
    "first": "first_name",
    "given_name": "first_name",
    "lastname": "last_name",
    "last": "last_name",
    "surname": "last_name",
    "family_name": "last_name",
    "dob": "date_of_birth",
    "birthday": "date_of_birth",
    "birth_date": "date_of_birth",
    "gender": "sex",
    "phone": "phone_number",
    "mobile": "phone_number",
    "address": "address_line_1",
    "street": "address_line_1",
    "address1": "address_line_1",
    "line1": "address_line_1",
    "address2": "address_line_2",
    "line2": "address_line_2",
    "apt": "address_line_2",
    "apartment": "address_line_2",
    "zip": "zip_code",
    "postal_code": "zip_code",
    "postal": "zip_code",
    "insurance": "insurance_provider",
    "payer": "insurance_provider",
    "member_id": "insurance_member_id",
    "subscriber_id": "insurance_member_id",
    "language": "preferred_language",
    "emergency_name": "emergency_contact_name",
    "emergency_phone": "emergency_contact_phone",
}


class FieldErrors(Exception):
    def __init__(self, fields: dict[str, str]):
        self.fields = fields
        super().__init__("; ".join(f"{key}: {value}" for key, value in fields.items()))


@dataclass
class FieldVerdict:
    ok: bool
    value: str | None = None
    reason: str | None = None
    skipped: bool = False


def canonical_field(name: str) -> str | None:
    key = (name or "").strip().lower().replace(" ", "_").replace("-", "_")
    if key in ALL_FIELDS:
        return key
    return FIELD_ALIASES.get(key)


def _age_years(born: date, today: date) -> int:
    years = today.year - born.year
    if (today.month, today.day) < (born.month, born.day):
        years -= 1
    return years


def validate_date_of_birth(spoken: str, today: date | None = None) -> FieldVerdict:
    today = today or date.today()
    parsed = parse_date(spoken, today=today)
    if parsed.incomplete or not parsed.value:
        return FieldVerdict(ok=False, reason=parsed.reason or "I still need a full date of birth.")
    born = datetime.strptime(parsed.value, "%m/%d/%Y").date()
    if born > today:
        return FieldVerdict(
            ok=False,
            reason="That date is in the future. What is the actual date of birth?",
        )
    if _age_years(born, today) > MAX_AGE_YEARS:
        return FieldVerdict(
            ok=False,
            reason="That would make the patient over 120 years old. Could you repeat the year?",
        )
    return FieldVerdict(ok=True, value=parsed.value)


def validate_field(field: str, spoken: str, today: date | None = None) -> FieldVerdict:
    name = canonical_field(field)
    if name is None:
        return FieldVerdict(ok=False, reason=f"I can't store a field called {field}.")
    text = "" if spoken is None else str(spoken)
    if name == "emergency_contact_name" and not sanitize_text(text, 80):
        return FieldVerdict(ok=True, value=None, skipped=True)
    if name in {"first_name", "last_name", "emergency_contact_name"}:
        parsed = parse_name(text)
        if parsed.value is None:
            return FieldVerdict(ok=False, reason=parsed.reason or "I didn't catch the name.")
        return FieldVerdict(ok=True, value=parsed.value)
    if name == "date_of_birth":
        return validate_date_of_birth(text, today=today)
    if name == "sex":
        parsed = parse_sex(text)
    elif name in {"phone_number", "emergency_contact_phone"}:
        parsed = parse_phone(text)
    elif name == "email":
        if not sanitize_text(text, 160):
            return FieldVerdict(ok=True, value=None, skipped=True)
        parsed = parse_email(text)
    elif name == "address_line_1":
        parsed = parse_address_line(text, required=True)
    elif name == "address_line_2":
        if not sanitize_text(text, 200):
            return FieldVerdict(ok=True, value=None, skipped=True)
        parsed = parse_address_line(text, required=False)
    elif name == "city":
        parsed = parse_city(text)
    elif name == "state":
        parsed = parse_state(text)
    elif name == "zip_code":
        parsed = parse_zip(text)
    elif name == "insurance_provider":
        if not sanitize_text(text, 100):
            return FieldVerdict(ok=True, value=None, skipped=True)
        parsed = parse_free_text(text, 100, "I didn't catch the insurance company.")
    elif name == "insurance_member_id":
        if not sanitize_text(text, 40):
            return FieldVerdict(ok=True, value=None, skipped=True)
        parsed = parse_member_id(text)
    elif name == "preferred_language":
        if not sanitize_text(text, 50):
            return FieldVerdict(ok=True, value="English")
        parsed = parse_language(text)
    else:
        return FieldVerdict(ok=False, reason=f"I can't store a field called {field}.")

    if parsed.value is None and (parsed.reason or parsed.incomplete):
        return FieldVerdict(ok=False, reason=parsed.reason)
    return FieldVerdict(ok=True, value=parsed.value, reason=None)


def _blank(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def normalize_api_record(payload: dict, *, partial: bool, today: date | None = None) -> dict:
    """Validate a REST payload. Raises FieldErrors with a per-field map."""
    errors: dict[str, str] = {}
    cleaned: dict[str, str | None] = {}
    remapped: dict[str, object] = {}
    for key, value in payload.items():
        name = canonical_field(str(key)) if not isinstance(key, str) or key not in ALL_FIELDS else key
        if isinstance(key, str) and key in ALL_FIELDS:
            name = key
        elif isinstance(key, str):
            name = canonical_field(key)
        if name is None:
            continue
        remapped[name] = value

    fields_to_check = list(remapped.keys()) if partial else list(REQUIRED_FIELDS) + [
        name for name in OPTIONAL_FIELDS if name in remapped
    ]
    if not partial:
        for name in REQUIRED_FIELDS:
            if name not in remapped or _blank(remapped.get(name)):
                errors[name] = "This field is required."

    for name in fields_to_check:
        if name in errors:
            continue
        if name not in remapped:
            continue
        raw = remapped[name]
        if _blank(raw):
            if name in REQUIRED_FIELDS:
                errors[name] = "This field is required."
            elif name == "preferred_language":
                cleaned[name] = "English"
            else:
                cleaned[name] = None
            continue
        if not isinstance(raw, str):
            errors[name] = "This field must be text."
            continue
        verdict = validate_field(name, raw, today=today)
        if not verdict.ok:
            errors[name] = verdict.reason or "That value isn't valid."
            continue
        cleaned[name] = verdict.value

    if not partial and "preferred_language" not in cleaned and "preferred_language" not in errors:
        cleaned["preferred_language"] = "English"

    if errors:
        raise FieldErrors(errors)
    return cleaned


def dob_to_date(value: str) -> date:
    return datetime.strptime(value, "%m/%d/%Y").date()


def format_dob(value: date) -> str:
    return value.strftime("%m/%d/%Y")


def is_uuid(value: str) -> bool:
    return re.fullmatch(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
        value or "",
    ) is not None


def parse_query_dob(value: str) -> date:
    """Query filters use a strict MM/DD/YYYY. A real but unmatched date is not an error."""
    text = (value or "").strip()
    if not re.fullmatch(r"\d{2}/\d{2}/\d{4}", text):
        raise ValueError("date_of_birth must be MM/DD/YYYY.")
    try:
        return datetime.strptime(text, "%m/%d/%Y").date()
    except ValueError as exc:
        raise ValueError("date_of_birth is not a real calendar date.") from exc

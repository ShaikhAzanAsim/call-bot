"""Patient REST endpoints. Validation and writes go through app.services.patients."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy.orm import Session

from app.db.session import session_scope
from app.services.normalization import parse_phone
from app.services.patients import (
    create_patient,
    get_patient,
    list_patients,
    patient_to_dict,
    soft_delete_patient,
    update_patient,
)
from app.services.validation import FieldErrors, is_uuid, parse_query_dob

router = APIRouter(prefix="/patients", tags=["patients"])


def get_db() -> Session:
    yield from session_scope()


def ok(data: object, status: int = 200) -> JSONResponse:
    return JSONResponse(status_code=status, content={"data": data, "error": None})


def fail(status: int, code: str, message: str, fields: dict | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"data": None, "error": {"code": code, "message": message, "fields": fields or {}}},
    )


class PatientBody(BaseModel):
    model_config = ConfigDict(extra="allow")
    first_name: str | None = None
    last_name: str | None = None
    date_of_birth: str | None = None
    sex: str | None = None
    phone_number: str | None = None
    email: str | None = None
    address_line_1: str | None = None
    address_line_2: str | None = None
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None
    insurance_provider: str | None = None
    insurance_member_id: str | None = None
    preferred_language: str | None = None
    emergency_contact_name: str | None = None
    emergency_contact_phone: str | None = None


def _provided(model: BaseModel) -> dict:
    return {key: value for key, value in model.model_dump().items() if key in model.model_fields_set}


@router.get("")
def list_patients_route(
    last_name: str | None = None,
    date_of_birth: str | None = None,
    phone_number: str | None = None,
    db: Session = Depends(get_db),
) -> JSONResponse:
    dob = None
    if date_of_birth:
        try:
            dob = parse_query_dob(date_of_birth)
        except ValueError as exc:
            return fail(400, "BAD_REQUEST", str(exc), {"date_of_birth": str(exc)})
    phone = None
    if phone_number:
        parsed = parse_phone(phone_number)
        if not parsed.value:
            return fail(400, "BAD_REQUEST", parsed.reason or "Invalid phone_number.", {"phone_number": parsed.reason or "Invalid phone_number."})
        phone = parsed.value
    rows = list_patients(db, last_name=last_name, date_of_birth=dob, phone_number=phone)
    return ok([patient_to_dict(row) for row in rows])


@router.get("/{patient_id}")
def get_patient_route(patient_id: str, db: Session = Depends(get_db)) -> JSONResponse:
    if not is_uuid(patient_id):
        return fail(400, "BAD_REQUEST", "patient_id must be a UUID.", {"patient_id": "Must be a UUID."})
    patient = get_patient(db, patient_id)
    if patient is None:
        return fail(404, "NOT_FOUND", "Patient not found.")
    return ok(patient_to_dict(patient))


@router.post("", status_code=201)
async def create_patient_route(request: Request, db: Session = Depends(get_db)) -> JSONResponse:
    body, error = await _body(request)
    if error is not None:
        return error
    try:
        patient = create_patient(db, body)
    except FieldErrors as exc:
        return fail(422, "VALIDATION_ERROR", "Some fields are invalid.", exc.fields)
    return ok(patient_to_dict(patient), status=201)


@router.put("/{patient_id}")
async def update_patient_route(patient_id: str, request: Request, db: Session = Depends(get_db)) -> JSONResponse:
    if not is_uuid(patient_id):
        return fail(400, "BAD_REQUEST", "patient_id must be a UUID.", {"patient_id": "Must be a UUID."})
    body, error = await _body(request, partial=True)
    if error is not None:
        return error
    if get_patient(db, patient_id) is None:
        return fail(404, "NOT_FOUND", "Patient not found.")
    try:
        patient = update_patient(db, patient_id, body)
    except FieldErrors as exc:
        return fail(422, "VALIDATION_ERROR", "Some fields are invalid.", exc.fields)
    if patient is None:
        return fail(404, "NOT_FOUND", "Patient not found.")
    return ok(patient_to_dict(patient))


@router.delete("/{patient_id}")
def delete_patient_route(patient_id: str, db: Session = Depends(get_db)) -> JSONResponse:
    if not is_uuid(patient_id):
        return fail(400, "BAD_REQUEST", "patient_id must be a UUID.", {"patient_id": "Must be a UUID."})
    patient = soft_delete_patient(db, patient_id)
    if patient is None:
        return fail(404, "NOT_FOUND", "Patient not found.")
    return ok(patient_to_dict(patient))


async def _body(request: Request, partial: bool = False) -> tuple[dict, JSONResponse | None]:
    try:
        payload = await request.json()
    except Exception:
        return {}, fail(400, "BAD_REQUEST", "Request body must be JSON.")
    if not isinstance(payload, dict):
        return {}, fail(400, "BAD_REQUEST", "Request body must be a JSON object.")
    try:
        model = PatientBody.model_validate(payload)
    except ValidationError as exc:
        fields = {}
        for item in exc.errors():
            loc = ".".join(str(part) for part in item.get("loc", [])) or "body"
            fields[loc] = item.get("msg", "Invalid value.")
        return {}, fail(400, "BAD_REQUEST", "Malformed patient payload.", fields)
    data = model.model_dump(exclude_unset=True) if partial else model.model_dump(exclude_unset=True)
    if not partial:
        # Missing keys must reach the validator so required-field errors are 422s.
        data = {**{name: None for name in PatientBody.model_fields}, **data}
        # Keys the client omitted stay None and are reported as required.
        for key in list(data):
            if key not in payload:
                data[key] = None
    return data, None

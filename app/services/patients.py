"""Patient persistence. Routes and voice tools both call this, never the tables directly."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import Patient, utcnow
from app.services.normalization import parse_phone
from app.services.validation import dob_to_date, format_dob, normalize_api_record


class StorageError(Exception):
    """The database write did not happen. The caller should keep the draft."""


def new_patient_id() -> str:
    return str(uuid.uuid4())


def patient_to_dict(patient: Patient) -> dict:
    def stamp(value: datetime | None) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    return {
        "patient_id": patient.patient_id,
        "first_name": patient.first_name,
        "last_name": patient.last_name,
        "date_of_birth": format_dob(patient.date_of_birth),
        "sex": patient.sex,
        "phone_number": patient.phone_number,
        "email": patient.email,
        "address_line_1": patient.address_line_1,
        "address_line_2": patient.address_line_2,
        "city": patient.city,
        "state": patient.state,
        "zip_code": patient.zip_code,
        "insurance_provider": patient.insurance_provider,
        "insurance_member_id": patient.insurance_member_id,
        "preferred_language": patient.preferred_language,
        "emergency_contact_name": patient.emergency_contact_name,
        "emergency_contact_phone": patient.emergency_contact_phone,
        "created_at": stamp(patient.created_at),
        "updated_at": stamp(patient.updated_at),
        "deleted_at": stamp(patient.deleted_at),
    }


def _apply(patient: Patient, fields: dict) -> None:
    for key, value in fields.items():
        if key == "date_of_birth" and isinstance(value, str):
            value = dob_to_date(value)
        setattr(patient, key, value)


def _guard(settings: Settings | None, force_failure: bool) -> None:
    if force_failure or (settings is not None and settings.simulate_db_write_failure):
        raise StorageError("simulated database write failure")


def list_patients(
    db: Session,
    *,
    last_name: str | None = None,
    date_of_birth: date | None = None,
    phone_number: str | None = None,
) -> list[Patient]:
    query = select(Patient).where(Patient.deleted_at.is_(None))
    if last_name:
        query = query.where(func.lower(Patient.last_name) == last_name.strip().lower())
    if date_of_birth is not None:
        query = query.where(Patient.date_of_birth == date_of_birth)
    if phone_number:
        query = query.where(Patient.phone_number == phone_number)
    query = query.order_by(Patient.created_at.desc())
    return list(db.scalars(query).all())


def get_patient(db: Session, patient_id: str) -> Patient | None:
    patient = db.get(Patient, patient_id)
    if patient is None or patient.deleted_at is not None:
        return None
    return patient


def find_by_phone(db: Session, phone: str) -> Patient | None:
    if phone.isdigit() and len(phone) == 10:
        digits = phone
    else:
        digits = parse_phone(phone).value
    if not digits:
        return None
    query = (
        select(Patient)
        .where(Patient.deleted_at.is_(None), Patient.phone_number == digits)
        .order_by(Patient.updated_at.desc())
    )
    return db.scalars(query).first()


def create_patient(
    db: Session,
    payload: dict,
    *,
    settings: Settings | None = None,
    force_failure: bool = False,
    already_clean: bool = False,
) -> Patient:
    _guard(settings, force_failure)
    fields = payload if already_clean else normalize_api_record(payload, partial=False)
    now = utcnow()
    patient = Patient(
        patient_id=new_patient_id(),
        created_at=now,
        updated_at=now,
        deleted_at=None,
        preferred_language=fields.get("preferred_language") or "English",
    )
    _apply(patient, fields)
    db.add(patient)
    db.commit()
    db.refresh(patient)
    return patient


def update_patient(
    db: Session,
    patient_id: str,
    payload: dict,
    *,
    settings: Settings | None = None,
    force_failure: bool = False,
    already_clean: bool = False,
) -> Patient | None:
    _guard(settings, force_failure)
    patient = get_patient(db, patient_id)
    if patient is None:
        return None
    fields = payload if already_clean else normalize_api_record(payload, partial=True)
    if fields:
        _apply(patient, fields)
    patient.updated_at = utcnow()
    db.commit()
    db.refresh(patient)
    return patient


def soft_delete_patient(db: Session, patient_id: str) -> Patient | None:
    patient = get_patient(db, patient_id)
    if patient is None:
        return None
    now = utcnow()
    patient.deleted_at = now
    patient.updated_at = now
    db.commit()
    db.refresh(patient)
    return patient

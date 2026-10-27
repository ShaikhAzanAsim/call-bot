"""Two obviously fake patients. 555-01xx numbers are the reserved fictional range."""

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Patient, utcnow

SEED_PATIENTS = [
    {
        "first_name": "Jane",
        "last_name": "Doe",
        "date_of_birth": date(1985, 3, 15),
        "sex": "Female",
        "phone_number": "2025550101",
        "email": "jane.doe@example.com",
        "address_line_1": "1600 Pennsylvania Avenue NW",
        "address_line_2": None,
        "city": "Washington",
        "state": "DC",
        "zip_code": "20500",
        "insurance_provider": "Example Health",
        "insurance_member_id": "FAKE1001",
        "preferred_language": "English",
        "emergency_contact_name": "Alex Doe",
        "emergency_contact_phone": "2025550102",
    },
    {
        "first_name": "Carlos",
        "last_name": "Rivera",
        "date_of_birth": date(1990, 11, 2),
        "sex": "Male",
        "phone_number": "4155550199",
        "email": "carlos.rivera@example.com",
        "address_line_1": "1 Market Street",
        "address_line_2": "Suite 100",
        "city": "San Francisco",
        "state": "CA",
        "zip_code": "94105",
        "insurance_provider": None,
        "insurance_member_id": None,
        "preferred_language": "Spanish",
        "emergency_contact_name": None,
        "emergency_contact_phone": None,
    },
]


def seed_if_empty(db: Session) -> int:
    existing = db.scalar(select(Patient.patient_id).limit(1))
    if existing:
        return 0
    now = utcnow()
    for row in SEED_PATIENTS:
        db.add(
            Patient(
                patient_id=str(uuid.uuid4()),
                created_at=now,
                updated_at=now,
                deleted_at=None,
                **row,
            )
        )
    db.commit()
    return len(SEED_PATIENTS)

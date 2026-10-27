"""SQLAlchemy models. Constraints are enforced in the database, not only in Python."""

from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON

SEX_VALUES = ("Male", "Female", "Other", "Decline to Answer")

STATE_CODES = (
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "HI", "ID",
    "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO",
    "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA",
    "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "AS", "GU", "MP", "PR", "VI",
)


def _digits(column: str, start: int, count: int) -> str:
    return " AND ".join(
        f"substr({column}, {start + offset}, 1) BETWEEN '0' AND '9'"
        for offset in range(count)
    )


def _phone_rule(column: str) -> str:
    """10-digit NANP: area code and exchange cannot start with 0 or 1, and neither can be N11."""
    return " AND ".join(
        [
            f"length({column}) = 10",
            _digits(column, 1, 10),
            f"substr({column}, 1, 1) BETWEEN '2' AND '9'",
            f"substr({column}, 4, 1) BETWEEN '2' AND '9'",
            f"substr({column}, 2, 2) <> '11'",
            f"substr({column}, 5, 2) <> '11'",
        ]
    )


def _zip_rule() -> str:
    five = " AND ".join(["length(zip_code) = 5", _digits("zip_code", 1, 5)])
    plus4 = " AND ".join(
        [
            "length(zip_code) = 10",
            _digits("zip_code", 1, 5),
            "substr(zip_code, 6, 1) = '-'",
            _digits("zip_code", 7, 4),
        ]
    )
    return f"(({five}) OR ({plus4}))"


def _no_digits(column: str) -> str:
    return " AND ".join(f"{column} NOT LIKE '%{digit}%'" for digit in "0123456789")


class Base(DeclarativeBase):
    pass


class Patient(Base):
    __tablename__ = "patients"

    patient_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    first_name: Mapped[str] = mapped_column(String(50), nullable=False)
    last_name: Mapped[str] = mapped_column(String(50), nullable=False)
    date_of_birth: Mapped[date] = mapped_column(Date, nullable=False)
    sex: Mapped[str] = mapped_column(String(20), nullable=False)
    phone_number: Mapped[str] = mapped_column(String(10), nullable=False)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    address_line_1: Mapped[str] = mapped_column(String(200), nullable=False)
    address_line_2: Mapped[str | None] = mapped_column(String(200), nullable=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(2), nullable=False)
    zip_code: Mapped[str] = mapped_column(String(10), nullable=False)
    insurance_provider: Mapped[str | None] = mapped_column(String(100), nullable=True)
    insurance_member_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    preferred_language: Mapped[str] = mapped_column(String(50), nullable=False, default="English")
    emergency_contact_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    emergency_contact_phone: Mapped[str | None] = mapped_column(String(10), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("length(first_name) BETWEEN 1 AND 50", name="ck_patients_first_name_len"),
        CheckConstraint("length(last_name) BETWEEN 1 AND 50", name="ck_patients_last_name_len"),
        CheckConstraint(_no_digits("first_name"), name="ck_patients_first_name_chars"),
        CheckConstraint(_no_digits("last_name"), name="ck_patients_last_name_chars"),
        CheckConstraint(
            "sex IN ('Male', 'Female', 'Other', 'Decline to Answer')",
            name="ck_patients_sex",
        ),
        CheckConstraint(_phone_rule("phone_number"), name="ck_patients_phone"),
        CheckConstraint(
            "email IS NULL OR (length(email) BETWEEN 6 AND 254 AND email LIKE '%_@_%._%' "
            "AND email NOT LIKE '% %' AND email NOT LIKE '%@%@%')",
            name="ck_patients_email",
        ),
        CheckConstraint("length(address_line_1) BETWEEN 1 AND 200", name="ck_patients_addr1"),
        CheckConstraint("length(city) BETWEEN 1 AND 100", name="ck_patients_city"),
        CheckConstraint(
            "state IN (" + ", ".join(f"'{code}'" for code in STATE_CODES) + ")",
            name="ck_patients_state",
        ),
        CheckConstraint(_zip_rule(), name="ck_patients_zip"),
        CheckConstraint(
            "insurance_member_id IS NULL OR ("
            "length(insurance_member_id) BETWEEN 1 AND 40 "
            "AND insurance_member_id NOT LIKE '% %')",
            name="ck_patients_member_id",
        ),
        CheckConstraint(
            "length(preferred_language) BETWEEN 1 AND 50",
            name="ck_patients_language",
        ),
        CheckConstraint(
            "emergency_contact_phone IS NULL OR (" + _phone_rule("emergency_contact_phone") + ")",
            name="ck_patients_emergency_phone",
        ),
        Index("ix_patients_last_name", "last_name"),
        Index("ix_patients_phone_number", "phone_number"),
        Index("ix_patients_date_of_birth", "date_of_birth"),
        Index("ix_patients_deleted_at", "deleted_at"),
    )


class CallSession(Base):
    __tablename__ = "call_sessions"

    call_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    caller_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="in_progress")
    draft_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    patient_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("patients.patient_id"), nullable=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    language: Mapped[str] = mapped_column(String(50), nullable=False, default="English")
    registering_for_other: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    relationship: Mapped[str | None] = mapped_column(String(50), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('in_progress', 'completed', 'abandoned', 'failed')",
            name="ck_call_sessions_status",
        ),
        Index("ix_call_sessions_caller", "caller_number"),
        Index("ix_call_sessions_status", "status"),
    )


class CallEvent(Base):
    __tablename__ = "call_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    call_id: Mapped[str] = mapped_column(String(80), nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    type: Mapped[str] = mapped_column(String(40), nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False)

    __table_args__ = (Index("ix_call_events_call_id", "call_id"),)


class CallLog(Base):
    __tablename__ = "call_logs"

    call_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    transcript_json: Mapped[list | dict | None] = mapped_column(JSON, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    patient_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("patients.patient_id"), nullable=True
    )
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)

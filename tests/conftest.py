import os

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SEED_ON_STARTUP"] = "false"
os.environ["VAPI_WEBHOOK_SECRET"] = "test-secret"
os.environ["SIMULATE_DB_WRITE_FAILURE"] = "false"
os.environ["PUBLIC_BASE_URL"] = "http://testserver"

from app.config import clear_settings_cache

clear_settings_cache()

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from patient_samples import VALID_PATIENT

__all__ = ["VALID_PATIENT"]


@pytest.fixture
def client():
    application = create_app()
    with TestClient(application, raise_server_exceptions=False) as test_client:
        yield test_client


VALID_PATIENT = {
    "first_name": "Maria",
    "last_name": "Lopez",
    "date_of_birth": "03/05/1992",
    "sex": "Female",
    "phone_number": "2065550142",
    "email": "maria.lopez@example.com",
    "address_line_1": "410 Pike Street",
    "address_line_2": "Apt 2",
    "city": "Seattle",
    "state": "WA",
    "zip_code": "98101",
    "insurance_provider": "Example Health",
    "insurance_member_id": "ABC123",
    "preferred_language": "English",
    "emergency_contact_name": "Luis Lopez",
    "emergency_contact_phone": "2065550148",
}

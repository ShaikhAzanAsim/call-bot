from app.config import Settings, clear_settings_cache
from app.db.seed import seed_if_empty
from app.db.session import dispose_engine, get_session_factory, init_engine
from app.services.address import check_address
from app.services.patients import create_patient, get_patient


def test_zip_state_mismatch_uses_local_table():
    settings = Settings(census_timeout_seconds=0.2, database_url="sqlite://")
    result = check_address("1 Main Street", "Austin", "WA", "78701", settings)
    assert result["ok"] is False
    assert "78701" in result["say"]
    assert "TX" in result["say"]


def test_write_survives_new_connection(tmp_path):
    url = f"sqlite:///{tmp_path / 'patients.db'}"
    settings = Settings(database_url=url, seed_on_startup=False, app_env="test")
    clear_settings_cache()
    init_engine(settings)
    db = get_session_factory()()
    try:
        created = create_patient(
            db,
            {
                "first_name": "Pat",
                "last_name": "Persistence",
                "date_of_birth": "04/04/1984",
                "sex": "Other",
                "phone_number": "3035550177",
                "address_line_1": "100 Main Street",
                "city": "Denver",
                "state": "CO",
                "zip_code": "80202",
            },
        )
        patient_id = created.patient_id
    finally:
        db.close()
        dispose_engine()

    init_engine(settings)
    db = get_session_factory()()
    try:
        found = get_patient(db, patient_id)
        assert found is not None
        assert found.last_name == "Persistence"
        assert seed_if_empty(db) == 0
    finally:
        db.close()
        dispose_engine()

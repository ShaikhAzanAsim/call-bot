"""Run every YAML scenario against the real tool implementations.

    python -m evals.run --all
    python -m evals.run --llm
"""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from app.config import Settings
from app.db.session import dispose_engine, get_session_factory, init_engine
from app.services.patients import create_patient, get_patient, list_patients, patient_to_dict
from app.services.sessions import finish_call, start_call
from app.voice.tools import dispatch_tool
from evals.report import write_report
from evals.scorer import expect_ok, score_scenario
from evals.simulator import llm_available

SCENARIOS = Path(__file__).resolve().parent / "scenarios"


def load_scenarios() -> list[dict]:
    rows = []
    for path in sorted(SCENARIOS.glob("*.yaml")):
        rows.append(yaml.safe_load(path.read_text(encoding="utf-8")))
    return rows


def _settings(database_url: str) -> Settings:
    return Settings(
        app_env="test",
        database_url=database_url,
        seed_on_startup=False,
        simulate_db_write_failure=False,
        vapi_webhook_secret="eval",
        vapi_assistant_id="",
        census_timeout_seconds=0.4,
    )


def run_scenario(scenario: dict, settings: Settings) -> dict:
    db = get_session_factory()()
    call_id = scenario["id"]
    caller = scenario.get("caller_number")
    try:
        if scenario.get("setup_patient"):
            create_patient(db, scenario["setup_patient"])
        prior = scenario.get("prior_call")
        if prior:
            session, _ = start_call(db, prior["id"], caller, settings)
            session.draft_json["fields"] = dict(prior.get("fields") or {})
            session.status = "abandoned"
            from sqlalchemy.orm.attributes import flag_modified

            flag_modified(session, "draft_json")
            db.commit()
        results = []
        for index, step in enumerate(scenario.get("steps") or [], start=1):
            result = dispatch_tool(
                db,
                call_id,
                caller,
                settings,
                step["tool"],
                step.get("args") or {},
            )
            notes = expect_ok(result, step.get("expect") or {})
            results.append(
                {"index": index, "tool": step["tool"], "args": step.get("args") or {}, "result": result, "notes": notes}
            )
        if "abandoned" in (scenario.get("checks") or []) or scenario.get("steps"):
            finish_call(
                db,
                call_id,
                transcript=None,
                summary=None,
                duration_seconds=None,
                ended_reason="eval-end",
            )
        from app.services.sessions import get_session

        session = get_session(db, call_id)
        patient = None
        saved_id = None if session is None else (session.draft_json or {}).get("meta", {}).get("saved_patient_id")
        if saved_id:
            row = get_patient(db, saved_id)
            patient = patient_to_dict(row) if row else None
        elif "updated_not_duplicated" in (scenario.get("checks") or []):
            rows = list_patients(db, phone_number=scenario["setup_patient"]["phone_number"])
            patient = patient_to_dict(rows[0]) if rows else None
            if len(rows) != 1:
                results.append(
                    {
                        "index": 0,
                        "tool": "check",
                        "args": {},
                        "result": {},
                        "notes": [f"expected 1 patient, found {len(rows)}"],
                    }
                )
        return score_scenario(scenario, session, patient, results, settings)
    finally:
        db.close()


def run_all(database_url: str = "sqlite://") -> list[dict]:
    settings = _settings(database_url)
    init_engine(settings)
    try:
        return [run_scenario(scenario, settings) for scenario in load_scenarios()]
    finally:
        dispose_engine()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the registration eval lab")
    parser.add_argument("--all", action="store_true", help="Run every YAML scenario")
    parser.add_argument("--llm", action="store_true", help="Also note whether LLM mode can run")
    args = parser.parse_args()
    if not args.all and not args.llm:
        args.all = True
    settings = Settings()
    rows = run_all() if args.all or args.llm else []
    mode = "deterministic tool harness"
    if args.llm:
        if llm_available(settings):
            mode += "; LLM key is set but this entrypoint still reports the deterministic scorecard"
        else:
            mode += "; LLM mode skipped because EVAL_LLM_API_KEY is empty"
    path = write_report(rows, mode)
    passed = sum(1 for row in rows if row["passed"])
    print(f"{passed}/{len(rows)} passed. Wrote {path}")
    if passed != len(rows):
        raise SystemExit(1)


if __name__ == "__main__":
    main()

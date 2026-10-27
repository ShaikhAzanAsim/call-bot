# Requirements checklist

Source of truth: `docs/assessment.pdf`. The build brief adds detail; where they disagree, the PDF wins.

Legend: `[x]` done in this repo, `[ ]` blocked on an account, `[-]` deferred on purpose.

## PDF — working system

- [ ] Real dialable U.S. phone number is live (blocked: needs a Vapi account and number)
- [x] Agent code conducts a natural flow (prompt, one question at a time, tools, not an IVR menu)
- [x] Data persists across a new database connection (`tests/test_persistence.py`)
- [x] A later call from the same number can see the earlier draft, and saved patients stay in the API
- [x] Confirmation read-back is required before save (`confirm_registration` gate)
- [x] Invalid data re-prompts that specific field
- [x] Success line is "You're all set, [First Name]." and the assistant has Vapi `endCall`
- [x] Final collected payload is printed to stdout on the end-of-call report

## PDF — data model

- [x] All required and optional demographic fields
- [x] `patient_id` UUID
- [x] `created_at` / `updated_at` UTC
- [x] Server-side validation matching the PDF rules
- [x] Optional fields are offered in the prompt, not forced
- [x] Two obviously fake seed patients

## PDF — database

- [x] Relational schema with column types and `CHECK` constraints
- [x] Data survives a new connection to the same file
- [x] Soft delete via `deleted_at`

## PDF — REST API

- [x] `GET /patients` with `last_name`, `date_of_birth`, `phone_number`
- [x] `GET /patients/{id}`
- [x] `POST /patients` returns `patient_id`
- [x] `PUT /patients/{id}` partial update
- [x] `DELETE /patients/{id}` soft delete
- [x] Status codes 200, 201, 400, 404, 422, 500
- [x] Envelope on every API response
- [x] Server-side validation and input sanitization
- [x] No hardcoded secrets

## PDF — voice integration

- [x] Confirmed data is written through the shared service layer
- [x] A failed write returns a spoken error and keeps the draft
- [x] Duplicate phone recognition offers an update

## PDF — delivery

- [x] README with setup, architecture, stack, env vars, limitations
- [x] System prompt included and commented
- [x] Trade-offs documented
- [ ] Live API base URL in the README (blocked: needs hosting)
- [ ] Phone number in the README (blocked: needs Vapi)

## Build brief — architecture

- [x] FastAPI, Pydantic v2, SQLAlchemy 2, SQLite WAL, `DATABASE_URL` can point at PostgreSQL
- [x] Telephony isolated in `app/voice/vapi_adapter.py`
- [x] REST routes contain no business rules
- [x] Voice tools and REST share `app/services/`
- [x] `/health`, OpenAPI at `/docs`
- [x] Webhook shared-secret check
- [x] API left open; limitation noted

## Build brief — reliability behavior

- [x] Spoken-input normalization
- [x] Draft sessions, resume after drop, stale drafts marked abandoned
- [x] Repair strategy escalates
- [x] Start over / go back
- [x] Proxy registration
- [x] Spanish switch
- [x] Confirmation gate enforced in the tool
- [x] `save_patient` idempotent per call
- [x] Census geocoder with timeout and ZIP3 fallback
- [x] Tool handlers stay off the slow path except `check_address`

## Build brief — extras

- [x] Eval Lab: 21 scenarios, scorer, `evals/RESULTS.md` (21/21 on the tool harness)
- [x] Live dashboard (SSE)
- [x] Call flight recorder
- [x] Address check visible in tool results and the event timeline
- [x] Call summary stored on `call_logs` and shown on the dashboard
- [-] Mock appointment scheduling (after a real deployed call works)
- [-] Post-call SMS (documented under Next Steps; A2P 10DLC)

## Tests

- [x] Unit tests for validators and normalizers
- [x] API integration tests including status codes, envelope, soft delete, partial update
- [x] Voice tool tests: lookup/resume, record failure, save, save failure, idempotent retry
- [x] Persistence test across a new database connection
- [x] `scripts/smoke_test.sh` and `scripts/smoke_test.py`

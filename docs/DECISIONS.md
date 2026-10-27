# Decisions

One line per trade-off: what, why, what we did not do.

- Vapi for telephony: the PDF encourages a managed voice platform, and one webhook covers STT, TTS, and a U.S. number. We did not build Twilio + Deepgram ourselves.
- SQLite on a persistent volume: one file survives restarts and needs no extra database service. PostgreSQL is a `DATABASE_URL` change, not a rewrite. We did not start on hosted Postgres.
- Portable `CHECK` constraints (length, enums, digit `substr` tests) instead of SQLite-only `GLOB`: the same model creates a valid schema on PostgreSQL.
- `deleted_at` column even though the PDF field table omits it: the PDF `DELETE` endpoint requires a soft delete, and the row has to remember that timestamp.
- No unique constraint on phone number: the brief says families share numbers, and duplicate handling is a conversation, not a schema rule.
- Seed numbers are `202-555-0101` and `415-555-0199`: the reserved fictional exchange is `555-01xx`, which still passes NANP because the exchange starts with 5. A bare `555-01xx` without a real area code would fail the "exchange cannot start with 0 or 1" rule.
- Two-digit years use the latest century that is not in the future and not more than 120 years ago, then the agent reads the four-digit year back. We did not ask a separate "nineteen or twenty" question on the first try.
- `confirm_registration` is an extra tool the brief's list does not name: the server rejects `save_patient` until this is called, so a confused model cannot skip the explicit yes. The alternative was trusting the prompt alone.
- Phone-number server URL plus a saved assistant id is the production setup: Vapi attaches the webhook secret to saved resources, and a fully transient assistant often arrives with no signature. Transient mode remains for local dev.
- Census geocoder is advisory and times out in 1.5s: a slow geocoder must not blow the tool-call budget. The bundled ZIP3 table answers state mismatches with no network.
- Eval Lab default mode drives the real tools from YAML scripts and does not call an LLM: it runs in CI without keys. `python -m evals.run --llm` is the caller-vs-agent mode when `EVAL_LLM_API_KEY` is set. We did not pretend a scripted run was a listening test.
- Dashboard is one static HTML file: no build step, served by FastAPI, live updates over SSE.
- API writes are unauthenticated: the brief says leave the API open until an API key is requested. Webhooks still check the shared secret in production.
- Single Uvicorn worker with SQLite: WAL is safe for one process. More workers need Postgres.
- In-memory SSE hub: fine for one instance. It does not fan out across multiple servers.
- Appointment scheduling and SMS are not in this build: SMS needs A2P 10DLC registration, and scheduling waits until a real call has succeeded on the deployed number.

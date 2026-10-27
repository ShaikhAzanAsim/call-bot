"""Parse Vapi server-url payloads and shape the responses Vapi expects.

Payload notes, checked against https://docs.vapi.ai/server-url/events
and https://docs.vapi.ai/tools/custom-tools on 2026-10-27:

- Every webhook is POST JSON: {"message": {"type": "...", "call": {...}, ...}}.
- tool-calls include toolCallList[].id and either function.name + function.arguments
  (current) or a flat name + parameters (older docs). arguments may be an object
  or a JSON string. We accept both.
- The tool response must be HTTP 200: {"results": [{"toolCallId": "...", "result": "<one line>"}]}.
  Business failures go in the result string, not an HTTP error, so the model can speak them.
- assistant-request must be answered within 7.5 seconds. We only do a local database lookup.
- end-of-call-report carries artifact.transcript / artifact.messages and sometimes analysis.summary.
- Caller ID is message.call.customer.number. Older examples used call.from.phoneNumber.
- Auth is the X-Vapi-Secret header (legacy secret / bearer credential) or Authorization: Bearer.
  A ?token= query param is accepted because transient assistants sometimes omit the header.
"""

from __future__ import annotations

import json
import secrets
from typing import Any

from app.config import Settings


def _eq(expected: str, supplied: str) -> bool:
    if not expected or not supplied or len(expected) != len(supplied):
        return False
    return secrets.compare_digest(expected, supplied)


def authorized(headers: dict[str, str], query_token: str | None, settings: Settings) -> bool:
    secret = settings.vapi_webhook_secret
    if not secret:
        return not settings.is_production
    folded = {key.lower(): value for key, value in headers.items()}
    supplied = folded.get("x-vapi-secret", "")
    auth = folded.get("authorization", "")
    bearer = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    return _eq(secret, supplied) or _eq(secret, bearer) or _eq(secret, query_token or "")


def message_of(payload: dict) -> dict:
    message = payload.get("message")
    if isinstance(message, dict):
        return message
    return payload if isinstance(payload, dict) else {}


def message_type(payload: dict) -> str:
    return str(message_of(payload).get("type") or "")


def call_id_of(payload: dict) -> str:
    message = message_of(payload)
    call = message.get("call") if isinstance(message.get("call"), dict) else {}
    return str(call.get("id") or message.get("callId") or "unknown-call")


def caller_number_of(payload: dict) -> str | None:
    message = message_of(payload)
    call = message.get("call") if isinstance(message.get("call"), dict) else {}
    customer = call.get("customer") if isinstance(call.get("customer"), dict) else {}
    if not customer and isinstance(message.get("customer"), dict):
        customer = message["customer"]
    legacy_from = call.get("from") if isinstance(call.get("from"), dict) else {}
    for candidate in (
        customer.get("number"),
        legacy_from.get("phoneNumber"),
        legacy_from.get("number"),
        call.get("customerNumber"),
    ):
        if candidate:
            return str(candidate)
    return None


def _arguments(raw: Any) -> dict:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def tool_calls_of(payload: dict) -> list[dict]:
    """Normalize both Vapi tool-call shapes into {id, name, arguments}."""
    message = message_of(payload)
    raw_list = message.get("toolCallList") or []
    calls = []
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        function = item.get("function") if isinstance(item.get("function"), dict) else {}
        name = function.get("name") or item.get("name") or ""
        arguments = _arguments(function.get("arguments", item.get("parameters", item.get("arguments"))))
        tool_id = str(item.get("id") or item.get("toolCallId") or "")
        calls.append({"id": tool_id, "name": str(name), "arguments": arguments})
    return calls


def tool_results_response(results: list[tuple[str, dict]]) -> dict:
    packed = []
    for tool_call_id, result in results:
        text = json.dumps(result, separators=(",", ":"), default=str)
        text = text.replace("\n", " ")
        packed.append({"toolCallId": tool_call_id, "result": text})
    return {"results": packed}


def transcript_of(payload: dict) -> Any:
    message = message_of(payload)
    artifact = message.get("artifact") if isinstance(message.get("artifact"), dict) else {}
    if artifact.get("messages"):
        return artifact.get("messages")
    if artifact.get("transcript"):
        return artifact.get("transcript")
    if message.get("transcript"):
        return message.get("transcript")
    return None


def summary_of(payload: dict) -> str | None:
    message = message_of(payload)
    analysis = message.get("analysis") if isinstance(message.get("analysis"), dict) else {}
    for candidate in (
        analysis.get("summary"),
        message.get("summary"),
        (message.get("artifact") or {}).get("summary") if isinstance(message.get("artifact"), dict) else None,
    ):
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return None


def duration_of(payload: dict) -> int | None:
    message = message_of(payload)
    for key in ("durationSeconds", "duration"):
        value = message.get(key)
        if isinstance(value, (int, float)):
            return int(value)
    call = message.get("call") if isinstance(message.get("call"), dict) else {}
    for key in ("durationSeconds", "duration"):
        value = call.get(key)
        if isinstance(value, (int, float)):
            return int(value)
    return None


def ended_reason_of(payload: dict) -> str | None:
    message = message_of(payload)
    reason = message.get("endedReason") or message.get("ended_reason")
    return str(reason) if reason else None

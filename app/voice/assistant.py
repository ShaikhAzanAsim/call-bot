"""Build the Vapi assistant definition from the commented prompt file."""

from __future__ import annotations

import re

from app.config import PROMPT_PATH, Settings
from app.services.sessions import caller_digits

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "lookup_caller",
            "description": "Look up the caller ID. Returns a greeting, a masked existing patient if any, and an unfinished draft to resume. Call this before the first question if you were not already given a greeting.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "record_field",
            "description": "Normalize and store one field from the caller's exact words. Always call this for every value. Trust ok and say. On failure, follow repair_step.",
            "parameters": {
                "type": "object",
                "properties": {
                    "field": {
                        "type": "string",
                        "description": "first_name, last_name, date_of_birth, sex, phone_number, email, address_line_1, address_line_2, city, state, zip_code, insurance_provider, insurance_member_id, preferred_language, emergency_contact_name, emergency_contact_phone",
                    },
                    "spoken_value": {"type": "string", "description": "The caller's words for this field, not your paraphrase."},
                },
                "required": ["field", "spoken_value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_address",
            "description": "Check the street, city, state, and ZIP. Say the returned sentence. Do not change the address unless the caller agrees.",
            "parameters": {
                "type": "object",
                "properties": {
                    "line1": {"type": "string"},
                    "city": {"type": "string"},
                    "state": {"type": "string"},
                    "zip": {"type": "string"},
                },
                "required": ["line1", "city", "state", "zip"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_draft",
            "description": "Return collected fields, missing required fields, and the read-back script. Call this before reading the record back.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reset_draft",
            "description": "Start over (scope=all) or clear one field (scope=field plus field name).",
            "parameters": {
                "type": "object",
                "properties": {
                    "scope": {"type": "string", "enum": ["all", "field"]},
                    "field": {"type": "string"},
                },
                "required": ["scope"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_proxy_registration",
            "description": "Caller is registering someone else, such as a parent or child. Pass the relationship. Then collect the patient's details.",
            "parameters": {
                "type": "object",
                "properties": {"relationship": {"type": "string"}},
                "required": ["relationship"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "confirm_registration",
            "description": "Call only after get_draft's read-back was spoken and the caller clearly said yes. This unlocks save_patient.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_patient",
            "description": "Save the registration. Refuses unless confirm_registration succeeded. Say the returned sentence. On failure, retry once.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_existing_by_phone",
            "description": "Look up a spoken phone number. If found, ask whether to update that record.",
            "parameters": {
                "type": "object",
                "properties": {"phone": {"type": "string"}},
                "required": ["phone"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "choose_duplicate_action",
            "description": "After the caller decides: action is update or create_new. Pass patient_id when you have it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["update", "create_new"]},
                    "patient_id": {"type": "string"},
                },
                "required": ["action"],
            },
        },
    },
    {"type": "endCall"},
]


def load_system_prompt() -> str:
    raw = PROMPT_PATH.read_text(encoding="utf-8")
    stripped = re.sub(r"<!--.*?-->", "", raw, flags=re.DOTALL)
    stripped = re.sub(r"\n{3,}", "\n\n", stripped).strip()
    return stripped


def assistant_payload(settings: Settings, context: dict) -> dict:
    prompt = load_system_prompt().replace("{{caller_context}}", _context_block(context))
    server_url = _server_url(settings)
    assistant = {
        "name": "Intake Coordinator",
        "firstMessage": context.get("greeting"),
        "model": {
            "provider": "openai",
            "model": settings.vapi_model,
            "temperature": 0.3,
            "messages": [{"role": "system", "content": prompt}],
            "tools": TOOL_DEFINITIONS,
        },
        "voice": {"provider": settings.vapi_voice_provider, "voiceId": settings.vapi_voice_id},
        "transcriber": {"provider": "deepgram", "model": "nova-2", "language": "multi"},
        "silenceTimeoutSeconds": 30,
        "maxDurationSeconds": 900,
        "backgroundDenoisingEnabled": True,
        "endCallMessage": "Thanks for calling. Goodbye.",
        "serverMessages": [
            "tool-calls",
            "end-of-call-report",
            "status-update",
            "transcript",
            "conversation-update",
            "hang",
        ],
        "analysisPlan": {
            "summaryPrompt": (
                "In two sentences, summarize this patient registration call. "
                "Say whether it was saved, and name any field the caller had to repeat. Do not invent data."
            )
        },
    }
    if server_url:
        server: dict = {"url": server_url}
        if settings.vapi_webhook_secret:
            server["secret"] = settings.vapi_webhook_secret
        assistant["server"] = server
    if settings.vapi_assistant_id:
        return {
            "assistantId": settings.vapi_assistant_id,
            "assistantOverrides": {
                "firstMessage": context.get("greeting"),
                "variableValues": {
                    "caller_context": _context_block(context),
                    "greeting": context.get("greeting") or "",
                },
            },
        }
    return {"assistant": assistant}


def _context_block(context: dict) -> str:
    lines = ["Call context (do not read this label aloud):"]
    number = caller_digits(context.get("caller_number"))
    if number:
        lines.append(f"Caller ID ends in {number[-4:]}.")
    existing = context.get("existing_patient")
    if existing:
        lines.append(
            f"Caller ID matches {existing['first_name']} {existing['last_initial']}. "
            "Greet them by first name and ask if they want to update their record."
        )
    resume = context.get("resume")
    if resume:
        lines.append(
            f"Unfinished draft collected {resume['collected']}. "
            f"Offer to continue from {resume['next']}. If they decline, call reset_draft scope all."
        )
    if len(lines) == 1:
        lines.append("No matching patient and no unfinished draft.")
    return " ".join(lines)


def _server_url(settings: Settings) -> str:
    base = (settings.public_base_url or "").rstrip("/")
    if not base:
        return ""
    return f"{base}/voice/webhook"

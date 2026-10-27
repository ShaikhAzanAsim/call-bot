"""Optional LLM caller. Off unless EVAL_LLM_API_KEY is set.

The deterministic harness is the one CI runs. This module is the same tool
dispatch loop with an OpenAI-compatible chat model playing the caller and
another playing the agent from the real system prompt.
"""

from __future__ import annotations

import json

import httpx

from app.config import Settings
from app.voice.assistant import TOOL_DEFINITIONS, load_system_prompt


def llm_available(settings: Settings) -> bool:
    return bool(settings.eval_llm_api_key)


def chat(settings: Settings, messages: list[dict], tools: list[dict] | None = None) -> dict:
    payload: dict = {"model": settings.eval_llm_model, "temperature": 0.2, "messages": messages}
    if tools:
        payload["tools"] = tools
    response = httpx.post(
        f"{settings.eval_llm_base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {settings.eval_llm_api_key}"},
        json=payload,
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]


def agent_system(caller_context: str) -> str:
    return load_system_prompt().replace("{{caller_context}}", caller_context)


def openai_tools() -> list[dict]:
    converted = []
    for tool in TOOL_DEFINITIONS:
        if tool.get("type") == "endCall":
            converted.append(
                {
                    "type": "function",
                    "function": {
                        "name": "end_call",
                        "description": "End the call after the goodbye.",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            )
            continue
        converted.append(tool)
    return converted


def caller_system(scenario: dict) -> str:
    truth = json.dumps(scenario.get("ground_truth") or {}, ensure_ascii=False)
    return (
        "You are a person calling a clinic to register. Stay in character. "
        "Do not mention that you are a simulation. Use this hidden record, and do not invent a different one: "
        f"{truth}. Persona: {scenario.get('description', 'cooperative')}. "
        "Answer one question at a time unless the persona says otherwise. "
        "Say yes only after the agent has read the details back."
    )

"""OpenAI-compatible chat calls, JSON extraction, and one repair attempt."""

from __future__ import annotations

import json
import logging
import re
from typing import Callable, TypeVar

from pydantic import BaseModel, ValidationError

from hinga.config import Settings

logger = logging.getLogger("hinga.llm")

T = TypeVar("T", bound=BaseModel)
Transport = Callable[[list[dict[str, str]]], str]

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def parse_json_object(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = _FENCE.sub("", text).strip()
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("model JSON was not an object")
    return data


def post_chat(settings: Settings, messages: list[dict[str, str]]) -> str:
    import httpx

    url = settings.llm_base_url.rstrip("/") + "/chat/completions"

    def send(extra: dict) -> httpx.Response:
        return httpx.post(
            url,
            headers={"Authorization": f"Bearer {settings.llm_api_key}"},
            json={
                "model": settings.llm_model,
                "temperature": 0.2,
                "messages": messages,
                **extra,
            },
            timeout=25,
        )

    response = send({"response_format": {"type": "json_object"}})
    if response.status_code == 400:
        response = send({})
    response.raise_for_status()
    payload = response.json()
    content = payload["choices"][0]["message"]["content"]
    if not isinstance(content, str) or not content.strip():
        raise ValueError("model content was empty")
    return content


def complete_json(
    settings: Settings,
    system: str,
    user: str,
    model: type[T],
    transport: Transport | None = None,
) -> T:
    """Call the model, validate, and repair once. Raises if both attempts fail."""
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    send = transport or (lambda batch: post_chat(settings, batch))
    raw = send(messages)
    try:
        return model.model_validate(parse_json_object(raw))
    except (ValidationError, ValueError, json.JSONDecodeError) as first:
        logger.info("model JSON failed validation, retrying once: %s", type(first).__name__)
        messages = [
            *messages,
            {"role": "assistant", "content": raw},
            {
                "role": "user",
                "content": (
                    "That JSON failed validation: "
                    + str(first)
                    + ". Return one corrected JSON object and nothing else."
                ),
            },
        ]
        repaired = send(messages)
        return model.model_validate(parse_json_object(repaired))

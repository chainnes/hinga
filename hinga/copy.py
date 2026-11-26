"""Fixed copy. The crisis response is a constant, not model output."""

from __future__ import annotations

DISCLAIMER = (
    "This assistant is a journaling desk, not medical advice and not a substitute for "
    "professional care. Reflections describe your own words. They are not a diagnosis, "
    "a treatment plan, or a clinical assessment."
)

SAFETY_TITLE = "Pause here."

# Identical for every crisis input. The token is deliberate: replace it with a
# checked local helpline before any public demo. Do not let a model fill it in.
FIXED_SAFETY_RESPONSE = (
    "Pause here. This assistant will not analyze this and will not diagnose. "
    "If you might act on thoughts of suicide or self-harm, or you are in danger, "
    "contact a person who can help. Helpline: <HELPLINE_PLACEHOLDER>. "
    "Replace this token with a checked local line before any public demo."
)

# Kept so older imports still resolve. The payload uses the fixed response.
SAFETY_MESSAGE = FIXED_SAFETY_RESPONSE
SAFETY_PREVIEW_MESSAGE = FIXED_SAFETY_RESPONSE

RESOURCES: list[dict[str, str]] = [
    {
        "name": "Helpline",
        "detail": "<HELPLINE_PLACEHOLDER>",
        "href": "",
    }
]

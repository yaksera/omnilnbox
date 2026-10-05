"""Minimal OpenRouter client (OpenAI-compatible chat completions)."""
import json
import logging
import re

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class AIError(Exception):
    """Shown to the user as-is."""


def configured():
    return bool(settings.OPENROUTER_API_KEY)


def chat(messages, *, json_mode=False, max_tokens=600, temperature=0.4, model=None, timeout=60):
    """Return (text, total_tokens)."""
    if not configured():
        raise AIError("AI is not set up yet: add OPENROUTER_API_KEY to backend/.env and restart the server.")
    body = {
        "model": model or settings.OPENROUTER_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    try:
        resp = requests.post(
            f"{settings.OPENROUTER_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                "HTTP-Referer": settings.FRONTEND_URL,  # shows up in your OpenRouter dashboard
                "X-Title": "OmniInbox",
            },
            json=body, timeout=timeout,
        )
    except requests.Timeout as exc:
        raise AIError("The AI took too long to answer. Try again.") from exc
    except requests.RequestException as exc:
        raise AIError("Couldn't reach OpenRouter. Check the server's internet connection.") from exc

    if resp.status_code >= 400:
        try:
            detail = (resp.json().get("error") or {}).get("message", "")
        except ValueError:
            detail = resp.text[:200]
        logger.warning("OpenRouter %s: %s", resp.status_code, detail)
        friendly = {
            401: "The OpenRouter API key is invalid. Check OPENROUTER_API_KEY in backend/.env.",
            402: "Your OpenRouter account is out of credit. Top up at openrouter.ai/credits.",
            429: "The AI is busy (rate limit). Try again in a moment.",
        }.get(resp.status_code, f"AI request failed ({resp.status_code}): {detail[:200]}")
        raise AIError(friendly)
    try:
        data = resp.json()
        text = data["choices"][0]["message"]["content"] or ""
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise AIError("The AI returned an unexpected response. Try again.") from exc
    tokens = int((data.get("usage") or {}).get("total_tokens") or 0)
    return text.strip(), tokens


def parse_json(text):
    """Parse the model's JSON answer, tolerating ```json fences or stray text."""
    try:
        return json.loads(text)
    except ValueError:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except ValueError:
                pass
    raise AIError("The AI returned an answer we couldn't read. Try again.")

"""Gemini text generation; a configured Gemini key takes priority over Claude."""

import asyncio
import httpx
from urllib.parse import quote

from app.config import settings


def enabled() -> bool:
    key = settings.gemini_api_key.strip()
    return bool(key) and "your-" not in key


async def generate(system: str, message: str) -> str:
    if not enabled():
        raise ValueError("GEMINI_API_KEY is not configured")
    model = quote(settings.gemini_model, safe="")
    async with httpx.AsyncClient(timeout=60) as client:
        for attempt in range(3):
            response = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                headers={"x-goog-api-key": settings.gemini_api_key.strip()},
                json={
                    "systemInstruction": {"parts": [{"text": system}]},
                    "contents": [{"role": "user", "parts": [{"text": message}]}],
                },
            )
            if response.status_code not in {429, 500, 502, 503, 504} or attempt == 2:
                break
            await asyncio.sleep(2 ** attempt)
    # Do not include response bodies or credentials in errors/logs.
    if response.status_code != 200:
        raise RuntimeError(f"Gemini request failed (HTTP {response.status_code})")
    candidates = response.json().get("candidates", [])
    if not candidates or candidates[0].get("finishReason") != "STOP":
        raise RuntimeError("Gemini returned no complete answer")
    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
    if not text:
        raise RuntimeError("Gemini returned an empty answer")
    return text

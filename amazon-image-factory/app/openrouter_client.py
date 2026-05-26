import json
import os
from urllib.request import Request, urlopen


OPENROUTER_CHAT_COMPLETIONS_URL = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterError(RuntimeError):
    pass


def openrouter_headers() -> dict:
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise OpenRouterError("OPENROUTER_API_KEY is not configured.")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    referer = os.environ.get("OPENROUTER_HTTP_REFERER", "").strip()
    title = os.environ.get("OPENROUTER_APP_TITLE", "Amazon Product Image Factory").strip()
    if referer:
        headers["HTTP-Referer"] = referer
    if title:
        headers["X-Title"] = title
    return headers


def chat_completion(messages: list[dict], model: str, temperature: float = 0.2, response_format: dict | None = None) -> dict:
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    if response_format:
        payload["response_format"] = response_format
    request = Request(
        OPENROUTER_CHAT_COMPLETIONS_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=openrouter_headers(),
        method="POST",
    )
    with urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def extract_message_text(response: dict) -> str:
    choices = response.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content") or ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                parts.append(item.get("text") or "")
        return "\n".join(part for part in parts if part)
    return str(content)

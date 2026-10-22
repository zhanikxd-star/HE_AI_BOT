"""LLM adapters. The test adapter is the default and performs no network call."""

from __future__ import annotations

import logging

from app.domain.rules import parse_natural_request
from app.ports import LlmRequest, LlmResponse

logger = logging.getLogger(__name__)

_CLOSINGS = (
    "Пусть день будет тёплым.",
    "Хорошего тебе года рядом с командой.",
    "Спасибо, что ты с нами.",
    "Пусть работа спорится, а вечер будет спокойным.",
)


class TestLlmAdapter:
    """Deterministic drafts. The response lists every field the adapter received."""

    provider = "test"

    def __init__(self, model_name: str = "test") -> None:
        self.model_name = model_name

    def complete(self, request: LlmRequest) -> LlmResponse:
        fields = dict(request.fields)
        received = sorted(fields)
        data: dict
        text: str
        if request.task == "greeting":
            text = _greeting_text(fields)
            data = {"greeting_text": text}
        elif request.task == "announcement":
            text = _announcement_text(fields)
            data = {"body": text, "title": fields.get("title") or "Объявление"}
        elif request.task == "collection":
            text = (
                f"Черновик сбора для {fields.get('preferred_name', 'коллеги')}. "
                "Взнос и реквизиты берутся из настроек организации."
            )
            data = {
                "title": f"Сбор на подарок — {fields.get('preferred_name', 'коллега')}",
                "description": "Участие добровольное. Отказ не нужно объяснять.",
                "contribution_mode": "fixed",
                "deadline": fields.get("deadline"),
            }
        elif request.task == "gift_ideas":
            budget = fields.get("budget_amount") or "небольшом бюджете"
            name = fields.get("preferred_name", "коллеги")
            ideas = [
                f"Книга или сертификат в пределах {budget} {fields.get('currency') or 'KZT'}",
                f"Тёплый командный подарок для {name} без персональной гравировки",
                "Совместный обед, если человек не против общего формата",
            ]
            text = "\n".join(ideas)
            data = {"gift_ideas": ideas}
        elif request.task == "nl_command":
            parsed = parse_natural_request(str(fields.get("instruction") or ""), list(fields.get("candidate_names") or []))
            text = parsed.get("greeting_text") or "Черновик подготовлен и не отправлен."
            data = parsed
        else:
            text = "Черновик подготовлен и не отправлен."
            data = {}
        return LlmResponse(provider=self.provider, model=request.model or self.model_name, received_fields=received, text=text, data=data)


class OpenAiCompatibleLlm:
    """Live provider. Called only when an API key is configured. Tests do not use it."""

    provider = "openai"

    def __init__(self, api_key: str, base_url: str, timeout: float = 30) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def complete(self, request: LlmRequest) -> LlmResponse:
        import json

        import httpx

        prompt = json.dumps({"task": request.task, "fields": request.fields, "style": request.style}, ensure_ascii=False)
        response = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": request.model,
                "temperature": 0.4,
                "messages": [
                    {
                        "role": "system",
                        "content": "Ты помощник HR. Верни короткий текст на русском. Не проси дополнительные персональные данные.",
                    },
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        return LlmResponse(
            provider=self.provider,
            model=request.model,
            received_fields=sorted(request.fields),
            text=str(content).strip(),
            data={"text": str(content).strip()},
        )


def llm_runtime_mode(provider: str | None, openai_api_key: str | None) -> str:
    """Live OpenAI only when the org provider is openai and OPENAI_API_KEY is set."""
    if (provider or "openai") == "openai" and openai_api_key:
        return "live"
    return "test"


def build_llm(provider: str, model_name: str, openai_api_key: str | None, base_url: str):
    """Select an adapter. This does not call the provider."""
    model = (model_name or "").strip() or "gpt-4o-mini"
    if llm_runtime_mode(provider, openai_api_key) == "live":
        logger.info("llm adapter is openai", extra={"event": "llm_mode"})
        return OpenAiCompatibleLlm(openai_api_key, base_url), model
    logger.info("llm test adapter is active", extra={"event": "llm_mode"})
    return TestLlmAdapter(model), model


def _greeting_text(fields: dict) -> str:
    name = fields.get("preferred_name") or "коллега"
    department = fields.get("department")
    position = fields.get("position")
    variant = int(fields.get("variant") or 0)
    closing = _CLOSINGS[variant % len(_CLOSINGS)]
    parts = [f"{name}, с днём рождения!"]
    if department:
        parts.append(f"Команда «{department}» поздравляет тебя.")
    else:
        parts.append("Команда поздравляет тебя.")
    if position:
        parts.append(f"Удачи тебе в роли {position}.")
    parts.append(closing)
    return " ".join(parts)


def _announcement_text(fields: dict) -> str:
    title = fields.get("title") or "Объявление"
    kind = fields.get("announcement_type") or "news"
    audience = fields.get("audience_label") or "коллеги"
    style = fields.get("style") or "friendly"
    current = fields.get("current_text")
    base = f"{title}. Сообщение для: {audience}."
    if style == "official":
        text = f"{base} Просим ознакомиться."
    else:
        text = f"{base} Будем рады, если получится присоединиться."
    if current:
        text = f"{text} Черновик HR: {current}"
    if kind == "survey":
        text = f"{text} Тип «опрос» зарезервирован, отдельный конструктор опросов не включён."
    return text

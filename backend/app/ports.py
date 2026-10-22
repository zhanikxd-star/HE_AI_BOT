"""Telegram and LLM ports. Adapters live outside the domain services."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


class TransientTelegramError(Exception):
    """Retryable Telegram failure: timeout, flood wait, 5xx."""


class PermanentDeliveryError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


@dataclass
class Button:
    text: str
    callback_data: str


@dataclass
class SendResult:
    ok: bool
    message_id: int | None
    provider: str
    simulated: bool = False


class TelegramSender(Protocol):
    def send_message(
        self,
        chat_id: int,
        text: str,
        *,
        buttons: list[list[Button]] | None = None,
        image_url: str | None = None,
        document_url: str | None = None,
    ) -> SendResult: ...


@dataclass
class LlmRequest:
    task: str
    model: str
    fields: dict
    style: str | None = None


@dataclass
class LlmResponse:
    provider: str
    model: str
    received_fields: list[str]
    text: str
    data: dict = field(default_factory=dict)


class LlmAdapter(Protocol):
    def complete(self, request: LlmRequest) -> LlmResponse: ...

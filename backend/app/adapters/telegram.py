"""Telegram senders: retry wrapper, test adapter, and live aiogram sender."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable

from app.ports import Button, PermanentDeliveryError, SendResult, TelegramSender, TransientTelegramError

logger = logging.getLogger(__name__)


class FakeTelegramSender:
    """In-memory double for tests. Not used when the token is simply missing."""

    def __init__(self, transient_failures: int = 0, permanent_code: str | None = None, provider: str = "telegram") -> None:
        self.transient_failures = transient_failures
        self.permanent_code = permanent_code
        self.provider = provider
        self.calls: list[dict] = []

    def send_message(
        self,
        chat_id: int,
        text: str,
        *,
        buttons: list[list[Button]] | None = None,
        image_url: str | None = None,
        document_url: str | None = None,
    ) -> SendResult:
        self.calls.append(
            {
                "chat_id": chat_id,
                "text": text,
                "buttons": buttons,
                "image_url": image_url,
                "document_url": document_url,
            }
        )
        if self.permanent_code:
            raise PermanentDeliveryError(self.permanent_code)
        if self.transient_failures > 0:
            self.transient_failures -= 1
            raise TransientTelegramError("temporary")
        return SendResult(ok=True, message_id=len(self.calls), provider=self.provider, simulated=False)


class TestTelegramAdapter:
    """Used when TELEGRAM_BOT_TOKEN is unset. Nothing is delivered to Telegram."""

    provider_name = "test"

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def send_message(
        self,
        chat_id: int,
        text: str,
        *,
        buttons: list[list[Button]] | None = None,
        image_url: str | None = None,
        document_url: str | None = None,
    ) -> SendResult:
        self.calls.append({"chat_id": chat_id, "text": text})
        logger.info("telegram test adapter accepted a message; it was not sent to Telegram", extra={"event": "telegram_test_send"})
        return SendResult(ok=True, message_id=None, provider="test", simulated=True)


class RetryingTelegramSender:
    """Retries transient errors inside the sender port. Permanent errors are not retried."""

    def __init__(
        self,
        inner: TelegramSender,
        max_attempts: int = 3,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self.inner = inner
        self.max_attempts = max_attempts
        self.sleep = sleep or time.sleep

    def send_message(
        self,
        chat_id: int,
        text: str,
        *,
        buttons: list[list[Button]] | None = None,
        image_url: str | None = None,
        document_url: str | None = None,
    ) -> SendResult:
        last: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                return self.inner.send_message(
                    chat_id,
                    text,
                    buttons=buttons,
                    image_url=image_url,
                    document_url=document_url,
                )
            except TransientTelegramError as exc:
                last = exc
                logger.warning(
                    "transient telegram error, attempt %s of %s",
                    attempt,
                    self.max_attempts,
                    extra={"event": "telegram_retry"},
                )
                if attempt >= self.max_attempts:
                    raise
                self.sleep(0.2 * attempt)
        assert last is not None
        raise last


class LiveTelegramSender:
    """Bot API via aiogram. Constructed only when TELEGRAM_BOT_TOKEN is set."""

    provider_name = "telegram"

    def __init__(self, token: str, min_interval: float = 0.05) -> None:
        if not token:
            raise RuntimeError("LiveTelegramSender requires TELEGRAM_BOT_TOKEN")
        self._token = token
        self._min_interval = min_interval
        self._last_sent = 0.0

    def send_message(
        self,
        chat_id: int,
        text: str,
        *,
        buttons: list[list[Button]] | None = None,
        image_url: str | None = None,
        document_url: str | None = None,
    ) -> SendResult:
        self._pace()
        try:
            message_id = asyncio.run(
                self._send(chat_id, text, buttons=buttons, image_url=image_url, document_url=document_url)
            )
        except PermanentDeliveryError:
            raise
        except TransientTelegramError:
            raise
        return SendResult(ok=True, message_id=message_id, provider="telegram", simulated=False)

    def _pace(self) -> None:
        if self._min_interval <= 0:
            return
        wait = self._min_interval - (time.monotonic() - self._last_sent)
        if wait > 0:
            time.sleep(wait)
        self._last_sent = time.monotonic()

    async def _send(
        self,
        chat_id: int,
        text: str,
        *,
        buttons: list[list[Button]] | None,
        image_url: str | None,
        document_url: str | None,
    ) -> int:
        from aiogram import Bot
        from aiogram.exceptions import (
            TelegramBadRequest,
            TelegramForbiddenError,
            TelegramNetworkError,
            TelegramRetryAfter,
            TelegramServerError,
        )
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        markup = None
        if buttons:
            markup = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text=button.text, callback_data=button.callback_data) for button in row]
                    for row in buttons
                ]
            )
        bot = Bot(token=self._token)
        try:
            if image_url:
                message = await bot.send_photo(chat_id, image_url, caption=text, reply_markup=markup)
            elif document_url:
                message = await bot.send_document(chat_id, document_url, caption=text, reply_markup=markup)
            else:
                message = await bot.send_message(chat_id, text, reply_markup=markup)
            return int(message.message_id)
        except TelegramRetryAfter as exc:
            raise TransientTelegramError("retry_after") from exc
        except (TelegramNetworkError, TelegramServerError) as exc:
            raise TransientTelegramError(exc.__class__.__name__) from exc
        except TelegramForbiddenError as exc:
            raise PermanentDeliveryError("blocked", "bot blocked") from exc
        except TelegramBadRequest as exc:
            detail = str(exc).lower()
            if "blocked" in detail:
                raise PermanentDeliveryError("blocked", "bot blocked") from exc
            if "chat not found" in detail or "bot was kicked" in detail or "user is deactivated" in detail:
                raise PermanentDeliveryError("not_started", "chat unavailable") from exc
            raise PermanentDeliveryError("bad_request", "telegram rejected the message") from exc
        finally:
            await bot.session.close()


def build_sender(token: str | None, max_attempts: int = 3, min_interval: float = 0.05) -> RetryingTelegramSender:
    if token:
        inner: TelegramSender = LiveTelegramSender(token, min_interval=min_interval)
        logger.info("telegram sender is live", extra={"event": "telegram_mode"})
    else:
        inner = TestTelegramAdapter()
        logger.warning(
            "TELEGRAM_BOT_TOKEN is unset; Telegram test adapter is active",
            extra={"event": "telegram_mode"},
        )
    return RetryingTelegramSender(inner, max_attempts=max_attempts)

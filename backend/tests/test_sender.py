import pytest

from app.adapters.telegram import FakeTelegramSender, RetryingTelegramSender, TestTelegramAdapter, build_sender
from app.ports import PermanentDeliveryError, TransientTelegramError


def test_retries_transient_errors_then_succeeds():
    fake = FakeTelegramSender(transient_failures=2)
    sender = RetryingTelegramSender(fake, max_attempts=3, sleep=lambda _seconds: None)
    result = sender.send_message(10, "привет")
    assert result.ok
    assert len(fake.calls) == 3


def test_permanent_errors_are_not_retried():
    fake = FakeTelegramSender(permanent_code="blocked")
    sender = RetryingTelegramSender(fake, max_attempts=3, sleep=lambda _seconds: None)
    with pytest.raises(PermanentDeliveryError) as caught:
        sender.send_message(10, "привет")
    assert caught.value.code == "blocked"
    assert len(fake.calls) == 1


def test_missing_token_uses_test_adapter(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    sender = build_sender(None)
    assert isinstance(sender.inner, TestTelegramAdapter)
    result = sender.send_message(1, "черновик")
    assert result.simulated is True
    assert result.provider == "test"


def test_exhausted_retries_raise():
    fake = FakeTelegramSender(transient_failures=5)
    sender = RetryingTelegramSender(fake, max_attempts=3, sleep=lambda _seconds: None)
    with pytest.raises(TransientTelegramError):
        sender.send_message(1, "x")
    assert len(fake.calls) == 3

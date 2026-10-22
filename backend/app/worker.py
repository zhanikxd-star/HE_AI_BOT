"""Separate worker process. Polls due scheduled actions."""

import logging
import time

from app.adapters.telegram import build_sender
from app.config import get_settings
from app.db import session_scope
from app.logging_setup import setup_logging
from app.services.org import apply_corporate_chat_from_env
from app.services.scheduler import run_due

logger = logging.getLogger(__name__)


def main() -> None:
    setup_logging()
    settings = get_settings()
    sender = build_sender(
        settings.telegram_bot_token,
        max_attempts=settings.telegram_max_attempts,
        min_interval=settings.telegram_send_interval_seconds,
    )
    with session_scope() as session:
        apply_corporate_chat_from_env(session, settings.corporate_chat_id)
    if not settings.telegram_bot_token:
        logger.warning("TELEGRAM_BOT_TOKEN is unset; Telegram test adapter is active", extra={"event": "telegram_mode"})
    while True:
        try:
            with session_scope() as session:
                run_due(session, sender)
        except Exception:
            logger.exception("worker iteration failed", extra={"event": "worker_error"})
        time.sleep(settings.worker_interval_seconds)


if __name__ == "__main__":
    main()

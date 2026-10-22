"""FastAPI application."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.adapters.telegram import build_sender
from app.api.routes import router
from app.config import get_settings
from app.db import session_scope
from app.errors import DomainError, DuplicateEmployeeError, NotFoundError
from app.logging_setup import setup_logging
from app.services.org import bootstrap_local_admin, apply_corporate_chat_from_env

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    settings = get_settings()
    app.state.sender = build_sender(
        settings.telegram_bot_token,
        max_attempts=settings.telegram_max_attempts,
        min_interval=settings.telegram_send_interval_seconds,
    )
    with session_scope() as session:
        bootstrap_local_admin(session, settings)
        apply_corporate_chat_from_env(session, settings.corporate_chat_id)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="HR AI Agent", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list or ["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)

    @app.exception_handler(DuplicateEmployeeError)
    async def duplicate_handler(_request: Request, exc: DuplicateEmployeeError):
        return JSONResponse(status_code=409, content={"detail": exc.message, "code": exc.code, "matches": exc.matches})

    @app.exception_handler(NotFoundError)
    async def not_found_handler(_request: Request, exc: NotFoundError):
        return JSONResponse(status_code=404, content={"detail": exc.message, "code": exc.code})

    @app.exception_handler(DomainError)
    async def domain_handler(_request: Request, exc: DomainError):
        status = 401 if exc.code == "auth" else 400
        return JSONResponse(status_code=status, content={"detail": exc.message, "code": exc.code})

    @app.exception_handler(Exception)
    async def unexpected_handler(request: Request, exc: Exception):
        logger.exception(
            "unhandled error",
            extra={"event": "http_error", "status_code": 500, "entity_type": request.url.path},
        )
        return JSONResponse(status_code=500, content={"detail": "Внутренняя ошибка"})

    return app


app = create_app()

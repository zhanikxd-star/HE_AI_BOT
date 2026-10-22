"""Button-driven Telegram handlers. Polling starts only when TELEGRAM_BOT_TOKEN is set."""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from uuid import UUID

from aiogram import F, Router
from aiogram.filters import CommandObject, CommandStart, Filter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, Message, ReplyKeyboardMarkup

from app.bot.i18n import text
from app.db import session_scope
from app.errors import DomainError
from app.services.announcements import set_rsvp
from app.services.collections import declare_payment, peer_view, respond
from app.services.employees import bind_telegram, find_by_telegram, set_own_consent, set_own_notifications
from app.services.onboarding import active_application, answer, choose_existing, choose_sales, greet, set_consent

logger = logging.getLogger(__name__)
router = Router()


class PayFlow(StatesGroup):
    amount = State()


class InOnboarding(Filter):
    async def __call__(self, message: Message) -> bool:
        if message.from_user is None or not message.text:
            return False
        if message.text in {"Объявления", "Сборы", "Настройки", "Я новый в отделе продаж", "Я уже в команде"}:
            return False
        with session_scope() as session:
            return active_application(session, message.from_user.id) is not None


def choice_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Я новый в отделе продаж")], [KeyboardButton(text="Я уже в команде")]],
        resize_keyboard=True,
    )


def consent_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="Да", callback_data="ob:yes"),
            InlineKeyboardButton(text="Нет", callback_data="ob:no"),
        ]]
    )


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Объявления"), KeyboardButton(text="Сборы")],
            [KeyboardButton(text="Настройки")],
        ],
        resize_keyboard=True,
    )


def settings_keyboard(consent: bool, announcements: bool, collections: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Поздравление: да" if not consent else "Поздравление: нет", callback_data="s:c")],
            [InlineKeyboardButton(text="Объявления вкл/выкл", callback_data="s:a")],
            [InlineKeyboardButton(text="Сборы вкл/выкл", callback_data="s:k")],
        ]
    )


@router.message(CommandStart())
async def start(message: Message, command: CommandObject) -> None:
    token = (command.args or "").strip()
    telegram_id = message.from_user.id if message.from_user else 0
    username = message.from_user.username if message.from_user else None
    with session_scope() as session:
        if token:
            try:
                employee = bind_telegram(session, token, telegram_id, username)
            except DomainError as exc:
                await message.answer(exc.message)
                return
            await message.answer(text("welcome", name=employee.preferred_name), reply_markup=main_menu())
            return
        reply = greet(session, telegram_id)
    await _show(message, reply)


@router.message(F.text == "Я новый в отделе продаж")
async def sales_onboarding(message: Message) -> None:
    if message.from_user is None:
        return
    with session_scope() as session:
        reply = choose_sales(session, message.from_user.id, message.from_user.username)
    await _show(message, reply)


@router.message(F.text == "Я уже в команде")
async def existing_teammate(message: Message) -> None:
    if message.from_user is None:
        return
    with session_scope() as session:
        reply = choose_existing(session, message.from_user.id)
    await _show(message, reply)


@router.callback_query(F.data.in_({"ob:yes", "ob:no"}))
async def onboarding_consent(callback: CallbackQuery) -> None:
    if callback.data is None:
        return
    with session_scope() as session:
        try:
            reply = set_consent(session, callback.from_user.id, callback.from_user.username, callback.data == "ob:yes")
        except DomainError as exc:
            await callback.answer(exc.message, show_alert=True)
            return
    await callback.answer()
    if callback.message:
        await _show(callback.message, reply)


@router.message(InOnboarding())
async def onboarding_answer(message: Message) -> None:
    if message.from_user is None:
        return
    with session_scope() as session:
        try:
            reply = answer(session, message.from_user.id, message.from_user.username, message.text or "")
        except DomainError as exc:
            await message.answer(exc.message)
            return
    await _show(message, reply)


@router.message(F.text == "Настройки")
async def settings(message: Message) -> None:
    employee = _bound(message)
    if employee is None:
        await message.answer(text("need_invite"))
        return
    prefs = employee["notification_settings"]
    await message.answer(
        text(
            "settings",
            consent=text("consent_on") if employee["consent"] else text("consent_off"),
            announcements=text("consent_on") if prefs.get("announcements", True) else text("consent_off"),
            collections=text("consent_on") if prefs.get("collections", True) else text("consent_off"),
        ),
        reply_markup=settings_keyboard(employee["consent"], prefs.get("announcements", True), prefs.get("collections", True)),
    )


@router.callback_query(F.data == "s:c")
async def toggle_consent(callback: CallbackQuery) -> None:
    employee_id = _employee_id(callback)
    if employee_id is None:
        await callback.answer(text("need_invite"), show_alert=True)
        return
    with session_scope() as session:
        current = find_by_telegram(session, callback.from_user.id)
        updated = set_own_consent(session, employee_id, not current.public_greeting_consent)
        value = updated.public_greeting_consent
    await callback.answer(text("saved"))
    if callback.message:
        await callback.message.answer("Публичное поздравление включено." if value else "Публичное поздравление выключено.")


@router.callback_query(F.data.in_({"s:a", "s:k"}))
async def toggle_notifications(callback: CallbackQuery) -> None:
    employee_id = _employee_id(callback)
    if employee_id is None:
        await callback.answer(text("need_invite"), show_alert=True)
        return
    with session_scope() as session:
        current = find_by_telegram(session, callback.from_user.id)
        prefs = dict(current.notification_settings or {})
        if callback.data == "s:a":
            set_own_notifications(session, employee_id, announcements=not prefs.get("announcements", True), collections=None)
        else:
            set_own_notifications(session, employee_id, announcements=None, collections=not prefs.get("collections", True))
    await callback.answer(text("saved"))


@router.message(F.text == "Сборы")
async def my_collections(message: Message) -> None:
    employee = _bound(message)
    if employee is None:
        await message.answer(text("need_invite"))
        return
    from sqlalchemy import select

    from app.models import CollectionParticipant

    with session_scope() as session:
        rows = list(
            session.scalars(
                select(CollectionParticipant).where(CollectionParticipant.employee_id == UUID(employee["id"]))
            )
        )
        if not rows:
            await message.answer(text("no_collections"))
            return
        for row in rows:
            view = peer_view(session, row.collection_id, UUID(employee["id"]))
            await message.answer(_collection_card(view), reply_markup=_collection_keyboard(view))


@router.callback_query(F.data.startswith("c:a:"))
async def accept_collection(callback: CallbackQuery, state: FSMContext) -> None:
    await _collection_decision(callback, state, "accept")


@router.callback_query(F.data.startswith("c:d:"))
async def decline_collection(callback: CallbackQuery, state: FSMContext) -> None:
    await _collection_decision(callback, state, "decline")


@router.callback_query(F.data.startswith("c:p:"))
async def paid(callback: CallbackQuery, state: FSMContext) -> None:
    employee_id = _employee_id(callback)
    if employee_id is None or callback.data is None:
        await callback.answer(text("need_invite"), show_alert=True)
        return
    collection_id = UUID(callback.data.split(":", 2)[2])
    with session_scope() as session:
        view = peer_view(session, collection_id, employee_id)
        if view["contribution_mode"] == "arbitrary":
            await state.set_state(PayFlow.amount)
            await state.update_data(collection_id=str(collection_id))
            await callback.answer()
            if callback.message:
                await callback.message.answer(text("amount_prompt"))
            return
        declare_payment(session, collection_id, employee_id, None)
    await callback.answer(text("declared"))


@router.message(PayFlow.amount)
async def amount(message: Message, state: FSMContext) -> None:
    employee = _bound(message)
    if employee is None:
        await message.answer(text("need_invite"))
        return
    raw = (message.text or "").replace(" ", "").replace(",", ".")
    try:
        value = Decimal(raw)
    except InvalidOperation:
        await message.answer(text("amount_bad"))
        return
    data = await state.get_data()
    with session_scope() as session:
        try:
            declare_payment(session, UUID(data["collection_id"]), UUID(employee["id"]), value)
        except DomainError as exc:
            await message.answer(exc.message)
            return
    await state.clear()
    await message.answer(text("declared"))


@router.message(F.text == "Объявления")
async def my_announcements(message: Message) -> None:
    employee = _bound(message)
    if employee is None:
        await message.answer(text("need_invite"))
        return
    from sqlalchemy import select

    from app.models import Announcement, AnnouncementDelivery

    with session_scope() as session:
        deliveries = list(
            session.scalars(select(AnnouncementDelivery).where(AnnouncementDelivery.employee_id == UUID(employee["id"])))
        )
        visible = [item for item in deliveries if item.delivery_status in {"sent", "simulated"}]
        if not visible:
            await message.answer(text("no_announcements"))
            return
        for delivery in visible:
            announcement = session.get(Announcement, delivery.announcement_id)
            if announcement is None:
                continue
            keyboard = None
            if announcement.requires_rsvp:
                keyboard = InlineKeyboardMarkup(
                    inline_keyboard=[[
                        InlineKeyboardButton(text="Буду", callback_data=f"r:y:{announcement.id}"),
                        InlineKeyboardButton(text="Не смогу", callback_data=f"r:n:{announcement.id}"),
                    ]]
                )
            await message.answer(f"{announcement.title}\n\n{announcement.body}", reply_markup=keyboard)


@router.callback_query(F.data.startswith("r:"))
async def rsvp(callback: CallbackQuery) -> None:
    employee_id = _employee_id(callback)
    if employee_id is None or callback.data is None:
        await callback.answer(text("need_invite"), show_alert=True)
        return
    _, code, raw_id = callback.data.split(":", 2)
    choice = "will_attend" if code == "y" else "cannot_attend"
    with session_scope() as session:
        try:
            set_rsvp(session, UUID(raw_id), employee_id, choice)
        except DomainError as exc:
            await callback.answer(exc.message, show_alert=True)
            return
    await callback.answer(text("rsvp_yes") if choice == "will_attend" else text("rsvp_no"))


@router.message()
async def fallback(message: Message) -> None:
    await message.answer(text("unknown"), reply_markup=main_menu())


async def _collection_decision(callback: CallbackQuery, state: FSMContext, decision: str) -> None:
    employee_id = _employee_id(callback)
    if employee_id is None or callback.data is None:
        await callback.answer(text("need_invite"), show_alert=True)
        return
    collection_id = UUID(callback.data.split(":", 2)[2])
    with session_scope() as session:
        try:
            respond(session, collection_id, employee_id, decision)
            view = peer_view(session, collection_id, employee_id)
        except DomainError as exc:
            await callback.answer(exc.message, show_alert=True)
            return
    if decision == "decline":
        await callback.answer(text("declined"))
        return
    details = view.get("payment_details") or ""
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            text(
                "accepted",
                details=details,
                amount=view.get("asked_amount") or "",
                currency=view.get("currency") or "",
            ),
            reply_markup=_paid_keyboard(str(collection_id)),
        )
    if view["contribution_mode"] == "arbitrary":
        await state.set_state(PayFlow.amount)
        await state.update_data(collection_id=str(collection_id))
        if callback.message:
            await callback.message.answer(text("amount_prompt"))


def _collection_card(view: dict) -> str:
    lines = [view["title"], view.get("description") or "", f"Ваш статус: {_status_label(view['own_status'])}"]
    if view.get("asked_amount"):
        lines.append(f"Фиксированный взнос: {view['asked_amount']} {view.get('currency') or ''}".strip())
    if view.get("payment_details"):
        lines.append(str(view["payment_details"]))
    return "\n".join(line for line in lines if line)


def _collection_keyboard(view: dict) -> InlineKeyboardMarkup | None:
    if view.get("collection_status") != "open" or view["own_status"] != "invited":
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="Участвовать", callback_data=f"c:a:{view['id']}"),
            InlineKeyboardButton(text="Пропустить", callback_data=f"c:d:{view['id']}"),
        ]]
    )


def _paid_keyboard(collection_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Я перевёл", callback_data=f"c:p:{collection_id}")]]
    )


def _status_label(status: str) -> str:  # noqa: the labels stay in Russian for the employee bot
    return {
        "invited": "приглашение",
        "accepted": "участвуете",
        "declined": "пропустили",
        "payment_declared": "перевод отмечен, ждём HR",
        "confirmed": "HR подтвердил получение",
    }.get(status, status)


async def _show(message: Message, reply) -> None:
    markup = main_menu() if reply.menu else choice_menu() if reply.choice else None
    await message.answer(reply.text, reply_markup=consent_keyboard() if reply.consent else markup)
    for item in reply.documents:
        await message.answer_document(item["url"], caption=item.get("name") or None)


def _bound(message: Message) -> dict | None:
    if message.from_user is None:
        return None
    with session_scope() as session:
        employee = find_by_telegram(session, message.from_user.id)
        if employee is None:
            return None
        return {
            "id": str(employee.id),
            "consent": employee.public_greeting_consent,
            "notification_settings": dict(employee.notification_settings or {}),
        }


def _employee_id(callback: CallbackQuery) -> UUID | None:
    with session_scope() as session:
        employee = find_by_telegram(session, callback.from_user.id)
        if employee is None:
            return None
        return employee.id

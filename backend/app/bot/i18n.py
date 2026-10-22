"""Russian bot copy. kk and en can be added beside RU."""

RU = {
    "need_invite": "Нужна персональная ссылка от HR. Откройте её и нажмите «Запустить».",
    "invalid_invite": "Ссылка не подошла. Попросите HR прислать новую.",
    "welcome": "{name}, привет. Здесь объявления, сборы и настройки. Кнопки внизу.",
    "menu_hint": "Выбери раздел кнопкой.",
    "no_announcements": "Новых объявлений нет.",
    "no_collections": "Открытых сборов для вас нет.",
    "settings": "Публичное поздравление: {consent}.\nОбъявления: {announcements}.\nСборы: {collections}.",
    "consent_on": "включено",
    "consent_off": "выключено",
    "saved": "Сохранено.",
    "declined": "Вы пропустили сбор. Объяснять отказ не нужно.",
    "accepted": "Спасибо. Фиксированный взнос: {amount} {currency}.\n{details}\nПеревод не считается полученным, пока HR его не подтвердит.",
    "declared": "HR увидит, что вы отметили перевод. Это ещё не подтверждение оплаты.",
    "cancelled": "Этот сбор закрыт.",
    "rsvp_yes": "Записали: будете.",
    "rsvp_no": "Записали: не получится.",
    "amount_prompt": "Введите сумму перевода числом.",
    "amount_bad": "Нужно положительное число.",
    "unknown": "Нажмите кнопку меню.",
}


def text(key: str, **kwargs: object) -> str:
    template = RU[key]
    return template.format(**kwargs) if kwargs else template

# HR-агент Impact Admissions

Веб для HR и Telegram-бот для сотрудников: дни рождения, сборы на подарок, объявления и анкета нового сотрудника отдела продаж. Живые Telegram, OpenAI и Notion включаются только переменными окружения. Пока ключей нет, работают тестовые адаптеры.

## Локальный запуск

Нужны Python 3.12, Node.js 22 и PostgreSQL 16.

```bash
cp .env.example .env
```

В `.env` не записывайте настоящие `TELEGRAM_BOT_TOKEN`, `OPENAI_API_KEY` и `NOTION_API_KEY`. Пустые значения оставляют тестовые адаптеры.

```bash
cd backend
python3 -m pip install -r requirements.txt
DATABASE_URL=postgresql+psycopg://hr:hr@127.0.0.1:5432/hr python3 -m alembic upgrade head
python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

В другом окне: `python3 -m app.worker` из `backend`. Бот `python3 -m app.bot` без токена к Telegram не подключается.

Фронтенд:

```bash
cd frontend
npm install
npm run dev
```

Интерфейс: http://localhost:3000. API: http://localhost:8000. Локальный суперадмин создаётся один раз, если `APP_ENV=local`, заданы `BOOTSTRAP_ADMIN_EMAIL` и `BOOTSTRAP_ADMIN_PASSWORD` и пользователей ещё нет.

Docker Compose описан в `docker-compose.yml` (Postgres, backend, worker, bot, frontend). На машине, где собиралась эта версия, Docker не был установлен, поэтому миграции и тесты прогнаны на локальном PostgreSQL 16.

Резервная копия: `DATABASE_URL=... ./scripts/backup_db.sh backup.dump`.

## Деплой

Поднимите PostgreSQL, прогоните `alembic upgrade head`, запустите API, воркер и бота. Секреты передайте окружением, не файлом в образе. Фронтенд ходит на API с `CORS_ORIGINS`. Для живого бота нужен `TELEGRAM_BOT_TOKEN`. Для живой модели — `OPENAI_API_KEY` и провайдер `openai` в настройках. Для записи анкеты в Notion — `NOTION_API_KEY`. Id базы уже лежит в настройках организации.

## Роли

- Суперадмин меняет настройки организации и назначает HR.
- HR ведёт сотрудников, поздравления, сборы и объявления.
- Сотрудник пользуется только ботом.
- Новый человек отдела продаж заполняет анкету кнопками после `/start`.

## Что реализовано и что проверено

Реализовано:

- сотрудники, импорт, дубли, приглашение в бота, согласие на публичное поздравление;
- идемпотентные поздравления и рассылки, отмена ещё не отправленного;
- сборы с исключением именинника, скрытые от коллег отказы и суммы, реквизиты и фиксированная сумма из настроек организации;
- черновики ассистента без самостоятельной отправки;
- анкета отдела продаж в локальную базу, повтор того же Telegram id не создаёт вторую карточку, пустой пакет обучения не выдумывает файлы;
- в организации записаны чат «Контент impact» (`-1002615527142`, supergroup) и база Notion Document Hub (`40159421a41f80c1bfd5ce5b06de3213`, database).

Проверено здесь, без сети к Telegram, OpenAI и Notion:

- `cd backend && python3 -m pytest -q -p no:cacheprovider` — 27 тестов, код выхода 0. Предупреждения pytest только о том, что классы тестовых адаптеров не собираются как тесты.
- `DATABASE_URL=postgresql+psycopg://hr:hr@127.0.0.1:5432/hr python3 -m alembic upgrade head` — ревизия `004_onboarding`. Docker на этой машине не установлен, поэтому миграция шла в локальный PostgreSQL 16.
- Точка входа бота: `python -m app.bot`. Импорт проверен. Без `TELEGRAM_BOT_TOKEN` процесс пишет в журнал, что опрос Telegram не запущен, и не вызывает `start_polling`. Живой процесс бота здесь не запускался.
- `npm run build` во фронтенде прошёл: Next.js 14 собрал 12 страниц. На файловой системе этого каталога `npm install` упирается в `ENOSYS` при rename, поэтому сборка выполнена из копии исходников. В Docker зависимости ставятся уже внутри образа.

Не проверялось на живом Telegram, живой модели и живом Notion. `TELEGRAM_BOT_TOKEN`, `OPENAI_API_KEY` и `NOTION_API_KEY` в этом окружении нет, в файлы они не записывались. Подтверждение чата и базы Document Hub пришло извне и записано в настройки организации.

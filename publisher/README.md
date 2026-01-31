# Publisher (Telegram Stories)

Отдельный сервис, который публикует Telegram Stories через MTProto (Telethon) под USER-аккаунтом и берет задания из той же SQLite БД, что и бот.

## Требования

- Python 3.10+
- `ffprobe` (желательно для чтения метаданных видео)
- Доступ к TG API ID/HASH

## Получение TG_API_ID / TG_API_HASH

1. Перейдите на [my.telegram.org](https://my.telegram.org).
2. Войдите в аккаунт Telegram.
3. Откройте раздел **API development tools**.
4. Создайте приложение и получите `api_id` и `api_hash`.

## Установка

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r publisher/requirements.txt
```

Создайте `.env` (можно скопировать `publisher/.env.publisher.example`) и заполните переменные.

## Запуск

Однократный проход:

```bash
python -m publisher.main --once
```

Постоянный polling:

```bash
python -m publisher.main
```

Первый запуск запросит код из Telegram (и 2FA пароль, если включен) — сессия сохранится в `TG_SESSION_PATH`.

## Где хранится сессия

По умолчанию: `publisher/session/mom.session`.

## Добавление delivery в БД (пример)

```sql
INSERT INTO deliveries (task_id, target, status, created_at)
VALUES (123, 'tg_story', 'queued', datetime('now'));
```

Publisher подберет задачи только если `tasks.prepared_path` заполнен.

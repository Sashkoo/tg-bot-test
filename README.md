# Telegram-бот для анкет кандидатов

Легкий бот на Python и `aiogram`, который принимает анкету кандидата, валидирует длинные ответы, сохраняет данные в `SQLite` и отправляет валидные анкеты в административный чат Telegram.

## Что умеет бот

- запускает последовательную анкету после `/start`
- сохраняет ответы в `SQLite`
- продолжает анкету после перезапуска бота, если кандидат не закончил заполнение
- автоматически отклоняет анкету, если ответ на подробный вопрос короче 100 символов
- не позволяет отправить анкету повторно
- отправляет валидную анкету в админ-чат с кнопками `Пригласить` и `Отказать`
- уведомляет кандидата о решении администратора
- пишет логи ошибок в стандартный вывод

## Структура проекта

- `bot.py` - основной файл бота
- `config.py` - загрузка переменных окружения
- `database.py` - работа с `SQLite`
- `questionnaire.py` - тексты и список вопросов
- `.env.example` - пример переменных окружения

## Быстрый запуск локально

1. Установите Python 3.11+.
2. Создайте виртуальное окружение:

```powershell
python -m venv .venv
.venv\Scripts\activate
```

3. Установите зависимости:

```powershell
pip install -r requirements.txt
```

4. Создайте `.env` на основе примера:

```powershell
copy .env.example .env
```

5. Заполните `.env`:

```env
BOT_TOKEN=токен_бота_от_BotFather
ADMIN_CHAT_ID=telegram_id_админа_или_чата
DATABASE_PATH=bot.db
```

6. Запустите бота:

```powershell
python bot.py
```

## Как узнать `ADMIN_CHAT_ID`

- Для личного аккаунта администратора можно использовать его Telegram ID.
- Для группы или канала нужно добавить бота в чат и использовать числовой ID этого чата.
- Если используется группа, боту обычно нужны права на отправку сообщений.

## Какие вопросы требуют минимум 100 символов

Сейчас ограничение включено для вопросов, где в ТЗ явно нужен развернутый ответ. Список находится в `questionnaire.py` в поле `min_length` у конкретных вопросов. Если захотите, можно быстро поменять правила без изменения остального кода.

## Хранение данных

Все данные сохраняются в `SQLite`-файл, путь к которому задается через `DATABASE_PATH`.

Основные поля:

- `telegram_id`
- `username`
- `created_at`
- `completed_at`
- `answers_json`
- `status`
- `current_question_index`

Статусы:

- `in_progress`
- `new`
- `invited`
- `rejected`
- `auto_rejected`

## Деплой на VPS

Общий порядок:

1. Установить Python 3.11+ на сервер.
2. Скопировать проект на сервер.
3. Создать виртуальное окружение и установить зависимости.
4. Создать `.env`.
5. Запустить бота через `systemd`, `pm2` или Docker.

### Пример `systemd` для Linux

Файл `/etc/systemd/system/telegram-bot-margo.service`:

```ini
[Unit]
Description=Telegram bot for candidate questionnaires
After=network.target

[Service]
User=deploy
WorkingDirectory=/opt/telegram_bot_margo
ExecStart=/opt/telegram_bot_margo/.venv/bin/python /opt/telegram_bot_margo/bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Дальше:

```bash
sudo systemctl daemon-reload
sudo systemctl enable telegram-bot-margo
sudo systemctl start telegram-bot-margo
sudo systemctl status telegram-bot-margo
```

## Важные замечания

- Бот использует polling, поэтому для него не нужен webhook.
- Если кандидат уже завершил анкету или был автоматически отклонен, повторная подача запрещена.
- Если кандидат начал анкету, но не закончил, бот продолжит с последнего сохраненного вопроса.
- Для кнопок администратора бот должен иметь возможность писать кандидату в личные сообщения. Если пользователь заблокировал бота, сообщение не доставится, но статус в базе обновится.

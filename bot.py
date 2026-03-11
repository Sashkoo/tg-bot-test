import asyncio
import html
import logging
from datetime import datetime

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import load_settings
from database import Database
from questionnaire import (
    ALREADY_SUBMITTED_TEXT,
    INTRO_TEXT,
    INVITE_TEXT,
    QUESTIONS,
    REJECT_TEXT,
    SUCCESS_TEXT,
    TOO_SHORT_TEXT,
)


router = Router()
settings = load_settings()
db = Database(settings.database_path)
TELEGRAM_MESSAGE_LIMIT = 4000


def admin_keyboard(telegram_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Пригласить", callback_data=f"invite:{telegram_id}"),
                InlineKeyboardButton(text="Отказать", callback_data=f"reject:{telegram_id}"),
            ]
        ]
    )


def format_question(question_index: int) -> str:
    question = QUESTIONS[question_index]
    extra = ""
    if question.min_length:
        extra = f"\n\nМинимальный объем ответа: {question.min_length} символов."
    return f"Вопрос {question_index + 1} из {len(QUESTIONS)}.\n{question.number}. {question.text}{extra}"


def format_admin_message(application: dict) -> str:
    username = application.get("username") or "-"
    completed_at = application.get("completed_at") or application.get("updated_at")
    answers = application.get("answers", {})

    try:
        filled_at = datetime.fromisoformat(completed_at).strftime("%d.%m.%Y %H:%M:%S")
    except (TypeError, ValueError):
        filled_at = str(completed_at)

    answer_blocks = []
    for question in QUESTIONS:
        safe_question = html.escape(question.text)
        safe_answer = html.escape(answers.get(str(question.number), "-"))
        answer_blocks.append(f"{question.number}. {safe_question}\n{safe_answer}")

    full_name = html.escape(application.get("full_name") or "-")
    username_line = f"@{html.escape(username)}" if username != "-" else "-"

    return (
        "<b>Новая анкета кандидата</b>\n\n"
        f"<b>Имя в Telegram:</b> {full_name}\n"
        f"<b>Username:</b> {username_line}"
        f"\n<b>Telegram ID:</b> <code>{application['telegram_id']}</code>\n"
        f"<b>Дата заполнения:</b> {filled_at}\n\n"
        "<b>Ответы:</b>\n\n"
        + "\n\n".join(answer_blocks)
    )


def split_text(text: str, max_length: int = TELEGRAM_MESSAGE_LIMIT) -> list[str]:
    if len(text) <= max_length:
        return [text]

    parts: list[str] = []
    current = ""

    for block in text.split("\n\n"):
        candidate = f"{current}\n\n{block}" if current else block
        if len(candidate) <= max_length:
            current = candidate
            continue

        if current:
            parts.append(current)
            current = ""

        if len(block) <= max_length:
            current = block
            continue

        start = 0
        while start < len(block):
            parts.append(block[start : start + max_length])
            start += max_length

    if current:
        parts.append(current)

    return parts


async def send_application_to_admin(bot: Bot, application: dict) -> None:
    message_parts = split_text(format_admin_message(application))
    first_message = None

    for index, part in enumerate(message_parts):
        sent_message = await bot.send_message(
            chat_id=settings.admin_chat_id,
            text=part,
            reply_markup=admin_keyboard(application["telegram_id"]) if index == 0 else None,
            reply_to_message_id=first_message.message_id if index > 0 and first_message else None,
        )
        if first_message is None:
            first_message = sent_message


async def send_current_question(message: Message, question_index: int) -> None:
    await message.answer(format_question(question_index))


def user_has_final_status(application: dict | None) -> bool:
    return application is not None and application["status"] in {
        "new",
        "invited",
        "rejected",
        "auto_rejected",
    }


@router.message(CommandStart())
async def start_handler(message: Message) -> None:
    user = message.from_user
    if user is None:
        return

    application = db.get_application(user.id)

    if user_has_final_status(application):
        await message.answer(ALREADY_SUBMITTED_TEXT)
        return

    if application and application["status"] == "in_progress":
        await message.answer(
            "Вы уже начали заполнять анкету. Продолжим с последнего сохраненного вопроса."
        )
        await send_current_question(message, application["current_question_index"])
        return

    db.create_or_reset_in_progress(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        full_name=user.full_name,
    )

    await message.answer(INTRO_TEXT)
    await send_current_question(message, 0)


@router.message(F.text)
async def questionnaire_handler(message: Message) -> None:
    user = message.from_user
    if user is None:
        return

    application = db.get_application(user.id)
    if application is None or application["status"] != "in_progress":
        return

    question_index = application["current_question_index"]
    if question_index >= len(QUESTIONS):
        await message.answer(ALREADY_SUBMITTED_TEXT)
        return

    answer = (message.text or "").strip()
    if not answer:
        await message.answer("Пожалуйста, отправьте текстовый ответ на вопрос.")
        return

    question = QUESTIONS[question_index]
    if question.min_length and len(answer) < question.min_length:
        db.save_answer(user.id, question.number, answer, question_index)
        db.mark_completed(user.id, "auto_rejected")
        await message.answer(TOO_SHORT_TEXT)
        return

    next_question_index = question_index + 1
    updated_application = db.save_answer(user.id, question.number, answer, next_question_index)
    if updated_application is None:
        await message.answer("Не удалось сохранить ответ. Попробуйте еще раз.")
        return

    if next_question_index < len(QUESTIONS):
        await send_current_question(message, next_question_index)
        return

    db.mark_completed(user.id, "new")
    final_application = db.get_application(user.id)
    await message.answer(SUCCESS_TEXT)

    if final_application is None:
        logging.error("Анкета пользователя %s не найдена после завершения.", user.id)
        return

    await send_application_to_admin(message.bot, final_application)


@router.callback_query(F.data.startswith("invite:"))
async def invite_candidate(callback: CallbackQuery) -> None:
    await process_admin_action(callback, "invite")


@router.callback_query(F.data.startswith("reject:"))
async def reject_candidate(callback: CallbackQuery) -> None:
    await process_admin_action(callback, "reject")


async def process_admin_action(callback: CallbackQuery, action: str) -> None:
    if callback.message is None or callback.data is None:
        await callback.answer()
        return

    user_id = int(callback.data.split(":", maxsplit=1)[1])
    application = db.get_application(user_id)
    if application is None:
        await callback.answer("Анкета не найдена.", show_alert=True)
        return

    if action == "invite":
        status = "invited"
        candidate_text = INVITE_TEXT
        result_text = "Кандидат приглашен"
    else:
        status = "rejected"
        candidate_text = REJECT_TEXT
        result_text = "Кандидату отправлен отказ"

    if application["status"] == status:
        await callback.answer("Это действие уже выполнено.")
        return

    db.update_status(user_id, status)

    try:
        await callback.bot.send_message(user_id, candidate_text)
    except TelegramForbiddenError:
        result_text += ", но бот не смог написать пользователю"
    except TelegramBadRequest as exc:
        logging.warning("Не удалось отправить сообщение кандидату %s: %s", user_id, exc)
        result_text += ", но сообщение пользователю не доставлено"

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        pass

    await callback.message.answer(f"{result_text}. Telegram ID: {user_id}")
    await callback.answer("Готово")


@router.message()
async def fallback_handler(message: Message) -> None:
    application = db.get_application(message.from_user.id) if message.from_user else None
    if application and application["status"] == "in_progress":
        await message.answer("Пожалуйста, отправляйте ответы текстом.")


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher()
    dispatcher.include_router(router)

    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Бот остановлен.")

import asyncio
import base64
import io
import logging

from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    BufferedInputFile,
)
from aiogram.filters import Command, CommandStart
from aiogram.enums import ParseMode, ChatAction

import config
import database as db
import claude_api

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)


# ──────────────────────── Auth ────────────────────────

def is_owner(message: Message) -> bool:
    return message.from_user.id == config.OWNER_ID


# ──────────────────────── Helpers ─────────────────────

def split_message(text: str, limit: int = config.TG_MSG_LIMIT) -> list[str]:
    """Split long text into Telegram-safe chunks, preserving code blocks."""
    if len(text) <= limit:
        return [text]

    chunks = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break

        # Try to split at a newline near the limit
        split_pos = text.rfind("\n", 0, limit)
        if split_pos == -1 or split_pos < limit // 2:
            # No good newline — split at space
            split_pos = text.rfind(" ", 0, limit)
        if split_pos == -1 or split_pos < limit // 2:
            split_pos = limit

        chunks.append(text[:split_pos])
        text = text[split_pos:].lstrip("\n")

    return chunks


async def send_long_message(message: Message, text: str):
    """Send a potentially long message, split into chunks."""
    chunks = split_message(text)
    for i, chunk in enumerate(chunks):
        try:
            await message.answer(chunk, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            # Markdown parsing failed — send as plain text
            await message.answer(chunk)


def model_short_name(model: str) -> str:
    for name, full in config.MODELS.items():
        if full == model:
            return name
    return model.split("-")[1] if "-" in model else model


# ──────────────────────── Commands ────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message):
    if not is_owner(message):
        return await message.answer("⛔ Private bot.")

    await message.answer(
        "🤖 *Claude Telegram Bot*\n\n"
        "Просто пиши — я отвечу через Claude API.\n"
        "Можешь отправлять фото, документы и голосовые.\n\n"
        "*Команды:*\n"
        "/new — новый диалог\n"
        "/model — сменить модель\n"
        "/project — сменить системный промпт\n"
        "/history — список диалогов\n"
        "/usage — статистика расходов\n"
        "/status — текущие настройки\n"
        "/search on|off — веб-поиск\n"
        "/n8n [запрос] — управление n8n воркфлоу\n"
        "/help — эта справка",
        parse_mode=ParseMode.MARKDOWN,
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    if not is_owner(message):
        return
    await cmd_start(message)


@router.message(Command("new"))
async def cmd_new(message: Message):
    if not is_owner(message):
        return

    # Get current settings to carry over
    current = await db.get_or_create_conversation(message.from_user.id)
    conv = await db.new_conversation(
        user_id=message.from_user.id,
        system_prompt_key=current.system_prompt_key,
        model=current.model,
    )
    await message.answer(
        f"🆕 Новый диалог #{conv.id}\n"
        f"Модель: `{model_short_name(conv.model)}`\n"
        f"Проект: `{conv.system_prompt_key}`",
        parse_mode=ParseMode.MARKDOWN,
    )


@router.message(Command("model"))
async def cmd_model(message: Message):
    if not is_owner(message):
        return

    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        name = args[1].strip().lower()
        if name in config.MODELS:
            conv = await db.get_or_create_conversation(message.from_user.id)
            await db.update_conversation(conv.id, model=config.MODELS[name])
            await message.answer(f"✅ Модель: *{name}*", parse_mode=ParseMode.MARKDOWN)
        else:
            models_list = ", ".join(config.MODELS.keys())
            await message.answer(f"❌ Доступные модели: `{models_list}`", parse_mode=ParseMode.MARKDOWN)
        return

    # Show buttons
    conv = await db.get_or_create_conversation(message.from_user.id)
    current = model_short_name(conv.model)

    buttons = []
    for name, full_name in config.MODELS.items():
        label = f"{'✓ ' if full_name == conv.model else ''}{name}"
        cost = config.COSTS.get(full_name, {})
        label += f" (${cost.get('input', '?')}/{cost.get('output', '?')} per 1M)"
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"model:{name}")])

    await message.answer(
        f"Текущая модель: *{current}*\nВыбери модель:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode=ParseMode.MARKDOWN,
    )


@router.callback_query(F.data.startswith("model:"))
async def cb_model(callback: CallbackQuery):
    if callback.from_user.id != config.OWNER_ID:
        return

    name = callback.data.split(":")[1]
    if name in config.MODELS:
        conv = await db.get_or_create_conversation(callback.from_user.id)
        await db.update_conversation(conv.id, model=config.MODELS[name])
        await callback.message.edit_text(f"✅ Модель: *{name}*", parse_mode=ParseMode.MARKDOWN)
    await callback.answer()


@router.message(Command("project"))
async def cmd_project(message: Message):
    if not is_owner(message):
        return

    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        name = args[1].strip().lower()
        if name in config.SYSTEM_PROMPTS:
            conv = await db.get_or_create_conversation(message.from_user.id)
            await db.update_conversation(conv.id, system_prompt_key=name)
            await message.answer(f"✅ Проект: *{name}*", parse_mode=ParseMode.MARKDOWN)
        else:
            keys = ", ".join(config.SYSTEM_PROMPTS.keys())
            await message.answer(f"❌ Доступные проекты: `{keys}`", parse_mode=ParseMode.MARKDOWN)
        return

    conv = await db.get_or_create_conversation(message.from_user.id)
    buttons = []
    for name in config.SYSTEM_PROMPTS:
        label = f"{'✓ ' if name == conv.system_prompt_key else ''}{name}"
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"project:{name}")])

    await message.answer(
        f"Текущий проект: *{conv.system_prompt_key}*\nВыбери проект:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode=ParseMode.MARKDOWN,
    )


@router.callback_query(F.data.startswith("project:"))
async def cb_project(callback: CallbackQuery):
    if callback.from_user.id != config.OWNER_ID:
        return

    name = callback.data.split(":")[1]
    if name in config.SYSTEM_PROMPTS:
        conv = await db.get_or_create_conversation(callback.from_user.id)
        await db.update_conversation(conv.id, system_prompt_key=name)
        await callback.message.edit_text(f"✅ Проект: *{name}*", parse_mode=ParseMode.MARKDOWN)
    await callback.answer()


@router.message(Command("status"))
async def cmd_status(message: Message):
    if not is_owner(message):
        return

    conv = await db.get_or_create_conversation(message.from_user.id)
    msgs = await db.get_conversation_messages(conv.id)
    n8n_connected = bool(config.N8N_API_URL and config.N8N_API_KEY)
    web_search = web_search_enabled.get(message.from_user.id, True)

    await message.answer(
        f"📊 *Статус*\n\n"
        f"Диалог: #{conv.id}\n"
        f"Модель: `{model_short_name(conv.model)}`\n"
        f"Проект: `{conv.system_prompt_key}`\n"
        f"Сообщений: {len(msgs)}\n"
        f"Веб-поиск: {'✅' if web_search else '❌'}\n"
        f"n8n: {'✅ подключён' if n8n_connected else '❌ не настроен'}",
        parse_mode=ParseMode.MARKDOWN,
    )


@router.message(Command("search"))
async def cmd_search(message: Message):
    if not is_owner(message):
        return

    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        val = args[1].strip().lower()
        if val in ("on", "1", "да"):
            web_search_enabled[message.from_user.id] = True
            await message.answer("✅ Веб-поиск *включён*", parse_mode=ParseMode.MARKDOWN)
        elif val in ("off", "0", "нет"):
            web_search_enabled[message.from_user.id] = False
            await message.answer("❌ Веб-поиск *выключен*", parse_mode=ParseMode.MARKDOWN)
        else:
            await message.answer("Используй: `/search on` или `/search off`", parse_mode=ParseMode.MARKDOWN)
    else:
        current = web_search_enabled.get(message.from_user.id, True)
        await message.answer(
            f"Веб-поиск: {'✅ включён' if current else '❌ выключен'}\n"
            "Используй: `/search on` или `/search off`",
            parse_mode=ParseMode.MARKDOWN,
        )


@router.message(Command("n8n"))
async def cmd_n8n(message: Message):
    """Quick n8n status — shortcut to ask Claude about workflows."""
    if not is_owner(message):
        return

    args = message.text.split(maxsplit=1)
    query = args[1] if len(args) > 1 else "Покажи список всех моих воркфлоу в n8n и их статусы"
    await process_text_message(message, query)


@router.message(Command("usage"))
async def cmd_usage(message: Message):
    if not is_owner(message):
        return

    stats = await db.get_usage_stats(message.from_user.id)
    await message.answer(
        f"💰 *Расходы*\n\n"
        f"*Сегодня:*\n"
        f"  Input: {stats['today_input_tokens']:,} токенов\n"
        f"  Output: {stats['today_output_tokens']:,} токенов\n"
        f"  Стоимость: ${stats['today_cost']:.4f}\n\n"
        f"*За {stats['period_days']} дней:*\n"
        f"  Input: {stats['total_input_tokens']:,} токенов\n"
        f"  Output: {stats['total_output_tokens']:,} токенов\n"
        f"  Стоимость: ${stats['total_cost']:.4f}\n"
        f"  Запросов: {stats['total_requests']}",
        parse_mode=ParseMode.MARKDOWN,
    )


@router.message(Command("history"))
async def cmd_history(message: Message):
    if not is_owner(message):
        return

    convs = await db.get_conversation_list(message.from_user.id, limit=10)
    if not convs:
        return await message.answer("Нет диалогов.")

    lines = ["📜 *Последние диалоги:*\n"]
    for c in convs:
        status = "🟢" if c.is_active else "⚪"
        date_str = c.updated_at.strftime("%d.%m %H:%M") if c.updated_at else "—"
        lines.append(
            f"{status} #{c.id} | {model_short_name(c.model)} | "
            f"{c.system_prompt_key} | {date_str}"
        )

    buttons = []
    for c in convs:
        if not c.is_active:
            buttons.append([InlineKeyboardButton(
                text=f"Открыть #{c.id}",
                callback_data=f"resume:{c.id}"
            )])

    await message.answer(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None,
        parse_mode=ParseMode.MARKDOWN,
    )


@router.callback_query(F.data.startswith("resume:"))
async def cb_resume(callback: CallbackQuery):
    if callback.from_user.id != config.OWNER_ID:
        return

    conv_id = int(callback.data.split(":")[1])

    # Deactivate current active
    current = await db.get_or_create_conversation(callback.from_user.id)
    if current:
        await db.update_conversation(current.id, is_active=False)

    # Reactivate selected
    await db.update_conversation(conv_id, is_active=True)
    await callback.message.edit_text(f"✅ Диалог #{conv_id} восстановлен")
    await callback.answer()


# ──────────────────── Web search toggle ───────────────
web_search_enabled: dict[int, bool] = {}  # user_id -> bool


# ──────────────────── Message handlers ────────────────

@router.message(F.voice)
async def handle_voice(message: Message):
    """Handle voice messages — transcribe then send to Claude."""
    if not is_owner(message):
        return

    await bot.send_chat_action(message.chat.id, ChatAction.TYPING)

    # Download voice
    file = await bot.get_file(message.voice.file_id)
    voice_data = io.BytesIO()
    await bot.download_file(file.file_path, voice_data)

    # Transcribe
    transcription = await claude_api.transcribe_voice(voice_data.getvalue())
    if transcription.startswith("["):
        return await message.answer(transcription)

    # Show what was recognized
    await message.answer(f"🎤 _{transcription}_", parse_mode=ParseMode.MARKDOWN)

    # Send to Claude
    await process_text_message(message, transcription)


@router.message(F.photo)
async def handle_photo(message: Message):
    """Handle photos — send to Claude Vision."""
    if not is_owner(message):
        return

    await bot.send_chat_action(message.chat.id, ChatAction.TYPING)

    # Get largest photo
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    photo_data = io.BytesIO()
    await bot.download_file(file.file_path, photo_data)

    # Convert to base64
    b64 = base64.b64encode(photo_data.getvalue()).decode("utf-8")

    user_text = message.caption or "Что на этом изображении?"

    attachments = [{
        "type": "image",
        "media_type": "image/jpeg",
        "data": b64,
    }]

    await process_text_message(message, user_text, attachments=attachments)


@router.message(F.document)
async def handle_document(message: Message):
    """Handle documents — PDF via Vision, text files as text."""
    if not is_owner(message):
        return

    doc = message.document
    mime = doc.mime_type or ""
    file_name = doc.file_name or "document"

    await bot.send_chat_action(message.chat.id, ChatAction.TYPING)

    file = await bot.get_file(doc.file_id)
    file_data = io.BytesIO()
    await bot.download_file(file.file_path, file_data)
    raw = file_data.getvalue()

    user_text = message.caption or f"Проанализируй этот файл: {file_name}"

    if mime == "application/pdf":
        b64 = base64.b64encode(raw).decode("utf-8")
        attachments = [{
            "type": "document",
            "media_type": "application/pdf",
            "data": b64,
        }]
        await process_text_message(message, user_text, attachments=attachments)

    elif mime.startswith("image/"):
        b64 = base64.b64encode(raw).decode("utf-8")
        attachments = [{
            "type": "image",
            "media_type": mime,
            "data": b64,
        }]
        await process_text_message(message, user_text, attachments=attachments)

    elif mime.startswith("text/") or file_name.endswith((".py", ".js", ".json", ".md", ".txt", ".csv", ".html", ".css", ".yaml", ".yml", ".toml", ".sh", ".sql")):
        # Text file — include content in message
        try:
            text_content = raw.decode("utf-8")
        except UnicodeDecodeError:
            text_content = raw.decode("latin-1")

        full_text = f"{user_text}\n\n```\n{text_content}\n```"
        await process_text_message(message, full_text)

    else:
        await message.answer(
            f"⚠️ Формат `{mime}` пока не поддерживается.\n"
            "Поддерживаются: фото, PDF, текстовые файлы.",
            parse_mode=ParseMode.MARKDOWN,
        )


@router.message(F.text & ~F.text.startswith("/"))
async def handle_text(message: Message):
    """Handle plain text messages."""
    if not is_owner(message):
        return
    await process_text_message(message, message.text)


async def process_text_message(
    message: Message,
    text: str,
    attachments: list = None,
):
    """Core handler: send text (optionally with attachments) to Claude."""
    await bot.send_chat_action(message.chat.id, ChatAction.TYPING)

    conv = await db.get_or_create_conversation(message.from_user.id)
    search_on = web_search_enabled.get(message.from_user.id, True)

    # Status callback for tool use updates
    async def status_cb(status_text: str):
        try:
            await message.answer(status_text)
        except Exception:
            pass

    try:
        # Keep typing indicator alive during API call
        response_text, in_tok, out_tok = await claude_api.chat(
            conversation=conv,
            user_message=text,
            attachments=attachments,
            enable_web_search=search_on,
            status_callback=status_cb,
        )

        # Send response
        await send_long_message(message, response_text)

    except Exception as e:
        logger.error(f"Error processing message: {e}", exc_info=True)
        error_text = str(e)
        if "overloaded" in error_text.lower():
            await message.answer("⏳ Claude перегружен, попробуй через минуту.")
        elif "rate_limit" in error_text.lower():
            await message.answer("⏳ Лимит запросов, подожди немного.")
        elif "context_length" in error_text.lower() or "too many tokens" in error_text.lower():
            await message.answer(
                "📏 Контекст переполнен. Начинаю новый диалог...\n"
                "Используй /new для сброса."
            )
        else:
            await message.answer(f"❌ Ошибка: `{error_text[:200]}`", parse_mode=ParseMode.MARKDOWN)


# ──────────────────── Main ────────────────────────────

async def main():
    logger.info("Initializing database...")
    await db.init_db()

    logger.info("Starting bot...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

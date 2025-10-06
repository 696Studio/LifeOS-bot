import os
import asyncio
import logging

from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.client.default import DefaultBotProperties

from supabase import create_client, Client


# ---------- Load .env ----------
load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")

# Канал / менеджер (с запасными значениями)
CHANNEL_URL: str = (
    os.getenv("CHANNEL_URL")
    or os.getenv("LIFEOS_CHANNEL_URL")
    or "https://t.me/LifeOS_AI"
)
MANAGER_USERNAME: str = os.getenv("MANAGER_USERNAME", "@lifeos_admin1")


# ---------- Basic validation ----------
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_URL / SUPABASE_KEY are not set")


# ---------- Init bot / dp / db ----------
bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# ---------- Keyboard ----------
start_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="Start Diagnostic")]],
    resize_keyboard=True,
)


# ---------- DB helpers ----------
async def ensure_user_saved(user_id: int, username: str | None, first_name: str | None) -> None:
    """Проверяем, есть ли пользователь в таблице lifeos_users; если нет — добавляем."""
    try:
        existing = supabase.table("lifeos_users").select("*").eq("telegram_id", user_id).execute()
        if not existing.data:
            supabase.table("lifeos_users").insert(
                {
                    "telegram_id": user_id,
                    "username": username or "",
                    "first_name": first_name or "",
                }
            ).execute()
    except Exception as e:
        logging.exception("Failed to upsert user in lifeos_users: %s", e)


def safe_manager_tag(raw: str) -> str:
    """Приводим MANAGER_USERNAME к виду @username."""
    raw = (raw or "").strip()
    if not raw:
        return "@lifeos_admin1"
    if not raw.startswith("@"):
        return f"@{raw}"
    return raw


# ---------- Handlers ----------
@dp.message(CommandStart())
async def cmd_start(message: types.Message) -> None:
    user = message.from_user
    await ensure_user_saved(user.id, user.username, user.first_name)

    manager_tag = safe_manager_tag(MANAGER_USERNAME)

    text = (
        f"👋 Hey, <b>{user.first_name or 'there'}</b>!\n\n"
        f"Welcome to <b>LifeOS</b> — your personal AI Operator.\n"
        f"I’ll help you build your system of focus, automation, and growth.\n\n"
        f"👉 Join the community: <a href='{CHANNEL_URL}'>LifeOS Channel</a>\n"
        f"💬 Or talk to your manager: {manager_tag}"
    )

    await message.answer(text, reply_markup=start_kb)


@dp.message(Command("diagnostic"))
async def diagnostic_cmd(message: types.Message) -> None:
    await message.answer(
        "✅ Starting diagnostic! <i>(step 1 coming next)</i>",
        reply_markup=ReplyKeyboardRemove(),
    )


@dp.message(F.text.casefold() == "start diagnostic")
async def diagnostic_btn(message: types.Message) -> None:
    await diagnostic_cmd(message)


# ---------- Entrypoint ----------
async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    logging.info("🚀 LifeOS Bot started successfully")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())






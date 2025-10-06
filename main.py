import os
import re
import asyncio
import logging
from datetime import datetime

from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

# ВАЖНО: правильные импорты для настроек бота в aiogram 3.x
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from supabase import create_client, Client

# -------------------- Setup --------------------
logging.basicConfig(level=logging.INFO)
load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")

# Канал и менеджер (с запасными значениями, чтобы ссылки не ломались)
CHANNEL_URL: str = (
    os.getenv("CHANNEL_URL")
    or os.getenv("LIFEOS_CHANNEL_URL")
    or "https://t.me/LifeOS_AI"
)
MANAGER_USERNAME: str = os.getenv("MANAGER_USERNAME", "@lifeos_admin1")

# Базовая валидация (полезно для Railway)
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_URL / SUPABASE_KEY are not set")

# aiogram 3.x — создаём бота с корректным DefaultBotProperties
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher(storage=MemoryStorage())

# Supabase
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# -------------------- FSM --------------------
class Onboarding(StatesGroup):
    know = State()       # знает ли LifeOS
    pain = State()       # главная цель/боль
    email = State()      # емейл
    segment = State()    # сегмент (индивид/бизнес)

# -------------------- Helpers --------------------
def is_valid_email(text: str) -> bool:
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", text.strip(), flags=re.I))

async def upsert_user_diag(telegram_id: int, email: str | None, pain: str, segment: str):
    """
    Храним результаты опроса в таблице `users`
    Структура: id(bigint pk auto), user_id(text), email(text), is_business(bool), answers(json), created_at(timestamp)
    """
    answers = {
        "pain": pain,
        "segment": segment,
        "ts": datetime.utcnow().isoformat() + "Z",
    }
    is_business = segment.lower() != "individual"

    payload = {
        "user_id": str(Telegram_id := telegram_id),
        "email": email or None,
        "is_business": is_business,
        "answers": answers,
    }

    existing = supabase.table("users").select("*").eq("user_id", str(telegram_id)).execute()
    if existing.data:
        supabase.table("users").update(payload).eq("user_id", str(telegram_id)).execute()
    else:
        supabase.table("users").insert(payload).execute()

async def upsert_lifeos_user(user: types.User):
    """
    На всякий — поддерживаем твою таблицу `lifeos_users`
    (telegram_id, username, first_name). Если её нет — тихо пропустим.
    """
    try:
        existing = supabase.table("lifeos_users").select("*").eq("telegram_id", user.id).execute()
        if not existing.data:
            supabase.table("lifeos_users").insert({
                "telegram_id": user.id,
                "username": user.username or "",
                "first_name": user.first_name or ""
            }).execute()
    except Exception:
        pass  # таблицы нет — не падаем

# -------------------- Keyboards --------------------
yes_no_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="Yes"), KeyboardButton(text="No")]],
    resize_keyboard=True
)

pains_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Be more productive"), KeyboardButton(text="Automate routine")],
        [KeyboardButton(text="Stay focused & organized"), KeyboardButton(text="Build my ‘second brain’")],
        [KeyboardButton(text="Improve business ops")],
        [KeyboardButton(text="Type my own reason")],
    ],
    resize_keyboard=True
)

segment_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Individual")],
        [KeyboardButton(text="Small business (1–20)")],
        [KeyboardButton(text="Mid/Large company (20+)")],
    ],
    resize_keyboard=True
)

# -------------------- Flow --------------------
@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await upsert_lifeos_user(message.from_user)

    welcome = (
        f"👋 Hey, <b>{message.from_user.first_name or 'there'}</b>!\n\n"
        f"Welcome to <b>LifeOS</b> — your personal AI Operator.\n"
        f"I’ll help you build your system of focus, automation, and growth.\n\n"
        f"👉 Join the community: <a href=\"{CHANNEL_URL}\">LifeOS Channel</a>\n"
        f"💬 Or talk to your manager: {MANAGER_USERNAME}\n"
    )
    await message.answer(welcome, disable_web_page_preview=False)

    q = "Quick one: do you already know what <b>LifeOS</b> is?"
    await message.answer(q, reply_markup=yes_no_kb)
    await state.set_state(Onboarding.know)

@dp.message(Onboarding.know, F.text.casefold().in_(["yes", "no"]))
async def know_lifeos(message: types.Message, state: FSMContext):
    if message.text.lower() == "no":
        explain = (
            "Here’s the 10-second version:\n"
            "<b>LifeOS</b> is the operating system for humans.\n"
            "It turns one person into ten by combining AI agents, automations, and a "
            "simple workflow you actually use every day."
        )
        await message.answer(explain)

    ask_pain = (
        "What’s the <b>#1 reason</b> you want to optimize your life/work with AI?\n"
        "Pick a quick option or type your own."
    )
    await message.answer(ask_pain, reply_markup=pains_kb)
    await state.set_state(Onboarding.pain)

@dp.message(Onboarding.know)
async def know_fallback(message: types.Message):
    await message.answer("Please choose <b>Yes</b> or <b>No</b> 🙂", reply_markup=yes_no_kb)

@dp.message(Onboarding.pain, F.text.len() > 1)
async def save_pain(message: types.Message, state: FSMContext):
    await state.update_data(pain=message.text.strip())
    await message.answer(
        "Great — drop your <b>email</b> so I can send you templates and the quickstart guide.",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(Onboarding.email)

@dp.message(Onboarding.pain)
async def pain_fallback(message: types.Message):
    await message.answer(
        "Tell me in a few words what you want to improve (or pick a button).",
        reply_markup=pains_kb
    )

@dp.message(Onboarding.email)
async def capture_email(message: types.Message, state: FSMContext):
    text = (message.text or "").strip()
    if not is_valid_email(text):
        await message.answer("That doesn’t look like an email. Try again (example: name@company.com).")
        return

    await state.update_data(email=text)
    await message.answer("And lastly — what describes you best?", reply_markup=segment_kb)
    await state.set_state(Onboarding.segment)

@dp.message(
    Onboarding.segment,
    F.text.casefold().in_(["individual", "small business (1–20)", "mid/large company (20+)"])
)
async def finish_segment(message: types.Message, state: FSMContext):
    segment = message.text.strip()
    data = await state.get_data()
    pain = data.get("pain", "")
    email = data.get("email", None)

    await upsert_user_diag(
        telegram_id=message.from_user.id,
        email=email,
        pain=pain,
        segment=segment
    )

    summary = (
        "✅ <b>All set!</b>\n\n"
        f"• Pain/goal: <i>{pain}</i>\n"
        f"• Email: <i>{email}</i>\n"
        f"• Segment: <i>{segment}</i>\n\n"
    )

    if segment.lower() == "individual":
        summary += (
            "You’re in the right spot — you’ll get practical LifeOS templates, AI shortcuts, "
            "and weekly boosts to make you <b>meaningfully more effective</b>.\n\n"
        )
    elif "small business" in segment.lower():
        summary += (
            "Nice — we’ll focus on owner-friendly automation wins: lead handling, content ops, "
            "reporting, client onboarding, and more.\n\n"
        )
    else:
        summary += (
            "For larger teams, we also run <b>Automation Lab</b> — a hands-on track to ship "
            "cost-cutting automations and agentic workflows in weeks, not months. "
            f"Ping {MANAGER_USERNAME} if you want an outline.\n\n"
        )

    summary += (
        f"👉 Next: join the community — <a href=\"{CHANNEL_URL}\">LifeOS Channel</a>.\n"
        "I’ll DM you the quickstart pack shortly. Welcome aboard! 🚀"
    )

    await message.answer(summary, reply_markup=ReplyKeyboardRemove(), disable_web_page_preview=False)
    await state.clear()

@dp.message(Onboarding.segment)
async def segment_fallback(message: types.Message):
    await message.answer(
        "Please choose one: Individual / Small business (1–20) / Mid/Large company (20+).",
        reply_markup=segment_kb
    )

# -------------------- Run --------------------
async def main():
    logging.info("🚀 LifeOS Bot started successfully")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())








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

from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from supabase import create_client, Client

# -------------------- Setup --------------------
logging.basicConfig(level=logging.INFO)
load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")

CHANNEL_URL: str = (
    os.getenv("CHANNEL_URL")
    or os.getenv("LIFEOS_CHANNEL_URL")
    or "https://t.me/LifeOS_AI"
)
MANAGER_USERNAME: str = os.getenv("MANAGER_USERNAME", "@lifeos_admin1")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_URL / SUPABASE_KEY are not set")

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# -------------------- FSM --------------------
class Onboarding(StatesGroup):
    know = State()
    pain = State()
    email = State()
    segment = State()

# -------------------- Helpers --------------------
def is_valid_email(text: str) -> bool:
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", text.strip(), flags=re.I))

async def save_user_email_step(telegram_id: int, email: str, pain: str):
    """
    Сохраняем пользователя после шага email.
    Если есть запись — обновляем email/answers; иначе создаём новую.
    """
    user_id = str(telegram_id)
    answers = {"pain": pain, "segment": "unknown", "ts": datetime.utcnow().isoformat() + "Z"}

    try:
        existing = supabase.table("users").select("id").eq("user_id", user_id).execute()
        logging.info("check existing user_id=%s -> %s", user_id, existing.data)

        if existing.data:
            resp = (
                supabase.table("users")
                .update({"email": email, "answers": answers})
                .eq("user_id", user_id)
                .execute()
            )
            logging.info("UPDATE after email user_id=%s -> %s", user_id, resp.data)
        else:
            resp = (
                supabase.table("users")
                .insert({
                    "user_id": user_id,
                    "email": email,
                    "is_business": False,          # эвристика уточним после сегмента
                    "answers": answers,
                })
                .execute()
            )
            logging.info("INSERT after email user_id=%s -> %s", user_id, resp.data)
    except Exception as e:
        logging.exception("save_user_email_step FAILED: %s", e)

async def finalize_user_segment(telegram_id: int, email: str | None, pain: str, segment: str):
    """
    Финализируем сегмент: явный UPDATE и пересчёт is_business.
    """
    user_id = str(telegram_id)
    seg_low = (segment or "").lower()
    is_business = not (seg_low == "individual" or "freelancer" in seg_low or "solo" in seg_low)

    answers = {"pain": pain, "segment": segment, "ts": datetime.utcnow().isoformat() + "Z"}

    try:
        resp = (
            supabase.table("users")
            .update({
                "email": email,
                "is_business": is_business,
                "answers": answers,
            })
            .eq("user_id", user_id)
            .execute()
        )
        logging.info("UPDATE final segment user_id=%s -> %s", user_id, resp.data)
    except Exception as e:
        logging.exception("finalize_user_segment FAILED: %s", e)

async def upsert_lifeos_user(user: types.User):
    """
    Поддерживаем служебную таблицу lifeos_users (если есть).
    """
    try:
        existing = supabase.table("lifeos_users").select("id").eq("telegram_id", user.id).execute()
        if not existing.data:
            resp = supabase.table("lifeos_users").insert({
                "telegram_id": user.id,
                "username": user.username or "",
                "first_name": user.first_name or ""
            }).execute()
            logging.info("insert lifeos_users -> %s", resp.data)
    except Exception:
        # если таблицы нет — тихо пропускаем
        pass

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
        [KeyboardButton(text="Or type your own")],
    ],
    resize_keyboard=True
)

# -------------------- Flow --------------------
@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await upsert_lifeos_user(message.from_user)

    welcome = (
        f"👋 Hey, <b>{message.from_user.first_name or 'there'}</b>!\n\n"
        f"Welcome to <b>LifeOS</b> — a project at the beginning of its journey, built on a deep belief in the symbiosis between humans and artificial intelligence.\n\n"
        f"In today’s world, only a small percentage of people truly get a boost by using AI the right way.\n"
        f"You’re not behind the trends — you just haven’t learned how to use them yet.\n\n"
        f"👉 Join the community: <a href=\"{CHANNEL_URL}\">LifeOS Channel</a>\n"
        f"💬 Or talk to our manager: {MANAGER_USERNAME}\n\n"
        f"Now, let’s get to know you a little better 👇"
    )
    await message.answer(welcome, disable_web_page_preview=False)

    await message.answer("Do you already know what <b>LifeOS</b> is?", reply_markup=yes_no_kb)
    await state.set_state(Onboarding.know)

@dp.message(Onboarding.know, F.text.casefold().in_(["yes", "no"]))
async def know_lifeos(message: types.Message, state: FSMContext):
    if message.text.lower() == "no":
        explain = (
            "<b>LifeOS</b> is more than just an assistant — it’s your personal operating system for life.\n\n"
            "It builds your own AI-powered companion that breaks your life into categories, stays focused on your goals, "
            "and creates a clear roadmap to reach them.\n\n"
            "We automate your work processes with AI — removing tasks you don’t want to waste time on and keeping your attention on what truly matters.\n\n"
            "With the right priorities and deep AI integration, you’ll notice the upgrade after just the <b>first month</b> of using LifeOS."
        )
        await message.answer(explain)

    ask_pain = (
        "What’s the main reason you want to optimize your life or work with AI?\n"
        "Choose an option or type your own."
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
        "Great — leave your email so I can send you updates about the project.",
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

    # Сохраняем в БД сразу после email
    data = await state.get_data()
    await save_user_email_step(
        telegram_id=message.from_user.id,
        email=text,
        pain=data.get("pain", ""),
    )

    await message.answer(
        "And finally — what best describes you?\n(You can also type your own.)",
        reply_markup=segment_kb
    )
    await state.set_state(Onboarding.segment)

# Принимаем ЛЮБОЙ осмысленный текст как сегмент (кнопка или свой вариант)
@dp.message(Onboarding.segment, F.text.len() > 1)
async def finish_segment(message: types.Message, state: FSMContext):
    segment = message.text.strip()
    data = await state.get_data()
    pain = data.get("pain", "")
    email = data.get("email", None)

    await finalize_user_segment(
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

    seg_low = segment.lower()
    if seg_low == "individual":
        summary += (
            "You’re in the right place — you’ll start getting practical LifeOS templates, AI shortcuts, "
            "and weekly upgrades that make you <b>measurably more effective</b>.\n\n"
        )
    elif "small business" in seg_low or "mid/large company" in seg_low or "company" in seg_low or "business" in seg_low:
        summary += (
            "For companies, we run the <b>Automation Lab</b> — a team of engineers, integrators, and prompt architects "
            "building custom AI solutions for your business:\n"
            "CRM bots, content funnels, chat agents, Notion systems, auto-posting tools, report generators, "
            "internal AI utilities, and more.\n\n"
            f"Message {MANAGER_USERNAME} if you’d like a personalized plan.\n\n"
        )
    else:
        summary += "Got it — we’ll tailor the experience to your context and goals.\n\n"

    summary += (
        f"👉 Next: join the community — <a href=\"{CHANNEL_URL}\">LifeOS Channel</a>.\n"
        "Soon, you’ll start achieving what you want — faster.\n"
        "Technology isn’t evil; it’s the pure expression of humanity’s desire to create and live freely.\n"
        "Don’t just watch the future happen — be one of the first to make it part of your life. 🚀"
    )

    await message.answer(summary, reply_markup=ReplyKeyboardRemove(), disable_web_page_preview=False)
    await state.clear()

@dp.message(Onboarding.segment)
async def segment_fallback(message: types.Message):
    await message.answer(
        "Please choose one: Individual / Small business (1–20) / Mid/Large company (20+) — or type your own.",
        reply_markup=segment_kb
    )

# -------------------- Run --------------------
async def main():
    def _mask(s: str) -> str:
        return (s[:8] + "…") if s else ""

    logging.info("SUPABASE_URL = %s", SUPABASE_URL)
    logging.info("SUPABASE_KEY prefix = %s", _mask(SUPABASE_KEY))
    logging.info("🚀 LifeOS Bot started successfully")

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())













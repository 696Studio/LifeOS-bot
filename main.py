import os
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.types import LinkPreviewOptions
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
CHANNEL_URL = os.getenv("LIFEOS_CHANNEL_URL")
MANAGER_USERNAME = os.getenv("MANAGER_USERNAME")

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

@dp.message(CommandStart())
async def start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name

    existing = supabase.table("lifeos_users").select("*").eq("telegram_id", user_id).execute()
    if not existing.data:
        supabase.table("lifeos_users").insert({
            "telegram_id": user_id,
            "username": username,
            "first_name": first_name
        }).execute()

    username_clean = (MANAGER_USERNAME or "").lstrip("@")
    text = (
        f"👋 Привет, {first_name}!\n\n"
        f"Добро пожаловать в <b>LifeOS</b> — твой личный AI-оператор.\n"
        f"🚀 Я помогу тебе собрать свою систему продуктивности и начать путь оптимизации.\n\n"
        f"👉 Вступай в канал: <a href=\"{CHANNEL_URL}\">{CHANNEL_URL}</a>\n"
        f"💬 Или пиши менеджеру: <a href=\"https://t.me/{username_clean}\">@{username_clean}</a>"
    )

    await message.answer(text, link_preview_options=LinkPreviewOptions(is_disabled=True))

if __name__ == "__main__":
    import asyncio
    async def main():
        await dp.start_polling(bot)
    asyncio.run(main())



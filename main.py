from aiogram import types, F
from aiogram.filters import Command, CommandStart
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

import os

# Загружаем переменные окружения
CHANNEL_URL = os.getenv("CHANNEL_URL") or os.getenv("LIFEOS_CHANNEL_URL") or "https://t.me/LifeOS_AI"
MANAGER_USERNAME = os.getenv("MANAGER_USERNAME") or "@lifeos_admin1"

# Кнопка "Start Diagnostic"
start_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="Start Diagnostic")]],
    resize_keyboard=True
)

# Приветствие при старте
@dp.message(CommandStart())
async def start(message: types.Message):
    text = (
        f"👋 Hey, {message.from_user.first_name or 'there'}!\n\n"
        "Welcome to **LifeOS** — your personal AI Operator.\n"
        "I’ll help you build your system of focus, automation, and growth.\n\n"
        f"👉 Join the community: {CHANNEL_URL}\n"
        f"💬 Or talk to your manager: {MANAGER_USERNAME}"
    )
    await message.answer(text, reply_markup=start_kb, parse_mode="Markdown")

# Обработка команды /diagnostic
@dp.message(Command("diagnostic"))
async def diagnostic_entry(message: types.Message):
    await message.answer("Starting diagnostic… (step 1 coming next)", reply_markup=ReplyKeyboardRemove())

# Чтобы работала кнопка "Start Diagnostic"
@dp.message(F.text.casefold() == "start diagnostic")
async def diagnostic_via_button(message: types.Message):
    await diagnostic_entry(message)





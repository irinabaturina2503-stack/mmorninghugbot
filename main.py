import asyncio
import json
import random
import sqlite3
import os
from datetime import datetime

import pytz
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram import F

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

if not TOKEN:
    raise ValueError("BOT_TOKEN is not set!")

if ADMIN_ID == 0:
    raise ValueError("ADMIN_ID is not set!")

bot = Bot(token=TOKEN)
dp = Dispatcher()

DB_PATH = os.path.join(os.path.dirname(__file__), "bot.db")
MESSAGES_PATH = os.path.join(os.path.dirname(__file__), "messages.txt")

conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    messages TEXT,
    idx INTEGER,
    hour INTEGER,
    last_sent TEXT,
    timezone TEXT
)
""")
conn.commit()

# Migrate existing DB: add timezone column if missing
try:
    cursor.execute("ALTER TABLE users ADD COLUMN timezone TEXT")
    conn.commit()
except sqlite3.OperationalError:
    pass  # Column already exists


def load_messages():
    try:
        with open(MESSAGES_PATH, "r", encoding="utf-8") as f:
            messages = [line.strip() for line in f if line.strip()]
        if not messages:
            raise ValueError("messages.txt is empty!")
        return messages
    except FileNotFoundError:
        raise FileNotFoundError(f"messages.txt not found at {MESSAGES_PATH}")


BASE_MESSAGES = load_messages()

# Timezone map: button label → pytz timezone string
TIMEZONE_MAP = {
    "Москва":       "Europe/Moscow",       # UTC+3
    "Новосибирск":  "Asia/Novosibirsk",    # UTC+7
    "Европа":       "Europe/Berlin",       # UTC+1/+2 (Германия, Италия)
    "Азия":         "Asia/Bangkok",        # UTC+7 (Пхукет)
    "ОАЭ":          "Asia/Dubai",          # UTC+4 (Дубай)
}


def get_user(user_id):
    cursor.execute(
        "SELECT messages, idx, hour, last_sent, timezone FROM users WHERE user_id=?",
        (user_id,)
    )
    return cursor.fetchone()


def get_users():
    cursor.execute("SELECT user_id FROM users")
    return [r[0] for r in cursor.fetchall()]


def create_user(user_id):
    messages = BASE_MESSAGES.copy()
    random.shuffle(messages)
    cursor.execute("""
        INSERT INTO users (user_id, messages, idx, hour, last_sent, timezone)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (user_id, json.dumps(messages, ensure_ascii=False), 0, None, None, None))
    conn.commit()


def update_user(user_id, messages, idx, hour, last_sent, timezone=None):
    cursor.execute("""
        UPDATE users
        SET messages=?, idx=?, hour=?, last_sent=?, timezone=?
        WHERE user_id=?
    """, (
        json.dumps(messages, ensure_ascii=False),
        idx,
        hour,
        last_sent,
        timezone,
        user_id
    ))
    conn.commit()


def timezone_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🏙 Москва (UTC+3)",      callback_data="tz_Москва"),
            InlineKeyboardButton(text="🌲 Новосибирск (UTC+7)", callback_data="tz_Новосибирск"),
        ],
        [
            InlineKeyboardButton(text="🌍 Европа (UTC+1/2)",    callback_data="tz_Европа"),
            InlineKeyboardButton(text="🌴 Азия — Пхукет (UTC+7)", callback_data="tz_Азия"),
        ],
        [
            InlineKeyboardButton(text="🇦🇪 ОАЭ — Дубай (UTC+4)", callback_data="tz_ОАЭ"),
        ],
    ])


def time_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🌅 8:00",  callback_data="time_8"),
            InlineKeyboardButton(text="☀️ 9:00",  callback_data="time_9"),
            InlineKeyboardButton(text="🌤 10:00", callback_data="time_10"),
        ],
        [
            InlineKeyboardButton(text="🌇 11:00", callback_data="time_11"),
            InlineKeyboardButton(text="🌙 12:00", callback_data="time_12"),
        ]
    ])


def settings_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🌍 Сменить часовой пояс", callback_data="change_tz"),
        ],
        [
            InlineKeyboardButton(text="⏰ Сменить время",        callback_data="change_time"),
        ]
    ])


@dp.message(Command("start"))
async def start(message: types.Message):
    user_id = message.from_user.id

    if not get_user(user_id):
        create_user(user_id)

        await bot.send_message(
            ADMIN_ID,
            f"🆕 New user: {user_id}"
        )

        await message.answer(
            "Я буду присылать тебе одно сообщение каждое утро 💛\n\n"
            "Сначала выбери свой часовой пояс:",
            reply_markup=timezone_keyboard()
        )
    else:
        user = get_user(user_id)
        hour = user[2]
        tz_str = user[4]
        tz_label = next((k for k, v in TIMEZONE_MAP.items() if v == tz_str), "не задан")
        hour_text = f"{hour}:00" if hour is not None else "не задано"

        await message.answer(
            f"⚙️ Твои настройки:\n"
            f"🌍 Часовой пояс: {tz_label}\n"
            f"⏰ Время: {hour_text}\n\n"
            f"Что хочешь изменить?",
            reply_markup=settings_keyboard()
        )


@dp.message(Command("settings"))
async def settings(message: types.Message):
    user_id = message.from_user.id
    user = get_user(user_id)

    if not user:
        await message.answer("Сначала напиши /start")
        return

    hour = user[2]
    tz_str = user[4]
    tz_label = next((k for k, v in TIMEZONE_MAP.items() if v == tz_str), "не задан")
    hour_text = f"{hour}:00" if hour is not None else "не задано"

    await message.answer(
        f"⚙️ Твои настройки:\n"
        f"🌍 Часовой пояс: {tz_label}\n"
        f"⏰ Время: {hour_text}\n\n"
        f"Что хочешь изменить?",
        reply_markup=settings_keyboard()
    )


@dp.callback_query(F.data == "change_tz")
async def change_tz(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "Выбери новый часовой пояс:",
        reply_markup=timezone_keyboard()
    )
    await callback.answer()


@dp.callback_query(F.data == "change_time")
async def change_time(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "Выбери новое время:",
        reply_markup=time_keyboard()
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("tz_"))
async def set_timezone(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    tz_label = callback.data.replace("tz_", "", 1)  # e.g. "Москва"
    tz_str = TIMEZONE_MAP.get(tz_label)

    if not tz_str:
        await callback.answer("Неизвестный часовой пояс", show_alert=True)
        return

    user = get_user(user_id)
    if not user:
        create_user(user_id)
        user = get_user(user_id)

    messages = json.loads(user[0])
    idx = user[1]
    hour = user[2]
    last_sent = user[3]

    update_user(user_id, messages, idx, hour, last_sent, timezone=tz_str)

    await callback.message.edit_text(
        f"✅ Часовой пояс: {tz_label}\n\nТеперь выбери удобное время:",
        reply_markup=time_keyboard()
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("time_"))
async def set_time(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    hour = int(callback.data.split("_")[1])

    user = get_user(user_id)
    if not user:
        create_user(user_id)
        user = get_user(user_id)

    messages = json.loads(user[0])
    idx = user[1]
    timezone = user[4]

    if not timezone:
        await callback.message.answer(
            "Сначала выбери часовой пояс:",
            reply_markup=timezone_keyboard()
        )
        await callback.answer()
        return

    update_user(user_id, messages, idx, hour, None, timezone=timezone)

    await callback.message.edit_text(f"💛 Готово! Буду писать тебе в {hour}:00 ✨")
    await callback.answer()


def is_admin(user_id: int):
    return user_id == ADMIN_ID


@dp.message(Command("stats"))
async def stats(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    users = get_users()
    await message.answer(f"👥 Users: {len(users)}")


@dp.message(Command("users"))
async def cmd_users(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    users = get_users()
    text = "\n".join(map(str, users[:50]))
    await message.answer(f"📋 Users:\n{text}" if text else "No users yet.")


@dp.message(Command("broadcast"))
async def broadcast(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    text = message.text.replace("/broadcast", "").strip()
    if not text:
        await message.answer("Usage: /broadcast your text here")
        return

    users = get_users()
    sent = 0
    for user_id in users:
        try:
            await bot.send_message(user_id, f"📢 {text}")
            sent += 1
        except Exception as e:
            print(f"Broadcast error {user_id}: {e}")

    await message.answer(f"Sent to: {sent}")


async def sender_loop():
    while True:
        users = get_users()

        for user_id in users:
            user = get_user(user_id)
            if not user:
                continue

            messages_raw, idx, hour, last_sent, tz_str = user

            if hour is None or tz_str is None:
                continue

            messages = json.loads(messages_raw)

            try:
                tz = pytz.timezone(tz_str)
            except pytz.UnknownTimeZoneError:
                print(f"Unknown timezone for user {user_id}: {tz_str}")
                continue

            now = datetime.now(tz=tz)
            hour_now = now.hour
            today = now.strftime("%Y-%m-%d")

            if last_sent == today:
                continue

            if hour_now == hour:
                try:
                    await bot.send_message(user_id, messages[idx])
                except Exception as e:
                    print(f"Send error {user_id}: {e}")
                    continue

                idx += 1
                if idx >= len(messages):
                    random.shuffle(messages)
                    idx = 0

                update_user(user_id, messages, idx, hour, today, timezone=tz_str)

        await asyncio.sleep(60)


async def main():
    print("Bot is starting...")
    await asyncio.gather(
        sender_loop(),
        dp.start_polling(bot)
    )


if __name__ == "__main__":
    asyncio.run(main())

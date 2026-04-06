# main.py

import asyncio
import logging
import os
import aiohttp

from aiogram import Bot, Dispatcher, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

# ================== FIX SQLITE ==================
try:
    import sqlite3
except:
    import pysqlite3 as sqlite3

import aiosqlite

# ================== CONFIG (ВСТАВЬ СВОИ ДАННЫЕ) ==================
BOT_TOKEN = "8648072212:AAE-hC9VtVpHpAgdY3tgj8GNNEucu1QfRXc"
ADMIN_ID = 7785932103
ADMIN_USERNAME = "Stv18"
CRYPTO_PAY_TOKEN = "540011:AARTDw8jiNvxfbJNrCKkEp4l6l50XTuJOYX"

DB_PATH = "database.db"

# ================== LOGGING ==================
logging.basicConfig(level=logging.INFO)

# ================== BOT ==================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ================== DB ==================
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance REAL DEFAULT 0
        )
        """)

        await db.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT,
            api_id INTEGER,
            api_hash TEXT,
            session TEXT,
            has_tgp INTEGER DEFAULT 0,
            price_per_min REAL DEFAULT 0,
            rented_by INTEGER,
            rent_until INTEGER
        )
        """)

        await db.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            status TEXT
        )
        """)

        await db.commit()

# ================== STATES ==================
class AddAccount(StatesGroup):
    phone = State()
    api_id = State()
    api_hash = State()
    code = State()

class Mailing(StatesGroup):
    text = State()
    interval = State()
    targets = State()

# ================== KEYBOARDS ==================
def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="mailing")],
        [InlineKeyboardButton(text="👤 Аккаунты", callback_data="accounts")],
        [InlineKeyboardButton(text="💰 Баланс", callback_data="balance")],
        [InlineKeyboardButton(text="🛟 Support", url="https://t.me/Dutsi18")]
    ])

def admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить аккаунт", callback_data="add_acc")]
    ])

# ================== TELETHON ==================
clients = {}

async def create_client(phone, api_id, api_hash):
    client = TelegramClient(f"sessions/{phone}", api_id, api_hash)
    await client.connect()
    return client

# ================== PAYMENTS ==================
API_URL = "https://pay.crypt.bot/api"

async def create_invoice(amount):
    if not CRYPTO_PAY_TOKEN:
        return {"ok": False}

    headers = {"Crypto-Pay-API-Token": CRYPTO_PAY_TOKEN}
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{API_URL}/createInvoice",
            json={"asset": "USDT", "amount": amount},
            headers=headers
        ) as resp:
            return await resp.json()

# ================== HELPERS ==================
def is_admin(user):
    return user.id == ADMIN_ID and user.username == ADMIN_USERNAME

# ================== USER ==================
@dp.message(Command("start"))
async def start(msg: Message):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users(user_id) VALUES(?)",
            (msg.from_user.id,)
        )
        await db.commit()

    await msg.answer("Добро пожаловать!", reply_markup=main_menu())

@dp.callback_query(F.data == "balance")
async def balance(call: CallbackQuery):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT balance FROM users WHERE user_id=?",
            (call.from_user.id,)
        )
        bal = await cur.fetchone()

    balance_value = bal[0] if bal else 0
    await call.message.edit_text(f"💰 Баланс: {balance_value}$")

# ================== MAILING ==================
@dp.callback_query(F.data == "mailing")
async def mailing_start(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("Введите текст:")
    await state.set_state(Mailing.text)

@dp.message(Mailing.text)
async def mailing_text(msg: Message, state: FSMContext):
    await state.update_data(text=msg.text)
    await msg.answer("Интервал (5-300):")
    await state.set_state(Mailing.interval)

@dp.message(Mailing.interval)
async def mailing_interval(msg: Message, state: FSMContext):
    try:
        interval = int(msg.text)
    except:
        return await msg.answer("Введите число")

    if interval < 5 or interval > 300:
        return await msg.answer("5-300 сек")

    await state.update_data(interval=interval)
    await msg.answer("@username через запятую:")
    await state.set_state(Mailing.targets)

@dp.message(Mailing.targets)
async def mailing_targets(msg: Message, state: FSMContext):
    data = await state.get_data()
    targets = msg.text.split(",")

    if not clients:
        return await msg.answer("❌ Нет аккаунтов")

    client = list(clients.values())[0]

    for t in targets:
        try:
            await client.send_message(t.strip(), data["text"])
            await asyncio.sleep(data["interval"])
        except Exception as e:
            logging.error(e)

    await msg.answer("✅ Готово")
    await state.clear()

# ================== ADMIN ==================
@dp.message(Command("admin"))
async def admin_panel(msg: Message):
    if not is_admin(msg.from_user):
        return await msg.answer("❌ Нет доступа")

    await msg.answer("Админ панель", reply_markup=admin_menu())

@dp.callback_query(F.data == "add_acc")
async def add_acc(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user):
        return

    await call.message.answer("Телефон:")
    await state.set_state(AddAccount.phone)

@dp.message(AddAccount.phone)
async def acc_phone(msg: Message, state: FSMContext):
    await state.update_data(phone=msg.text)
    await msg.answer("api_id:")
    await state.set_state(AddAccount.api_id)

@dp.message(AddAccount.api_id)
async def acc_api(msg: Message, state: FSMContext):
    await state.update_data(api_id=int(msg.text))
    await msg.answer("api_hash:")
    await state.set_state(AddAccount.api_hash)

@dp.message(AddAccount.api_hash)
async def acc_hash(msg: Message, state: FSMContext):
    data = await state.get_data()

    client = await create_client(data["phone"], data["api_id"], msg.text)
    await client.send_code_request(data["phone"])

    await state.update_data(client=client)
    await msg.answer("Код:")
    await state.set_state(AddAccount.code)

@dp.message(AddAccount.code)
async def acc_code(msg: Message, state: FSMContext):
    data = await state.get_data()
    client = data["client"]

    try:
        await client.sign_in(data["phone"], msg.text)
    except SessionPasswordNeededError:
        return await msg.answer("❌ 2FA не поддерживается")

    clients[data["phone"]] = client

    await msg.answer("✅ Аккаунт добавлен")
    await state.clear()

# ================== MAIN ==================
async def main():
    os.makedirs("sessions", exist_ok=True)
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
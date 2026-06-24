import os
import logging
import sqlite3
import random
import asyncio
import re
import io
import string
from datetime import datetime, timedelta
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, CallbackQueryHandler, ContextTypes
)
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

try:
    from groq import AsyncGroq
except ImportError:
    raise ImportError("Установи groq: pip install groq")

try:
    import qrcode
    from PIL import Image
except ImportError:
    raise ImportError("Установи qrcode и pillow: pip install qrcode pillow")

from dotenv import load_dotenv
load_dotenv()

# ========= НАСТРОЙКИ =========
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("❌ Не задан BOT_TOKEN")

SUPER_ADMINS = [8259326014, 5132524185, 8505422185]
REQUESTS_CHAT = -1003981149887

# ===== НОВЫЙ КАНАЛ =====
CHANNEL_ID = -1004473890976
CHANNEL_LINK = "https://t.me/+m7LEI4ACCKFjZjlh"

DRAW_GROUP_ID = -1003679834464
DRAW_CHANNEL_IDS = [-1004473890976]
DRAW_CHANNEL_LINKS = ["https://t.me/+m7LEI4ACCKFjZjlh"]
START_IMAGE = "start.jpg"

LEADERBOARD_GROUP = -1003934854858

STREAK_GRACE_HOURS = 36
SUB_REMINDER_DAYS_BEFORE = 2

BOT_USERNAME = "PWRLAB_bot"

# ===== ССЫЛКА НА САЙТ С ?v=2 =====
NORMATIVES_URL = "https://nikitatopro36-dot.github.io/pwrlabs-normatives/?v=2"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

conn = sqlite3.connect("bot.db", check_same_thread=False)
conn.execute("PRAGMA journal_mode=WAL")

def db():
    return conn.cursor()

# ========= СОЗДАНИЕ ТАБЛИЦ =========
cur = db()
cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    bench INTEGER,
    deadlift INTEGER,
    squat INTEGER,
    weight INTEGER,
    age INTEGER,
    updated TEXT,
    username TEXT,
    full_name TEXT,
    ref_code TEXT UNIQUE,
    bonus INTEGER DEFAULT 0
)
""")
cur.execute("""
CREATE TABLE IF NOT EXISTS progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    bench INTEGER,
    deadlift INTEGER,
    squat INTEGER,
    date TEXT
)
""")
cur.execute("""
CREATE TABLE IF NOT EXISTS subs (
    user_id INTEGER PRIMARY KEY,
    until TEXT,
    sub_type TEXT
)
""")
cur.execute("""
CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    sub_type TEXT,
    days INTEGER,
    date TEXT
)
""")
cur.execute("""
CREATE TABLE IF NOT EXISTS draw_users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    full_name TEXT,
    status TEXT,
    captcha INTEGER,
    joined INTEGER DEFAULT 0
)
""")
cur.execute("""
CREATE TABLE IF NOT EXISTS draws (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prize TEXT,
    status TEXT
)
""")
cur.execute("""
CREATE TABLE IF NOT EXISTS questionnaires (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    type TEXT,
    answers TEXT,
    result TEXT,
    date TEXT
)
""")
cur.execute("""
CREATE TABLE IF NOT EXISTS banned_users (
    user_id INTEGER PRIMARY KEY,
    reason TEXT,
    banned_at TEXT
)
""")
cur.execute("""
CREATE TABLE IF NOT EXISTS message_stats (
    user_id INTEGER PRIMARY KEY,
    count INTEGER DEFAULT 0,
    date TEXT
)
""")
cur.execute("""
CREATE TABLE IF NOT EXISTS streaks (
    user_id INTEGER PRIMARY KEY,
    current_streak INTEGER DEFAULT 0,
    best_streak INTEGER DEFAULT 0,
    last_checkin TEXT
)
""")
cur.execute("""
CREATE TABLE IF NOT EXISTS faq (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question TEXT,
    answer TEXT
)
""")
cur.execute("""
CREATE TABLE IF NOT EXISTS support_mode (
    user_id INTEGER PRIMARY KEY,
    started_at TEXT
)
""")
cur.execute("""
CREATE TABLE IF NOT EXISTS sub_reminders_sent (
    user_id INTEGER,
    until TEXT,
    PRIMARY KEY (user_id, until)
)
""")
cur.execute("""
CREATE TABLE IF NOT EXISTS reminder_settings (
    user_id INTEGER PRIMARY KEY,
    enabled INTEGER DEFAULT 1
)
""")
cur.execute("""
CREATE TABLE IF NOT EXISTS user_progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    bench INTEGER,
    deadlift INTEGER,
    squat INTEGER,
    date TEXT
)
""")
cur.execute("""
CREATE TABLE IF NOT EXISTS referrals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    referrer_id INTEGER,
    referred_id INTEGER UNIQUE,
    date TEXT
)
""")
cur.execute("""
CREATE TABLE IF NOT EXISTS workout_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    date TEXT,
    workout_type TEXT,
    duration INTEGER,
    notes TEXT,
    exercises TEXT
)
""")
cur.execute("""
CREATE TABLE IF NOT EXISTS promo_codes (
    code TEXT PRIMARY KEY,
    discount_percent INTEGER,
    valid_until TEXT,
    max_uses INTEGER,
    used_count INTEGER DEFAULT 0,
    created_by INTEGER,
    created_at TEXT
)
""")
cur.execute("""
CREATE TABLE IF NOT EXISTS promo_activations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    code TEXT,
    activated_at TEXT
)
""")
cur.execute("""
CREATE TABLE IF NOT EXISTS activity_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    hour INTEGER,
    date TEXT,
    action TEXT
)
""")
cur.execute("""
CREATE TABLE IF NOT EXISTS admins (
    user_id INTEGER PRIMARY KEY,
    added_by INTEGER,
    added_at TEXT
)
""")
cur.execute("""
CREATE TABLE IF NOT EXISTS trial_used (
    user_id INTEGER PRIMARY KEY,
    used_at TEXT
)
""")
cur.execute("""
CREATE TABLE IF NOT EXISTS leaderboard_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    exercise TEXT,
    weight INTEGER,
    video_file_id TEXT,
    status TEXT DEFAULT 'pending',
    date TEXT
)
""")
cur.execute("""
CREATE TABLE IF NOT EXISTS ai_usage (
    user_id INTEGER PRIMARY KEY,
    date TEXT,
    count INTEGER DEFAULT 0
)
""")
cur.execute("""
CREATE TABLE IF NOT EXISTS site_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    action TEXT,
    date TEXT
)
""")
conn.commit()

# ===== ДОБАВЛЯЕМ НЕДОСТАЮЩИЕ КОЛОНКИ =====
cur = db()
cur.execute("PRAGMA table_info(users)")
existing_cols = [col[1] for col in cur.fetchall()]
cols_to_add = {
    'bench': 'INTEGER',
    'deadlift': 'INTEGER',
    'squat': 'INTEGER',
    'weight': 'INTEGER',
    'age': 'INTEGER',
    'updated': 'TEXT',
    'username': 'TEXT',
    'full_name': 'TEXT',
    'ref_code': 'TEXT',
    'bonus': 'INTEGER DEFAULT 0'
}
for col_name, col_type in cols_to_add.items():
    if col_name not in existing_cols:
        try:
            cur.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")
            logger.info(f"✅ Добавлена колонка {col_name}")
        except Exception as e:
            logger.warning(f"Не удалось добавить колонку {col_name}: {e}")
conn.commit()

# ========= ГЕНЕРАЦИЯ РЕФЕРАЛЬНОГО КОДА =========
def generate_ref_code():
    while True:
        code = 'ref_' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        cur = db()
        cur.execute("SELECT 1 FROM users WHERE ref_code=?", (code,))
        if not cur.fetchone():
            return code

# ========= ПРОВЕРКА АДМИНА =========
def is_admin(uid):
    cur = db()
    cur.execute("SELECT 1 FROM admins WHERE user_id=?", (uid,))
    if cur.fetchone():
        return True
    return uid in SUPER_ADMINS

def is_super_admin(uid):
    return uid in SUPER_ADMINS

def is_banned(uid):
    cur = db()
    cur.execute("SELECT 1 FROM banned_users WHERE user_id=?", (uid,))
    return cur.fetchone() is not None

# ========= ПРОВЕРКА ПОДПИСКИ =========
def is_pro(uid):
    cur = db()
    cur.execute("SELECT until FROM subs WHERE user_id=?", (uid,))
    row = cur.fetchone()
    if not row:
        return False
    until = datetime.fromisoformat(row[0])
    if datetime.now() > until:
        cur.execute("DELETE FROM subs WHERE user_id=?", (uid,))
        conn.commit()
        return False
    return True

def is_full_pro(uid):
    cur = db()
    cur.execute("SELECT until, sub_type FROM subs WHERE user_id=?", (uid,))
    row = cur.fetchone()
    if not row:
        return False
    until, sub_type = row
    if datetime.now() > datetime.fromisoformat(until):
        cur.execute("DELETE FROM subs WHERE user_id=?", (uid,))
        conn.commit()
        return False
    if sub_type:
        if 'ref_pro' in sub_type or 'trial' in sub_type:
            if '+' in sub_type:
                return True
            return False
    return True

def get_sub_type(uid):
    cur = db()
    cur.execute("SELECT sub_type FROM subs WHERE user_id=?", (uid,))
    row = cur.fetchone()
    return row[0] if row else None

# ========= ЛИМИТ AI =========
def check_ai_limit(uid):
    today = datetime.now().strftime("%Y-%m-%d")
    cur = db()
    cur.execute("SELECT count FROM ai_usage WHERE user_id=? AND date=?", (uid, today))
    row = cur.fetchone()
    if not row:
        return True, 4
    count = row[0]
    if count >= 4:
        return False, 0
    return True, 4 - count

def increment_ai_usage(uid):
    today = datetime.now().strftime("%Y-%m-%d")
    cur = db()
    cur.execute(
        "INSERT INTO ai_usage (user_id, date, count) VALUES (?, ?, 1) "
        "ON CONFLICT(user_id) DO UPDATE SET count = count + 1 WHERE user_id=?",
        (uid, today, uid)
    )
    conn.commit()

# ========= БАН / РАЗБАН =========
async def ban_user(update, context):
    if not is_super_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Нет доступа!")
        return
    if len(context.args) < 1:
        await update.message.reply_text("❌ /ban ID [причина]")
        return
    try:
        uid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Неверный ID")
        return
    reason = " ".join(context.args[1:]) if len(context.args) > 1 else "Не указана"
    cur = db()
    cur.execute("INSERT OR REPLACE INTO banned_users VALUES (?, ?, ?)", (uid, reason, datetime.now().isoformat()))
    conn.commit()
    await update.message.reply_text(f"✅ Пользователь {uid} забанен\nПричина: {reason}")
    try:
        await context.bot.send_message(uid, f"⛔ Вас забанили в боте!\nПричина: {reason}")
    except Exception:
        pass

async def unban_user(update, context):
    if not is_super_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Нет доступа!")
        return
    if len(context.args) < 1:
        await update.message.reply_text("❌ /unban ID")
        return
    try:
        uid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Неверный ID")
        return
    cur = db()
    cur.execute("DELETE FROM banned_users WHERE user_id=?", (uid,))
    conn.commit()
    await update.message.reply_text(f"✅ Пользователь {uid} разбанен")
    try:
        await context.bot.send_message(uid, "✅ Вы разбанены в боте!")
    except Exception:
        pass

# ========= РАССЫЛКИ =========
async def near_all(update, context):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Нет доступа!")
        return
    if not context.args:
        await update.message.reply_text("❌ /near текст сообщения")
        return
    text = " ".join(context.args)
    cur = db()
    cur.execute("SELECT DISTINCT user_id FROM users")
    users = cur.fetchall()
    sent = 0
    for (uid,) in users:
        try:
            await context.bot.send_message(uid, f"📢 РАССЫЛКА:\n\n{text}")
            sent += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass
    await update.message.reply_text(f"✅ Отправлено {sent} пользователям")

async def broadcast_pro(update, context):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Нет доступа!")
        return
    if not context.args:
        await update.message.reply_text("❌ /broadcast_pro текст сообщения")
        return
    text = " ".join(context.args)
    cur = db()
    cur.execute("SELECT user_id, until FROM subs")
    rows = cur.fetchall()
    now = datetime.now()
    sent = 0
    for uid, until in rows:
        try:
            if datetime.fromisoformat(until) < now:
                continue
        except Exception:
            continue
        try:
            await context.bot.send_message(uid, f"💎 СПЕЦИАЛЬНО ДЛЯ PRO:\n\n{text}")
            sent += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass
    await update.message.reply_text(f"✅ Отправлено {sent} PRO-пользователям")

# ========= АНТИФЛУД =========
user_last_message = {}
def check_antiflood(uid):
    now = datetime.now().timestamp()
    if uid in user_last_message:
        if now - user_last_message[uid] < 1:
            return False
    user_last_message[uid] = now
    return True

def check_message_limit(uid):
    if is_pro(uid):
        return True
    today = datetime.now().strftime("%Y-%m-%d")
    cur = db()
    cur.execute("SELECT count FROM message_stats WHERE user_id=? AND date=?", (uid, today))
    row = cur.fetchone()
    if not row:
        cur.execute("INSERT INTO message_stats VALUES (?, 1, ?)", (uid, today))
        conn.commit()
        return True
    if row[0] >= 10:
        return False
    cur.execute("UPDATE message_stats SET count = count + 1 WHERE user_id=? AND date=?", (uid, today))
    conn.commit()
    return True

# ========= КНОПКИ =========
GROQ_API_KEYS_STR = os.environ.get("GROQ_API_KEYS", "")
GROQ_API_KEYS = [k.strip() for k in GROQ_API_KEYS_STR.split(",") if k.strip()]

if GROQ_API_KEYS:
    main_menu = InlineKeyboardMarkup([
        [InlineKeyboardButton("🏋️‍♂️🍽️ ПРОГРАММЫ И ПИТАНИЕ", callback_data="programs_menu")],
        [InlineKeyboardButton("💎 PRO SUBSCRIPTION", callback_data="pro_menu")],
        [InlineKeyboardButton("🔥 МОЙ ПРОГРЕСС", callback_data="progress_menu")],
        [InlineKeyboardButton("📊 МОЙ ПРОГРЕСС (ручной)", callback_data="manual_progress_menu")],
        [InlineKeyboardButton("📋 НОРМАТИВЫ", callback_data="normatives_menu")],
        [InlineKeyboardButton("👥 ПРИГЛАСИТЬ ДРУЗЕЙ", callback_data="invite_menu")],
        [InlineKeyboardButton("🏆 ЛИДЕРЫ", callback_data="leaderboard_menu")],
        [InlineKeyboardButton("📓 ДНЕВНИК ТРЕНИРОВОК", callback_data="workout_log_menu")],
        [InlineKeyboardButton("🎁 РОЗЫГРЫШ", callback_data="draw_menu")],
        [InlineKeyboardButton("🤖 Ассистент", callback_data="ask_ai")],
        [InlineKeyboardButton("📝 ОНЛАЙН-ТРЕНЕР", callback_data="coach_menu")],
        [InlineKeyboardButton("📢 КАНАЛ", callback_data="channel_menu")],
        [InlineKeyboardButton("❓ FAQ", callback_data="faq_menu"), InlineKeyboardButton("📞 ПОДДЕРЖКА", callback_data="support_menu")]
    ])
else:
    main_menu = InlineKeyboardMarkup([
        [InlineKeyboardButton("🏋️‍♂️🍽️ ПРОГРАММЫ И ПИТАНИЕ", callback_data="programs_menu")],
        [InlineKeyboardButton("💎 PRO SUBSCRIPTION", callback_data="pro_menu")],
        [InlineKeyboardButton("🔥 МОЙ ПРОГРЕСС", callback_data="progress_menu")],
        [InlineKeyboardButton("📊 МОЙ ПРОГРЕСС (ручной)", callback_data="manual_progress_menu")],
        [InlineKeyboardButton("📋 НОРМАТИВЫ", callback_data="normatives_menu")],
        [InlineKeyboardButton("👥 ПРИГЛАСИТЬ ДРУЗЕЙ", callback_data="invite_menu")],
        [InlineKeyboardButton("🏆 ЛИДЕРЫ", callback_data="leaderboard_menu")],
        [InlineKeyboardButton("📓 ДНЕВНИК ТРЕНИРОВОК", callback_data="workout_log_menu")],
        [InlineKeyboardButton("🎁 РОЗЫГРЫШ", callback_data="draw_menu")],
        [InlineKeyboardButton("🤖 Ассистент", callback_data="ask_ai")],
        [InlineKeyboardButton("📝 ОНЛАЙН-ТРЕНЕР", callback_data="coach_menu")],
        [InlineKeyboardButton("📢 КАНАЛ", callback_data="channel_menu")],
        [InlineKeyboardButton("❓ FAQ", callback_data="faq_menu"), InlineKeyboardButton("📞 ПОДДЕРЖКА", callback_data="support_menu")]
    ])

programs_menu = InlineKeyboardMarkup([
    [InlineKeyboardButton("📊 ЖИМ РАСКЛАДКИ", callback_data="bench_layout")],
    [InlineKeyboardButton("💪 БОДИБИЛДИНГ", callback_data="bodybuilding")],
    [InlineKeyboardButton("🎯 МОЙ ПМ", callback_data="calculate_pm")],
    [InlineKeyboardButton("🍽️ ПИТАНИЕ", callback_data="nutrition")],
    [InlineKeyboardButton("🔙 НАЗАД", callback_data="back_to_main")]
])

pro_menu = InlineKeyboardMarkup([
    [InlineKeyboardButton("💎 КУПИТЬ PRO", callback_data="buy_menu")],
    [InlineKeyboardButton("📅 МОЯ ПОДПИСКА", callback_data="my_sub")],
    [InlineKeyboardButton("📋 ЧТО ВХОДИТ В PRO", callback_data="pro_features")],
    [InlineKeyboardButton("📋 ПРОГРАММЫ PRO", callback_data="pro_programs")],
    [InlineKeyboardButton("🍽️ КАЛЬКУЛЯТОР КАЛОРИЙ PRO", callback_data="calc_calories_pro")],
    [InlineKeyboardButton("📋 МОИ АНКЕТЫ", callback_data="my_questionnaires")],
    [InlineKeyboardButton("🔙 НАЗАД", callback_data="back_to_main")]
])

progress_menu = InlineKeyboardMarkup([
    [InlineKeyboardButton("✅ ОТМЕТИТЬ ТРЕНИРОВКУ", callback_data="checkin")],
    [InlineKeyboardButton("🔥 МОЙ СТРИК", callback_data="my_streak")],
    [InlineKeyboardButton("⏰ НАПОМИНАНИЯ ВКЛ/ВЫКЛ", callback_data="toggle_reminders")],
    [InlineKeyboardButton("🔙 НАЗАД", callback_data="back_to_main")]
])

manual_progress_menu = InlineKeyboardMarkup([
    [InlineKeyboardButton("➕ ОБНОВИТЬ СИЛОВЫЕ", callback_data="update_progress")],
    [InlineKeyboardButton("📈 ГРАФИК ПРОГРЕССА", callback_data="manual_progress_chart")],
    [InlineKeyboardButton("🗑️ УДАЛИТЬ ПРОГРЕСС", callback_data="delete_progress")],
    [InlineKeyboardButton("🔙 НАЗАД", callback_data="back_to_main")]
])

workout_log_menu = InlineKeyboardMarkup([
    [InlineKeyboardButton("➕ ЗАПИСАТЬ ТРЕНИРОВКУ", callback_data="add_workout")],
    [InlineKeyboardButton("📋 МОИ ТРЕНИРОВКИ", callback_data="my_workouts")],
    [InlineKeyboardButton("🗑️ УДАЛИТЬ ЗАПИСЬ", callback_data="delete_workout")],
    [InlineKeyboardButton("🔙 НАЗАД", callback_data="back_to_main")]
])

leaderboard_menu = InlineKeyboardMarkup([
    [InlineKeyboardButton("🏋️ ПО ЖИМУ", callback_data="leaderboard_bench")],
    [InlineKeyboardButton("🦵 ПО ПРИСЕДУ", callback_data="leaderboard_squat")],
    [InlineKeyboardButton("💪 ПО ТЯГЕ", callback_data="leaderboard_deadlift")],
    [InlineKeyboardButton("📹 ОТПРАВИТЬ ВИДЕО", callback_data="leaderboard_video")],
    [InlineKeyboardButton("🔙 НАЗАД", callback_data="back_to_main")]
])

admin_menu = InlineKeyboardMarkup([
    [InlineKeyboardButton("📊 СТАТИСТИКА", callback_data="admin_stats")],
    [InlineKeyboardButton("📊 АКТИВНОСТЬ (часы)", callback_data="admin_activity")],
    [InlineKeyboardButton("💎 СПИСОК ПОДПИСОК", callback_data="admin_subs")],
    [InlineKeyboardButton("➕ ВЫДАТЬ PRO", callback_data="admin_givepro")],
    [InlineKeyboardButton("🎲 УПРАВЛЕНИЕ РОЗЫГРЫШЕМ", callback_data="admin_draw")],
    [InlineKeyboardButton("❓ УПРАВЛЕНИЕ FAQ", callback_data="admin_faq")],
    [InlineKeyboardButton("👑 УПРАВЛЕНИЕ АДМИНАМИ", callback_data="admin_admins")],
    [InlineKeyboardButton("🏆 ПОДТВЕРДИТЬ ВИДЕО", callback_data="admin_leaderboard")],
    [InlineKeyboardButton("📊 АНАЛИТИКА ЗА НЕДЕЛЮ", callback_data="admin_analytics")],
    [InlineKeyboardButton("🔙 НАЗАД", callback_data="back_to_main")]
])

sub_kb = InlineKeyboardMarkup([
    [InlineKeyboardButton("📢 ПОДПИСАТЬСЯ", url=CHANNEL_LINK)],
    [InlineKeyboardButton("👌 Я ПОДПИСАЛСЯ", callback_data="check_sub")]
])

faq_menu_kb = InlineKeyboardMarkup([
    [InlineKeyboardButton("📞 ПОДДЕРЖКА", callback_data="support_menu")],
    [InlineKeyboardButton("🔙 НАЗАД", callback_data="back_to_main")]
])

support_menu_kb = InlineKeyboardMarkup([
    [InlineKeyboardButton("✍️ НАПИСАТЬ В ПОДДЕРЖКУ", callback_data="support_write")],
    [InlineKeyboardButton("🔙 НАЗАД", callback_data="back_to_main")]
])

coach_menu_kb = InlineKeyboardMarkup([
    [InlineKeyboardButton("📩 ЗАПИСАТЬСЯ", callback_data="coach_signup")],
    [InlineKeyboardButton("🔙 НАЗАД", callback_data="back_to_main")]
])

channel_menu_kb = InlineKeyboardMarkup([
    [InlineKeyboardButton("📢 ПОДПИСАТЬСЯ НА КАНАЛ", url=CHANNEL_LINK)],
    [InlineKeyboardButton("🔙 НАЗАД", callback_data="back_to_main")]
])

# ========= ОБНОВЛЁННЫЕ АНКЕТЫ =========

BODYBUILDING_QUESTIONS = """
💪 **БОДИБИЛДИНГ - ВЫБЕРИТЕ ТИП ТРЕНИРОВКИ:**

1️⃣ Тип тренировки (сплит/верхниз/фулбади): _______

📌 **Пример заполнения:**
сплит

❗ Если вам что-то непонятно, напишите /support или нажмите кнопку «Поддержка» — я передам ваш вопрос специалисту.
"""

BENCH_QUESTIONS = """
📊 **ЖИМ РАСКЛАДКИ - ОТВЕТЬТЕ НА ВОПРОСЫ:**

1️⃣ Ваш максимум в жиме лёжа (кг): _______

📌 **Пример заполнения:**
100

❗ Если вам что-то непонятно, напишите /support или нажмите кнопку «Поддержка» — я передам ваш вопрос специалисту.
"""

PM_QUESTIONS = """
🎯 **РАСЧЁТ ПМ - ВВЕДИТЕ ДАННЫЕ:**

Введите ваш рабочий вес и количество повторений.

📌 **Примеры:**
• 100x5  (100 кг на 5 раз)
• 110x2  (110 кг на 2 раза)
• 90x8   (90 кг на 8 раз)

Поддерживается от 2 до 9 повторений.

❗ Если вам что-то непонятно, напишите /support или нажмите кнопку «Поддержка» — я передам ваш вопрос специалисту.
"""

NUTRITION_QUESTIONS = """
🍽️ **ПИТАНИЕ - ОТВЕТЬТЕ НА ВОПРОСЫ:**

1️⃣ Ваш возраст (лет): _______
2️⃣ Ваш вес (кг): _______
3️⃣ Ваш рост (см): _______
4️⃣ Уровень активности (сидячая работа+3 тренировки/стоячая работа+2 тренировки/активный образ жизни): _______
5️⃣ Ваша цель (набор массы/сушка/поддержание): _______

📌 **Пример заполнения:**
25 / 75 / 175 / сидячая работа+3 тренировки / набор массы

❗ Если вам что-то непонятно, напишите /support или нажмите кнопку «Поддержка» — я передам ваш вопрос специалисту.
"""

CALORIES_PRO_QUESTIONS = """
🍽️ **ТОЧНЫЙ КАЛЬКУЛЯТОР КАЛОРИЙ (PRO) — ОТВЕТЬТЕ НА ВОПРОСЫ:**

1️⃣ Пол (м/ж): _______
2️⃣ Ваш возраст (лет): _______
3️⃣ Ваш вес (кг): _______
4️⃣ Ваш рост (см): _______
5️⃣ Уровень активности (1-сидячий/2-лёгкая активность/3-средняя/4-высокая/5-очень высокая): _______
6️⃣ Ваша цель (набор массы/сушка/поддержание): _______

📌 **Пример заполнения:**
м / 25 / 75 / 175 / 3 / набор массы

❗ Если вам что-то непонятно, напишите /support или нажмите кнопку «Поддержка» — я передам ваш вопрос специалисту.
"""

WORKOUT_LOG_FREE = """
📓 **ЗАПИСЬ ТРЕНИРОВКИ**

Просто напиши текст о своей тренировке. Например:

«Сегодня делал жим лёжа 5х5, потом трицепс. Чувствую себя отлично!»

Бот сохранит твою запись с датой и временем.
"""

# ========= ПРОГРАММЫ PRO =========
def get_powerlifting_program(week_num):
    if week_num == 1:
        return """
📋 **НЕДЕЛЯ 1**

**Понедельник:**
1. Присед — 4×6-8
2. Жим лёжа — 4×6-8
3. Разгибания в тренажере — 3×12-15
4. Румынская тяга с гантелями — 4×10-12
5. Хамер на верх груди — 3×10-12
6. Пресс — 8 минут

**Среда:**
1. Тяга становая — 4×5-6
2. Подтягивания с весом — 5×6-8
3. Молотки на скамье Скотта — 3×10-12
4. Горизонтальная тяга — 3×10-12
5. Махи в стороны — 4×12-15
6. Бицепс со штангой — 4×10-12

**Пятница:**
1. Жим штанги лёжа — 4×6-8
2. Жим стоя со штангой — 4×8-10
3. Трицепс из-за головы с гантелью — 6×10-12
4. Тягун лыжник — 3×10-12
5. Гиперэкстензия — 8 минут
"""
    else:
        return """
📋 **НЕДЕЛЯ 2**

**Понедельник:**
1. Жим лёжа — 4×6-8
2. Присед — 4×6-8
3. Сгибание ног в тренажере — 3×12-15
4. Болгарские выпады — 3×10-12
5. Жим гантелей — 3×10-12
6. Пресс — 8 минут

**Среда:**
1. Становая тяга — 4×5-6
2. Вертикальная тяга — 6×8-10 (3 с прямой ручкой, 3 с узкой)
3. Бицепс со штангой — 5×10-12
4. Тяга гантелей на скамье — 4×10-12
5. Махи в стороны — 4×12-15
6. Молотки на скамье Скотта — 3×10-12

**Пятница:**
1. Жим лёжа — 4×6-8
2. Жим стоя — 4×8-10
3. Трицепс на блоке — 6×10-12
4. Тягун лыжник — 3×10-12
5. Гиперэкстензия — 8 минут
"""

def get_full_program_cycle():
    week1 = get_powerlifting_program(1)
    week2 = get_powerlifting_program(2)
    return f"""
📋 **ПРОГРАММА PRO — ПОЛНЫЙ ЦИКЛ (2 НЕДЕЛИ)**

{week1}

---
{week2}

---
⚡ **ПРАВИЛА ПРОГРАММЫ:**
1. Все базовые движения — с контролем техники
2. Отдых между подходами: 2-3 минуты (база), 1-1.5 минуты (вспомогательные)
3. Перед каждой тренировкой — разминка 10-15 минут
4. Рабочие веса подбирай так, чтобы последние повторения были с усилием, но не в отказ
5. Каждую неделю добавляй 2.5-5 кг на штангу в базовых движениях
6. После 2 недель — повтор цикла с новыми весами

💡 Программа автоматически зациклена — после 2-й недели идёт 1-я.
"""

# ========= ОСНОВНЫЕ ФУНКЦИИ =========
def round_weight(weight):
    weight = round(weight * 2) / 2
    rem = weight % 2.5
    return weight - rem if rem <= 1.25 else weight + (2.5 - rem)

def calculate_pm(weight, reps):
    epley = weight * (1 + reps / 30)
    brzycki = weight * (36 / (37 - reps)) if 2 <= reps <= 9 else epley
    avg = (epley + brzycki) / 2
    return round(epley, 1), round(brzycki, 1), round(avg, 1)

def get_bench_program(pm):
    w1 = round_weight(pm * 0.7)
    w2 = round_weight(pm * 0.9)
    w3 = round_weight(pm * 0.75)
    w4 = round_weight(pm * 0.95)
    w5 = round_weight(pm * 1.1)
    w6 = round_weight(pm * 0.6)
    w7 = round_weight(pm * 0.55)
    w8 = round_weight(pm * 0.85)
    w9 = round_weight(pm * 1.25)
    w10 = round_weight(pm * 0.65)
    w11 = round_weight(pm * 1.0)
    w12 = round_weight(pm * 1.05)
    return f"""
📊 **ПРОГРАММА ПО ЖИМУ (ПМ = {pm} кг)**

*Первое число — подходы, второе — повторы (пример: 3×8 = 3 подхода по 8 повторов)*

**ВВОДНАЯ Тренировка** Пятница
• {w1}кг 5×5 — RPE 6-7 Динамика/Техника/Взрыв и Скорость

**ОСНОВНАЯ ПРОГРАММА (10 ТРЕНИРОВОК, ПН/ПТ)**

**1️⃣ ПН (рекрутирование + добивка):** Средне/Тяж жим
• {w2}кг 6×2 — RPE 7-8
• {w1}кг 1×8 — добивка

**2️⃣ ПТ (объём):** Динамика/Техника/Взрыв и Скорость
• {w3}кг 6×5 — RPE 7-8

**3️⃣ ПН (тяжёлый рекрутинг + бруски):** Тяжелый объем
• {w4}кг 6×2 — RPE 8-9
• {w5}кг с бруска 1×2 — RPE 9
• {w6}кг 1×10 — закисление

**4️⃣ ПТ (объём лёгкий):** Динамика/Техника/Взрыв и Скорость
• {w1}кг 6×4 — RPE 6-7
• {w7}кг 1×10 — добивка

**5️⃣ ПН (пауза 1 секунда + добивка):** Средний Жим/Динамика/
• {w8}кг в паузу 6×3 — RPE 8
• {w1}кг 1×5 — добивка

**6️⃣ ПТ (рекрутинг + бруски):** Тяжелый объем
• {w4}кг 6×3 — RPE 8-9
• {w9}кг с бруска 1×2
• {w1}кг 1×8 — добивка

**7️⃣ ПН (объём):** Динамика/Техника/Взрыв и Скорость
• {w3}кг 6×5 — RPE 7-8

**8️⃣ ПТ** Средний жим/Техника
• {w2}кг в паузу 6×3 — RPE 8
• {w1}кг 1×10 — добивка

**9️⃣ ПН** Динамика/Техника/Взрыв и Скорость
• {w10}кг 3×5 — RPE 6
• {w1}кг 3×4 — RPE 7

**🔟 ПТ (ПРОХОДКА):**
• {w4}кг 1×1
• {w11}кг 1×1
• {w12}кг 1×1

---

⚡ **ПРАВИЛА ПРОГРАММЫ:**
1. Рекрутирование — в конце жимовой тренировки, последним подходом добавляем 60-65% на 8-10 повторов
2. МИНИМУМ 5 подходов, оптимально 6-7
3. В отказ не работаем. Если тяжело — убавь 5-10%
4. Сон 7.5-8 часов, профицит калорий
5. Перед тяжёлыми жимами не делай трицепс/плечи
6. Все мы индивидуальны — на ком-то план сработает, на ком-то нет

📐 **Веса округлены до реальных (0, 2.5, 5, 7.5 кг)**
"""

# ========= ФУНКЦИИ ДЛЯ БОДИБИЛДИНГ =========
def get_split_program():
    return """
💪 **СПЛИТ ПРОГРАММА (3 ДНЯ В НЕДЕЛЮ)**
*Где 3×10-12: первое число — подходы, второе — повторы*

**ДЕНЬ 1: ГРУДЬ + СПИНА**
• Жим штанги лёжа — 4×8-10
• Подтягивания — 4×6-10
• Жим гантелей 45 градусов — 3×10-12
• Тяга штанги в наклоне — 4×8-10
• Бабочка — 3×12-15
• Горизонтальная тяга — 3×10-12

**ДЕНЬ 2: БИЦЕПС БЕДРА + ТРИЦЕПС + БИЦЕПС РУК**
• Румынская тяга — 4×8-10
• Сгибания ног лёжа — 3×10-12
• Французский жим — 4×10-12
• Подъём штанги на бицепс — 4×8-10
• Разгибания на блоке — 3×12-15
• Молотки — 3×10-12

**ДЕНЬ 3: КВАДРИЦЕПСЫ + ПЛЕЧИ**
• Приседания со штангой — 4×6-8
• Разгибания в тренажере — 3×8-10
• Махи гантелями в стороны — 4×12-15
• Жим гантелей сидя (90°) — 3×8-10
• Задняя дельта (разведения) в бабочке — 3×12-15
• Икры — 4×15-20
"""

def get_upper_lower_program():
    return """
💪 **ВЕРХ/НИЗ ПРОГРАММА (4 ДНЯ В НЕДЕЛЮ)**
*Где 3×10-12: первое число — подходы, второе — повторы*

**ДЕНЬ 1: ВЕРХ**
• Жим штанги лёжа — 5×6-8
• Подтягивания — 3×6-10
• Разгибание гантели из-за головы — 4×8-10
• Жим гантелей 45 градусов — 3×8-10
• Тяга штанги в наклоне — 4×6-8
• Бабочка — 3×8-12

**ДЕНЬ 2: НИЗ, ЧУТЬ ВЕРХ**
• Приседания со штангой — 4×5-8
• Румынская тяга — 4×8-10
• Бицепс со штангой — 5×10-12
• Сгибания ног — 3×10-12
• Молотки — 3×8-10

**ДЕНЬ 3: ВЕРХ**
• Жим лёжа — 5×10-12
• Вертикальная тяга — 3×10-12
• Хамер на верх груди — 3×10-12
• Горизонтальная тяга — 3×8-12
• Разгибание на блоке — 3×10-12

**ДЕНЬ 4: НИЗ, ЧУТЬ ВЕРХ**
• Жим ногами — 4×10-12
• Разгибания ног — 4×12-15
• Махи — 4×10-12
• Жим гантелей 90 градусов — 3×10-12
• Разведение в бабочке — 3×10-12
"""

def get_fullbody_program():
    return """
💪 **ФУЛБАДИ ПРОГРАММА (3 ДНЯ В НЕДЕЛЮ)**
*Где 3×10-12: первое число — подходы, второе — повторы*

**ДЕНЬ 1**
• Жим штанги лёжа — 5×6-8
• Приседания со штангой — 4×6-8
• Подтягивания — 3×6-10
• Тяга штанги в наклоне — 4×6-8
• Горизонтальная тяга — 3×8-10

**ДЕНЬ 2**
• Жим гантелей на наклонной 45 градусов — 4×10-12
• Вертикальная тяга — 3×10-12
• Жим гантелей сидя (90°) — 3×10-12
• Трицепс (французский жим или разгибание одной гантели из-за головы двумя руками) — 4×10-12
• Бицепс (подъём штанги) — 4×10-12

**ДЕНЬ 3**
• Румынская тяга — 4×8-10
• Разгибания в тренажере — 3×10-12
• Бабочка (Pec-Deck) — 3×12-15
• Махи гантелей в стороны — 4×10-12
• Сведения рук в бабочке — 3×10-12
"""

def get_supplements():
    return """
💊 **РЕКОМЕНДУЕМЫЕ ДОБАВКИ:**
• Креатин — 5 г/день
• Омега-3 — 1-2 г/день
• Магний — 300-400 мг перед сном
• Витамин D3 — 2000-4000 МЕ (при дефиците)
• Цинк — 15-30 мг/день
• BCAA — по желанию
⚠️ Перед использованием добавок проконсультируйтесь с врачом
"""

def get_workout_program(workout_type):
    if workout_type == "сплит":
        return get_split_program() + "\n\n" + get_supplements()
    elif workout_type == "верхниз":
        return get_upper_lower_program() + "\n\n" + get_supplements()
    elif workout_type == "фулбади":
        return get_fullbody_program() + "\n\n" + get_supplements()
    return get_split_program() + "\n\n" + get_supplements()

def get_nutrition_advice():
    return """
🍽️ **РЕКОМЕНДАЦИИ ПО ПИТАНИЮ**
• Белок: 1.6-2.2 г/кг веса
• Жиры: 0.8-1.2 г/кг веса
• Углеводы: остальное под калорийность
Для набора: профицит 300-500 ккал. Для сушки: дефицит 200-300 ккал.
""" + get_supplements()

def get_technique_tips():
    return """
📖 **СОВЕТЫ ПО ТЕХНИКЕ**
ЖИМ ЛЁЖА: лопатки сведены, мост в грудном отделе, ноги упираются
ПРИСЕД: колени по носкам, таз назад, корпус жёсткий
ТЯГА: спина прямая, гриф близко к ногам, толчок ногами
"""

# ========= ТОЧНЫЙ РАСЧЁТ КАЛОРИЙ =========
ACTIVITY_FACTORS = {1: 1.2, 2: 1.375, 3: 1.55, 4: 1.725, 5: 1.9}

def calculate_calories_precise(sex, age, weight, height, activity_level, goal):
    if sex == "м":
        bmr = 10 * weight + 6.25 * height - 5 * age + 5
    else:
        bmr = 10 * weight + 6.25 * height - 5 * age - 161
    factor = ACTIVITY_FACTORS.get(activity_level, 1.55)
    tdee = bmr * factor
    if "набор" in goal:
        target = tdee + 400
    elif "суш" in goal:
        target = tdee - 400
    else:
        target = tdee
    protein = weight * 2.0
    fats = weight * 1.0
    protein_kcal = protein * 4
    fats_kcal = fats * 9
    carbs_kcal = target - protein_kcal - fats_kcal
    carbs = max(carbs_kcal / 4, 0)
    return {
        "bmr": round(bmr),
        "tdee": round(tdee),
        "target": round(target),
        "protein": round(protein),
        "fats": round(fats),
        "carbs": round(carbs),
    }

# ========= УНИВЕРСАЛЬНАЯ ПРОВЕРКА ПОДПИСКИ =========
async def ensure_subscription(update, context):
    user_id = update.effective_user.id
    try:
        await asyncio.sleep(1)
        member = await context.bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        if member.status in ["member", "administrator", "creator"]:
            return True
    except Exception as e:
        logger.error(f"[ENSURE SUB ERROR] user={user_id} error={e}")
    if update.callback_query:
        try:
            await update.callback_query.message.reply_text(
                "🔒 Для использования бота подпишись на канал 👇",
                reply_markup=sub_kb
            )
        except Exception:
            pass
    elif update.message:
        await update.message.reply_text(
            "🔒 Для использования бота подпишись на канал 👇",
            reply_markup=sub_kb
        )
    return False

# ========= РЕНДЕР =========
async def render(query, text, keyboard, image="start.jpg"):
    try:
        if os.path.exists(image):
            await query.edit_message_media(
                media=InputMediaPhoto(media=open(image, "rb"), caption=text),
                reply_markup=keyboard
            )
        else:
            await query.edit_message_text(text, reply_markup=keyboard)
    except Exception as e:
        if "Message is not modified" not in str(e):
            logger.error(f"RENDER ERROR: {e}")

async def safe_answer(query):
    try:
        await query.answer()
    except Exception as e:
        logger.error(f"SAFE_ANSWER ERROR: {e}")

# ========= ФУНКЦИИ =========
def save_user_data(uid, bench, deadlift, squat, weight, age, username=None, full_name=None):
    cur = db()
    cur.execute("SELECT ref_code FROM users WHERE user_id=?", (uid,))
    row = cur.fetchone()
    ref_code = row[0] if row else generate_ref_code()
    cur.execute("""
        INSERT OR REPLACE INTO users
        (user_id, bench, deadlift, squat, weight, age, updated, username, full_name, ref_code)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (uid, bench, deadlift, squat, weight, age, datetime.now().isoformat(), username, full_name, ref_code))
    cur.execute("""
        INSERT INTO progress (user_id, bench, deadlift, squat, date)
        VALUES (?, ?, ?, ?, ?)
    """, (uid, bench, deadlift, squat, datetime.now().isoformat()))
    conn.commit()

def save_questionnaire(uid, q_type, answers, result):
    cur = db()
    cur.execute("""
        INSERT INTO questionnaires (user_id, type, answers, result, date)
        VALUES (?, ?, ?, ?, ?)
    """, (uid, q_type, answers, result, datetime.now().isoformat()))
    conn.commit()

def validate_answers_format(text, expected_parts):
    parts = re.split(r'[/\s]+', text.strip())
    if len(parts) < expected_parts:
        return False, "❌ Неверный формат. Отправьте данные по примеру."
    return True, None

# ========= РУЧНОЙ ПРОГРЕСС =========
def save_user_progress(uid, bench, deadlift, squat):
    cur = db()
    cur.execute("""
        INSERT INTO user_progress (user_id, bench, deadlift, squat, date)
        VALUES (?, ?, ?, ?, ?)
    """, (uid, bench, deadlift, squat, datetime.now().isoformat()))
    conn.commit()

def get_user_progress(uid):
    cur = db()
    cur.execute("""
        SELECT bench, deadlift, squat, date FROM user_progress
        WHERE user_id=? ORDER BY date
    """, (uid,))
    return cur.fetchall()

def delete_user_progress(uid):
    cur = db()
    cur.execute("DELETE FROM user_progress WHERE user_id=?", (uid,))
    conn.commit()
    return cur.rowcount > 0

def build_progress_chart_from_manual(uid):
    rows = get_user_progress(uid)
    if len(rows) < 2:
        return None
    dates = [datetime.fromisoformat(r[3]).strftime("%d.%m") for r in rows]
    bench = [r[0] for r in rows]
    deadlift = [r[1] for r in rows]
    squat = [r[2] for r in rows]
    plt.figure(figsize=(10, 6))
    plt.plot(dates, bench, marker='o', label='Жим')
    plt.plot(dates, deadlift, marker='o', label='Тяга')
    plt.plot(dates, squat, marker='o', label='Присед')
    plt.title('Прогресс силовых показателей (ручной ввод)')
    plt.xlabel('Дата')
    plt.ylabel('Вес, кг')
    plt.xticks(rotation=45)
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()
    return buf

# ========= НОРМАТИВЫ =========
async def normatives_menu_callback(query, context):
    await query.message.delete()
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=f"📋 **НОРМАТИВЫ ПО ПАУЭРЛИФТИНГУ**\n\n"
             f"🌐 Открой полный справочник на сайте:\n\n"
             f"🔗 `{NORMATIVES_URL}`\n\n"
             f"Там можно выбрать дисциплину, пол и федерацию.\n"
             f"Все нормативы в удобных таблицах с цветными разрядами! 🔥",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🌐 ОТКРЫТЬ НОРМАТИВЫ", url=NORMATIVES_URL)],
            [InlineKeyboardButton("🔙 НАЗАД", callback_data="back_to_main")]
        ]),
        parse_mode='Markdown',
        disable_web_page_preview=True
    )

# ========= КАНАЛ =========
async def channel_menu_callback(query, context):
    await query.message.delete()
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="📢 **ПОДПИШИСЬ НА НАШ КАНАЛ!**\n\n"
             "В канале «PWR NIK» ты найдёшь:\n"
             "🔥 Новости и анонсы\n"
             "💪 Советы по тренировкам\n"
             "📢 Розыгрыши и акции\n\n"
             "Нажми на кнопку ниже, чтобы подписаться! 👇",
        reply_markup=channel_menu_kb
    )

# ========= РЕФЕРАЛЬНАЯ СИСТЕМА =========
async def invite_menu_callback(query, context):
    uid = query.from_user.id
    cur = db()
    cur.execute("SELECT ref_code FROM users WHERE user_id=?", (uid,))
    row = cur.fetchone()
    if not row or not row[0]:
        ref_code = generate_ref_code()
        cur.execute("UPDATE users SET ref_code=? WHERE user_id=?", (ref_code, uid))
        conn.commit()
    else:
        ref_code = row[0]
    ref_link = f"https://t.me/{BOT_USERNAME}?start={ref_code}"
    
    await query.message.delete()
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=f"👥 **Пригласи друга в PWR!**\n\n"
             f"🔗 Твоя реферальная ссылка:\n`{ref_link}`\n\n"
             f"📌 Когда друг перейдёт по ссылке, **вы оба получите 1 день PRO-подписки!**\n\n"
             f"📌 Подписка **суммируется**: пригласи 3 друзей — получи 3 дня PRO!\n\n"
             f"🎁 **Сейчас все основные функции бота** (жим раскладки, бодибилдинг, ПМ, питание, стрики, лидеры, дневник) — **полностью бесплатны** для всех!\n\n"
             f"💎 **PRO-подписка** даёт доступ к эксклюзивным программам тренировок и циклам на 2 недели.\n\n"
             f"🔒 В однодневной подписке (за приглашение) эксклюзивные программы **НЕДОСТУПНЫ** — только в полной PRO-подписке.",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 НАЗАД", callback_data="back_to_main")]
        ])
    )

async def handle_referral(update, context):
    uid = update.effective_user.id
    if context.args and context.args[0].startswith('ref_'):
        ref_code = context.args[0]
        cur = db()
        cur.execute("SELECT user_id FROM users WHERE ref_code=? AND user_id!=?", (ref_code, uid))
        row = cur.fetchone()
        if not row:
            return
        referrer_id = row[0]
        cur.execute("SELECT 1 FROM referrals WHERE referred_id=?", (uid,))
        if cur.fetchone():
            return
        cur.execute("INSERT INTO referrals (referrer_id, referred_id, date) VALUES (?, ?, ?)",
                    (referrer_id, uid, datetime.now().isoformat()))
        conn.commit()
        try:
            cur.execute("SELECT until, sub_type FROM subs WHERE user_id=?", (referrer_id,))
            row = cur.fetchone()
            if row:
                until = datetime.fromisoformat(row[0])
                if datetime.now() < until:
                    new_until = until + timedelta(days=1)
                    new_type = row[1] + " + бонус за реферала"
                else:
                    new_until = datetime.now() + timedelta(days=1)
                    new_type = "Бонус за реферала (1 день)"
            else:
                new_until = datetime.now() + timedelta(days=1)
                new_type = "Бонус за реферала (1 день)"
            cur.execute("INSERT OR REPLACE INTO subs VALUES (?, ?, ?)", (referrer_id, new_until.isoformat(), "ref_pro: " + new_type))
            conn.commit()
            await context.bot.send_message(referrer_id, f"🎉 Твой друг присоединился! Ты получил +1 день PRO-подписки! (суммируется) 🎁")
        except Exception:
            pass
        try:
            cur.execute("SELECT until, sub_type FROM subs WHERE user_id=?", (uid,))
            row = cur.fetchone()
            if row:
                until = datetime.fromisoformat(row[0])
                if datetime.now() < until:
                    new_until = until + timedelta(days=1)
                    new_type = row[1] + " + бонус за регистрацию"
                else:
                    new_until = datetime.now() + timedelta(days=1)
                    new_type = "Бонус за регистрацию (1 день)"
            else:
                new_until = datetime.now() + timedelta(days=1)
                new_type = "Бонус за регистрацию (1 день)"
            cur.execute("INSERT OR REPLACE INTO subs VALUES (?, ?, ?)", (uid, new_until.isoformat(), "ref_pro: " + new_type))
            conn.commit()
        except Exception:
            pass
        await update.message.reply_text("🎉 Отлично! Ты пришёл по ссылке друга и получил +1 день PRO-подписки (суммируется)! 🎁")

# ========= ОНЛАЙН-ВЕДЕНИЕ =========
async def coach_menu_callback(query, context):
    await query.message.delete()
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="👨‍🏫 **ОНЛАЙН-ВЕДЕНИЕ ОТ АВТОРА**\n\n"
             "Что входит:\n"
             "✅ Индивидуальная программа тренировок по **ЖИМУ ЛЁЖА**\n"
             "✅ Еженедельная корректировка плана\n"
             "✅ Разбор техники по видео\n"
             "✅ Персональный план питания и БЖУ\n"
             "✅ Обратная связь 24/7\n\n"
             "💰 **Стоимость:** 2 000 ₽ / месяц\n\n"
             "📌 **Как записаться:**\n"
             "Нажмите кнопку «Записаться» — я свяжусь с вами в ближайшее время.",
        reply_markup=coach_menu_kb
    )

async def coach_signup_callback(query, context):
    uid = query.from_user.id
    username = query.from_user.username or f"ID: {uid}"
    full_name = query.from_user.full_name or "Не указано"
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✉️ Написать пользователю", callback_data=f"support_reply_{uid}")]
    ])
    await context.bot.send_message(
        REQUESTS_CHAT,
        f"📝 **НОВАЯ ЗАЯВКА НА ОНЛАЙН-ВЕДЕНИЕ**\n"
        f"👤 Имя: {full_name}\n"
        f"🆔 ID: {uid}\n"
        f"📱 Username: @{username}\n\n"
        f"Свяжитесь с пользователем для обсуждения деталей.",
        reply_markup=kb
    )
    
    await query.message.edit_text(
        "✅ **Заявка отправлена!**\n\n"
        "Я свяжусь с вами в ближайшее время. Обычно это занимает не более часа.\n\n"
        "Если у вас есть вопросы, напишите /support.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 НАЗАД", callback_data="back_to_main")]
        ])
    )
    await safe_answer(query)

async def coach_cmd(update, context):
    uid = update.effective_user.id
    await update.message.reply_text(
        "👨‍🏫 **Запись на онлайн-ведение**\n\n"
        "Нажмите кнопку ниже, чтобы оставить заявку.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📩 ЗАПИСАТЬСЯ", callback_data="coach_signup")],
            [InlineKeyboardButton("🔙 НАЗАД", callback_data="back_to_main")]
        ])
    )

# ========= ОБРАБОТКА АНКЕТ =========
async def process_bench_survey(update, context, answers_text):
    uid = update.effective_user.id
    try:
        pm = int(re.search(r"(\d+)", answers_text).group(1))
        if pm < 20 or pm > 500:
            await update.message.reply_text("❌ Введите корректный вес (20-500 кг)")
            return
    except Exception:
        await update.message.reply_text("❌ Введите число. Пример: 100")
        return
    result = get_bench_program(pm)
    await update.message.reply_text(result)
    save_questionnaire(uid, "bench", answers_text, result)

async def process_pm_survey(update, context, answers_text):
    match = re.search(r"(\d+)\s*[хx×\s]*\s*(\d+)", answers_text, re.IGNORECASE)
    if not match:
        await update.message.reply_text("❌ Неверный формат. Отправьте: 100x5 или 100 кг на 5")
        return
    weight = int(match.group(1))
    reps = int(match.group(2))
    if reps < 2 or reps > 9:
        await update.message.reply_text("❌ Количество повторений должно быть от 2 до 9")
        return
    epley, brzycki, avg = calculate_pm(weight, reps)
    result = f"""
🎯 **РАСЧЁТ ОДНОПОВТОРНОГО МАКСИМУМА (ПМ)**

📊 Введено: **{weight} кг × {reps} раз**

📐 **Формула Эпли:** ПМ = **{epley} кг**
📐 **Формула Бржицки:** ПМ = **{brzycki} кг**
⭐ **СРЕДНИЙ ПМ:** **{avg} кг**

---
💡 Ваш примерный одноповторный максимум — **{avg} кг**
Используйте это значение для расчёта процентов в программах.
"""
    await update.message.reply_text(result)
    save_questionnaire(update.effective_user.id, "pm", answers_text, result)

async def process_bodybuilding_survey(update, context, answers_text):
    uid = update.effective_user.id
    parts = re.split(r'[/\s]+', answers_text.strip())
    parts = [p for p in parts if p]
    if len(parts) < 1:
        await update.message.reply_text(
            "❌ Неверный формат. Отправьте тип тренировки:\n"
            "• сплит\n"
            "• верхниз\n"
            "• фулбади"
        )
        return
    
    workout_type = parts[0].lower()
    if workout_type not in ["сплит", "верхниз", "фулбади"]:
        await update.message.reply_text(
            "❌ Доступные типы тренировок:\n"
            "• сплит\n"
            "• верхниз\n"
            "• фулбади"
        )
        return
    
    result = f"""
💪 **БОДИБИЛДИНГ ПРОГРАММА**

**Тип тренировки:** {workout_type.upper()}

{get_workout_program(workout_type)}
"""
    await update.message.reply_text(result)
    save_questionnaire(uid, "bodybuilding", answers_text, result)

async def process_nutrition_survey(update, context, answers_text):
    parts = re.split(r'[/\s]+', answers_text)
    weight = parts[1] if len(parts) > 1 and parts[1].isdigit() else "?"
    result = f"""
🍽️ **ПЕРСОНАЛЬНЫЙ ПЛАН ПИТАНИЯ**

{get_nutrition_advice()}

**РАСЧЁТ БЖУ (при весе {weight} кг):**
• Белок: {int(float(weight)*1.8) if weight != "?" else "?"} г/день
• Жиры: {int(float(weight)*1.0) if weight != "?" else "?"} г/день
• Калории для набора: {int(float(weight)*35) if weight != "?" else "?"} ккал/день
"""
    await update.message.reply_text(result)
    save_questionnaire(update.effective_user.id, "nutrition", answers_text, result)

async def process_calories_pro_survey(update, context, answers_text):
    uid = update.effective_user.id
    if not is_full_pro(uid):
        await update.message.reply_text(
            "🔒 **Точный калькулятор калорий доступен только с полной PRO-подпиской.**\n\n"
            "Оформите подписку через меню «PRO SUBSCRIPTION» → «КУПИТЬ PRO»."
        )
        return
    parts = re.split(r'[/\s]+', answers_text.strip())
    parts = [p for p in parts if p]
    if len(parts) < 6:
        await update.message.reply_text("❌ Неверный формат. Отправьте: м / 25 / 75 / 175 / 3 / набор массы")
        return
    sex_raw, age_raw, weight_raw, height_raw, activity_raw = parts[0], parts[1], parts[2], parts[3], parts[4]
    goal_raw = " ".join(parts[5:])
    sex = "м" if sex_raw.lower().startswith("м") else "ж"
    try:
        age = int(age_raw)
        weight = float(weight_raw)
        height = float(height_raw)
        activity_level = int(activity_raw)
        if not (10 <= age <= 100 and 30 <= weight <= 300 and 100 <= height <= 250 and 1 <= activity_level <= 5):
            raise ValueError
    except (ValueError, TypeError):
        await update.message.reply_text("❌ Проверьте числовые значения")
        return
    data = calculate_calories_precise(sex, age, weight, height, activity_level, goal_raw.lower())
    result = f"""
🍽️ **ТОЧНЫЙ РАСЧЁТ КАЛОРИЙ (Миффлин-Сан Жеор)**

👤 Пол: {sex_raw} | Возраст: {age} | Вес: {weight} кг | Рост: {height} см

📐 **Базовый обмен (BMR):** {data['bmr']} ккал/день
🔥 **Расход с учётом активности (TDEE):** {data['tdee']} ккал/день
🎯 **Целевая калорийность ({goal_raw}):** {data['target']} ккал/день

**БЖУ:** Белки: {data['protein']} г | Жиры: {data['fats']} г | Углеводы: {data['carbs']} г
"""
    await update.message.reply_text(result)
    save_questionnaire(uid, "calories_pro", answers_text, result)

# ========= ДНЕВНИК ТРЕНИРОВОК =========
def save_workout(uid, text):
    cur = db()
    cur.execute("""
        INSERT INTO workout_log (user_id, date, notes)
        VALUES (?, ?, ?)
    """, (uid, datetime.now().isoformat(), text))
    conn.commit()

def get_user_workouts(uid, limit=10):
    cur = db()
    cur.execute("""
        SELECT id, date, notes FROM workout_log
        WHERE user_id=? ORDER BY date DESC LIMIT ?
    """, (uid, limit))
    return cur.fetchall()

def delete_workout(uid, workout_id):
    cur = db()
    cur.execute("DELETE FROM workout_log WHERE id=? AND user_id=?", (workout_id, uid))
    conn.commit()
    return cur.rowcount > 0

async def add_workout_callback(query, context):
    context.user_data["awaiting_workout"] = True
    await query.message.reply_text(WORKOUT_LOG_FREE)

async def handle_workout_input(update, context):
    uid = update.effective_user.id
    text = update.message.text.strip()
    save_workout(uid, text)
    await update.message.reply_text(
        f"✅ Тренировка записана!\n\n📝 {text}",
        reply_markup=workout_log_menu
    )

async def my_workouts_callback(query, context):
    uid = query.from_user.id
    rows = get_user_workouts(uid)
    if not rows:
        await query.message.reply_text("📓 У тебя пока нет записей тренировок.", reply_markup=workout_log_menu)
        return
    text = "📓 **ТВОИ ПОСЛЕДНИЕ ТРЕНИРОВКИ:**\n\n"
    for wid, date, notes in rows:
        dt = datetime.fromisoformat(date).strftime("%d.%m.%Y %H:%M")
        text += f"📅 {dt}\n📝 {notes}\n🆔 ID: {wid}\n\n"
    await query.message.reply_text(text, parse_mode='Markdown', reply_markup=workout_log_menu)

async def delete_workout_callback(query, context):
    await query.message.reply_text(
        "✍️ Отправь ID записи, которую хочешь удалить.\n"
        "Например: `123`\n\n"
        "IDs можно посмотреть в «МОИ ТРЕНИРОВКИ».",
        reply_markup=workout_log_menu
    )
    context.user_data["awaiting_delete_workout"] = True

async def handle_delete_workout(update, context):
    uid = update.effective_user.id
    try:
        workout_id = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Введи число (ID записи).")
        return
    if delete_workout(uid, workout_id):
        await update.message.reply_text(f"✅ Запись {workout_id} удалена.", reply_markup=workout_log_menu)
    else:
        await update.message.reply_text("❌ Запись не найдена или она не твоя.", reply_markup=workout_log_menu)

# ========= ЛИДЕРЫ =========
async def leaderboard_menu_callback(query, context):
    await query.message.delete()
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="🏆 **ТАБЛИЦА ЛИДЕРОВ**\n\n"
             "Выбери дисциплину, чтобы посмотреть топ:\n\n"
             "📹 **Как попасть в лидеры:**\n"
             "1. Сними видео своего подхода\n"
             "2. Напиши в сообщении: `ЖИМ 150` или `ПРИСЕД 180`\n"
             "3. Отправь видео в бот через кнопку «ОТПРАВИТЬ ВИДЕО»\n"
             "4. Администратор проверит и добавит результат!",
        reply_markup=leaderboard_menu
    )

async def show_leaderboard(query, context, exercise):
    col_map = {'bench': 'bench', 'squat': 'squat', 'deadlift': 'deadlift'}
    col = col_map.get(exercise, 'bench')
    cur = db()
    cur.execute(f"""
        SELECT user_id, {col}, weight, username, full_name
        FROM users
        WHERE {col} > 0
        ORDER BY {col} DESC
        LIMIT 10
    """)
    rows = cur.fetchall()
    if not rows:
        await query.message.reply_text("📊 Пока нет данных для таблицы лидеров.", reply_markup=leaderboard_menu)
        return
    names = {'bench': 'ЖИМ', 'squat': 'ПРИСЕД', 'deadlift': 'ТЯГА'}
    text = f"🏆 **ТОП-10 ПО {names.get(exercise, exercise)}**\n\n"
    for i, (uid_row, val, weight, username, full_name) in enumerate(rows, 1):
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"{i}.")
        name = username or full_name or f"ID{uid_row}"
        pro_badge = "💎" if is_full_pro(uid_row) else ""
        text += f"{medal} **{name}** {pro_badge} — {val} кг"
        if weight and weight > 0:
            text += f" (вес {weight} кг)"
        text += "\n"
    await query.message.reply_text(text, parse_mode='Markdown', reply_markup=leaderboard_menu)

async def leaderboard_video_callback(query, context):
    uid = query.from_user.id
    await query.message.reply_text(
        "📹 **Отправь видео для таблицы лидеров**\n\n"
        "Инструкция:\n"
        "1. Сними видео, как ты выполняешь упражнение\n"
        "2. В сообщении напиши: `ЖИМ 150` или `ПРИСЕД 180` или `ТЯГА 200`\n"
        "3. Отправь видео одним сообщением\n\n"
        "Администратор проверит и добавит результат в таблицу!"
    )
    context.user_data["awaiting_leaderboard_video"] = True

async def handle_leaderboard_video(update, context):
    uid = update.effective_user.id

    if not update.message.video and not update.message.video_note:
        await update.message.reply_text(
            "❌ Отправь видео (MP4 или кружок).\n"
            "Фото и другие файлы не принимаются."
        )
        return

    caption = update.message.caption or ""
    if not caption.strip():
        await update.message.reply_text(
            "❌ Напиши в сообщении: `ЖИМ 150` или `ПРИСЕД 180` или `ТЯГА 200`"
        )
        return

    match = re.search(r'(ЖИМ|ПРИСЕД|ТЯГА)\s*(\d+)', caption.upper())
    if not match:
        await update.message.reply_text(
            "❌ Не распознано упражнение и вес.\n"
            "Пример: `ЖИМ 150` или `ПРИСЕД 180` или `ТЯГА 200`"
        )
        return

    exercise = match.group(1)
    weight = int(match.group(2))
    exercise_map = {'ЖИМ': 'bench', 'ПРИСЕД': 'squat', 'ТЯГА': 'deadlift'}
    exercise_db = exercise_map.get(exercise)

    if weight < 10 or weight > 500:
        await update.message.reply_text("❌ Укажи реальный вес (от 10 до 500 кг).")
        return

    context.user_data["awaiting_leaderboard_video"] = False

    video_file_id = update.message.video.file_id if update.message.video else update.message.video_note.file_id

    cur = db()
    cur.execute("""
        INSERT INTO leaderboard_requests (user_id, exercise, weight, video_file_id, status, date)
        VALUES (?, ?, ?, ?, 'pending', ?)
    """, (uid, exercise_db, weight, video_file_id, datetime.now().isoformat()))
    conn.commit()
    request_id = cur.lastrowid

    username = update.effective_user.username or f"ID: {uid}"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Подтвердить", callback_data=f"lb_accept_{request_id}")],
        [InlineKeyboardButton("❌ Отклонить", callback_data=f"lb_reject_{request_id}")]
    ])

    try:
        await context.bot.send_video(
            chat_id=LEADERBOARD_GROUP,
            video=video_file_id,
            caption=f"📹 **НОВАЯ ЗАЯВКА В ЛИДЕРЫ**\n"
                    f"👤 @{username}\n"
                    f"🆔 ID: {uid}\n"
                    f"🏋️ {exercise}: {weight} кг",
            reply_markup=kb
        )
        await update.message.reply_text("✅ Видео отправлено на проверку администратору!")
        logger.info(f"Видео от {uid} отправлено в группу {LEADERBOARD_GROUP}")
    except Exception as e:
        logger.error(f"Ошибка отправки видео в группу: {e}")
        await update.message.reply_text(
            "❌ Не удалось отправить видео на проверку. Обратитесь в поддержку через кнопку «Поддержка»."
        )
        try:
            await context.bot.send_message(
                REQUESTS_CHAT,
                f"⚠️ Ошибка отправки видео в лидеры от пользователя {uid} (@{username})\n"
                f"Ошибка: {e}"
            )
        except Exception as e2:
            logger.error(f"Не удалось уведомить админов об ошибке: {e2}")

async def combined_video_handler(update, context):
    uid = update.effective_user.id
    if is_banned(uid):
        await update.message.reply_text("⛔ Вы забанены.")
        return
    if not check_antiflood(uid):
        await update.message.reply_text("⏳ Слишком часто!")
        return

    if context.user_data.get("awaiting_leaderboard_video"):
        await handle_leaderboard_video(update, context)
        return

    await update.message.reply_text("❓ Отправь видео для таблицы лидеров через кнопку «ОТПРАВИТЬ ВИДЕО».")

async def admin_leaderboard_callback(query, context):
    if not is_admin(query.from_user.id):
        await query.answer("⛔ Нет доступа!", show_alert=True)
        return
    cur = db()
    cur.execute("""
        SELECT id, user_id, exercise, weight, status, date
        FROM leaderboard_requests
        WHERE status='pending'
        ORDER BY date DESC
    """)
    rows = cur.fetchall()
    if not rows:
        await query.message.reply_text("📋 Нет заявок на подтверждение.", reply_markup=admin_menu)
        return
    text = "📋 **Заявки в лидеры:**\n\n"
    for rid, uid, exercise, weight, status, date in rows:
        dt = datetime.fromisoformat(date).strftime("%d.%m.%Y %H:%M")
        text += f"🆔 {rid} — ID{uid} — {exercise}: {weight} кг ({dt})\n"
    text += "\nИспользуй кнопки в группе для подтверждения."
    await query.message.reply_text(text, parse_mode='Markdown', reply_markup=admin_menu)

async def leaderboard_accept(query, context):
    if not is_admin(query.from_user.id):
        await query.answer("⛔ Нет доступа!", show_alert=True)
        return
    request_id = int(query.data.split('_')[2])
    cur = db()
    cur.execute("SELECT user_id, exercise, weight FROM leaderboard_requests WHERE id=?", (request_id,))
    row = cur.fetchone()
    if not row:
        await query.edit_message_caption("❌ Заявка не найдена.")
        return
    uid, exercise, weight = row
    cur.execute(f"UPDATE users SET {exercise}=? WHERE user_id=?", (weight, uid))
    cur.execute("UPDATE leaderboard_requests SET status='approved' WHERE id=?", (request_id,))
    conn.commit()
    logger.info(f"✅ Лидер обновлён: пользователь {uid}, {exercise}: {weight} кг")
    await query.edit_message_caption(f"✅ Подтверждено! {exercise}: {weight} кг")
    try:
        await context.bot.send_message(uid, f"🎉 Твой результат {exercise}: {weight} кг подтверждён! Ты в таблице лидеров!")
    except Exception:
        pass

async def leaderboard_reject(query, context):
    if not is_admin(query.from_user.id):
        await query.answer("⛔ Нет доступа!", show_alert=True)
        return
    request_id = int(query.data.split('_')[2])
    cur = db()
    cur.execute("SELECT user_id FROM leaderboard_requests WHERE id=?", (request_id,))
    row = cur.fetchone()
    if row:
        uid = row[0]
        try:
            await context.bot.send_message(uid, "❌ Твоё видео отклонено. Попробуй ещё раз.")
        except Exception:
            pass
    cur.execute("UPDATE leaderboard_requests SET status='rejected' WHERE id=?", (request_id,))
    conn.commit()
    await query.edit_message_caption("❌ Отклонено")

# ========= ПРОБНЫЙ PRO =========
async def trial_cmd(update, context):
    uid = update.effective_user.id
    cur = db()
    cur.execute("SELECT 1 FROM trial_used WHERE user_id=?", (uid,))
    if cur.fetchone():
        await update.message.reply_text("❌ Ты уже активировал пробный период ранее.")
        return
    cur.execute("SELECT until FROM subs WHERE user_id=?", (uid,))
    row = cur.fetchone()
    if row and datetime.now() < datetime.fromisoformat(row[0]):
        await update.message.reply_text("❌ У тебя уже есть активная PRO-подписка.")
        return
    until = datetime.now() + timedelta(days=3)
    cur.execute("INSERT OR REPLACE INTO subs VALUES (?, ?, ?)", (uid, until.isoformat(), "Пробный PRO (3 дня) - trial"))
    cur.execute("INSERT INTO trial_used VALUES (?, ?)", (uid, datetime.now().isoformat()))
    conn.commit()
    await update.message.reply_text(
        f"🎉 **Пробный PRO активирован!**\n\n"
        f"📅 Действует до: {until.strftime('%d.%m.%Y')}\n\n"
        f"💎 Теперь тебе доступны все PRO-функции бота!",
        reply_markup=main_menu
    )

# ========= ПРОМОКОДЫ =========
def create_promo_code(code, discount_percent, max_uses, valid_days=30):
    cur = db()
    valid_until = (datetime.now() + timedelta(days=valid_days)).isoformat()
    cur.execute("""
        INSERT OR REPLACE INTO promo_codes (code, discount_percent, valid_until, max_uses, created_by, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (code, discount_percent, valid_until, max_uses, 0, datetime.now().isoformat()))
    conn.commit()
    return True

def activate_promo(user_id, code):
    cur = db()
    cur.execute("SELECT discount_percent, valid_until, max_uses, used_count FROM promo_codes WHERE code=?", (code,))
    row = cur.fetchone()
    if not row:
        return False, "Промокод не найден"
    discount, valid_until, max_uses, used_count = row
    if datetime.now() > datetime.fromisoformat(valid_until):
        return False, "Промокод истёк"
    if used_count >= max_uses:
        return False, "Промокод уже использован максимальное количество раз"
    cur.execute("SELECT 1 FROM promo_activations WHERE user_id=? AND code=?", (user_id, code))
    if cur.fetchone():
        return False, "Ты уже активировал этот промокод"
    cur.execute("UPDATE promo_codes SET used_count = used_count + 1 WHERE code=?", (code,))
    cur.execute("INSERT INTO promo_activations (user_id, code, activated_at) VALUES (?, ?, ?)",
                (user_id, code, datetime.now().isoformat()))
    conn.commit()
    return True, discount

async def create_promo_cmd(update, context):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Нет доступа!")
        return
    if len(context.args) < 3:
        await update.message.reply_text("❌ /create_promo КОД СКИДКА% ЛИМИТ\n\nПример: `/create_promo SUMMER2024 30 10`")
        return
    code = context.args[0].upper()
    try:
        discount = int(context.args[1])
        max_uses = int(context.args[2])
    except ValueError:
        await update.message.reply_text("❌ Скидка и лимит должны быть числами.")
        return
    if discount < 1 or discount > 100:
        await update.message.reply_text("❌ Скидка должна быть от 1 до 100%.")
        return
    if max_uses < 1:
        await update.message.reply_text("❌ Лимит использований должен быть больше 0.")
        return
    if create_promo_code(code, discount, max_uses):
        await update.message.reply_text(f"✅ Промокод **{code}** создан!\nСкидка: {discount}%\nЛимит: {max_uses}")
    else:
        await update.message.reply_text("❌ Не удалось создать промокод.")

async def promo_cmd(update, context):
    uid = update.effective_user.id
    if not context.args:
        await update.message.reply_text("❌ Использование: /promo КОД")
        return
    code = context.args[0].upper()
    success, result = activate_promo(uid, code)
    if success:
        discount = result
        await update.message.reply_text(
            f"🎉 **Промокод {code} активирован!**\n\n"
            f"💰 Скидка: **{discount}%** на PRO-подписку!\n\n"
            f"Перейди в меню «PRO SUBSCRIPTION» → «КУПИТЬ PRO».",
            reply_markup=main_menu
        )
    else:
        await update.message.reply_text(f"❌ {result}")

async def list_promo_cmd(update, context):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Нет доступа!")
        return
    cur = db()
    cur.execute("SELECT code, discount_percent, valid_until, max_uses, used_count FROM promo_codes")
    rows = cur.fetchall()
    if not rows:
        await update.message.reply_text("📋 Активных промокодов нет.")
        return
    text = "📋 **Список промокодов:**\n\n"
    for code, discount, valid_until, max_uses, used_count in rows:
        valid_until_dt = datetime.fromisoformat(valid_until).strftime("%d.%m.%Y")
        text += f"• **{code}** — {discount}% (исп. {used_count}/{max_uses}) до {valid_until_dt}\n"
    await update.message.reply_text(text, parse_mode='Markdown')

async def delete_promo_cmd(update, context):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Нет доступа!")
        return
    if not context.args:
        await update.message.reply_text("❌ Использование: /delete_promo КОД")
        return
    code = context.args[0].upper()
    cur = db()
    cur.execute("DELETE FROM promo_codes WHERE code=?", (code,))
    conn.commit()
    await update.message.reply_text(f"✅ Промокод {code} удалён.")

# ========= СТАТИСТИКА АКТИВНОСТИ =========
def log_activity(uid, action):
    cur = db()
    hour = datetime.now().hour
    cur.execute("INSERT INTO activity_stats (user_id, hour, date, action) VALUES (?, ?, ?, ?)",
                (uid, hour, datetime.now().strftime("%Y-%m-%d"), action))
    conn.commit()

async def admin_activity_callback(query, context):
    if not is_admin(query.from_user.id):
        await query.answer("⛔ Нет доступа!", show_alert=True)
        return
    cur = db()
    cur.execute("""
        SELECT hour, COUNT(*) FROM activity_stats
        WHERE date = date('now')
        GROUP BY hour
        ORDER BY hour
    """)
    rows = cur.fetchall()
    if not rows:
        await query.message.reply_text("📊 Нет данных активности за сегодня.", reply_markup=admin_menu)
        return
    text = "📊 **Активность пользователей (сегодня):**\n\n"
    for hour, count in rows:
        bar = "█" * min(count // 2, 20)
        text += f"{hour:02d}:00 — {bar} ({count})\n"
    await query.message.reply_text(text, parse_mode='Markdown', reply_markup=admin_menu)

# ========= УПРАВЛЕНИЕ АДМИНАМИ =========
async def add_admin_cmd(update, context):
    if not is_super_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Только супер-админ может назначать админов!")
        return
    if not context.args:
        await update.message.reply_text("❌ Использование: /add_admin ID")
        return
    try:
        uid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Неверный ID")
        return
    cur = db()
    cur.execute("INSERT OR REPLACE INTO admins (user_id, added_by, added_at) VALUES (?, ?, ?)",
                (uid, update.effective_user.id, datetime.now().isoformat()))
    conn.commit()
    await update.message.reply_text(f"✅ Пользователь {uid} назначен админом!")
    try:
        await context.bot.send_message(uid, "👑 Вас назначили админом бота PWR!")
    except Exception:
        pass

async def remove_admin_cmd(update, context):
    if not is_super_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Только супер-админ может удалять админов!")
        return
    if not context.args:
        await update.message.reply_text("❌ Использование: /remove_admin ID")
        return
    try:
        uid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Неверный ID")
        return
    cur = db()
    cur.execute("DELETE FROM admins WHERE user_id=?", (uid,))
    conn.commit()
    await update.message.reply_text(f"✅ Пользователь {uid} лишён прав админа.")

async def list_admins_cmd(update, context):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Нет доступа!")
        return
    cur = db()
    cur.execute("SELECT user_id, added_by, added_at FROM admins")
    rows = cur.fetchall()
    text = "👑 **Список админов:**\n\n"
    text += "• Супер-админы: " + ", ".join([str(uid) for uid in SUPER_ADMINS]) + "\n"
    if rows:
        for uid, added_by, added_at in rows:
            dt = datetime.fromisoformat(added_at).strftime("%d.%m.%Y")
            text += f"• {uid} (добавлен {dt})\n"
    else:
        text += "• Назначенных админов нет."
    await update.message.reply_text(text, parse_mode='Markdown')

# ========= СТРИК-СИСТЕМА =========
def get_streak(uid):
    cur = db()
    cur.execute("SELECT current_streak, best_streak, last_checkin FROM streaks WHERE user_id=?", (uid,))
    return cur.fetchone()

def do_checkin(uid):
    now = datetime.now()
    row = get_streak(uid)
    cur = db()
    if not row:
        cur.execute("INSERT INTO streaks (user_id, current_streak, best_streak, last_checkin) VALUES (?, 1, 1, ?)",
                    (uid, now.isoformat()))
        conn.commit()
        return 1, 1, True, False
    current_streak, best_streak, last_checkin = row
    last_dt = datetime.fromisoformat(last_checkin)
    if last_dt.date() == now.date():
        return current_streak, best_streak, False, True
    hours_passed = (now - last_dt).total_seconds() / 3600
    if hours_passed <= STREAK_GRACE_HOURS:
        new_streak = current_streak + 1
    else:
        new_streak = 1
    is_record = new_streak > best_streak
    new_best = max(new_streak, best_streak)
    cur.execute("UPDATE streaks SET current_streak=?, best_streak=?, last_checkin=? WHERE user_id=?",
                (new_streak, new_best, now.isoformat(), uid))
    conn.commit()
    return new_streak, new_best, is_record, False

def get_reminders_enabled(uid):
    cur = db()
    cur.execute("SELECT enabled FROM reminder_settings WHERE user_id=?", (uid,))
    row = cur.fetchone()
    return bool(row[0]) if row else True

def toggle_reminders_setting(uid):
    cur = db()
    current = get_reminders_enabled(uid)
    new_val = 0 if current else 1
    cur.execute("INSERT OR REPLACE INTO reminder_settings (user_id, enabled) VALUES (?, ?)", (uid, new_val))
    conn.commit()
    return bool(new_val)

# ========= FAQ =========
def get_all_faq():
    cur = db()
    cur.execute("SELECT id, question, answer FROM faq ORDER BY id")
    return cur.fetchall()

def add_faq_entry(question, answer):
    cur = db()
    cur.execute("INSERT INTO faq (question, answer) VALUES (?, ?)", (question, answer))
    conn.commit()
    return cur.lastrowid

def delete_faq_entry(faq_id):
    cur = db()
    cur.execute("DELETE FROM faq WHERE id=?", (faq_id,))
    conn.commit()
    return cur.rowcount > 0

def build_faq_text():
    rows = get_all_faq()
    if not rows:
        return "❓ **ЧАСТЫЕ ВОПРОСЫ**\n\nПока вопросов нет."
    text = "❓ **ЧАСТЫЕ ВОПРОСЫ**\n\n"
    for _id, question, answer in rows:
        text += f"**{question}**\n{answer}\n\n"
    return text

# ========= ПОДДЕРЖКА =========
def set_support_mode(uid):
    cur = db()
    cur.execute("INSERT OR REPLACE INTO support_mode (user_id, started_at) VALUES (?, ?)",
                (uid, datetime.now().isoformat()))
    conn.commit()

def is_in_support_mode(uid):
    cur = db()
    cur.execute("SELECT 1 FROM support_mode WHERE user_id=?", (uid,))
    return cur.fetchone() is not None

def clear_support_mode(uid):
    cur = db()
    cur.execute("DELETE FROM support_mode WHERE user_id=?", (uid,))
    conn.commit()

# ========= ЭКСПОРТ ПРОГРАММЫ В PDF =========
_CYRILLIC_FONT_REGISTERED = False
_CYRILLIC_FONT_NAME = "Helvetica"
_CYRILLIC_FONT_NAME_BOLD = "Helvetica-Bold"

def _ensure_cyrillic_font():
    global _CYRILLIC_FONT_REGISTERED, _CYRILLIC_FONT_NAME, _CYRILLIC_FONT_NAME_BOLD
    if _CYRILLIC_FONT_REGISTERED:
        return
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    base_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        (os.path.join(base_dir, "fonts", "DejaVuSans.ttf"),
         os.path.join(base_dir, "fonts", "DejaVuSans-Bold.ttf")),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ]
    for regular_path, bold_path in candidates:
        if os.path.exists(regular_path):
            try:
                pdfmetrics.registerFont(TTFont("DejaVuSans", regular_path))
                _CYRILLIC_FONT_NAME = "DejaVuSans"
                if os.path.exists(bold_path):
                    pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", bold_path))
                    _CYRILLIC_FONT_NAME_BOLD = "DejaVuSans-Bold"
                else:
                    _CYRILLIC_FONT_NAME_BOLD = "DejaVuSans"
                _CYRILLIC_FONT_REGISTERED = True
                return
            except Exception:
                pass

def build_program_pdf(uid, title, content_text):
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.lib.enums import TA_LEFT
    _ensure_cyrillic_font()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            topMargin=20*mm, bottomMargin=20*mm,
                            leftMargin=18*mm, rightMargin=18*mm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('TitleRu', parent=styles['Title'], alignment=TA_LEFT, fontSize=18,
                                 fontName=_CYRILLIC_FONT_NAME_BOLD)
    body_style = ParagraphStyle('BodyRu', parent=styles['Normal'], fontSize=10.5, leading=15,
                                fontName=_CYRILLIC_FONT_NAME)
    story = [Paragraph(title, title_style), Spacer(1, 10)]
    for line in content_text.split('\n'):
        line = line.strip()
        if not line:
            story.append(Spacer(1, 4))
            continue
        safe_line = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        line_html = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", safe_line)
        try:
            story.append(Paragraph(line_html, body_style))
        except:
            story.append(Paragraph(safe_line, body_style))
    doc.build(story)
    buf.seek(0)
    return buf

# ========= AI-АССИСТЕНТ =========
_groq_key_index = 0
_groq_clients = {}

def get_groq_client():
    if not GROQ_API_KEYS:
        return None
    global _groq_key_index
    for _ in range(len(GROQ_API_KEYS)):
        key = GROQ_API_KEYS[_groq_key_index]
        _groq_key_index = (_groq_key_index + 1) % len(GROQ_API_KEYS)
        if key not in _groq_clients:
            _groq_clients[key] = AsyncGroq(api_key=key)
        return _groq_clients[key]
    return None

async def ask_groq(question: str, user_data: dict = None) -> dict:
    client = get_groq_client()
    if client is None:
        return {"answer": "❌ Ассистент временно недоступен.", "need_human": True}
    if len(question) > 3000:
        question = question[:3000] + "..."
    user_context = f"\nДанные пользователя: {user_data}" if user_data else ""

    system_prompt = f"""
Ты — AI-навигатор бота «PWR» (пауэрлифтинг, бодибилдинг, стритлифтинг).

**О боте:**
PWR — фитнес-бот. Вот что важно знать:

🔹 **Все основные функции (жим раскладки, бодибилдинг, ПМ, питание, стрики, лидеры, дневник) — БЕСПЛАТНЫ для всех пользователей.**

🔹 **PRO-подписка (300₽/мес, 1399₽/3 мес, 2999₽/год) даёт доступ к эксклюзивным программам** в разделе «ПРОГРАММЫ PRO» (цикличная программа на 2 недели). Также PRO даёт доступ к точному калькулятору калорий, PDF-экспорту и истории анкет.

🔹 **Реферальная система:** пригласи друга — вы оба получите 1 день PRO, который суммируется. В этой однодневной подписке эксклюзивные программы НЕДОСТУПНЫ.

🔹 **Онлайн-ведение:** автор бота ведёт по ЖИМУ ЛЁЖА (2000 ₽/мес). Запись через кнопку «ОНЛАЙН-ТРЕНЕР» или команду /coach.

🔹 **Нормативы:** открывай через кнопку «НОРМАТИВЫ» — ссылка ведёт на сайт с таблицами.

🔹 **Канал:** подписывайся через кнопку «📢 КАНАЛ».

🔹 **У тебя (AI) есть лимит 4 вопроса в день для каждого пользователя.** Это сделано, чтобы экономить ресурсы.

🔹 **Твоя задача:** помогать пользователям разбираться с функциями бота, направлять к нужным кнопкам, объяснять, как что работает. Ты НЕ отвечаешь на вопросы по спорту, тренировкам, питанию как эксперт — всегда отправляй к кнопкам бота.

🔹 **В начале диалога приветствуй и напоминай, что все основные функции бесплатны.**
🔹 **В конце КАЖДОГО ответа добавляй фразу:**  
«Если что-то осталось непонятным, напишите /support или нажмите кнопку «Поддержка» — я передам ваш вопрос специалисту.»

🔹 **Если пользователь просит оператора — напиши в ответе «НУЖЕН ОПЕРАТОР»** (это служебная метка, пользователь её не увидит).

Новые функции бота:
📊 **Аналитика** — для админов показывает статистику за неделю.
💾 **Автоматический бэкап БД** — каждый день в 03:00.

Данные пользователя: {user_context}
"""
    try:
        completion = await client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": system_prompt},
                      {"role": "user", "content": question}],
            temperature=0.65, max_tokens=650, top_p=0.9
        )
        answer = completion.choices[0].message.content.strip()
        need_human = "НУЖЕН ОПЕРАТОР" in answer.upper()
        answer = re.sub(r"НУЖЕН ОПЕРАТОР", "", answer, flags=re.IGNORECASE).strip()
        if "поддержк" not in answer.lower() and "support" not in answer.lower():
            answer += "\n\nЕсли что-то осталось непонятным, напишите /support или нажмите кнопку «Поддержка» — я передам ваш вопрос специалисту."
        return {"answer": answer, "need_human": need_human}
    except Exception as e:
        logger.error(f"GROQ ERROR: {e}")
        return {"answer": "⚠️ Ошибка AI. Попробуй позже.", "need_human": True}

async def process_ai_question(update, context, question):
    uid = update.effective_user.id
    can_ask, remaining = check_ai_limit(uid)
    if not can_ask:
        await update.message.reply_text(
            "❌ У вас закончились запросы на сегодня.\n\n"
            "Приходите завтра! 🔄"
        )
        return
    increment_ai_usage(uid)
    
    cur = db()
    cur.execute("SELECT weight, age, bench, deadlift, squat FROM users WHERE user_id=?", (uid,))
    user_row = cur.fetchone()
    user_data = None
    if user_row:
        weight, age, bench, deadlift, squat = user_row
        user_data = f"Вес: {weight} кг, Возраст: {age}, Жим: {bench}, Тяга: {deadlift}, Присед: {squat}"
    thinking = await update.message.reply_text(f"🤔 Думаю... (осталось {remaining-1} запросов на сегодня)")
    result = await ask_groq(question, user_data)
    answer = result["answer"]
    if result["need_human"]:
        username = update.effective_user.username or f"ID: {uid}"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("✉️ Ответить", callback_data=f"support_reply_{uid}")]])
        await context.bot.send_message(
            REQUESTS_CHAT,
            f"🆘 **ЗАПРОС ОПЕРАТОРА**\n👤 @{username}\n🆔 ID: {uid}\n\n💬 Вопрос: {question}\n\n🤖 Ответ: {answer[:200]}...",
            reply_markup=kb
        )
        answer += "\n\n📞 Я передал ваш вопрос оператору."
    await thinking.edit_text(answer, reply_markup=main_menu)

# ========= START =========
async def start(update, context):
    uid = update.effective_user.id
    if is_banned(uid):
        await update.message.reply_text("⛔ Вы забанены.")
        return

    if context.args and context.args[0].startswith('ref_'):
        await handle_referral(update, context)

    if not await ensure_subscription(update, context):
        return

    cur = db()
    cur.execute("SELECT user_id FROM users WHERE user_id=?", (uid,))
    if not cur.fetchone():
        ref_code = generate_ref_code()
        cur.execute("""
            INSERT INTO users (user_id, username, full_name, ref_code)
            VALUES (?, ?, ?, ?)
        """, (uid, update.effective_user.username, update.effective_user.full_name, ref_code))
        conn.commit()

    caption = """🔥 PWR 🔥

🏋️‍♂️ ПАУЭРЛИФТИНГ
💪 БОДИБИЛДИНГ
💪 СТРИТЛИФТИНГ

👇 Выбери действие:"""
    if os.path.exists("start.jpg"):
        await update.message.reply_photo(photo=open("start.jpg", "rb"), caption=caption, reply_markup=main_menu)
    else:
        await update.message.reply_text(caption, reply_markup=main_menu)

# ========= АДМИН ПАНЕЛЬ =========
async def admin_panel(update, context):
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text("⛔ Нет доступа!")
        return
    await update.message.reply_text("👑 Админ панель:", reply_markup=admin_menu)

# ========= АДМИН-КОМАНДЫ ДЛЯ FAQ =========
async def add_faq_cmd(update, context):
    if not is_admin(update.effective_user.id):
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("❌ /add_faq Вопрос|Ответ")
        return
    text = " ".join(args)
    if "|" not in text:
        await update.message.reply_text("❌ Раздели вопрос и ответ символом |")
        return
    q, a = text.split("|", 1)
    faq_id = add_faq_entry(q.strip(), a.strip())
    await update.message.reply_text(f"✅ Вопрос добавлен (ID: {faq_id})")

async def del_faq_cmd(update, context):
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("❌ /del_faq ID")
        return
    try:
        faq_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Неверный ID")
        return
    if delete_faq_entry(faq_id):
        await update.message.reply_text(f"✅ Вопрос {faq_id} удалён")
    else:
        await update.message.reply_text("❌ Вопрос не найден")

async def list_faq_cmd(update, context):
    if not is_admin(update.effective_user.id):
        return
    rows = get_all_faq()
    if not rows:
        await update.message.reply_text("📋 FAQ пуст.")
        return
    text = "📋 **Список FAQ:**\n"
    for faq_id, q, _ in rows:
        text += f"{faq_id}. {q}\n"
    await update.message.reply_text(text)

# ========= КОМАНДЫ AI =========
async def ask_ai_cmd(update, context):
    uid = update.effective_user.id
    if is_banned(uid):
        await update.message.reply_text("⛔ Вы забанены.")
        return
    if not check_antiflood(uid):
        await update.message.reply_text("⏳ Подожди.")
        return
    if not await ensure_subscription(update, context):
        return
    if not GROQ_API_KEYS:
        await update.message.reply_text("❌ Ассистент временно недоступен.")
        return

    can_ask, remaining = check_ai_limit(uid)
    if not can_ask:
        await update.message.reply_text(
            "❌ У вас закончились запросы на сегодня.\n\n"
            "Приходите завтра! 🔄"
        )
        return

    if context.args:
        question = " ".join(context.args)
        await process_ai_question(update, context, question)
    else:
        context.user_data["awaiting_ai_question"] = True
        await update.message.reply_text(
            f"🤖 **AI-навигатор по боту**\n\n"
            f"У вас есть **{remaining} вопроса(ов) на сегодня**.\n\n"
            f"Я помогаю разбираться с функциями бота:\n"
            f"• Как найти программу?\n"
            f"• Что даёт PRO?\n"
            f"• Как работает реферальная система?\n"
            f"• Где посмотреть нормативы?\n\n"
            f"Задайте свой вопрос одним сообщением:"
        )

async def support_cmd(update, context):
    uid = update.effective_user.id
    if is_banned(uid):
        await update.message.reply_text("⛔ Вы забанены.")
        return
    if not check_antiflood(uid):
        await update.message.reply_text("⏳ Подожди.")
        return
    if not await ensure_subscription(update, context):
        return
    set_support_mode(uid)
    await update.message.reply_text("✍️ Напиши своё сообщение — оно уйдёт в поддержку.", reply_markup=main_menu)

# ========= ОБРАБОТЧИК РУЧНОГО ПРОГРЕССА =========
async def handle_manual_progress(update, context):
    uid = update.effective_user.id
    text = update.message.text.strip()
    parts = re.split(r'[/\s]+', text)
    parts = [p for p in parts if p]
    if len(parts) < 3:
        await update.message.reply_text("❌ Формат: Жим / Присед / Тяга")
        return
    try:
        bench = int(parts[0])
        squat = int(parts[1])
        deadlift = int(parts[2])
    except ValueError:
        await update.message.reply_text("❌ Введите числа.")
        return
    if not (0 <= bench <= 300 and 0 <= squat <= 300 and 0 <= deadlift <= 300):
        await update.message.reply_text("❌ Веса от 0 до 300 кг.")
        return
    
    save_user_progress(uid, bench, deadlift, squat)
    await update.message.reply_text(
        f"✅ Прогресс сохранён для графиков!\n\n🏋️ Жим: {bench} кг\n🦵 Присед: {squat} кг\n💪 Тяга: {deadlift} кг\n\n"
        f"📌 Эти результаты НЕ влияют на таблицу лидеров. Для попадания в лидеры отправь видео через кнопку «ОТПРАВИТЬ ВИДЕО».",
        reply_markup=manual_progress_menu
    )

# ========= ОСНОВНОЙ ОБРАБОТЧИК ТЕКСТА =========
async def handle(update, context):
    uid = update.effective_user.id
    if is_banned(uid):
        await update.message.reply_text("⛔ Вы забанены.")
        return
    if not check_antiflood(uid):
        await update.message.reply_text("⏳ Слишком часто!")
        return
    text = update.message.text

    log_activity(uid, "message")

    if is_in_support_mode(uid):
        username = update.effective_user.username or f"ID: {uid}"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("✉️ Ответить", callback_data=f"support_reply_{uid}")]])
        await context.bot.send_message(
            REQUESTS_CHAT,
            f"📩 СООБЩЕНИЕ В ПОДДЕРЖКУ\n👤 @{username}\n🆔 {uid}\n\n💬 {text}",
            reply_markup=kb
        )
        await update.message.reply_text("✅ Отправлено в поддержку.", reply_markup=main_menu)
        clear_support_mode(uid)
        return

    if is_admin(uid) and update.message.reply_to_message:
        match = re.search(r"ID: (\d+)", update.message.reply_to_message.text or "")
        if match and ("ПОДДЕРЖКУ" in (update.message.reply_to_message.text or "")):
            target_uid = int(match.group(1))
            try:
                await context.bot.send_message(target_uid, f"📩 Ответ от поддержки:\n\n{text}")
                await update.message.reply_text("✅ Ответ отправлен.")
            except Exception:
                await update.message.reply_text("❌ Не удалось отправить.")
            return

    if context.user_data.get("awaiting_workout"):
        context.user_data["awaiting_workout"] = False
        await handle_workout_input(update, context)
        return

    if context.user_data.get("awaiting_delete_workout"):
        context.user_data["awaiting_delete_workout"] = False
        await handle_delete_workout(update, context)
        return

    if context.user_data.get("awaiting_manual_progress"):
        context.user_data["awaiting_manual_progress"] = False
        await handle_manual_progress(update, context)
        return

    if context.user_data.get("awaiting_ai_question"):
        question = text
        context.user_data["awaiting_ai_question"] = False
        await process_ai_question(update, context, question)
        return

    if not await ensure_subscription(update, context):
        return

    if context.user_data.get("awaiting_survey") and context.user_data.get("survey_type"):
        survey_type = context.user_data["survey_type"]
        context.user_data["awaiting_survey"] = False
        if survey_type == "bench":
            await process_bench_survey(update, context, text)
        elif survey_type == "pm":
            await process_pm_survey(update, context, text)
        elif survey_type == "bodybuilding":
            await process_bodybuilding_survey(update, context, text)
        elif survey_type == "nutrition":
            await process_nutrition_survey(update, context, text)
        elif survey_type == "calories_pro":
            await process_calories_pro_survey(update, context, text)
        del context.user_data["survey_type"]
        return

    if "техник" in text.lower() or "как делать" in text.lower():
        await update.message.reply_text(get_technique_tips())
    elif "питание" in text.lower() or "бжу" in text.lower():
        await update.message.reply_text(get_nutrition_advice())
    elif "присед" in text.lower():
        await update.message.reply_text("🦵 **ПРИСЕД:**\n✔️ Колени по носкам\n✔️ Таз назад\n✔️ Корпус жёсткий\n❌ Завал вперёд, колени внутрь")
    elif "тяга" in text.lower():
        await update.message.reply_text("🏋️ **ТЯГА:**\n✔️ Спина прямая\n✔️ Гриф близко к ногам\n✔️ Толчок ногами\n❌ Рывок, круглая спина")
    else:
        await update.message.reply_text("📖 Основные правила тренировок... Нажми кнопку в меню!")

# ========= ОБРАБОТЧИК КНОПОК =========
async def callback_handler(update, context):
    query = update.callback_query
    data = query.data
    if not data:
        await query.answer("⚠️ Ошибка", show_alert=True)
        return
    uid = query.from_user.id
    await safe_answer(query)

    if is_banned(uid):
        await query.message.reply_text("⛔ Вы забанены.")
        return

    if data == "check_sub":
        try:
            member = await context.bot.get_chat_member(chat_id=CHANNEL_ID, user_id=uid)
            if member.status in ["member", "administrator", "creator"]:
                await render(query, "🔓 Подписка подтверждена!", main_menu)
            else:
                await query.answer("🔒 Ты не подписан!", show_alert=True)
        except Exception:
            await query.answer("⚠️ Ошибка", show_alert=True)
        return

    if not await ensure_subscription(update, context):
        return

    try:
        if data == "back_to_main":
            await render(query, "👇 Выбери действие:", main_menu)
            return

        if data == "admin_analytics":
            if not is_admin(uid):
                await query.answer("⛔ Нет доступа!", show_alert=True)
                return
            analytics_text = await build_analytics_report(context)
            await render(query, analytics_text, admin_menu)
            return

        if data == "programs_menu":
            await render(query, "📚 Выбери раздел:", programs_menu)
            return

        if data == "pro_menu":
            await render(query, "💎 Управление подпиской:", pro_menu)
            return

        if data == "pro_features":
            text = """
💎 **ЧТО ДАЁТ PRO ПОДПИСКА (300₽/мес):**

Сейчас все основные функции бота бесплатны для всех пользователей!

В PRO-подписку входит:
🔹 Эксклюзивные программы в разделе «ПРОГРАММЫ PRO» (цикл 2 недели)
🔹 Точный калькулятор калорий (Миффлин-Сан Жеор)
🔹 История анкет
🔹 Экспорт программ в PDF

Подписка — это ваш доступ к эксклюзивному контенту и поддержка развития бота!

💰 Тарифы: 300₽/мес, 1399₽/3 мес, 2999₽/год
💳 Оплата: 2200702056156958
"""
            await render(query, text, pro_menu)
            return

        if data == "pro_programs":
            if not is_full_pro(uid):
                await render(query, "🔒 **Программы PRO доступны только с полной подпиской.**\n\nОформите подписку через меню «PRO SUBSCRIPTION» → «КУПИТЬ PRO».", pro_menu)
                return
            program_text = get_full_program_cycle()
            await query.message.reply_text(program_text)
            await render(query, "📋 Программа отправлена выше. Выберите действие:", pro_menu)
            return

        if data == "calc_calories_pro":
            if not is_full_pro(uid):
                await render(query, "🔒 **Точный калькулятор калорий доступен только с полной PRO-подпиской.**\n\nОформите подписку через меню «PRO SUBSCRIPTION».", pro_menu)
                return
            context.user_data["awaiting_survey"] = True
            context.user_data["survey_type"] = "calories_pro"
            await query.message.reply_text(CALORIES_PRO_QUESTIONS)
            return

        if data == "my_questionnaires":
            if not is_pro(uid):
                await render(query, "🔒 **История анкет доступна только с PRO-подпиской.**\n\nОформите подписку через меню «PRO SUBSCRIPTION».", pro_menu)
                return
            cur = db()
            cur.execute("SELECT type, result, date FROM questionnaires WHERE user_id=? ORDER BY date DESC LIMIT 5", (uid,))
            rows = cur.fetchall()
            if not rows:
                await render(query, "📋 Нет анкет.", pro_menu)
                return
            text = "📋 **Твои анкеты:**\n\n"
            for typ, res, dt in rows:
                text += f"{typ}: {res[:80]}...\n"
            await render(query, text, pro_menu)
            return

        if data == "manual_progress_menu":
            await render(query, "📊 Управление прогрессом:", manual_progress_menu)
            return

        if data == "update_progress":
            context.user_data["awaiting_manual_progress"] = True
            await query.message.reply_text("✍️ Введи: `Жим / Присед / Тяга`\n\n(Эти данные пойдут только в график, не в лидеры.)")
            return

        if data == "manual_progress_chart":
            chart = build_progress_chart_from_manual(uid)
            if not chart:
                await query.message.reply_text("📈 Недостаточно данных. Добавь минимум 2 записи.")
                return
            await query.message.reply_photo(photo=chart, caption="📈 Твой прогресс (ручной ввод)")
            return

        if data == "delete_progress":
            if delete_user_progress(uid):
                await render(query, "🗑️ Прогресс удалён.", manual_progress_menu)
            else:
                await render(query, "❌ Нет данных.", manual_progress_menu)
            return

        if data == "normatives_menu":
            await normatives_menu_callback(query, context)
            return

        if data == "invite_menu":
            await invite_menu_callback(query, context)
            return

        if data == "channel_menu":
            await channel_menu_callback(query, context)
            return

        if data == "workout_log_menu":
            await render(query, "📓 **Дневник тренировок**", workout_log_menu)
            return

        if data == "add_workout":
            await add_workout_callback(query, context)
            return

        if data == "my_workouts":
            await my_workouts_callback(query, context)
            return

        if data == "delete_workout":
            await delete_workout_callback(query, context)
            return

        if data == "leaderboard_menu":
            await leaderboard_menu_callback(query, context)
            return

        if data == "leaderboard_bench":
            await show_leaderboard(query, context, "bench")
            return

        if data == "leaderboard_squat":
            await show_leaderboard(query, context, "squat")
            return

        if data == "leaderboard_deadlift":
            await show_leaderboard(query, context, "deadlift")
            return

        if data == "leaderboard_video":
            await leaderboard_video_callback(query, context)
            return

        if data == "admin_leaderboard":
            await admin_leaderboard_callback(query, context)
            return

        if data.startswith("lb_accept_"):
            await leaderboard_accept(query, context)
            return

        if data.startswith("lb_reject_"):
            await leaderboard_reject(query, context)
            return

        if data == "draw_menu":
            draw = get_draw()
            if not draw:
                await render(query, "❌ Нет активного розыгрыша", main_menu)
                return
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("📢 Канал", url=DRAW_CHANNEL_LINKS[0])],
                [InlineKeyboardButton("👌 Проверить", callback_data="check_draw")]
            ])
            await render(query, "🎁 Участие в розыгрыше", kb)
            return

        if data == "join_draw":
            await join_draw_callback(query, context)
            return

        if data == "check_draw":
            await check_draw_callback(update, context)
            return

        if data == "buy_menu":
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("💎 1 мес — 300₽", callback_data="buy_1")],
                [InlineKeyboardButton("💎 3 мес — 1399₽", callback_data="buy_3")],
                [InlineKeyboardButton("💎 12 мес — 2999₽", callback_data="buy_12")],
                [InlineKeyboardButton("🔙 Назад", callback_data="pro_menu")]
            ])
            await render(query, "💎 Выбери тариф:", kb)
            return

        if data == "my_sub":
            cur = db()
            cur.execute("SELECT until, sub_type FROM subs WHERE user_id=?", (uid,))
            row = cur.fetchone()
            if not row:
                await render(query, "❌ Нет подписки", pro_menu)
            else:
                until = datetime.fromisoformat(row[0])
                if datetime.now() > until:
                    cur.execute("DELETE FROM subs WHERE user_id=?", (uid,))
                    conn.commit()
                    await render(query, "❌ Подписка истекла", pro_menu)
                else:
                    sub_type = row[1] or "PRO"
                    await render(query, f"💎 {sub_type}\n📅 до {until.strftime('%d.%m.%Y')}", pro_menu)
            return

        if data == "bench_layout":
            context.user_data["awaiting_survey"] = True
            context.user_data["survey_type"] = "bench"
            await query.message.reply_text(BENCH_QUESTIONS)
            return

        if data == "calculate_pm":
            context.user_data["awaiting_survey"] = True
            context.user_data["survey_type"] = "pm"
            await query.message.reply_text(PM_QUESTIONS)
            return

        if data == "bodybuilding":
            context.user_data["awaiting_survey"] = True
            context.user_data["survey_type"] = "bodybuilding"
            await query.message.reply_text(BODYBUILDING_QUESTIONS)
            return

        if data == "nutrition":
            context.user_data["awaiting_survey"] = True
            context.user_data["survey_type"] = "nutrition"
            await query.message.reply_text(NUTRITION_QUESTIONS)
            return

        if data.startswith("buy_"):
            mapping = {"buy_1": ("1 месяц", 30), "buy_3": ("3 месяца", 90), "buy_12": ("1 год", 365)}
            sub_name, days = mapping[data]
            context.user_data["buy"] = (sub_name, days)
            await render(query, f"💎 {sub_name}\n\n💳 Оплата: 2200702056156958\n📸 Отправь скрин", pro_menu)
            return

        if data == "progress_menu":
            await render(query, "🔥 Твой прогресс:", progress_menu)
            return

        if data == "checkin":
            streak, best, is_record, already = do_checkin(uid)
            if already:
                text = f"✅ Уже отметил сегодня!\n🔥 Текущий: {streak} дн.\n🏆 Лучший: {best} дн."
            elif is_record:
                text = f"🎉 Тренировка засчитана!\n🔥 Новый рекорд: {best} дн.!"
            else:
                text = f"✅ Тренировка засчитана!\n🔥 Текущий: {streak} дн.\n🏆 Лучший: {best} дн."
            await render(query, text, progress_menu)
            return

        if data == "my_streak":
            row = get_streak(uid)
            if not row:
                text = "🔥 Нет стрика. Отметь тренировку!"
            else:
                cur_streak, best_streak, last_checkin = row
                last_dt = datetime.fromisoformat(last_checkin)
                hours = (datetime.now() - last_dt).total_seconds() / 3600
                status = "🟢 активен" if hours <= STREAK_GRACE_HOURS else "🔴 истёк"
                text = f"🔥 Текущий: {cur_streak} дн. ({status})\n🏆 Лучший: {best_streak} дн."
            await render(query, text, progress_menu)
            return

        if data == "toggle_reminders":
            enabled = toggle_reminders_setting(uid)
            await render(query, f"⏰ Напоминания {'включены ✅' if enabled else 'выключены ❌'}", progress_menu)
            return

        if data == "faq_menu":
            await render(query, build_faq_text(), faq_menu_kb)
            return

        if data == "support_menu":
            await render(query, "📞 **ПОДДЕРЖКА**\nНапиши нам", support_menu_kb)
            return

        if data == "support_write":
            set_support_mode(uid)
            await query.message.reply_text("✍️ Напиши своё сообщение.")
            return

        if data == "ask_ai":
            if not GROQ_API_KEYS:
                await query.message.reply_text("❌ Ассистент недоступен.")
                return
            can_ask, remaining = check_ai_limit(uid)
            if not can_ask:
                await query.message.reply_text(
                    "❌ У вас закончились запросы на сегодня.\n\n"
                    "Приходите завтра! 🔄"
                )
                return
            context.user_data["awaiting_ai_question"] = True
            await query.message.reply_text(
                f"🤖 **AI-навигатор по боту**\n\n"
                f"У вас есть **{remaining} вопроса(ов) на сегодня**.\n\n"
                f"Я помогаю разбираться с функциями бота.\n"
                f"Задайте свой вопрос одним сообщением:"
            )
            return

        if data == "coach_menu":
            await coach_menu_callback(query, context)
            return

        if data == "coach_signup":
            await coach_signup_callback(query, context)
            return

        if data == "admin_stats":
            if not is_admin(uid):
                await query.answer("⛔ Нет доступа!", show_alert=True)
                return
            cur = db()
            users = cur.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            subs = cur.execute("SELECT COUNT(*) FROM subs").fetchone()[0]
            await render(query, f"📊 Статистика\n👥 Всего: {users}\n💎 PRO: {subs}", admin_menu)
            return

        if data == "admin_activity":
            await admin_activity_callback(query, context)
            return

        if data == "admin_subs":
            if not is_admin(uid):
                await query.answer("⛔ Нет доступа!", show_alert=True)
                return
            cur = db()
            rows = cur.execute("SELECT user_id, until, sub_type FROM subs").fetchall()
            if not rows:
                await render(query, "💎 Нет подписок", admin_menu)
                return
            text = "💎 Активные подписки:\n"
            for uid_row, until, sub_type in rows:
                text += f"👤 {uid_row} — {sub_type}\n📅 до {until[:10]}\n\n"
            await render(query, text, admin_menu)
            return

        if data == "admin_givepro":
            await render(query, "❌ Используй /givepro ID ДНЕЙ", admin_menu)
            return

        if data == "admin_faq":
            if not is_admin(uid):
                await query.answer("⛔ Нет доступа!", show_alert=True)
                return
            rows = get_all_faq()
            text = "❓ Управление FAQ:\nКоманды: /add_faq, /del_faq, /list_faq\n\n"
            if rows:
                for faq_id, q, _ in rows:
                    text += f"{faq_id}. {q}\n"
            else:
                text += "Пока пусто."
            await render(query, text, admin_menu)
            return

        if data == "admin_admins":
            if not is_admin(uid):
                await query.answer("⛔ Нет доступа!", show_alert=True)
                return
            text = "👑 **Управление админами**\n\n"
            text += "Команды:\n`/add_admin ID`\n`/remove_admin ID`\n`/list_admins`\n\n"
            text += "Супер-админы: " + ", ".join([str(x) for x in SUPER_ADMINS])
            await render(query, text, admin_menu)
            return

        if data == "admin_draw":
            if not is_admin(uid):
                await query.answer("⛔ Нет доступа!", show_alert=True)
                return
            cur = db()
            cur.execute("SELECT COUNT(*) FROM draw_users WHERE joined=1")
            count = cur.fetchone()[0]
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🎲 1 победитель", callback_data="pick_1")],
                [InlineKeyboardButton("🏆 3 победителя", callback_data="pick_3")],
                [InlineKeyboardButton("👑 Ручной", callback_data="manual_draw")],
                [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
            ])
            await render(query, f"🎲 Управление розыгрышем\nУчастников: {count}", kb)
            return

        if data.startswith("pick_"):
            if not is_admin(uid):
                await query.answer("⛔ Нет доступа!", show_alert=True)
                return
            count = int(data.split("_")[1])
            cur = db()
            cur.execute("SELECT user_id, username, full_name FROM draw_users WHERE joined=1")
            users = cur.fetchall()
            if not users:
                await render(query, "❌ Нет участников", admin_menu)
                return
            winners = random.sample(users, min(count, len(users)))
            msg = await spin_animation(update, "🎰 Выбираем победителя...", is_callback=True)
            text = "🏆 Победители:\n"
            for i, u in enumerate(winners, 1):
                text += f"{i}. {mention(u[0], u[1], u[2])}\n"
                try:
                    await context.bot.send_message(u[0], "🎉 Ты выиграл в розыгрыше!")
                except Exception:
                    pass
            close_draw()
            await msg.edit_text(text, parse_mode="HTML", reply_markup=admin_menu)
            return

        if data == "manual_draw":
            await render(query, "❓ Используй /win ID или @username", admin_menu)
            return

        if data.startswith("ok_draw") or data.startswith("no_draw"):
            await admin_check_draw_callback(update, context)
            return

        if data.startswith("support_reply_"):
            if not is_admin(uid):
                await query.answer("⛔ Нет доступа!", show_alert=True)
                return
            target_uid = int(data.split("_")[2])
            context.user_data["support_reply_target"] = target_uid
            await query.message.reply_text(f"✍️ Напиши ответ пользователю {target_uid}.")
            return

        if data.startswith("accept_"):
            _, target_uid, days, sub_name = data.split("_")
            target_uid = int(target_uid)
            days = int(days)
            cur = db()
            cur.execute("SELECT until, sub_type FROM subs WHERE user_id=?", (target_uid,))
            old = cur.fetchone()
            if old and datetime.now() < datetime.fromisoformat(old[0]):
                new_until = datetime.fromisoformat(old[0]) + timedelta(days=days)
                if old[1] and ('ref_pro' in old[1] or 'trial' in old[1]):
                    new_type = sub_name
                else:
                    new_type = f"{old[1]} + {sub_name}"
            else:
                new_until = datetime.now() + timedelta(days=days)
                new_type = sub_name
            cur.execute("INSERT OR REPLACE INTO subs VALUES (?, ?, ?)", (target_uid, new_until.isoformat(), new_type))
            cur.execute("INSERT INTO payments (user_id, sub_type, days, date) VALUES (?, ?, ?, ?)",
                        (target_uid, sub_name, days, datetime.now().isoformat()))
            conn.commit()
            try:
                await context.bot.send_message(target_uid, f"💎 Подписка до {new_until.strftime('%d.%m.%Y')}")
            except Exception:
                pass
            await query.message.delete()
            await context.bot.send_message(REQUESTS_CHAT, f"✅ Принято! {target_uid} — {sub_name} {days} дней")
            return

        if data.startswith("decline_"):
            await query.message.delete()
            await context.bot.send_message(REQUESTS_CHAT, "❌ Отклонено")
            return

    except Exception as e:
        logger.error(f"CALLBACK ERROR: {e}")

# ========= АНАЛИТИКА ЗА НЕДЕЛЮ =========
async def build_analytics_report(context):
    cur = db()
    now = datetime.now()
    week_ago = now - timedelta(days=7)
    week_ago_str = week_ago.isoformat()
    today_str = now.strftime("%Y-%m-%d")
    week_start = (now - timedelta(days=now.weekday())).strftime("%d.%m")
    week_end = now.strftime("%d.%m")

    total_users = cur.execute("SELECT COUNT(*) FROM users").fetchone()[0] or 0
    new_users = cur.execute("SELECT COUNT(*) FROM users WHERE updated >= ?", (week_ago_str,)).fetchone()[0] or 0
    total_subs = cur.execute("SELECT COUNT(*) FROM subs").fetchone()[0] or 0
    paid_subs = cur.execute("SELECT COUNT(*) FROM subs WHERE sub_type NOT LIKE '%ref_pro%' AND sub_type NOT LIKE '%trial%' AND sub_type NOT LIKE '%Бонус%'").fetchone()[0] or 0
    trial_subs = cur.execute("SELECT COUNT(*) FROM subs WHERE sub_type LIKE '%trial%'").fetchone()[0] or 0
    normatives_total = cur.execute("SELECT COUNT(*) FROM activity_stats WHERE action='normatives' AND date >= ?", (today_str,)).fetchone()[0] or 0
    site_visits = cur.execute("SELECT COUNT(*) FROM site_stats WHERE date >= ? AND action='visit'", (week_ago_str,)).fetchone()[0] or 0
    leaderboard_views = cur.execute("SELECT COUNT(*) FROM activity_stats WHERE action LIKE 'leaderboard%' AND date >= ?", (today_str,)).fetchone()[0] or 0
    workout_logs = cur.execute("SELECT COUNT(*) FROM workout_log WHERE date >= ?", (week_ago_str,)).fetchone()[0] or 0
    lb_requests = cur.execute("SELECT COUNT(*) FROM leaderboard_requests WHERE date >= ?", (week_ago_str,)).fetchone()[0] or 0
    support_msgs = cur.execute("SELECT COUNT(*) FROM support_mode WHERE started_at >= ?", (week_ago_str,)).fetchone()[0] or 0
    today_streaks = cur.execute("SELECT COUNT(*) FROM streaks WHERE last_checkin >= ?", (today_str,)).fetchone()[0] or 0

    peak_hours = cur.execute("""
        SELECT hour, COUNT(*) as cnt FROM activity_stats
        WHERE date >= ?
        GROUP BY hour
        ORDER BY cnt DESC
        LIMIT 1
    """, (week_ago_str,)).fetchone()
    peak_time = f"{peak_hours[0]}:00–{peak_hours[0]+1}:00" if peak_hours else "нет данных"

    report = f"""
📊 **АНАЛИТИКА ЗА НЕДЕЛЮ** ({week_start} — {week_end})

👥 **ПОЛЬЗОВАТЕЛИ**
• Всего: {total_users}
• Новых за неделю: {new_users}
• Активных сегодня: {today_streaks}

💎 **ПОДПИСКИ**
• Всего PRO: {total_subs}
• Платных: {paid_subs}
• Пробных: {trial_subs}

📋 **АКТИВНОСТЬ**
• Нормативы открыли: {normatives_total} раз
• Переходов на сайт: {site_visits}
• Лидеры посмотрели: {leaderboard_views} раз
• Дневник тренировок: {workout_logs} записей
• Заявки в лидеры: {lb_requests}
• Сообщений в поддержку: {support_msgs}

📈 **ПИК АКТИВНОСТИ:** {peak_time}

---
📌 Статистика собирается автоматически на основе действий пользователей.
"""

    top_users = cur.execute("""
        SELECT user_id, COUNT(*) as cnt FROM activity_stats
        WHERE date >= ?
        GROUP BY user_id
        ORDER BY cnt DESC
        LIMIT 5
    """, (week_ago_str,)).fetchall()

    if top_users:
        report += "\n🏆 **ТОП-5 АКТИВНЫХ ПОЛЬЗОВАТЕЛЕЙ:**\n"
        for i, (uid, cnt) in enumerate(top_users, 1):
            cur.execute("SELECT username FROM users WHERE user_id=?", (uid,))
            user_row = cur.fetchone()
            name = user_row[0] if user_row and user_row[0] else f"ID{uid}"
            report += f"{i}. {name} — {cnt} действий\n"

    return report

# ========= АВТОМАТИЧЕСКИЙ БЭКАП БД =========
async def backup_database(context):
    try:
        db_path = "bot.db"
        if not os.path.exists(db_path):
            logger.warning("Файл БД не найден для бэкапа")
            return

        backup_name = f"bot_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        backup_path = f"/tmp/{backup_name}"

        import shutil
        shutil.copy2(db_path, backup_path)

        size = os.path.getsize(backup_path)
        size_mb = size / (1024 * 1024)

        for admin_id in SUPER_ADMINS:
            try:
                if size_mb > 50:
                    await context.bot.send_message(
                        admin_id,
                        f"💾 **БЭКАП БД**\n\n"
                        f"Файл: {backup_name}\n"
                        f"Размер: {size_mb:.1f} МБ\n\n"
                        f"⚠️ Файл слишком большой для отправки в Telegram.\n"
                        f"Загрузите его с сервера вручную: `{backup_path}`"
                    )
                else:
                    with open(backup_path, "rb") as f:
                        await context.bot.send_document(
                            admin_id,
                            document=f,
                            filename=backup_name,
                            caption=f"💾 **Автоматический бэкап БД**\n"
                                    f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
                                    f"📦 Размер: {size_mb:.1f} МБ"
                        )
                logger.info(f"Бэкап отправлен админу {admin_id}")
            except Exception as e:
                logger.error(f"Ошибка отправки бэкапа админу {admin_id}: {e}")

        try:
            os.remove(backup_path)
        except:
            pass

    except Exception as e:
        logger.error(f"Ошибка создания бэкапа: {e}")

# ========= РОЗЫГРЫШИ =========
async def join_draw_callback(query, context):
    user_id = query.from_user.id
    cur = db()
    cur.execute("SELECT joined FROM draw_users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    if row and row[0] == 1:
        await render(query, "🎉 Ты уже участвуешь!", main_menu)
        return
    cur.execute("INSERT OR REPLACE INTO draw_users (user_id, username, full_name, status) VALUES (?, ?, ?, 'start')",
                (user_id, query.from_user.username, query.from_user.full_name))
    conn.commit()
    kb = [[InlineKeyboardButton("📢 Канал", url=link)] for link in DRAW_CHANNEL_LINKS]
    kb.append([InlineKeyboardButton("👌 Проверить", callback_data="check_draw")])
    await render(query, "📢 Подпишись на канал", InlineKeyboardMarkup(kb))

async def check_draw_callback(update, context):
    query = update.callback_query
    await safe_answer(query)
    user_id = query.from_user.id
    ok = await check_draw_sub(user_id, context)
    if not ok:
        await query.answer("🔒 Не подписан!", show_alert=True)
        return
    cur = db()
    cur.execute("UPDATE draw_users SET status='kick' WHERE user_id=?", (user_id,))
    conn.commit()
    await query.edit_message_text("✅ Подписка подтверждена!\n📸 Отправь скрин в этот чат.")

async def photo_draw(update, context):
    user = update.message.from_user
    cur = db()
    cur.execute("SELECT status FROM draw_users WHERE user_id=?", (user.id,))
    row = cur.fetchone()
    if not row or row[0] != "kick":
        await update.message.reply_text("❓ Начни участие.")
        return
    file_id = update.message.photo[-1].file_id
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("👍 Принять", callback_data=f"ok_draw_{user.id}")],
        [InlineKeyboardButton("👎 Отклонить", callback_data=f"no_draw_{user.id}")]
    ])
    await context.bot.send_photo(DRAW_GROUP_ID, file_id,
                                caption=f"🆔 {user.id}\n👤 @{user.username}\n📝 {user.full_name}",
                                reply_markup=kb)
    await update.message.reply_text("📸 Скрин отправлен на проверку.")

async def admin_check_draw_callback(update, context):
    query = update.callback_query
    await safe_answer(query)
    user_id = int(query.data.split("_")[2])
    cur = db()
    if query.data.startswith("ok_draw"):
        cur.execute("UPDATE draw_users SET joined=1, status='done' WHERE user_id=?", (user_id,))
        conn.commit()
        try:
            await context.bot.send_message(user_id, "🎉 Ты участвуешь в розыгрыше!")
        except Exception:
            pass
        await query.edit_message_caption("✅ Принято!")
    else:
        await query.edit_message_caption("❌ Отклонено")

async def new_draw(update, context):
    if not is_admin(update.effective_user.id):
        return
    prize = " ".join(context.args)
    create_draw(prize)
    await update.message.reply_text(f"🎲 Розыгрыш создан!\n🏆 Приз: {prize}", reply_markup=admin_menu)

async def manual_win_cmd(update, context):
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("❌ /win ID или @username", reply_markup=admin_menu)
        return
    arg = context.args[0]
    cur = db()
    if arg.startswith("@"):
        username = arg.replace("@", "")
        cur.execute("SELECT user_id, username, full_name FROM draw_users WHERE username=?", (username,))
    else:
        if not arg.isdigit():
            await update.message.reply_text("❌ Неверный ID", reply_markup=admin_menu)
            return
        cur.execute("SELECT user_id, username, full_name FROM draw_users WHERE user_id=?", (int(arg),))
    user = cur.fetchone()
    if not user:
        await update.message.reply_text("❌ Участник не найден", reply_markup=admin_menu)
        return
    msg = await spin_animation(update, "🎰 Выбираем победителя...", is_callback=False)
    try:
        await context.bot.send_message(user[0], "🎉 Ты выиграл!")
    except Exception:
        pass
    await msg.edit_text(f"🏆 Победитель:\n{mention(user[0], user[1], user[2])}",
                       parse_mode="HTML", reply_markup=admin_menu)
    close_draw()

async def photo_payment(update, context):
    uid = update.effective_user.id
    photo = update.message.photo[-1].file_id
    if "buy" not in context.user_data:
        await update.message.reply_text("❌ Сначала выбери тариф.")
        return
    sub_name, days = context.user_data["buy"]
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("👍 Принять", callback_data=f"accept_{uid}_{days}_{sub_name}")],
        [InlineKeyboardButton("👎 Отклонить", callback_data=f"decline_{uid}")]
    ])
    await context.bot.send_photo(REQUESTS_CHAT, photo,
                                caption=f"💰 ЗАЯВКА НА PRO!\nID: {uid}\nТариф: {sub_name}\nДней: {days}",
                                reply_markup=kb)
    await update.message.reply_text("📸 Скрин отправлен!")
    del context.user_data["buy"]

async def give_pro(update, context):
    if not is_admin(update.effective_user.id):
        return
    if len(context.args) < 2:
        await update.message.reply_text("❌ /givepro ID ДНЕЙ", reply_markup=admin_menu)
        return
    try:
        uid = int(context.args[0])
        days = int(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ Числа нужны", reply_markup=admin_menu)
        return
    until = datetime.now() + timedelta(days=days)
    cur = db()
    cur.execute("INSERT OR REPLACE INTO subs VALUES (?, ?, ?)", (uid, until.isoformat(), f"Выдано админом ({days} дн)"))
    cur.execute("INSERT INTO payments (user_id, sub_type, days, date) VALUES (?, ?, ?, ?)",
                (uid, f"Выдано админом ({days} дн)", days, datetime.now().isoformat()))
    conn.commit()
    await update.message.reply_text(f"💎 PRO выдан {uid} на {days} дней", reply_markup=admin_menu)
    try:
        await context.bot.send_message(uid, f"🎉 Вам выдали PRO на {days} дней!")
    except Exception:
        pass

def get_draw():
    cur = db()
    cur.execute("SELECT id, prize FROM draws WHERE status='active'")
    return cur.fetchone()

def create_draw(prize):
    cur = db()
    cur.execute("UPDATE draws SET status='finished'")
    cur.execute("DELETE FROM draw_users")
    cur.execute("INSERT INTO draws (prize, status) VALUES (?, 'active')", (prize,))
    conn.commit()

def close_draw():
    cur = db()
    cur.execute("UPDATE draws SET status='finished'")
    conn.commit()

def mention(uid, username, name):
    return f"@{username}" if username else f"<a href='tg://user?id={uid}'>{name}</a>"

async def check_draw_sub(user_id, context):
    for ch_id in DRAW_CHANNEL_IDS:
        try:
            await asyncio.sleep(0.5)
            member = await context.bot.get_chat_member(chat_id=ch_id, user_id=user_id)
            if member.status not in ["member", "administrator", "creator"]:
                return False
        except Exception:
            return False
    return True

async def spin_animation(update, text, is_callback=True):
    steps = ["🎲 1", "🎲 2", "🎲 3", "🎰 Крутим...", "🎰 Ещё чуть..."]
    if is_callback and update.callback_query:
        msg = await update.callback_query.message.reply_text(text)
    else:
        msg = await update.message.reply_text(text)
    for step in steps:
        await asyncio.sleep(0.7)
        try:
            await msg.edit_text(f"{step}\n{text}")
        except Exception:
            pass
    return msg

# ========= АДМИН ОТВЕЧАЕТ В ПОДДЕРЖКУ =========
async def support_reply_text_handler(update, context):
    uid = update.effective_user.id
    if not is_admin(uid):
        return False
    target_uid = context.user_data.get("support_reply_target")
    if not target_uid:
        return False
    text = update.message.text
    try:
        await context.bot.send_message(target_uid, f"📩 Ответ от поддержки:\n\n{text}")
        await update.message.reply_text("✅ Ответ отправлен.")
    except Exception:
        await update.message.reply_text("❌ Не удалось отправить.")
    del context.user_data["support_reply_target"]
    return True

# ========= ФОТО =========
async def combined_photo_handler(update, context):
    uid = update.effective_user.id
    if is_banned(uid):
        await update.message.reply_text("⛔ Вы забанены.")
        return
    if not check_antiflood(uid):
        await update.message.reply_text("⏳ Слишком часто!")
        return
    if "buy" in context.user_data:
        await photo_payment(update, context)
        return
    cur = db()
    cur.execute("SELECT status FROM draw_users WHERE user_id=?", (uid,))
    draw_row = cur.fetchone()
    if draw_row and draw_row[0] == "kick":
        await photo_draw(update, context)
    else:
        await update.message.reply_text("❓ Отправь фото для участия в розыгрыше или оплаты PRO.")

async def combined_text_handler(update, context):
    if context.user_data.get("support_reply_target"):
        handled = await support_reply_text_handler(update, context)
        if handled:
            return
    await handle(update, context)

# ========= ЭКСПОРТ PDF =========
async def export_pdf_cmd(update, context):
    uid = update.effective_user.id
    if is_banned(uid):
        await update.message.reply_text("⛔ Вы забанены.")
        return
    if not is_pro(uid):
        await update.message.reply_text("🔒 **Экспорт PDF доступен только с PRO-подпиской.**\n\nОформите подписку через меню «PRO SUBSCRIPTION».")
        return
    cur = db()
    cur.execute("SELECT type, result, date FROM questionnaires WHERE user_id=? ORDER BY date DESC LIMIT 1", (uid,))
    row = cur.fetchone()
    if not row:
        await update.message.reply_text("❌ Нет анкет.")
        return
    q_type, result, date = row
    type_names = {"bench":"Жим раскладка","pm":"Расчёт ПМ","bodybuilding":"Бодибилдинг","nutrition":"Питание","calories_pro":"Точный расчёт калорий"}
    title = f"Программа: {type_names.get(q_type, q_type)}"
    pdf_buf = build_program_pdf(uid, title, result)
    await update.message.reply_document(document=pdf_buf, filename="program.pdf",
                                       caption=f"📄 {title}\n📅 от {datetime.fromisoformat(date).strftime('%d.%m.%Y')}")

# ========= ФОНОВЫЕ ЗАДАЧИ =========
async def daily_training_reminder(context):
    cur = db()
    cur.execute("SELECT user_id, current_streak, last_checkin FROM streaks")
    rows = cur.fetchall()
    now = datetime.now()
    for uid, streak, last_checkin in rows:
        if not get_reminders_enabled(uid) or is_banned(uid):
            continue
        try:
            last_dt = datetime.fromisoformat(last_checkin)
        except:
            continue
        if last_dt.date() == now.date():
            continue
        if (now - last_dt).total_seconds() / 3600 > STREAK_GRACE_HOURS:
            continue
        try:
            await context.bot.send_message(uid, f"⏰ Не забудь тренировку! 🔥 Стрик: {streak} дн.")
            await asyncio.sleep(0.05)
        except Exception:
            pass

async def daily_sub_expiry_reminder(context):
    cur = db()
    cur.execute("SELECT user_id, until, sub_type FROM subs")
    rows = cur.fetchall()
    now = datetime.now()
    for uid, until_str, sub_type in rows:
        try:
            until = datetime.fromisoformat(until_str)
        except:
            continue
        days_left = (until - now).days
        if days_left < 0 or days_left > SUB_REMINDER_DAYS_BEFORE:
            continue
        cur2 = db()
        cur2.execute("SELECT 1 FROM sub_reminders_sent WHERE user_id=? AND until=?", (uid, until_str))
        if cur2.fetchone():
            continue
        try:
            await context.bot.send_message(uid, f"⏳ PRO истекает {until.strftime('%d.%m.%Y')}!\nПродли через меню.")
            cur2.execute("INSERT OR IGNORE INTO sub_reminders_sent VALUES (?, ?)", (uid, until_str))
            conn.commit()
            await asyncio.sleep(0.05)
        except Exception:
            pass

async def error_handler(update, context):
    logger.error(f"ERROR: {context.error}")

# ========= MAIN =========
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("newdraw", new_draw))
    app.add_handler(CommandHandler("win", manual_win_cmd))
    app.add_handler(CommandHandler("givepro", give_pro))
    app.add_handler(CommandHandler("ban", ban_user))
    app.add_handler(CommandHandler("unban", unban_user))
    app.add_handler(CommandHandler("near", near_all))
    app.add_handler(CommandHandler("broadcast_pro", broadcast_pro))
    app.add_handler(CommandHandler("add_faq", add_faq_cmd))
    app.add_handler(CommandHandler("del_faq", del_faq_cmd))
    app.add_handler(CommandHandler("list_faq", list_faq_cmd))
    app.add_handler(CommandHandler("export_pdf", export_pdf_cmd))
    app.add_handler(CommandHandler("ask", ask_ai_cmd))
    app.add_handler(CommandHandler("support", support_cmd))
    app.add_handler(CommandHandler("trial", trial_cmd))
    app.add_handler(CommandHandler("promo", promo_cmd))
    app.add_handler(CommandHandler("create_promo", create_promo_cmd))
    app.add_handler(CommandHandler("list_promo", list_promo_cmd))
    app.add_handler(CommandHandler("delete_promo", delete_promo_cmd))
    app.add_handler(CommandHandler("add_admin", add_admin_cmd))
    app.add_handler(CommandHandler("remove_admin", remove_admin_cmd))
    app.add_handler(CommandHandler("list_admins", list_admins_cmd))
    app.add_handler(CommandHandler("coach", coach_cmd))

    app.add_handler(MessageHandler(filters.PHOTO, combined_photo_handler))
    app.add_handler(MessageHandler(filters.VIDEO | filters.VIDEO_NOTE, combined_video_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, combined_text_handler))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_error_handler(error_handler)

    job_queue = app.job_queue
    if job_queue is not None:
        job_queue.run_repeating(daily_training_reminder, interval=timedelta(hours=24), first=10)
        job_queue.run_repeating(daily_sub_expiry_reminder, interval=timedelta(hours=24), first=20)
        job_queue.run_daily(backup_database, time=datetime.strptime("03:00", "%H:%M").time())
        logger.info("✅ Задача бэкапа БД запланирована на 03:00")
    else:
        logger.warning("JobQueue недоступен")

    logger.info("🚀 Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()

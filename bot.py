import logging
import sqlite3
import random
import asyncio
from telegram import (
    Update, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, CallbackQueryHandler, ContextTypes
)


# ===== ДАННЫЕ =====
TOKEN = "8614454950:AAGE_R0SM3_C2IuMsDCif3a_O17lgd5Cs0o"
GROUP_ID = -1004497541953
ADMIN_IDS = [8259326014, 8505422185]  # основные админы (для совместимости)
CHANNEL_IDS = [-1002774320171, -1003852894722]
CHANNEL_LINKS = [
    "https://t.me/Velikiy_789",
    "https://t.me/Velikiy789TT"
]
KICK_LINK = "https://kick.com/velikiy789"
START_IMAGE = "start.jpg"
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
conn = sqlite3.connect("bot.db", check_same_thread=False)
cursor = conn.cursor()


# ===== МИГРАЦИЯ БД (добавляем недостающие поля) =====
def migrate_db():
    # Проверяем таблицу users
    cursor.execute("PRAGMA table_info(users)")
    cols = [c[1] for c in cursor.fetchall()]
    if "joined" not in cols:
        cursor.execute("ALTER TABLE users ADD COLUMN joined INTEGER DEFAULT 0")
        logger.info("✅ Добавлено поле joined")
    if "status" not in cols:
        cursor.execute("ALTER TABLE users ADD COLUMN status TEXT")
        logger.info("✅ Добавлено поле status")
    if "captcha" not in cols:
        cursor.execute("ALTER TABLE users ADD COLUMN captcha INTEGER")
        logger.info("✅ Добавлено поле captcha")
    # Проверяем таблицу draw
    cursor.execute("PRAGMA table_info(draw)")
    draw_cols = [c[1] for c in cursor.fetchall()]
    if "created_at" not in draw_cols:
        cursor.execute("ALTER TABLE draw ADD COLUMN created_at TEXT")
        logger.info("✅ Добавлено поле created_at в draw")
    conn.commit()


migrate_db()


# ===== СОЗДАНИЕ ТАБЛИЦ =====
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    full_name TEXT,
    status TEXT,
    captcha INTEGER,
    joined INTEGER DEFAULT 0
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS draw (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prize TEXT,
    status TEXT,
    created_at TEXT
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS admins (
    user_id INTEGER PRIMARY KEY
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS podcroot (
    user_id INTEGER PRIMARY KEY
)
""")
conn.commit()


# ===== ХЕЛПЕР ПРОВЕРКИ АДМИНА =====
def is_admin(user_id):
    if user_id in ADMIN_IDS:
        return True
    cursor.execute("SELECT 1 FROM admins WHERE user_id=?", (user_id,))
    return cursor.fetchone() is not None


# ===== ОСНОВНЫЕ ФУНКЦИИ =====
def get_draw():
    cursor.execute("SELECT id, prize FROM draw WHERE status='active'")
    return cursor.fetchone()


def create_draw(prize):
    cursor.execute("UPDATE draw SET status='finished'")
    cursor.execute("DELETE FROM users")
    cursor.execute("INSERT INTO draw (prize, status) VALUES (?, 'active')", (prize,))
    conn.commit()


def close_draw():
    cursor.execute("UPDATE draw SET status='finished'")
    conn.commit()


def mention(uid, username, name):
    return f"@{username}" if username else f"<a href='tg://user?id={uid}'>{name}</a>"


async def check_sub(user_id, context):
    for ch in CHANNEL_IDS:
        try:
            member = await context.bot.get_chat_member(ch, user_id)
            logger.info(f"[check_sub] канал={ch} пользователь={user_id} статус={member.status}")
            if member.status not in ["member", "administrator", "creator"]:
                logger.info(f"Пользователь {user_id} не подписан на канал {ch} (статус: {member.status})")
                return False
        except Exception as e:
            # ВАЖНО: сюда обычно попадают ошибки вида:
            # - "Chat not found" -> неверный CHANNEL_ID или бот не состоит в чате
            # - "Forbidden: bot is not a member of the channel chat" -> бот не админ/не в канале
            # - "Bad Request: user not found" -> пользователь никогда не писал боту/не виден боту
            logger.error(f"[check_sub] ОШИБКА проверки канала {ch} для пользователя {user_id}: {type(e).__name__}: {e}")
            return False
    return True


# 🎰 АНИМАЦИЯ
async def spin_animation(message, text):
    steps = [
        "1️⃣", "2️⃣", "3️⃣",
        "🎰 Крутим рулетку...",
        "🎰 Крутим...",
        "🎰 Еще чуть-чуть..."
    ]
    msg = await message.reply_text(text)
    for step in steps:
        await asyncio.sleep(0.7)
        await msg.edit_text(f"{step}\n{text}")
    return msg


# 📜 УСЛОВИЯ
async def rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = (
        "📜 <b>УСЛОВИЯ УЧАСТИЯ</b>\n\n"
        "1️⃣ Подписаться на все каналы\n"
        "2️⃣ Нажать кнопку проверки\n"
        "3️⃣ Отправить скрин Kick\n\n"
        "⚡ После проверки ты участвуешь"
    )
    await query.message.reply_text(text, parse_mode="HTML")


# 👥 УЧАСТНИКИ
async def members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    cursor.execute("SELECT COUNT(*) FROM users WHERE joined=1")
    count = cursor.fetchone()[0]
    await query.answer(f"👥 Участников: {count}", show_alert=True)


# START
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    draw = get_draw()
    if not draw:
        await update.message.reply_text("❌ Нет активного розыгрыша")
        return
    keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton("🎁 Участвовать")]],
        resize_keyboard=True
    )
    inline = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📜 Условия", callback_data="rules"),
            InlineKeyboardButton("👥 Участники", callback_data="members")
        ]
    ])
    try:
        await update.message.reply_photo(
            photo=open(START_IMAGE, "rb"),
            caption=(
                "╔══════════════════╗\n"
                "      🎁 РОЗЫГРЫШ 🎁\n"
                "╚══════════════════╝\n\n"
                f"🏆 <b>{draw[1]}</b>\n\n"
                "━━━━━━━━━━━━━━━\n"
                "📱 <b>IPHONE 17 PRO MAX</b>\n"
                "━━━━━━━━━━━━━━━\n\n"
                "💥 <b>ВЫИГРАЙ ИМЕННО ТЫ 😉</b>\n\n"
                "👇 Нажми участвовать ниже"
            ),
            reply_markup=inline,
            parse_mode="HTML"
        )
    except FileNotFoundError:
        await update.message.reply_text(
            f"🎁 РОЗЫГРЫШ\n\n🏆 {draw[1]}\n\n👇 Нажми участвовать ниже",
            reply_markup=inline
        )
    await update.message.reply_text(
        "👇 Кнопка участия ниже",
        reply_markup=keyboard
    )


# СОЗДАНИЕ
async def new_draw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id):
        return
    prize = " ".join(context.args)
    if not prize:
        await update.message.reply_text("❌ Укажи приз: /newdraw Iphone 17")
        return
    create_draw(prize)
    await update.message.reply_text(f"✅ Розыгрыш: {prize}")


# УЧАСТИЕ
async def join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    cursor.execute("SELECT joined FROM users WHERE user_id=?", (user.id,))
    row = cursor.fetchone()
    if row and row[0] == 1:
        await update.message.reply_text("✅ Ты уже участвуешь!")
        return
    cursor.execute("""
    INSERT OR REPLACE INTO users (user_id, username, full_name, status)
    VALUES (?, ?, ?, 'start')
    """, (user.id, user.username, user.full_name))
    conn.commit()
    keyboard = [[InlineKeyboardButton("📢 Канал", url=link)] for link in CHANNEL_LINKS]
    keyboard.append([InlineKeyboardButton("✅ Проверить подписку", callback_data="check")])
    await update.message.reply_text(
        "📢 Подпишись на каналы и нажми проверку:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ПРОВЕРКА (исправлена: строгий callback)
async def check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ok = await check_sub(query.from_user.id, context)
    if not ok:
        await query.answer("❌ Ты не подписан на все каналы!", show_alert=True)
        return
    cursor.execute("UPDATE users SET status='kick' WHERE user_id=?", (query.from_user.id,))
    conn.commit()
    await query.edit_message_text(
        f"✅ Подписка подтверждена!\n📺 Отправь скрин с {KICK_LINK}\n📸 Просто отправь фото в этот чат"
    )


# СКРИН
async def photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    cursor.execute("SELECT status FROM users WHERE user_id=?", (user.id,))
    row = cursor.fetchone()
    if not row or row[0] != "kick":
        await update.message.reply_text("❌ Ты не прошёл проверку подписки!")
        return
    file_id = update.message.photo[-1].file_id
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Подтвердить", callback_data=f"ok_{user.id}")],
        [InlineKeyboardButton("❌ Отклонить", callback_data=f"no_{user.id}")]
    ])
    await context.bot.send_photo(
        GROUP_ID,
        file_id,
        caption=f"📸 Скрин от пользователя ID: {user.id}",
        reply_markup=keyboard
    )
    await update.message.reply_text("📩 Скрин отправлен на проверку!")


# АДМИН ПРОВЕРКА
async def admin_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = int(query.data.split("_")[1])
    if query.data.startswith("ok_"):
        a, b = random.randint(1, 9), random.randint(1, 9)
        cursor.execute("UPDATE users SET status='captcha', captcha=? WHERE user_id=?", (a + b, user_id))
        conn.commit()
        await context.bot.send_message(user_id, f"🔐 Реши пример: {a}+{b}=?")
        await query.edit_message_caption("✅ Скрин подтверждён, капча отправлена")
    else:
        await query.edit_message_caption("❌ Скрин отклонён")


# КАПЧА
async def captcha(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    cursor.execute("SELECT captcha, status FROM users WHERE user_id=?", (user.id,))
    row = cursor.fetchone()
    if not row or row[1] != "captcha":
        return
    if not update.message.text or not update.message.text.isdigit():
        await update.message.reply_text("❌ Введи число!")
        return
    if int(update.message.text) == row[0]:
        cursor.execute("UPDATE users SET joined=1, status='done' WHERE user_id=?", (user.id,))
        conn.commit()
        await update.message.reply_text("🎉 Ты участвуешь в розыгрыше!!!")
    else:
        await update.message.reply_text("❌ Неправильно, попробуй ещё раз.")


# АДМИН
async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id):
        return
    cursor.execute("SELECT COUNT(*) FROM users WHERE joined=1")
    count = cursor.fetchone()[0]
    keyboard = [
        [InlineKeyboardButton("🎲 1 победитель", callback_data="pick_1")],
        [InlineKeyboardButton("🏆 3 победителя", callback_data="pick_3")]
    ]
    await update.message.reply_text(
        f"👑 Админ-панель\n👥 Участников: {count}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# 🔥 РОЗЫГРЫШ С ПОДКРУТОМ
async def random_win(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    count = int(query.data.split("_")[1])
    cursor.execute("SELECT user_id, username, full_name FROM users WHERE joined=1")
    users = cursor.fetchall()
    if not users:
        await query.message.reply_text("❌ Нет участников для розыгрыша!")
        return
    # Проверяем подкрут
    cursor.execute("SELECT user_id FROM podcroot LIMIT 1")
    podc = cursor.fetchone()
    winners = []
    if podc:
        podc_user_id = podc[0]
        forced_user = None
        for user in users:
            if user[0] == podc_user_id:
                forced_user = user
                break
        if forced_user:
            winners = [forced_user]
            if count > 1:
                others = [u for u in users if u[0] != podc_user_id]
                need = count - 1
                if need > 0 and others:
                    winners.extend(random.sample(others, min(need, len(others))))
        else:
            winners = random.sample(users, min(count, len(users)))
    else:
        winners = random.sample(users, min(count, len(users)))
    # Анимация
    msg = await spin_animation(query.message, "🎰 Выбираем победителя...")
    text = "🏆 Победители:\n\n"
    for i, u in enumerate(winners, 1):
        text += f"{i}. {mention(u[0], u[1], u[2])}\n"
        try:
            await context.bot.send_message(u[0], "🎉 Ты выиграл!")
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение {u[0]}: {e}")
    cursor.execute("DELETE FROM podcroot")
    conn.commit()
    close_draw()
    await msg.edit_text(text, parse_mode="HTML")


# 🔥 РУЧНОЙ
async def manual_win_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id):
        return
    if not context.args:
        await update.message.reply_text("❌ Используй: /win ID или @username")
        return
    arg = context.args[0]
    if arg.startswith("@"):
        username = arg.replace("@", "")
        cursor.execute("SELECT user_id, username, full_name FROM users WHERE username=?", (username,))
    else:
        if not arg.isdigit():
            await update.message.reply_text("❌ Неверный формат")
            return
        cursor.execute("SELECT user_id, username, full_name FROM users WHERE user_id=?", (int(arg),))
    user = cursor.fetchone()
    if not user:
        await update.message.reply_text("❌ Участник не найден")
        return
    msg = await spin_animation(update.message, "🎰 Выбираем победителя...")
    try:
        await context.bot.send_message(user[0], "🎉 Ты выиграл!!!")
    except:
        pass
    await msg.edit_text(
        f"🏆 Победитель:\n{mention(user[0], user[1], user[2])}",
        parse_mode="HTML"
    )
    close_draw()


# ===== КОМАНДЫ /addadmin и /podcroot =====
async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id):
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("❌ Используй: /addadmin ID")
        return
    new_id = int(context.args[0])
    cursor.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (new_id,))
    conn.commit()
    await update.message.reply_text(f"✅ Пользователь {new_id} назначен админом")


async def podcroot_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id):
        await update.message.reply_text("⛔ Только админ!")
        return
    if not context.args:
        await update.message.reply_text("❌ Используй: /podcroot [user_id]")
        return
    try:
        user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ ID должен быть числом!")
        return
    cursor.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,))
    if not cursor.fetchone():
        await update.message.reply_text("❌ Пользователь не найден в базе данных!")
        return
    cursor.execute("DELETE FROM podcroot")
    cursor.execute("INSERT INTO podcroot (user_id) VALUES (?)", (user_id,))
    conn.commit()
    await update.message.reply_text(f"🎯 Подкрут установлен на пользователя с ID: {user_id}")


# ===== MAIN =====
def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("newdraw", new_draw))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CommandHandler("win", manual_win_cmd))
    app.add_handler(CommandHandler("addadmin", add_admin))
    app.add_handler(CommandHandler("podcroot", podcroot_cmd))
    app.add_handler(MessageHandler(filters.Regex("🎁 Участвовать"), join))
    app.add_handler(MessageHandler(filters.PHOTO, photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, captcha))

    # ===== ИСПРАВЛЕННЫЕ ПАТТЕРНЫ (строгие) =====
    app.add_handler(CallbackQueryHandler(check, pattern="^check$"))
    app.add_handler(CallbackQueryHandler(admin_check, pattern="^(ok_|no_)"))
    app.add_handler(CallbackQueryHandler(random_win, pattern="^pick_"))
    app.add_handler(CallbackQueryHandler(rules, pattern="^rules$"))
    app.add_handler(CallbackQueryHandler(members, pattern="^members$"))

    logger.info("🤖 БОТ ЗАПУЩЕН")
    app.run_polling()


if __name__ == "__main__":
    main()

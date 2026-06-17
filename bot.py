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

TOKEN = "8653610980:AAF9EWd6xvAqOUH4cA5XwtSa55Ah_cq_1nA"

ADMIN_IDS = [8259326014, 8505422185]

GROUP_ID = -1003679834464

CHANNEL_IDS = [-1002774320171, -1003852894722]

CHANNEL_LINKS = [
    "https://t.me/Velikiy_789",
    "https://t.me/Velikiy789TT"
]

KICK_LINK = "https://kick.com/velikiy789"
START_IMAGE = "start.jpg"

logging.basicConfig(level=logging.INFO)

conn = sqlite3.connect("bot.db", check_same_thread=False)
cursor = conn.cursor()

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
    status TEXT
)
""")
conn.commit()


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
            if member.status not in ["member", "administrator", "creator"]:
                return False
        except:
            return False
    return True


# 🎰 АНИМАЦИЯ
async def spin_animation(message, text):
    steps = [
        "1️⃣",
        "2️⃣",
        "3️⃣",
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

    await update.message.reply_text(
        "👇 Кнопка участия ниже",
        reply_markup=keyboard
    )


# СОЗДАНИЕ
async def new_draw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id not in ADMIN_IDS:
        return

    prize = " ".join(context.args)
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
    keyboard.append([InlineKeyboardButton("✅ Проверить", callback_data="check")])

    await update.message.reply_text("Подпишись 👇", reply_markup=InlineKeyboardMarkup(keyboard))


# ПРОВЕРКА
async def check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    ok = await check_sub(query.from_user.id, context)

    if not ok:
        await query.answer("❌ Ты не подписан!", show_alert=True)
        return

    cursor.execute("UPDATE users SET status='kick' WHERE user_id=?", (query.from_user.id,))
    conn.commit()

    await query.edit_message_text(f"✅ Подписка ок\n📺 {KICK_LINK}\n📸 Отправь скрин")


# СКРИН
async def photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user

    cursor.execute("SELECT status FROM users WHERE user_id=?", (user.id,))
    row = cursor.fetchone()

    if not row or row[0] != "kick":
        return

    file_id = update.message.photo[-1].file_id

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Подтвердить", callback_data=f"ok_{user.id}")],
        [InlineKeyboardButton("❌ Отклонить", callback_data=f"no_{user.id}")]
    ])

    await context.bot.send_photo(GROUP_ID, file_id, caption=f"ID: {user.id}", reply_markup=keyboard)
    await update.message.reply_text("📩 Отправлено")


# АДМИН ПРОВЕРКА
async def admin_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = int(query.data.split("_")[1])

    if query.data.startswith("ok_"):
        a, b = random.randint(1, 9), random.randint(1, 9)

        cursor.execute("UPDATE users SET status='captcha', captcha=? WHERE user_id=?", (a + b, user_id))
        conn.commit()

        await context.bot.send_message(user_id, f"🔐 {a}+{b}=?")
        await query.edit_message_caption("✅ OK")
    else:
        await query.edit_message_caption("❌")


# КАПЧА
async def captcha(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user

    cursor.execute("SELECT captcha, status FROM users WHERE user_id=?", (user.id,))
    row = cursor.fetchone()

    if not row or row[1] != "captcha":
        return

    if update.message.text.isdigit() and int(update.message.text) == row[0]:
        cursor.execute("UPDATE users SET joined=1, status='done' WHERE user_id=?", (user.id,))
        conn.commit()
        await update.message.reply_text("🎉 Ты участвуешь!!!")


# АДМИН
async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("SELECT COUNT(*) FROM users WHERE joined=1")
    count = cursor.fetchone()[0]

    keyboard = [
        [InlineKeyboardButton("🎲 1 победитель", callback_data="pick_1")],
        [InlineKeyboardButton("🏆 3 победителя", callback_data="pick_3")]
    ]

    await update.message.reply_text(
        f"👑 Админ\n👥 Участников: {count}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# РАНДОМ
async def random_win(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    count = int(query.data.split("_")[1])

    cursor.execute("SELECT user_id, username, full_name FROM users WHERE joined=1")
    users = cursor.fetchall()

    winners = random.sample(users, min(count, len(users)))

    msg = await spin_animation(query.message, "🎰 Выбираем победителя...")

    text = "🏆 Победители:\n\n"
    for i, u in enumerate(winners, 1):
        text += f"{i}. {mention(u[0], u[1], u[2])}\n"
        try:
            await context.bot.send_message(u[0], "🎉 Ты выиграл!")
        except:
            pass

    close_draw()
    await msg.edit_text(text, parse_mode="HTML")


# 🔥 РУЧНОЙ
async def manual_win_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id not in ADMIN_IDS:
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


def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("newdraw", new_draw))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CommandHandler("win", manual_win_cmd))

    app.add_handler(MessageHandler(filters.Regex("🎁 Участвовать"), join))
    app.add_handler(MessageHandler(filters.PHOTO, photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, captcha))

    app.add_handler(CallbackQueryHandler(check, pattern="check"))
    app.add_handler(CallbackQueryHandler(admin_check, pattern="^(ok_|no_)"))
    app.add_handler(CallbackQueryHandler(random_win, pattern="pick_"))
    app.add_handler(CallbackQueryHandler(rules, pattern="rules"))
    app.add_handler(CallbackQueryHandler(members, pattern="members"))

    print("БОТ ЗАПУЩЕН")
    app.run_polling()


if __name__ == "__main__":
    main()

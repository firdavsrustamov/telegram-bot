
import asyncio
import logging
import json
import os
import sys
import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from filelock import FileLock, Timeout
from aiohttp import web
from config import TOKEN, ADMIN_ID

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

GROUPS_FILE = 'groups.json'
USERS_FILE = 'users.json'

def escape_markdown_v2(text):
    if not isinstance(text, str):
        text = str(text)
    chars = r'_*[]()~`>#+-=|{}.!,:'
    for char in chars:
        text = text.replace(char, f'\\{char}')
    return text

def load_data(file_path):
    try:
        with FileLock(file_path + '.lock', timeout=5):
            if os.path.exists(file_path):
                with open(file_path, 'r') as f:
                    return json.load(f)
    except Timeout:
        logger.error(f"Не удалось получить блокировку для файла: {file_path}")
    except Exception as e:
        logger.error(f"Ошибка чтения {file_path}: {e}")
    return []

def save_data(file_path, data):
    try:
        with FileLock(file_path + '.lock', timeout=5):
            with open(file_path, 'w') as f:
                json.dump(data, f)
    except Timeout:
        logger.error(f"Не удалось получить блокировку для записи в файл: {file_path}")
    except Exception as e:
        logger.error(f"Ошибка записи {file_path}: {e}")

def load_groups(): return load_data(GROUPS_FILE)
def save_groups(groups): save_data(GROUPS_FILE, groups)
def load_users(): return load_data(USERS_FILE)
def save_users(users): save_data(USERS_FILE, users)

def get_inline_keyboard(user_id=None):
    if user_id == ADMIN_ID:
        keyboard = [
            [InlineKeyboardButton("📋 Список групп", callback_data='list_groups'),
             InlineKeyboardButton("👥 Список пользователей", callback_data='list_users')],
            [InlineKeyboardButton("➕ Добавить", callback_data='add_entity'),
             InlineKeyboardButton("🗑 Удалить группу", callback_data='remove_group')],
            [InlineKeyboardButton("🗑 Удалить пользователя", callback_data='remove_user'),
             InlineKeyboardButton("🔄 Обновить меню", callback_data='refresh_menu')]
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("📋 Список групп", callback_data='list_groups'),
             InlineKeyboardButton("👥 Список пользователей", callback_data='list_users')],
            [InlineKeyboardButton("🔄 Обновить меню", callback_data='refresh_menu')]
        ]
    return InlineKeyboardMarkup(keyboard)

def get_main_menu():
    return ReplyKeyboardMarkup([[KeyboardButton("✨ Показать меню")]], resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and update.message.chat.type == 'private':
        user = update.message.from_user
        text = (
            f"*Привет\, {escape_markdown_v2(user.first_name)}\!*
"
            f"Я бот для рассылки сообщений\, фото\, стикеров и видео в Telegram-группы\.
"
            f"Используйте кнопки ниже для управления."
        )
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=get_inline_keyboard(user.id))
        await update.message.reply_text(escape_markdown_v2("🔽 Главное меню:"), parse_mode=ParseMode.MARKDOWN_V2,
                                        reply_markup=get_main_menu())

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data
    if query.message.chat.type != 'private':
        return

    if data == 'list_groups':
        groups = load_groups()
        text = "\n".join(f"🔹 {gid}" for gid in groups) or "📭 Список групп пуст."
        await query.message.reply_text(escape_markdown_v2(text), parse_mode=ParseMode.MARKDOWN_V2)

    elif data == 'list_users':
        users = load_users()
        text = "\n".join(f"🔹 {uid}" for uid in users) or "📭 Список пользователей пуст."
        await query.message.reply_text(escape_markdown_v2(text), parse_mode=ParseMode.MARKDOWN_V2)

    elif data in ['add_entity', 'remove_group', 'remove_user']:
        if user_id != ADMIN_ID:
            await query.message.reply_text(escape_markdown_v2("🚫 Только администратор может выполнять эту команду."),
                                           parse_mode=ParseMode.MARKDOWN_V2)
            return
        context.user_data['awaiting_entity_id'] = data
        prompts = {
            'add_entity': "➕ Введите ID:
- Группа: отрицательное число
- Пользователь: положительное число",
            'remove_group': "🗑 Введите ID группы для удаления:",
            'remove_user': "🗑 Введите ID пользователя для удаления:"
        }
        await query.message.reply_text(escape_markdown_v2(prompts[data]), parse_mode=ParseMode.MARKDOWN_V2)

    elif data == 'refresh_menu':
        await query.message.reply_text(escape_markdown_v2("🔄 Меню обновлено:"), parse_mode=ParseMode.MARKDOWN_V2,
                                       reply_markup=get_inline_keyboard(user_id))

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or update.message.chat.type != 'private':
        return
    user_id = update.message.from_user.id
    text = update.message.text

    if text == "✨ Показать меню":
        await update.message.reply_text(escape_markdown_v2("✨ Меню:"), parse_mode=ParseMode.MARKDOWN_V2,
                                        reply_markup=get_inline_keyboard(user_id))
        return

    if context.user_data.get('awaiting_entity_id'):
        try:
            entity_id = int(text)
        except ValueError:
            await update.message.reply_text(escape_markdown_v2("❌ ID должен быть числом."),
                                            parse_mode=ParseMode.MARKDOWN_V2)
            return
        action = context.user_data.pop('awaiting_entity_id')
        if action == 'add_entity':
            if entity_id < 0:
                groups = load_groups()
                if entity_id not in groups:
                    groups.append(entity_id)
                    save_groups(groups)
                    await update.message.reply_text(escape_markdown_v2("✅ Группа добавлена."),
                                                    parse_mode=ParseMode.MARKDOWN_V2)
            else:
                users = load_users()
                if entity_id not in users:
                    users.append(entity_id)
                    save_users(users)
                    await update.message.reply_text(escape_markdown_v2("✅ Пользователь добавлен."),
                                                    parse_mode=ParseMode.MARKDOWN_V2)
        elif action == 'remove_group':
            groups = load_groups()
            if entity_id in groups:
                groups.remove(entity_id)
                save_groups(groups)
                await update.message.reply_text(escape_markdown_v2("🗑 Группа удалена."),
                                                parse_mode=ParseMode.MARKDOWN_V2)
        elif action == 'remove_user':
            users = load_users()
            if entity_id in users:
                users.remove(entity_id)
                save_users(users)
                await update.message.reply_text(escape_markdown_v2("🗑 Пользователь удалён."),
                                                parse_mode=ParseMode.MARKDOWN_V2)
        return

    if user_id != ADMIN_ID and user_id not in load_users():
        await update.message.reply_text(escape_markdown_v2("🚫 Нет доступа к рассылке."),
                                        parse_mode=ParseMode.MARKDOWN_V2)
        return

    if update.message.photo:
        content = update.message.photo[-1]
        method = lambda gid: context.bot.send_photo(chat_id=gid, photo=content.file_id)
    elif update.message.video:
        content = update.message.video
        method = lambda gid: context.bot.send_video(chat_id=gid, video=content.file_id)
    elif update.message.sticker:
        content = update.message.sticker
        method = lambda gid: context.bot.send_sticker(chat_id=gid, sticker=content.file_id)
    else:
        content = escape_markdown_v2(text)
        method = lambda gid: context.bot.send_message(chat_id=gid, text=content, parse_mode=ParseMode.MARKDOWN_V2)

    groups = load_groups()
    sent = 0
    for gid in groups:
        try:
            await method(gid)
            sent += 1
            await asyncio.sleep(0.3)
        except Exception as e:
            logger.warning(f"Ошибка отправки в {gid}: {e}")

    await update.message.reply_text(escape_markdown_v2(f"✅ Отправлено в {sent} групп."),
                                    parse_mode=ParseMode.MARKDOWN_V2)

async def webhook_handler(request, application):
    try:
        data = await request.json()
        update = Update.de_json(data, application.bot)
        if update:
            await application.process_update(update)
        return web.Response(status=200)
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return web.Response(status=500)

async def main():
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_text))

    await application.initialize()

    webhook_url = os.getenv("WEBHOOK_URL") or f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/webhook"
    await application.bot.set_webhook(url=webhook_url)

    app = web.Application()
    app.router.add_post('/webhook', lambda request: webhook_handler(request, application))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', int(os.getenv("PORT", 10000)))
    await site.start()

    await application.start()
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())

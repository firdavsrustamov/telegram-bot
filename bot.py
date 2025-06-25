import logging
import json
import os
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from config import TOKEN, ADMIN_ID

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Пути к файлам
GROUPS_FILE = 'groups.json'
USERS_FILE = 'users.json'

def load_groups():
    if os.path.exists(GROUPS_FILE):
        with open(GROUPS_FILE, 'r') as f:
            return json.load(f)
    return []

def save_groups(groups):
    with open(GROUPS_FILE, 'w') as f:
        json.dump(groups, f)

def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r') as f:
            return json.load(f)
    return []

def save_users(users):
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f)

def get_inline_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("📋 Список групп", callback_data='list_groups'),
            InlineKeyboardButton("👥 Список пользователей", callback_data='list_users')
        ],
        [
            InlineKeyboardButton("🔄 Обновить меню", callback_data='refresh_menu')
        ]
    ]
    if ADMIN_ID:
        keyboard.extend([
            [
                InlineKeyboardButton("➕ Добавить группу/пользователя", callback_data='add_entity'),
                InlineKeyboardButton("🗑 Удалить группу", callback_data='remove_group')
            ],
            [
                InlineKeyboardButton("🗑 Удалить пользователя", callback_data='remove_user'),
            ]
        ])
    return InlineKeyboardMarkup(keyboard)

def get_main_menu():
    keyboard = [[KeyboardButton("✨ Показать меню")]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or update.message.chat.type != 'private':
        return
    user = update.message.from_user
    welcome_text = (
        f"*Привет, {user.first_name}!* 🎉\n\n"
        "Я бот для рассылки сообщений в группы Telegram. Просто отправь мне текст, и я разошлю его по всем группам.\n\n"
        "*Меню:* Вы можете посмотреть список групп или пользователей."
    )
    await update.message.reply_text(welcome_text, parse_mode='Markdown', reply_markup=get_inline_keyboard())
    await update.message.reply_text('🔽 *Главное меню*:', parse_mode='Markdown', reply_markup=get_main_menu())

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query.message.chat.type != 'private':
        return
    query = update.callback_query
    await query.answer()

    if query.data == 'list_groups':
        groups = load_groups()
        if groups:
            await query.message.reply_text('📋 *Список групп*:\n' + '\n'.join(f'🔹 {gid}' for gid in groups), parse_mode='Markdown')
        else:
            await query.message.reply_text('📭 *Список групп пуст.*', parse_mode='Markdown')
    elif query.data == 'list_users':
        users = load_users()
        if users:
            await query.message.reply_text('👥 *Список пользователей*:\n' + '\n'.join(f'🔹 {uid}' for uid in users), parse_mode='Markdown')
        else:
            await query.message.reply_text('📭 *Список пользователей пуст.*', parse_mode='Markdown')
    elif query.data == 'add_entity':
        if query.from_user.id != ADMIN_ID:
            await query.message.reply_text('🚫 *Только администратор может выполнять эту команду.*', parse_mode='Markdown')
            return
        await query.message.reply_text('➕ *Что добавить?*\n1️⃣ ID группы (отрицательное)\n2️⃣ ID пользователя (положительное)', parse_mode='Markdown')
        context.user_data['awaiting_entity_id'] = 'add'
    elif query.data == 'remove_group':
        if query.from_user.id != ADMIN_ID:
            await query.message.reply_text('🚫 *Только администратор может выполнять эту команду.*', parse_mode='Markdown')
            return
        await query.message.reply_text('🗑 *Введите ID группы для удаления*:', parse_mode='Markdown')
        context.user_data['awaiting_entity_id'] = 'remove_group'
    elif query.data == 'remove_user':
        if query.from_user.id != ADMIN_ID:
            await query.message.reply_text('🚫 *Только администратор может выполнять эту команду.*', parse_mode='Markdown')
            return
        await query.message.reply_text('🗑 *Введите ID пользователя для удаления*:', parse_mode='Markdown')
        context.user_data['awaiting_entity_id'] = 'remove_user'
    elif query.data == 'refresh_menu':
        await query.message.reply_text('🔄 *Меню обновлено*:', parse_mode='Markdown', reply_markup=get_inline_keyboard())

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or update.message.chat.type != 'private':
        return
    user_id = update.message.from_user.id
    text = update.message.text

    if text == '✨ Показать меню':
        await update.message.reply_text('✨ *Меню*:', parse_mode='Markdown', reply_markup=get_inline_keyboard())
        return

    if context.user_data.get('awaiting_entity_id'):
        if user_id != ADMIN_ID:
            await update.message.reply_text('🚫 *Только администратор может выполнять эту команду.*', parse_mode='Markdown')
            return
        try:
            entity_id = int(text)
            action = context.user_data['awaiting_entity_id']
            if action == 'add':
                groups = load_groups()
                users = load_users()
                if entity_id < 0:
                    if entity_id not in groups:
                        groups.append(entity_id)
                        save_groups(groups)
                        await update.message.reply_text(f'✅ *Группа {entity_id} добавлена.*', parse_mode='Markdown')
                    else:
                        await update.message.reply_text(f'⚠️ *Группа {entity_id} уже в списке.*', parse_mode='Markdown')
                else:
                    if entity_id not in users:
                        users.append(entity_id)
                        save_users(users)
                        await update.message.reply_text(f'✅ *Пользователь {entity_id} добавлен.*', parse_mode='Markdown')
                    else:
                        await update.message.reply_text(f'⚠️ *Пользователь {entity_id} уже в списке.*', parse_mode='Markdown')
            elif action == 'remove_group':
                groups = load_groups()
                if entity_id in groups:
                    groups.remove(entity_id)
                    save_groups(groups)
                    await update.message.reply_text(f'🗑 *Группа {entity_id} удалена.*', parse_mode='Markdown')
                else:
                    await update.message.reply_text(f'⚠️ *Группа {entity_id} не найдена.*', parse_mode='Markdown')
            elif action == 'remove_user':
                users = load_users()
                if entity_id in users:
                    users.remove(entity_id)
                    save_users(users)
                    await update.message.reply_text(f'🗑 *Пользователь {entity_id} удален.*', parse_mode='Markdown')
                else:
                    await update.message.reply_text(f'⚠️ *Пользователь {entity_id} не найден.*', parse_mode='Markdown')
            context.user_data.clear()
            await update.message.reply_text('✨ *Меню*:', parse_mode='Markdown', reply_markup=get_inline_keyboard())
        except ValueError:
            await update.message.reply_text('❌ *ID должен быть числом.*', parse_mode='Markdown')
        return

    # Рассылка сообщения в группы
    message_text = text
    groups = load_groups()
    success_count = 0

    for group_id in groups:
        try:
            await context.bot.send_message(chat_id=group_id, text=message_text, parse_mode='Markdown')
            success_count += 1
            logger.info(f"Сообщение отправлено в группу {group_id}")
        except Exception as e:
            logger.error(f"Ошибка при отправке в группу {group_id}: {e}")

    await update.message.reply_text(
        f'✅ *Сообщение отправлено в {success_count} из {len(groups)} групп.*',
        parse_mode='Markdown', reply_markup=get_inline_keyboard()
    )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} вызвал ошибку: {context.error}")
    try:
        if update and hasattr(update, 'message') and update.message:
            await update.message.reply_text(f'❌ *Ошибка:* `{context.error}`', parse_mode='Markdown')
    except Exception:
        pass

def main():
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_error_handler(error_handler)
    application.run_polling()

if __name__ == '__main__':
    main()

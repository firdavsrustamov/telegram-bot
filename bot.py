import asyncio
import logging
import json
import os
import sys
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, Update, ParseMode
from telegram.error import Forbidden, BadRequest, NetworkError, RetryAfter
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from filelock import FileLock
from config import TOKEN, ADMIN_ID

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Пути к файлам с сохранёнными ID групп и пользователей
GROUPS_FILE = 'groups.json'
USERS_FILE = 'users.json'

def escape_markdown_v2(text):
    """Экранирование специальных символов для MarkdownV2."""
    chars = r'_[]()~`>#+-=|{}.!'
    for char in chars:
        text = text.replace(char, f'\\{char}')
    return text

def load_groups():
    """Загрузка списка ID групп из файла с блокировкой."""
    with FileLock(GROUPS_FILE + ".lock"):
        if os.path.exists(GROUPS_FILE):
            with open(GROUPS_FILE, 'r') as f:
                return json.load(f)
        return []

def save_groups(groups):
    """Сохранение списка ID групп в файл с блокировкой."""
    with FileLock(GROUPS_FILE + ".lock"):
        with open(GROUPS_FILE, 'w') as f:
            json.dump(groups, f)

def load_users():
    """Загрузка списка ID пользователей из файла с блокировкой."""
    with FileLock(USERS_FILE + ".lock"):
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, 'r') as f:
                return json.load(f)
        return []

def save_users(users):
    """Сохранение списка ID пользователей в файл с блокировкой."""
    with FileLock(USERS_FILE + ".lock"):
        with open(USERS_FILE, 'w') as f:
            json.dump(users, f)

def get_inline_keyboard(user_id=None):
    """
    Формирование инлайн-клавиатуры меню.
    Если user_id соответствует ADMIN_ID, включаются кнопки администрирования.
    """
    keyboard = [
        [
            InlineKeyboardButton("📋 Список групп", callback_data='list_groups'),
            InlineKeyboardButton("👥 Список пользователей", callback_data='list_users')
        ],
        [
            InlineKeyboardButton("🔄 Обновить меню", callback_data='refresh_menu')
        ]
    ]
    if ADMIN_ID and user_id == ADMIN_ID:
        keyboard.extend([
            [
                InlineKeyboardButton("➕ Добавить группу/пользователя", callback_data='add_entity'),
                InlineKeyboardButton("🗑 Удалить группу", callback_data='remove_group')
            ],
            [
                InlineKeyboardButton("🗑 Удалить пользователя", callback_data='remove_user')
            ]
        ])
    return InlineKeyboardMarkup(keyboard)

def get_main_menu():
    """Формирование основной клавиатуры с кнопкой вызова меню."""
    keyboard = [[KeyboardButton("✨ Показать меню")]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start – приветствие и вывод меню (только в личных сообщениях)."""
    if not update.message or update.message.chat.type != 'private':
        return
    user = update.message.from_user
    logger.info(f"Пользователь {user.id} запустил команду /start")
    welcome_text = (
        f"*Привет, {escape_markdown_v2(user.first_name)}!* 🎉\n\n"
        "Я бот для рассылки сообщений в группы Telegram\. Просто отправь мне текст, и я разошлю его по всем подключенным группам и пользователям\.\n\n"
        "*Меню:* Вы можете посмотреть список групп или пользователей, а администратор – управлять ими\."
    )
    await update.message.reply_text(welcome_text, parse_mode=ParseMode.MARKDOWN_V2,
                                    reply_markup=get_inline_keyboard(user_id=user.id))
    await update.message.reply_text('🔽 *Главное меню*:', parse_mode=ParseMode.MARKDOWN_V2,
                                    reply_markup=get_main_menu())

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий инлайн-кнопок меню."""
    if update.callback_query.message.chat.type != 'private':
        return
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data
    logger.info(f"Пользователь {user_id} нажал кнопку {data}")

    if data == 'list_groups':
        groups = load_groups()
        if groups:
            group_list = '\n'.join(f'🔹 {gid}' for gid in groups)
            await query.message.reply_text(f'📋 *Список групп*:\n{escape_markdown_v2(group_list)}',
                                          parse_mode=ParseMode.MARKDOWN_V2)
        else:
            await query.message.reply_text('📭 *Список групп пуст\.*', parse_mode=ParseMode.MARKDOWN_V2)

    elif data == 'list_users':
        users = load_users()
        if users:
            user_list = '\n'.join(f'🔹 {uid}' for uid in users)
            await query.message.reply_text(f'👥 *Список пользователей*:\n{escape_markdown_v2(user_list)}',
                                          parse_mode=ParseMode.MARKDOWN_V2)
        else:
            await query.message.reply_text('📭 *Список пользователей пуст\.*', parse_mode=ParseMode.MARKDOWN_V2)

    elif data == 'add_entity':
        if user_id != ADMIN_ID:
            await query.message.reply_text('🚫 *Только администратор может выполнять эту команду\.*',
                                          parse_mode=ParseMode.MARKDOWN_V2)
            return
        await query.message.reply_text(
            '➕ *Что добавить?*\n1️⃣ ID группы \(отрицательное число\)\n2️⃣ ID пользователя \(положительное число\)',
            parse_mode=ParseMode.MARKDOWN_V2)
        context.user_data['awaiting_entity_id'] = 'add'

    elif data == 'remove_group':
        if user_id != ADMIN_ID:
            await query.message.reply_text('🚫 *Только администратор может выполнять эту команду\.*',
                                          parse_mode=ParseMode.MARKDOWN_V2)
            return
        await query.message.reply_text('🗑 *Введите ID группы для удаления*:', parse_mode=ParseMode.MARKDOWN_V2)
        context.user_data['awaiting_entity_id'] = 'remove_group'

    elif data == 'remove_user':
        if user_id != ADMIN_ID:
            await query.message.reply_text('🚫 *Только администратор может выполнять эту команду\.*',
                                          parse_mode=ParseMode.MARKDOWN_V2)
            return
        await query.message.reply_text('🗑 *Введите ID пользователя для удаления*:', parse_mode=ParseMode.MARKDOWN_V2)
        context.user_data['awaiting_entity_id'] = 'remove_user'

    elif data == 'refresh_menu':
        await query.message.reply_text('🔄 *Меню обновлено*:', parse_mode=ParseMode.MARKDOWN_V2,
                                      reply_markup=get_inline_keyboard(user_id=user_id))

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик текстовых сообщений в личном чате.
    - Если ожидается ввод ID, обрабатывает его.
    - Иначе воспринимает текст как сообщение для рассылки.
    """
    if not update.message or update.message.chat.type != 'private':
        return
    user_id = update.message.from_user.id
    text = update.message.text
    logger.info(f"Получено сообщение от пользователя {user_id}: {text}")

    if text == '✨ Показать меню':
        await update.message.reply_text('✨ *Меню*:', parse_mode=ParseMode.MARKDOWN_V2,
                                       reply_markup=get_inline_keyboard(user_id=user_id))
        return

    if context.user_data.get('awaiting_entity_id'):
        if user_id != ADMIN_ID:
            await update.message.reply_text('🚫 *Только администратор может выполнять эту команду\.*',
                                           parse_mode=ParseMode.MARKDOWN_V2)
            context.user_data.clear()
            return
        try:
            entity_id = int(text.strip())
        except ValueError:
            await update.message.reply_text('❌ *ID должен быть числом\.*', parse_mode=ParseMode.MARKDOWN_V2)
            return

        action = context.user_data.get('awaiting_entity_id')
        context.user_data.clear()
        if action == 'add':
            groups = load_groups()
            users = load_users()
            if entity_id < 0:
                if entity_id not in groups:
                    groups.append(entity_id)
                    save_groups(groups)
                    await update.message.reply_text(f'✅ *Группа {entity_id} добавлена\.*',
                                                  parse_mode=ParseMode.MARKDOWN_V2)
                else:
                    await update.message.reply_text(f'⚠️ *Группа {entity_id} уже есть в списке\.*',
                                                  parse_mode=ParseMode.MARKDOWN_V2)
            else:
                if entity_id not in users:
                    users.append(entity_id)
                    save_users(users)
                    await update.message.reply_text(f'✅ *Пользователь {entity_id} добавлен\.*',
                                                  parse_mode=ParseMode.MARKDOWN_V2)
                else:
                    await update.message.reply_text(f'⚠️ *Пользователь {entity_id} уже есть в списке\.*',
                                                  parse_mode=ParseMode.MARKDOWN_V2)

        elif action == 'remove_group':
            groups = load_groups()
            if entity_id in groups:
                groups.remove(entity_id)
                save_groups(groups)
                await update.message.reply_text(f'🗑 *Группа {entity_id} удалена из списка\.*',
                                              parse_mode=ParseMode.MARKDOWN_V2)
            else:
                await update.message.reply_text(f'⚠️ *Группа {entity_id} не найдена в списке\.*',
                                              parse_mode=ParseMode.MARKDOWN_V2)

        elif action == 'remove_user':
            users = load_users()
            if entity_id in users:
                users.remove(entity_id)
                save_users(users)
                await update.message.reply_text(f'🗑 *Пользователь {entity_id} удалён из списка\.*',
                                              parse_mode=ParseMode.MARKDOWN_V2)
            else:
                await update.message.reply_text(f'⚠️ *Пользователь {entity_id} не найден в списке\.*',
                                              parse_mode=ParseMode.MARKDOWN_V2)
        await update.message.reply_text('✨ *Меню*:', parse_mode=ParseMode.MARKDOWN_V2,
                                       reply_markup=get_inline_keyboard(user_id=user_id))
        return

    if user_id != ADMIN_ID:
        authorized_users = load_users()
        if user_id not in authorized_users:
            await update.message.reply_text('🚫 *У вас нет прав на отправку рассылки\.*',
                                           parse_mode=ParseMode.MARKDOWN_V2)
            return

    message_text = escape_markdown_v2(text)
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=message_text,
            parse_mode=ParseMode.MARKDOWN_V2
        )
    except BadRequest as e:
        if "can't parse" in str(e).lower():
            await update.message.reply_text(
                '❌ *Ошибка: некорректный Markdown\. Используйте корректную разметку или отправьте текст без форматирования\.*',
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return
        raise

    groups = load_groups()
    users = load_users()
    success_groups = 0
    success_users = 0
    groups_to_remove = []
    users_to_remove = []

    for group_id in groups:
        try:
            await context.bot.send_message(chat_id=group_id, text=message_text, parse_mode=ParseMode.MARKDOWN_V2)
            success_groups += 1
            logger.info(f"Сообщение отправлено в группу {group_id}")
            await asyncio.sleep(0.1)
        except Forbidden:
            logger.warning(f"Недостаточно прав для отправки в группу {group_id}")
            groups_to_remove.append(group_id)
        except BadRequest as e:
            if "chat not found" in str(e).lower():
                logger.warning(f"Группа {group_id} недоступна")
                groups_to_remove.append(group_id)
            else:
                logger.error(f"Ошибка разметки в группе {group_id}: {e}")
        except RetryAfter as e:
            logger.warning(f"Лимит Telegram API для группы {group_id}, ждём {e.retry_after} секунд")
            await asyncio.sleep(e.retry_after)
            await context.bot.send_message(chat_id=group_id, text=message_text, parse_mode=ParseMode.MARKDOWN_V2)
            success_groups += 1
        except NetworkError as e:
            logger.error(f"Сетевая ошибка при отправке в группу {group_id}: {e}")
        except Exception as e:
            logger.error(f"Неизвестная ошибка при отправке в группу {group_id}: {e}")

    for user in users:
        try:
            await context.bot.send_message(chat_id=user, text=message_text, parse_mode=ParseMode.MARKDOWN_V2)
            success_users += 1
            logger.info(f"Сообщение отправлено пользователю {user}")
            await asyncio.sleep(0.1)
        except Forbidden:
            logger.warning(f"Не удалось отправить пользователю {user}")
            users_to_remove.append(user)
        except BadRequest as e:
            if "chat not found" in str(e).lower():
                logger.warning(f"Пользователь {user} недоступен")
                users_to_remove.append(user)
            else:
                logger.error(f"Ошибка разметки для пользователя {user}: {e}")
        except RetryAfter as e:
            logger.warning(f"Лимит Telegram API для пользователя {user}, ждём {e.retry_after} секунд")
            await asyncio.sleep(e.retry_after)
            await context.bot.send_message(chat_id=user, text=message_text, parse_mode=ParseMode.MARKDOWN_V2)
            success_users += 1
        except NetworkError as e:
            logger.error(f"Сетевая ошибка при отправке пользователю {user}: {e}")
        except Exception as e:
            logger.error(f"Неизвестная ошибка при отправке пользователю {user}: {e}")

    if groups_to_remove:
        for group_id in groups_to_remove:
            groups.remove(group_id)
        save_groups(groups)
    if users_to_remove:
        for user in users_to_remove:
            users.remove(user)
        save_users(users)

    response_lines = [
        f'✅ *Сообщение отправлено в {success_groups} из {len(groups)} групп*\.',
        f'✅ *Сообщение отправлено {success_users} из {len(users)} пользователей*\.'
    ]
    if groups_to_remove or users_to_remove:
        removed_info = ""
        if groups_to_remove:
            removed_info += f"\n🗑 *Удалённые группы:* {', '.join(str(g) for g in groups_to_remove)}"
        if users_to_remove:
            removed_info += f"\n🗑 *Удалённые пользователи:* {', '.join(str(u) for u in users_to_remove)}"
        response_lines.append(escape_markdown_v2(removed_info))

    await update.message.reply_text(
        "\n".join(response_lines),
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=get_inline_keyboard(user_id=user_id)
    )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Глобальный обработчик ошибок."""
    logger.error(f"Ошибка: {context.error}", exc_info=context.error)
    if update and hasattr(update, 'message') and update.message:
        await update.message.reply_text(
            f'❌ *Ошибка:* `{escape_markdown_v2(str(context.error))}`',
            parse_mode=ParseMode.MARKDOWN_V2
        )
    if ADMIN_ID:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f'❌ *Ошибка бота:* `{escape_markdown_v2(str(context.error))}`',
            parse_mode=ParseMode.MARKDOWN_V2
        )

async def main():
    """Запуск бота."""
    try:
        logger.info(f"Starting bot with Python {sys.version} and python-telegram-bot {telegram.__version__}")
        application = await Application.builder().token(TOKEN).build()
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CallbackQueryHandler(button_callback))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
        application.add_error_handler(error_handler)
        await application.run_polling(allowed_updates=Update.ALL_TYPES)
    except Exception as e:
        logger.error(f"Failed to start bot: {e}", exc_info=e)
        if ADMIN_ID:
            await application.bot.send_message(
                chat_id=ADMIN_ID,
                text=f'❌ *Бот не запустился:* `{escape_markdown_v2(str(e))}`',
                parse_mode=ParseMode.MARKDOWN_V2
            )
        raise

if __name__ == '__main__':
    asyncio.run(main())

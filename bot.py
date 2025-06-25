```python
import asyncio
import logging
import json
import os
import sys
import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.constants import ParseMode
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

# Пути к файлам
GROUPS_FILE = 'groups.json'
USERS_FILE = 'users.json'

def escape_markdown(text):
    """Экранирование специальных символов для MarkdownV2."""
    chars = r'_*[]()~`>#+-=|{}.!'
    for char in chars:
        text = text.replace(char, f'\\{char}')
    return text

def load_groups():
    """Загрузка списка ID групп из файла с блокировкой."""
    with FileLock(GROUPS_FILE + '.lock'):
        if os.path.exists(GROUPS_FILE):
            with open(GROUPS_FILE, 'r') as f:
                return json.load(f)
        return []

def save_groups(groups):
    """Сохранение списка ID групп в файл."""
    with FileLock(GROUPS_FILE + '.lock'):
        with open(GROUPS_FILE, 'w') as f:
            json.dump(groups, f)

def load_users():
    """Заголовка списка ID пользователей из файла с блокировкой."""
    with FileLock(USERS_FILE + '.lock'):
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, 'r') as f:
                return json.load(f)
        return []

def save_users(users):
    """Сохранение списка ID пользователей в файл с блокировкой."""
    with FileLock(USERS_FILE + '.lock'):
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
        r"*Привет, {0}!* 🎉\n\n"
        r"Я бот для рассылки сообщений в группы Telegram\. Просто отправь мне текст, и я разошлю его по всем подключенным группам и пользователям\.\n\n"
        r"*Меню:* Вы можете посмотреть список групп или пользователей, а администратор – управлять ими\."
    ).format(escape_markdown_v2(user.first_name))
    await update.message.reply_text(welcome_text, parse_mode=ParseMode.MARKDOWN_V2,
                                    reply_markup=get_inline_keyboard(user_id=user.id))
    await update.message.reply_text(r'🔽 *Главное меню*:', parse_mode=ParseMode.MARKDOWN_V2,
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
            await query.message.reply_text(r'📋 *Список групп*:\n{0}'.format(escape_markdown_v2(group_list)),
                                          parse_mode=ParseMode.MARKDOWN_V2)
        else:
            await query.message.reply_text(r'📭 *Список групп пуст\.*', parse_mode=ParseMode.MARKDOWN_V2)

    elif data == 'list_users':
        users = load_users()
        if users:
            user_list = '\n'.join(f'🔹 {uid}' for uid in users)
            await query.message.reply_text(r'👥 *Список пользователей*:\n{0}'.format(escape_markdown_v2(user_list)),
                                          parse_mode=ParseMode.MARKDOWN_V2)
        else:
            await query.message.reply_text(r'📭 *Список пользователей пуст\.*', parse_mode=ParseMode.MARKDOWN_V2)

    elif data == 'add_entity':
        if user_id != ADMIN_ID:
            await query.message.reply_text(r'🚫 *Только администратор может выполнять эту команду\.*',
                                          parse_mode=ParseMode.MARKDOWN_V2)
            return
        await query.message.reply_text(
            r'➕ *Что добавить?*\n1️⃣ ID группы \(отрицательное число\)\n2️⃣ ID пользователя \(положительное число\)',
            parse_mode=ParseMode.MARKDOWN_V2)
        context.user_data['awaiting_entity_id'] = 'add'

    elif data == 'remove_group':
        if user_id != ADMIN_ID:
            await query.message.reply_text(r'🚫 *Только администратор может выполнять эту команду\.*',
                                          parse_mode=ParseMode.MARKDOWN_V2)
            return
        await query.message.reply_text(r'🗑 *Введите ID группы для удаления*:', parse_mode=ParseMode.MARKDOWN_V2)
        context.user_data['awaiting_entity_id'] = 'remove_group'

    elif data == 'remove_user':
        if user_id != ADMIN_ID:
            await query.message.reply_text(r'🚫 *Только администратор может выполнять эту команду\.*',
                                          parse_mode=ParseMode.MARKDOWN_V2)
            return
        await query.message.reply_text(r'🗑 *Введите ID пользователя для удаления*:', parse_mode=ParseMode.MARKDOWN_V2)
        context.user_data['awaiting_entity_id'] = 'remove_user'

    elif data == 'refresh_menu':
        await query.message.reply_text(r'🔄 *Меню обновлено*:', parse_mode=ParseMode.MARKDOWN_V2,
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
        await update.message.reply_text(r'✨ *Меню*:', parse_mode=ParseMode.MARKDOWN_V2,
                                       reply_markup=get_inline_keyboard(user_id=user_id))
        return

    if context.user_data.get('awaiting_entity_id'):
        if user_id != ADMIN_ID:
            await update.message.reply_text(r'🚫 *Только администратор может выполнять эту команду\.*',
                                           parse_mode=ParseMode.MARKDOWN_V2)
            context.user_data.clear()
            return
        try:
            entity_id = int(text.strip())
        except ValueError:
            await update.message.reply_text(r'❌ *ID должен быть числом\.*', parse_mode=ParseMode.MARKDOWN_V2)
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
                    await update.message.reply_text(r'✅ *Группа {0} добавлена\.*'.format(entity_id),
                                                  parse_mode=ParseMode.MARKDOWN_V2)
                else:
                    await update.message.reply_text(r'⚠️ *Группа {0} уже есть в списке\.*'.format(entity_id),
                                                  parse_mode=ParseMode.MARKDOWN_V2)
            else:
                if entity_id not in users:
                    users.append(entity_id)
                    save_users(users)
                    await update.message.reply_text(r'✅ *Пользователь {0} добавлен\.*'.format(entity_id),
                                                  parse_mode=ParseMode.MARKDOWN_V2)
                else:
                    await update.message.reply_text(r'⚠️ *Пользователь {0} уже есть в списке\.*'.format(entity_id),
                                                  parse_mode=ParseMode.MARKDOWN_V2)

        elif action == 'remove_group':
            groups = load_groups()
            if entity_id in groups:
                groups.remove(entity_id)
                save_groups(groups)
                await update.message.reply_text(r'🗑 *Группа {0} удалена из списка\.*'.format(entity_id),
                                              parse_mode=ParseMode.MARKDOWN_V2)
            else:
                await update.message.reply_text(r'⚠️ *Группа {0} не найдена в списке\.*'.format(entity_id),
                                              parse_mode=ParseMode.MARKDOWN_V2)

        elif action == 'remove_user':
            users = load_users()
            if entity_id in users:
                users.remove(entity_id)
                save_users(users)
                await update.message.reply_text(r'🗑 *Пользователь {0} удалён из списка\.*'.format(entity_id),
                                              parse_mode=ParseMode.MARKDOWN_V2)
            else:
                await update.message.reply_text(r'⚠️ *Пользователь {0} не найден в списке\.*'.format(entity_id),
                                              parse_mode=ParseMode.MARKDOWN_V2)
        await update.message.reply_text(r'✨ *Меню*:', parse_mode=ParseMode.MARKDOWN_V2,
                                       reply_markup=get_inline_keyboard(user_id=user_id))
        return

    if user_id != ADMIN_ID:
        authorized_users = load_users()
        if user_id not in authorized_users:
            await update.message.reply_text(r'🚫 *У вас нет прав на отправку рассылки\.*',
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
                r'❌ *Ошибка: некорректный Markdown\. Используйте корректную разметку или отправьте текст без форматирования\.*',
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
        r'✅ *Сообщение отправлено в {0} из {1} групп*\.'.format(success_groups, len(groups)),
        r'✅ *Сообщение отправлено {0} из {1} пользователей*\.'.format(success_users, len(users))
    ]
    if groups_to_remove or users_to_remove:
        removed_info = ""
        if groups_to_remove:
            removed_info += r"\n🗑 *Удалённые группы:* {0}".format(', '.join(str(g) for g in groups_to_remove))
        if users_to_remove:
            removed_info += r"\n🗑 *Удалённые пользователи:* {0}".format(', '.join(str(u) for u in users_to_remove))
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
            r'❌ *Ошибка:* `{0}`'.format(escape_markdown_v2(str(context.error))),
            parse_mode=ParseMode.MARKDOWN_V2
        )
    if ADMIN_ID:
        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=r'❌ Ошибка: `{0}`'.format(escape_markdown_v2(str(context.error))),
                parse_mode=ParseMode.MARKDOWN_V2
            )
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление об ошибке администратору: {e}")

async def main():
    """Запуск бота."""
    try:
        logger.info(f"Starting bot with Python {sys.version}, python-telegram-bot {telegram.__version__}")
        application = await Application.builder().token(TOKEN).build()
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CallbackQueryHandler(button_callback))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
        application.add_error_handler(error_handler)
        await application.run_polling(allowed_updates=Update.ALL_TYPES)
    except Exception as e:
        logger.error(f"Ошибка инициализации бота: {e}", exc_info=e)
        if ADMIN_ID:
            try:
                await application.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=r'❌ Бот не запустился: `{0}`'.format(escape_markdown_v2(str(e))),
                    parse_mode=ParseMode.MARKDOWN_V2
                )
            except Exception as notify_error:
                logger.error(f"Не удалось отправить уведомления об ошибке администратору: {notify_error}")
        raise

if __name__ == '__main__':
    asyncio.run(main())
```

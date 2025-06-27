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
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Пути к файлам
GROUPS_FILE = 'groups.json'
USERS_FILE = 'users.json'

def escape_markdown_v2(text):
    """Экранирование специальных символов для MarkdownV2."""
    if not isinstance(text, str):
        text = str(text)
    chars = r'_*[]()~`>#+-=|{}.!,:'
    for char in chars:
        text = text.replace(char, f'\\{char}')
    return text

def load_groups():
    """Загрузка списка ID групп из файла с блокировкой."""
    try:
        with FileLock(GROUPS_FILE + '.lock', timeout=5):
            if os.path.exists(GROUPS_FILE):
                with open(GROUPS_FILE, 'r') as f:
                    return json.load(f)
    except Timeout:
        logger.error("Не удалось получить блокировку для файла групп")
    except Exception as e:
        logger.error(f"Ошибка чтения файла групп: {e}")
    return []

def save_groups(groups):
    """Сохранение списка ID групп в файл с блокировкой."""
    try:
        with FileLock(GROUPS_FILE + '.lock', timeout=5):
            with open(GROUPS_FILE, 'w') as f:
                json.dump(groups, f)
    except Timeout:
        logger.error("Не удалось получить блокировку для сохранения групп")
    except Exception as e:
        logger.error(f"Ошибка сохранения файла групп: {e}")

def load_users():
    """Загрузка списка ID пользователей из файла с блокировкой."""
    try:
        with FileLock(USERS_FILE + '.lock', timeout=5):
            if os.path.exists(USERS_FILE):
                with open(USERS_FILE, 'r') as f:
                    return json.load(f)
    except Timeout:
        logger.error("Не удалось получить блокировку для файла пользователей")
    except Exception as e:
        logger.error(f"Ошибка чтения файла пользователей: {e}")
    return []

def save_users(users):
    """Сохранение списка ID пользователей в файл с блокировкой."""
    try:
        with FileLock(USERS_FILE + '.lock', timeout=5):
            with open(USERS_FILE, 'w') as f:
                json.dump(users, f)
    except Timeout:
        logger.error("Не удалось получить блокировку для сохранения пользователей")
    except Exception as e:
        logger.error(f"Ошибка сохранения файла пользователей: {e}")

def get_inline_keyboard(user_id=None):
    """Формирование инлайн-клавиатуры меню."""
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
        keyboard = [
            [
                InlineKeyboardButton("📋 Список групп", callback_data='list_groups'),
                InlineKeyboardButton("👥 Список пользователей", callback_data='list_users')
            ],
            [
                InlineKeyboardButton("➕ Добавить", callback_data='add_entity'),
                InlineKeyboardButton("🗑 Удалить группу", callback_data='remove_group')
            ],
            [
                InlineKeyboardButton("🗑 Удалить пользователя", callback_data='remove_user'),
                InlineKeyboardButton("🔄 Обновить меню", callback_data='refresh_menu')
            ]
        ]
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
        f"*Привет, {escape_markdown_v2(user.first_name)}\\!*\n\n"
        f"Я бот для рассылки сообщений, стикеров, фото, видео и GIF в группы Telegram\\. "
        f"Отправь мне текст или медиа, и я разошлю их по всем подключенным группам\\.\n\n"
        f"*Меню\\:* Вы можете посмотреть список групп или пользователей, а администратор – управлять ими\\."
    )
    await update.message.reply_text(welcome_text, parse_mode=ParseMode.MARKDOWN_V2,
                                    reply_markup=get_inline_keyboard(user_id=user.id))
    await update.message.reply_text(
        escape_markdown_v2("🔽 Главное меню:"),
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=get_main_menu()
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий инлайн-кнопок меню."""
    query = update.callback_query
    if query.message.chat.type != 'private':
        await query.answer()
        return
    await query.answer()
    user_id = query.from_user.id
    data = query.data
    logger.info(f"Пользователь {user_id} нажал кнопку {data}")

    if data == 'list_groups':
        groups = load_groups()
        if groups:
            group_list = '\n'.join(f'🔹 {gid}' for gid in groups)
            await query.message.reply_text(
                f'📋 *Список групп\\:* \n{escape_markdown_v2(group_list)}',
                parse_mode=ParseMode.MARKDOWN_V2
            )
        else:
            await query.message.reply_text(
                escape_markdown_v2("📭 Список групп пуст."),
                parse_mode=ParseMode.MARKDOWN_V2
            )

    elif data == 'list_users':
        users = load_users()
        if users:
            user_list = '\n'.join(f'🔹 {uid}' for uid in users)
            await query.message.reply_text(
                f'👥 *Список пользователей\\:* \n{escape_markdown_v2(user_list)}',
                parse_mode=ParseMode.MARKDOWN_V2
            )
        else:
            await query.message.reply_text(
                escape_markdown_v2("📭 Список пользователей пуст."),
                parse_mode=ParseMode.MARKDOWN_V2
            )

    elif data == 'add_entity':
        if user_id != ADMIN_ID:
            await query.message.reply_text(
                escape_markdown_v2("🚫 Только администратор может выполнять эту команду."),
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return
        add_text = "➕ Что добавить?\n1️⃣ ID группы (отрицательное число)\n2️⃣ ID пользователя (положительное число)"
        await query.message.reply_text(
            escape_markdown_v2(add_text),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        context.user_data['awaiting_entity_id'] = 'add'

    elif data == 'remove_group':
        if user_id != ADMIN_ID:
            await query.message.reply_text(
                escape_markdown_v2("🚫 Только администратор может выполнять эту команду."),
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return
        await query.message.reply_text(
            escape_markdown_v2("🗑 Введите ID группы для удаления:"),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        context.user_data['awaiting_entity_id'] = 'remove_group'

    elif data == 'remove_user':
        if user_id != ADMIN_ID:
            await query.message.reply_text(
                escape_markdown_v2("🚫 Только администратор может выполнять эту команду."),
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return
        await query.message.reply_text(
            escape_markdown_v2("🗑 Введите ID пользователя для удаления:"),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        context.user_data['awaiting_entity_id'] = 'remove_user'

    elif data == 'refresh_menu':
        await query.message.reply_text(
            escape_markdown_v2("🔄 Меню обновлено:"),
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=get_inline_keyboard(user_id=user_id)
        )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений и медиа в личном чате."""
    if not update.message or update.message.chat.type != 'private':
        return
    user_id = update.message.from_user.id
    logger.info(f"Получено сообщение от пользователя {user_id}")

    # Проверка авторизации пользователя в самом начале
    if user_id != ADMIN_ID:
        authorized_users = load_users()
        if user_id not in authorized_users:
            await update.message.reply_text(
                escape_markdown_v2("🚫 У вас нет прав на отправку рассылки."),
                parse_mode=ParseMode.MARKDOWN_V2,
                reply_markup=get_inline_keyboard(user_id=user_id)
            )
            return

    # Обработка текстового сообщения
    if text := update.message.text:
        logger.info(f"Текст: {text}")
        if text == '✨ Показать меню':
            await update.message.reply_text(
                escape_markdown_v2("✨ Меню:"),
                parse_mode=ParseMode.MARKDOWN_V2,
                reply_markup=get_inline_keyboard(user_id=user_id)
            )
            return

        # Обработка ввода ID для админ-действий
        if context.user_data.get('awaiting_entity_id'):
            if user_id != ADMIN_ID:
                await update.message.reply_text(
                    escape_markdown_v2("🚫 Только администратор может выполнять эту команду."),
                    parse_mode=ParseMode.MARKDOWN_V2
                )
                context.user_data.clear()
                return
            try:
                entity_id = int(text.strip())
            except ValueError:
                await update.message.reply_text(
                    escape_markdown_v2("❌ ID должен быть числом."),
                    parse_mode=ParseMode.MARKDOWN_V2
                )
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
                        await update.message.reply_text(
                            escape_markdown_v2(f"✅ Группа {entity_id} добавлена."),
                            parse_mode=ParseMode.MARKDOWN_V2
                        )
                    else:
                        await update.message.reply_text(
                            escape_markdown_v2(f"⚠️ Группа {entity_id} уже есть в списке."),
                            parse_mode=ParseMode.MARKDOWN_V2
                        )
                else:
                    if entity_id not in users:
                        users.append(entity_id)
                        save_users(users)
                        await update.message.reply_text(
                            escape_markdown_v2(f"✅ Пользователь {entity_id} добавлен."),
                            parse_mode=ParseMode.MARKDOWN_V2
                        )
                    else:
                        await update.message.reply_text(
                            escape_markdown_v2(f"⚠️ Пользователь {entity_id} уже есть в списке."),
                            parse_mode=ParseMode.MARKDOWN_V2
                        )

            elif action == 'remove_group':
                groups = load_groups()
                if entity_id in groups:
                    groups.remove(entity_id)
                    save_groups(groups)
                    await update.message.reply_text(
                        escape_markdown_v2(f"🗑 Группа {entity_id} удалена из списка."),
                        parse_mode=ParseMode.MARKDOWN_V2
                    )
                else:
                    await update.message.reply_text(
                        escape_markdown_v2(f"⚠️ Группа {entity_id} не найдена в списке."),
                        parse_mode=ParseMode.MARKDOWN_V2
                    )

            elif action == 'remove_user':
                users = load_users()
                if entity_id in users:
                    users.remove(entity_id)
                    save_users(users)
                    await update.message.reply_text(
                        escape_markdown_v2(f"🗑 Пользователь {entity_id} удалён из списка."),
                        parse_mode=ParseMode.MARKDOWN_V2
                    )
                else:
                    await update.message.reply_text(
                        escape_markdown_v2(f"⚠️ Пользователь {entity_id} не найден в списке."),
                        parse_mode=ParseMode.MARKDOWN_V2
                    )
            await update.message.reply_text(
                escape_markdown_v2("✨ Меню:"),
                parse_mode=ParseMode.MARKDOWN_V2,
                reply_markup=get_inline_keyboard(user_id=user_id)
            )
            return

        # Обработка текста для рассылки
        content = escape_markdown_v2(text) if any(c in text for c in r'_*[]()~`>#+-=|{}.!,:') else text
        content_type = 'text'
    else:
        # Обработка медиа (фото, видео, стикеры, GIF)
        if update.message.photo:
            logger.info(f"Фото от пользователя {user_id}")
            content = update.message.photo[-1]  # Берем фото с наилучшим качеством
            content_type = 'photo'
        elif update.message.video:
            logger.info(f"Видео от пользователя {user_id}")
            content = update.message.video
            content_type = 'video'
        elif update.message.sticker:
            logger.info(f"Стикер от пользователя {user_id}")
            content = update.message.sticker
            content_type = 'sticker'
        elif update.message.animation:
            logger.info(f"GIF от пользователя {user_id}")
            content = update.message.animation
            content_type = 'animation'
        else:
            await update.message.reply_text(
                escape_markdown_v2("❌ Поддерживаются только текст, фото, видео, стикеры и GIF."),
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return

    # Рассылка контента в группы
    groups = load_groups()
    success_groups = 0
    groups_to_remove = []

    for group_id in groups:
        try:
            if content_type == 'text':
                await context.bot.send_message(chat_id=group_id, text=content, parse_mode=ParseMode.MARKDOWN_V2)
            elif content_type == 'photo':
                await context.bot.send_photo(chat_id=group_id, photo=content.file_id)
            elif content_type == 'video':
                await context.bot.send_video(chat_id=group_id, video=content.file_id)
            elif content_type == 'sticker':
                await context.bot.send_sticker(chat_id=group_id, sticker=content.file_id)
            elif content_type == 'animation':
                await context.bot.send_animation(chat_id=group_id, animation=content.file_id)
            success_groups += 1
            logger.info(f"Контент ({content_type}) отправлен в группу {group_id}")
            await asyncio.sleep(0.3)  # Защита от лимитов Telegram
        except telegram.error.Forbidden:
            logger.warning(f"Недостаточно прав для отправки в группу {group_id}")
            groups_to_remove.append(group_id)
        except telegram.error.BadRequest as e:
            if "chat not found" in str(e).lower():
                logger.warning(f"Группа {group_id} недоступна")
                groups_to_remove.append(group_id)
            else:
                logger.error(f"Ошибка отправки в группу {group_id}: {e}")
        except telegram.error.RetryAfter as e:
            logger.warning(f"Лимит Telegram API для группы {group_id}, ждём {e.retry_after} секунд")
            await asyncio.sleep(e.retry_after)
            try:
                if content_type == 'text':
                    await context.bot.send_message(chat_id=group_id, text=content, parse_mode=ParseMode.MARKDOWN_V2)
                elif content_type == 'photo':
                    await context.bot.send_photo(chat_id=group_id, photo=content.file_id)
                elif content_type == 'video':
                    await context.bot.send_video(chat_id=group_id, video=content.file_id)
                elif content_type == 'sticker':
                    await context.bot.send_sticker(chat_id=group_id, sticker=content.file_id)
                elif content_type == 'animation':
                    await context.bot.send_animation(chat_id=group_id, animation=content.file_id)
                success_groups += 1
            except Exception as retry_e:
                logger.error(f"Повторная ошибка отправки в группу {group_id}: {retry_e}")
        except telegram.error.NetworkError as e:
            logger.error(f"Сетевая ошибка при отправке в группу {group_id}: {e}")
        except Exception as e:
            logger.error(f"Неизвестная ошибка при отправке в группу {group_id}: {e}")

    if groups_to_remove:
        for group_id in groups_to_remove:
            groups.remove(group_id)
        save_groups(groups)

    response_text = f"✅ Сообщение отправлено в {success_groups} из {len(groups)} групп."
    await update.message.reply_text(
        escape_markdown_v2(response_text),
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=get_inline_keyboard(user_id=user_id)
    )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Глобальный обработчик ошибок."""
    logger.error(f"Ошибка: {context.error}", exc_info=context.error)
    if update and hasattr(update, 'message') and update.message:
        await update.message.reply_text(
            f'❌ *Ошибка\\:* `{escape_markdown_v2(str(context.error))}`',
            parse_mode=ParseMode.MARKDOWN_V2
        )
    if ADMIN_ID:
        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f'❌ *Ошибка бота\\:* `{escape_markdown_v2(str(context.error))}`',
                parse_mode=ParseMode.MARKDOWN_V2
            )
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление об ошибке администратору: {e}")

async def webhook_handler(request, application):
    """Обработчик Webhook-запросов."""
    try:
        data = await request.json()
        logger.info(f"Received webhook update: {data}")
        update = Update.de_json(data, application.bot)
        if update:
            await application.process_update(update)
        return web.Response(status=200)
    except Exception as e:
        logger.error(f"Ошибка обработки Webhook: {e}", exc_info=e)
        return web.Response(status=500)

async def main():
    """Запуск бота."""
    try:
        logger.info(f"Starting bot with Python {sys.version}, python-telegram-bot {telegram.__version__}")
        application = Application.builder().token(TOKEN).build()
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CallbackQueryHandler(button_callback))
        application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_text))
        application.add_error_handler(error_handler)
        await application.initialize()

        # Настройка Webhook
        webhook_url = os.getenv("WEBHOOK_URL")
        if not webhook_url:
            hostname = os.getenv("RENDER_EXTERNAL_HOSTNAME")
            if not hostname:
                raise ValueError("WEBHOOK_URL or RENDER_EXTERNAL_HOSTNAME must be set")
            webhook_url = f"https://{hostname}/webhook"
        logger.info(f"Setting webhook: {webhook_url}")
        await application.bot.set_webhook(url=webhook_url)

        # Запуск HTTP-сервера
        app = web.Application()
        app.router.add_post('/webhook', lambda request: webhook_handler(request, application))
        runner = web.AppRunner(app)
        await runner.setup()
        port = int(os.getenv("PORT", 10000))
        site = web.TCPSite(runner, '0.0.0.0', port)
        await site.start()
        logger.info(f"HTTP server started on port {port}")

        await application.start()
        # Бесконечный цикл для удержания процесса
        while True:
            await asyncio.sleep(3600)
    except Exception as e:
        logger.error(f"Ошибка инициализации бота: {e}", exc_info=e)
        if ADMIN_ID:
            try:
                bot = telegram.Bot(token=TOKEN)
                await bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f'❌ *Бот не запустился\\:* `{escape_markdown_v2(str(e))}`',
                    parse_mode=ParseMode.MARKDOWN_V2
                )
            except Exception as notify_error:
                logger.error(f"Не удалось отправить уведомление об ошибке администратору: {notify_error}")
        raise
    finally:
        if 'application' in locals():
            await application.stop()
            await application.shutdown()
        if 'runner' in locals():
            await runner.cleanup()

if __name__ == '__main__':
    asyncio.run(main())

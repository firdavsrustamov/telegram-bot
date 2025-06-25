import logging
import json
import os
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.error import Forbidden, BadRequest  # Добавлено для обработки ошибок доступа
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
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


def load_groups():
    """Загрузка списка ID групп из файла."""
    if os.path.exists(GROUPS_FILE):
        with open(GROUPS_FILE, 'r') as f:
            return json.load(f)
    return []


def save_groups(groups):
    """Сохранение списка ID групп в файл."""
    with open(GROUPS_FILE, 'w') as f:
        json.dump(groups, f)


def load_users():
    """Загрузка списка ID пользователей из файла."""
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r') as f:
            return json.load(f)
    return []


def save_users(users):
    """Сохранение списка ID пользователей в файл."""
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
    # Добавляем административные кнопки только для администратора
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
    """Обработчик команды /start – приветствие и вывод меню (только в личных сообщениях с ботом)."""
    if not update.message or update.message.chat.type != 'private':
        return  # Игнорируем команду /start, если она не в личном чате
    user = update.message.from_user
    welcome_text = (
        f"*Привет, {user.first_name}!* 🎉\n\n"
        "Я бот для рассылки сообщений в группы Telegram. Просто отправь мне текст, и я разошлю его по всем подключенным группам и пользователям.\n\n"
        "*Меню:* Вы можете посмотреть список групп или пользователей, а администратор – управлять ими."
    )
    # Приветственное сообщение с меню действий
    await update.message.reply_text(welcome_text, parse_mode='Markdown',
                                    reply_markup=get_inline_keyboard(user_id=user.id))
    # Отдельно выводим основное меню с кнопкой
    await update.message.reply_text('🔽 *Главное меню*:', parse_mode='Markdown', reply_markup=get_main_menu())


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий инлайн-кнопок меню."""
    if update.callback_query.message.chat.type != 'private':
        return  # Обрабатываем только нажатия в личном чате с ботом
    query = update.callback_query
    await query.answer()  # Подтверждаем нажатие без отправки уведомления

    user_id = query.from_user.id
    data = query.data

    if data == 'list_groups':
        groups = load_groups()
        if groups:
            # Выводим список сохранённых ID групп
            group_list = '\n'.join(f'🔹 {gid}' for gid in groups)
            await query.message.reply_text(f'📋 *Список групп*:\n{group_list}', parse_mode='Markdown')
        else:
            await query.message.reply_text('📭 *Список групп пуст.*', parse_mode='Markdown')

    elif data == 'list_users':
        users = load_users()
        if users:
            # Выводим список сохранённых ID пользователей
            user_list = '\n'.join(f'🔹 {uid}' for uid in users)
            await query.message.reply_text(f'👥 *Список пользователей*:\n{user_list}', parse_mode='Markdown')
        else:
            await query.message.reply_text('📭 *Список пользователей пуст.*', parse_mode='Markdown')

    elif data == 'add_entity':
        # Только администратор может добавлять
        if user_id != ADMIN_ID:
            await query.message.reply_text('🚫 *Только администратор может выполнять эту команду.*',
                                           parse_mode='Markdown')
            return
        # Спрашиваем, что добавить, и устанавливаем флаг ожидания ввода ID
        await query.message.reply_text(
            '➕ *Что добавить?*\n1️⃣ ID группы (отрицательное число)\n2️⃣ ID пользователя (положительное число)',
            parse_mode='Markdown')
        context.user_data['awaiting_entity_id'] = 'add'

    elif data == 'remove_group':
        if user_id != ADMIN_ID:
            await query.message.reply_text('🚫 *Только администратор может выполнять эту команду.*',
                                           parse_mode='Markdown')
            return
        await query.message.reply_text('🗑 *Введите ID группы для удаления*:', parse_mode='Markdown')
        context.user_data['awaiting_entity_id'] = 'remove_group'

    elif data == 'remove_user':
        if user_id != ADMIN_ID:
            await query.message.reply_text('🚫 *Только администратор может выполнять эту команду.*',
                                           parse_mode='Markdown')
            return
        await query.message.reply_text('🗑 *Введите ID пользователя для удаления*:', parse_mode='Markdown')
        context.user_data['awaiting_entity_id'] = 'remove_user'

    elif data == 'refresh_menu':
        # Обновляем меню (пересылаем клавиатуру заново, учитывая статус пользователя)
        await query.message.reply_text('🔄 *Меню обновлено*:', parse_mode='Markdown',
                                       reply_markup=get_inline_keyboard(user_id=user_id))


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик обычных текстовых сообщений (в личке с ботом).
    - Если ожидается ввод ID для добавления/удаления, обрабатывает его.
    - Иначе воспринимает сообщение как текст для рассылки.
    """
    if not update.message or update.message.chat.type != 'private':
        return  # Работаем только с сообщениями в личном чате с ботом

    user_id = update.message.from_user.id
    text = update.message.text

    # Если пользователь нажал кнопку "Показать меню"
    if text == '✨ Показать меню':
        await update.message.reply_text('✨ *Меню*:', parse_mode='Markdown',
                                        reply_markup=get_inline_keyboard(user_id=user_id))
        return

    # Если бот ожидает ввод ID (добавление или удаление)
    if context.user_data.get('awaiting_entity_id'):
        # Проверяем права администратора
        if user_id != ADMIN_ID:
            await update.message.reply_text('🚫 *Только администратор может выполнять эту команду.*',
                                            parse_mode='Markdown')
            context.user_data.clear()
            return
        try:
            entity_id = int(text.strip())
        except ValueError:
            await update.message.reply_text('❌ *ID должен быть числом.*', parse_mode='Markdown')
            return

        action = context.user_data.get('awaiting_entity_id')
        context.user_data.clear()  # Сбрасываем флаг ожидания ввода
        if action == 'add':
            # Добавление группы или пользователя
            groups = load_groups()
            users = load_users()
            if entity_id < 0:
                # Отрицательное значение — группа
                if entity_id not in groups:
                    groups.append(entity_id)
                    save_groups(groups)
                    await update.message.reply_text(f'✅ *Группа {entity_id} добавлена.*', parse_mode='Markdown')
                else:
                    await update.message.reply_text(f'⚠️ *Группа {entity_id} уже есть в списке.*',
                                                    parse_mode='Markdown')
            else:
                # Положительное значение — пользователь
                if entity_id not in users:
                    users.append(entity_id)
                    save_users(users)
                    await update.message.reply_text(f'✅ *Пользователь {entity_id} добавлен.*', parse_mode='Markdown')
                else:
                    await update.message.reply_text(f'⚠️ *Пользователь {entity_id} уже есть в списке.*',
                                                    parse_mode='Markdown')

        elif action == 'remove_group':
            groups = load_groups()
            if entity_id in groups:
                groups.remove(entity_id)
                save_groups(groups)
                await update.message.reply_text(f'🗑 *Группа {entity_id} удалена из списка.*', parse_mode='Markdown')
            else:
                await update.message.reply_text(f'⚠️ *Группа {entity_id} не найдена в списке.*', parse_mode='Markdown')

        elif action == 'remove_user':
            users = load_users()
            if entity_id in users:
                users.remove(entity_id)
                save_users(users)
                await update.message.reply_text(f'🗑 *Пользователь {entity_id} удалён из списка.*',
                                                parse_mode='Markdown')
            else:
                await update.message.reply_text(f'⚠️ *Пользователь {entity_id} не найден в списке.*',
                                                parse_mode='Markdown')

        # После операции добавляем обратно основное меню
        await update.message.reply_text('✨ *Меню*:', parse_mode='Markdown',
                                        reply_markup=get_inline_keyboard(user_id=user_id))
        return

    # Если дошли сюда, значит это обычный текст для рассылки.
    # Проверяем, имеет ли пользователь право рассылать сообщения через бота.
    if user_id != ADMIN_ID:
        authorized_users = load_users()
        if user_id not in authorized_users:
            # Если не админ и не в списке разрешённых пользователей
            await update.message.reply_text('🚫 *У вас нет прав на отправку рассылки.*', parse_mode='Markdown')
            return

    message_text = text  # Текст сообщения для рассылки
    groups = load_groups()
    users = load_users()
    success_groups = 0
    success_users = 0
    removed_groups = []
    removed_users = []

    # Рассылка по группам
    for group_id in list(groups):
        try:
            await context.bot.send_message(chat_id=group_id, text=message_text, parse_mode='Markdown')
            success_groups += 1
            logger.info(f"Сообщение успешно отправлено в группу {group_id}")
        except Forbidden as e:
            # Бот не имеет прав отправить сообщение (удалён из группы или заблокирован)
            logger.warning(f"Недостаточно прав для отправки в {group_id}: {e}")
            removed_groups.append(group_id)
            groups.remove(group_id)
            save_groups(groups)
        except BadRequest as e:
            # Неверный запрос (например, неправильный chat_id)
            if "chat not found" in str(e):
                logger.warning(f"Группа {group_id} недоступна (не найдена): {e}")
                removed_groups.append(group_id)
                groups.remove(group_id)
                save_groups(groups)
            else:
                # Другие ошибки BadRequest (например, ошибка разметки Markdown)
                logger.error(f"Ошибка при отправке в группу {group_id}: {e}")

        except Exception as e:
            logger.error(f"Неизвестная ошибка при отправке в группу {group_id}: {e}")

    # Рассылка по пользователям
    for user in list(users):
        try:
            await context.bot.send_message(chat_id=user, text=message_text, parse_mode='Markdown')
            success_users += 1
            logger.info(f"Сообщение успешно отправлено пользователю {user}")
        except Forbidden as e:
            # Бот не может отправить сообщение пользователю (возможно, бот заблокирован)
            logger.warning(f"Не удалось отправить пользователю {user}: {e}")
            removed_users.append(user)
            users.remove(user)
            save_users(users)
        except BadRequest as e:
            if "chat not found" in str(e):
                logger.warning(f"Пользователь {user} недоступен (не найден): {e}")
                removed_users.append(user)
                users.remove(user)
                save_users(users)
            else:
                logger.error(f"Ошибка при отправке пользователю {user}: {e}")
        except Exception as e:
            logger.error(f"Неизвестная ошибка при отправке пользователю {user}: {e}")

    # Формируем ответ администратору о результатах рассылки
    total_groups = len(groups)
    total_users = len(users)
    response_lines = []
    response_lines.append(f'✅ *Сообщение отправлено в {success_groups} из {total_groups} групп*.')
    response_lines.append(
        f'✅ *Сообщение отправлено {success_users} из {total_users} пользователей*.')  # статистика по пользователям

    # Уведомляем, если какие-то группы/пользователи были автоматически удалены
    if removed_groups or removed_users:
        removed_info = ""
        if removed_groups:
            removed_info += "\n🗑 *Удалённые группы:* " + ", ".join(str(g) for g in removed_groups)
        if removed_users:
            removed_info += "\n🗑 *Удалённые пользователи:* " + ", ".join(str(u) for u in removed_users)
        response_lines.append(removed_info)

    # Отправляем сводное сообщение о рассылке
    await update.message.reply_text("\n".join(response_lines), parse_mode='Markdown',
                                    reply_markup=get_inline_keyboard(user_id=user_id))


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Глобальный обработчик ошибок, чтобы логировать их и уведомлять администратора."""
    logger.error(f"Update {update} вызвал ошибку: {context.error}")
    try:
        # Отправляем информацию об ошибке в чат администратору (если случилось в контексте сообщения)
        if update and hasattr(update, 'message') and update.message:
            await update.message.reply_text(f'❌ *Ошибка:* `{context.error}`', parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Не удалось отправить сообщение об ошибке: {e}")


def main():
    """Запуск бота и настройка обработчиков команд и сообщений."""
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_error_handler(error_handler)

    # Запуск бота (доводчик)
    application.run_polling()


if __name__ == '__main__':
    main()

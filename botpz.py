import sqlite3
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import random
import urllib.parse
from typing import Dict, List, Set
import re

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('bot_database.db', check_same_thread=False)
    cursor = conn.cursor()
    
    # Таблица для исходных сообщений
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS original_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            original_text TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица для вариаций сообщений
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS message_variations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            original_message_id INTEGER NOT NULL,
            variation_text TEXT NOT NULL,
            send_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (original_message_id) REFERENCES original_messages (id)
        )
    ''')
    
    # Таблица для чатов и пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            chat_name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chat_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            FOREIGN KEY (chat_id) REFERENCES user_chats (id)
        )
    ''')
    
    conn.commit()
    conn.close()

init_db()

# Словарь для отслеживания состояний пользователей
user_states = {}

# Эмодзи для красивого оформления
EMOJI = {
    "welcome": "👋",
    "messages": "📝",
    "users": "👥",
    "spam": "🚀",
    "create": "✨",
    "delete": "🗑️",
    "add": "➕",
    "back": "🔙",
    "home": "🏠",
    "success": "✅",
    "error": "❌",
    "warning": "⚠️",
    "info": "ℹ️",
    "chat": "💬",
    "user": "👤",
    "stats": "📊",
    "random": "🎲",
    "link": "🔗",
    "next": "➡️",
    "prev": "⬅️"
}

# Функции для работы с базой данных
def get_db_connection():
    return sqlite3.connect('bot_database.db', check_same_thread=False)

def add_original_message(user_id: int, text: str) -> int:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO original_messages (user_id, original_text) VALUES (?, ?)', (user_id, text))
    message_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return message_id

def add_message_variation(user_id: int, original_message_id: int, variation_text: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO message_variations (user_id, original_message_id, variation_text) 
            VALUES (?, ?, ?)
        ''', (user_id, original_message_id, variation_text))
        conn.commit()
    except sqlite3.IntegrityError as e:
        logger.warning(f"Duplicate variation skipped: {e}")
    except Exception as e:
        logger.error(f"Error adding variation: {e}")
    finally:
        conn.close()

def get_user_original_messages(user_id: int) -> List[tuple]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, original_text FROM original_messages WHERE user_id = ? ORDER BY created_at DESC', (user_id,))
    messages = cursor.fetchall()
    conn.close()
    return messages

def delete_message_variations(user_id: int, original_message_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM message_variations WHERE user_id = ? AND original_message_id = ?', 
                   (user_id, original_message_id))
    cursor.execute('DELETE FROM original_messages WHERE id = ? AND user_id = ?', 
                   (original_message_id, user_id))
    conn.commit()
    conn.close()

def get_random_variation(user_id: int) -> tuple:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, variation_text, send_count 
        FROM message_variations 
        WHERE user_id = ? AND send_count < 5 
        ORDER BY RANDOM() 
        LIMIT 1
    ''', (user_id,))
    variation = cursor.fetchone()
    conn.close()
    return variation

def increment_send_count(variation_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE message_variations SET send_count = send_count + 1 WHERE id = ?', (variation_id,))
    conn.commit()
    conn.close()

def delete_used_variation(variation_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM message_variations WHERE id = ?', (variation_id,))
    conn.commit()
    conn.close()

def add_user_chat(user_id: int, chat_name: str) -> int:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO user_chats (user_id, chat_name) VALUES (?, ?)', (user_id, chat_name))
    chat_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return chat_id

def add_chat_users(chat_id: int, usernames: List[str]):
    conn = get_db_connection()
    cursor = conn.cursor()
    for username in usernames:
        cursor.execute('INSERT INTO chat_users (chat_id, username) VALUES (?, ?)', (chat_id, username))
    conn.commit()
    conn.close()

def get_user_chats(user_id: int) -> List[tuple]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, chat_name FROM user_chats WHERE user_id = ? ORDER BY created_at DESC', (user_id,))
    chats = cursor.fetchall()
    conn.close()
    return chats

def get_chat_users(chat_id: int) -> List[str]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT username FROM chat_users WHERE chat_id = ?', (chat_id,))
    users = [row[0] for row in cursor.fetchall()]
    conn.close()
    return users

def delete_user_chat(user_id: int, chat_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM chat_users WHERE chat_id = ?', (chat_id,))
    cursor.execute('DELETE FROM user_chats WHERE id = ? AND user_id = ?', (chat_id, user_id))
    conn.commit()
    conn.close()

def get_user_stats(user_id: int) -> dict:
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Количество исходных сообщений
    cursor.execute('SELECT COUNT(*) FROM original_messages WHERE user_id = ?', (user_id,))
    original_count = cursor.fetchone()[0]
    
    # Количество вариаций
    cursor.execute('SELECT COUNT(*) FROM message_variations WHERE user_id = ?', (user_id,))
    variations_count = cursor.fetchone()[0]
    
    # Количество доступных вариаций (send_count < 5)
    cursor.execute('SELECT COUNT(*) FROM message_variations WHERE user_id = ? AND send_count < 5', (user_id,))
    available_count = cursor.fetchone()[0]
    
    # Количество чатов
    cursor.execute('SELECT COUNT(*) FROM user_chats WHERE user_id = ?', (user_id,))
    chats_count = cursor.fetchone()[0]
    
    conn.close()
    
    return {
        'original_messages': original_count,
        'total_variations': variations_count,
        'available_variations': available_count,
        'chats': chats_count
    }

# Функция для диагностики проблем пользователя
def diagnose_user_issues(user_id: int) -> str:
    """Диагностика проблем пользователя для раздела спама"""
    issues = []
    
    # Проверяем чаты
    chats = get_user_chats(user_id)
    if not chats:
        issues.append("❌ Нет сохраненных чатов")
    else:
        issues.append(f"✅ Чатов: {len(chats)}")
        
        # Проверяем пользователей в чатах
        total_users = 0
        for chat_id, chat_name in chats:
            users = get_chat_users(chat_id)
            total_users += len(users)
            if len(users) == 0:
                issues.append(f"❌ В чате '{chat_name}' нет пользователей")
        
        issues.append(f"✅ Всего пользователей: {total_users}")
    
    # Проверяем вариации
    stats = get_user_stats(user_id)
    if stats['available_variations'] == 0:
        issues.append("❌ Нет доступных вариаций для отправки")
    else:
        issues.append(f"✅ Доступных вариаций: {stats['available_variations']}")
    
    if stats['total_variations'] == 0:
        issues.append("❌ Нет созданных вариаций")
    else:
        issues.append(f"✅ Всего вариаций: {stats['total_variations']}")
    
    return "\n".join(issues)

# УЛУЧШЕННАЯ функция для генерации вариаций
def generate_variations(text: str, count: int = 500) -> List[str]:
    """
    Генерирует уникальные вариации сообщения путем замены кириллических букв на латинские
    """
    logger.info(f"Generating variations for text: {text}")
    
    # Карта замен: кириллическая -> возможные латинские замены
    char_map = {
        'а': ['a', 'а'],  # латинская a, кириллическая а
        'с': ['c', 'с'],  # латинская c, кириллическая с
        'о': ['o', 'о'],  # латинская o, кириллическая о
        'р': ['p', 'р'],  # латинская p, кириллическая р
        'е': ['e', 'е'],  # латинская e, кириллическая е
        'х': ['x', 'х'],  # латинская x, кириллическая х
        'у': ['y', 'у'],  # латинская y, кириллическая у
        'А': ['A', 'А'],
        'С': ['C', 'С'],
        'О': ['O', 'О'],
        'Р': ['P', 'Р'],
        'Е': ['E', 'Е'],
        'Х': ['X', 'Х'],
        'У': ['Y', 'У']
    }
    
    variations = set()
    variations.add(text)  # Всегда добавляем оригинальный текст
    
    # Находим позиции букв, которые можно заменять
    replaceable_chars = []
    for char in text:
        if char in char_map:
            replaceable_chars.append(char)
    
    logger.info(f"Replaceable characters found: {len(replaceable_chars)}")
    
    if not replaceable_chars:
        logger.info("No replaceable characters found, returning original text")
        return [text] * count
    
    # Генерируем вариации
    max_attempts = count * 3
    attempts = 0
    
    while len(variations) < count and attempts < max_attempts:
        attempts += 1
        new_variation = []
        
        for char in text:
            if char in char_map and random.random() > 0.3:  # 70% шанс замены
                new_char = random.choice(char_map[char])
                new_variation.append(new_char)
            else:
                new_variation.append(char)
        
        variation_str = ''.join(new_variation)
        variations.add(variation_str)
    
    # Если не набрали достаточно вариаций, создаем дополнительные
    if len(variations) < count:
        base_variations = list(variations)
        needed = count - len(variations)
        
        for i in range(needed):
            # Берем случайную вариацию и немного модифицируем
            base = random.choice(base_variations)
            new_variation = []
            
            for char in base:
                if char in char_map and random.random() > 0.8:  # 20% шанс замены
                    new_char = random.choice(char_map[char])
                    new_variation.append(new_char)
                else:
                    new_variation.append(char)
            
            variation_str = ''.join(new_variation)
            variations.add(variation_str)
    
    result = list(variations)[:count]
    logger.info(f"Generated {len(result)} variations")
    return result

def generate_telegram_link(text: str) -> str:
    encoded_text = urllib.parse.quote(text)
    return f"https://t.me/PoizonRik?text={encoded_text}"

# Красивые функции оформления сообщений
def format_welcome_message(user_id: int = None) -> str:
    stats = get_user_stats(user_id) if user_id else None
    if stats:
        stats_text = f"""
*Ваша статистика:*
• Сообщений: {stats['original_messages']}
• Вариаций: {stats['total_variations']} 
• Доступно: {stats['available_variations']}
• Чатов: {stats['chats']}
"""
    else:
        stats_text = ""
    
    message = f"""
{EMOJI['welcome']} *Добро пожаловать в MessageVariator Bot!* {EMOJI['welcome']}

*Возможности бота:*
{EMOJI['messages']} Создание уникальных вариаций сообщений
{EMOJI['users']} Управление списками пользователей  
{EMOJI['spam']} Умная рассылка с ограничениями

{stats_text}
*Чтобы начать, выберите раздел ниже:*
    """
    return message.strip()

def format_messages_menu(user_id: int) -> str:
    stats = get_user_stats(user_id)
    return f"""
{EMOJI['messages']} *РАЗДЕЛ: СОЗДАНИЕ СООБЩЕНИЙ*

*Ваша статистика:*
• Исходных сообщений: {stats['original_messages']}
• Всего вариаций: {stats['total_variations']}
• Доступно для отправки: {stats['available_variations']}
    """.strip()

def format_users_menu(user_id: int) -> str:
    stats = get_user_stats(user_id)
    return f"""
{EMOJI['users']} *РАЗДЕЛ: МОИ ПОЛЬЗОВАТЕЛИ*

*Статистика:*
• Сохраненных чатов: {stats['chats']}
    """.strip()

def format_spam_menu(user_id: int) -> str:
    stats = get_user_stats(user_id)
    return f"""
{EMOJI['spam']} *РАЗДЕЛ: НАЧАТЬ РАССЫЛКУ*

*Готово к рассылке:*
• Доступных чатов: {stats['chats']}
• Доступных вариаций: {stats['available_variations']}
    """.strip()

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    keyboard = [
        [InlineKeyboardButton(f"{EMOJI['messages']} Создание сообщений", callback_data="create_messages")],
        [InlineKeyboardButton(f"{EMOJI['users']} Мои пользователи", callback_data="my_users")],
        [InlineKeyboardButton(f"{EMOJI['spam']} Начать рассылку", callback_data="start_spam")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.message:
        await update.message.reply_text(
            format_welcome_message(user_id), 
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    else:
        await update.callback_query.edit_message_text(
            format_welcome_message(user_id),
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

# Обработчики callback запросов
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    logger.info(f"User {user_id} pressed button: {data}")
    
    if data == "main_menu":
        await start(update, context)
    
    elif data == "create_messages":
        keyboard = [
            [InlineKeyboardButton(f"{EMOJI['create']} Создать новое сообщение", callback_data="create_new_message")],
            [InlineKeyboardButton(f"{EMOJI['delete']} Удалить сообщение", callback_data="delete_message")],
            [InlineKeyboardButton(f"{EMOJI['stats']} Статистика", callback_data="show_stats")],
            [InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            format_messages_menu(user_id),
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    elif data == "show_stats":
        stats = get_user_stats(user_id)
        stats_text = f"""
{EMOJI['stats']} *ВАША СТАТИСТИКА*

{EMOJI['messages']} *Сообщения:*
• Исходных сообщений: {stats['original_messages']}
• Всего вариаций: {stats['total_variations']}
• Доступно для отправки: {stats['available_variations']}

{EMOJI['users']} *Пользователи:*
• Чатов: {stats['chats']}
        """.strip()
        
        keyboard = [
            [InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data="create_messages")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            stats_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    elif data == "create_new_message":
        user_states[user_id] = "waiting_for_message"
        await query.edit_message_text(
            f"{EMOJI['create']} *СОЗДАНИЕ НОВОГО СООБЩЕНИЯ*\n\n"
            "Введите исходное сообщение для создания 500 уникальных вариаций.\n\n"
            f"{EMOJI['info']} *Бот заменит буквы:* а,с,о,р,е,х,у на латинские аналоги\n\n"
            f"{EMOJI['warning']} *Сообщение должно содержать хотя бы одну из этих букв!*",
            parse_mode='Markdown'
        )
    
    elif data == "delete_message":
        messages = get_user_original_messages(user_id)
        if not messages:
            keyboard = [
                [InlineKeyboardButton(f"{EMOJI['create']} Создать сообщение", callback_data="create_new_message")],
                [InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data="create_messages")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                f"{EMOJI['warning']} У вас нет сохраненных сообщений.",
                reply_markup=reply_markup
            )
            return
        
        keyboard = []
        for msg_id, msg_text in messages:
            button_text = f"{EMOJI['delete']} {msg_text[:25]}..." if len(msg_text) > 25 else f"{EMOJI['delete']} {msg_text}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"delete_msg_{msg_id}")])
        
        keyboard.append([InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data="create_messages")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"{EMOJI['delete']} *ВЫБЕРИТЕ СООБЩЕНИЕ ДЛЯ УДАЛЕНИЯ*\n\n"
            f"{EMOJI['warning']} Будет удалено исходное сообщение и ВСЕ его вариации!",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    elif data.startswith("delete_msg_"):
        msg_id = int(data.split("_")[2])
        delete_message_variations(user_id, msg_id)
        
        keyboard = [
            [InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data="create_messages")],
            [InlineKeyboardButton(f"{EMOJI['home']} Главное меню", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"{EMOJI['success']} Сообщение и все его вариации успешно удалены!",
            reply_markup=reply_markup
        )
    
    elif data == "my_users":
        keyboard = [
            [InlineKeyboardButton(f"{EMOJI['add']} Добавить пользователей", callback_data="add_users")],
            [InlineKeyboardButton(f"{EMOJI['delete']} Удалить список пользователей", callback_data="delete_chat_list")],
            [InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            format_users_menu(user_id),
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    elif data == "add_users":
        user_states[user_id] = "waiting_for_chat_name"
        await query.edit_message_text(
            f"{EMOJI['add']} *ДОБАВЛЕНИЕ ПОЛЬЗОВАТЕЛЕЙ*\n\n"
            "Напишите название чата, из которого взяли пользователей:",
            parse_mode='Markdown'
        )
    
    elif data == "delete_chat_list":
        chats = get_user_chats(user_id)
        if not chats:
            keyboard = [
                [InlineKeyboardButton(f"{EMOJI['add']} Добавить чат", callback_data="add_users")],
                [InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data="my_users")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                f"{EMOJI['warning']} У вас нет сохраненных чатов.",
                reply_markup=reply_markup
            )
            return
        
        keyboard = []
        for chat_id, chat_name in chats:
            keyboard.append([InlineKeyboardButton(f"{EMOJI['delete']} {chat_name}", callback_data=f"delete_chat_{chat_id}")])
        
        keyboard.append([InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data="my_users")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"{EMOJI['delete']} *ВЫБЕРИТЕ ЧАТ ДЛЯ УДАЛЕНИЯ*\n\n"
            f"{EMOJI['warning']} Будет удален чат и ВСЕ его пользователи!",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    elif data.startswith("delete_chat_"):
        chat_id = int(data.split("_")[2])
        delete_user_chat(user_id, chat_id)
        
        keyboard = [
            [InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data="my_users")],
            [InlineKeyboardButton(f"{EMOJI['home']} Главное меню", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"{EMOJI['success']} Чат и все его пользователи успешно удалены!",
            reply_markup=reply_markup
        )
    
    elif data == "start_spam":
        logger.info(f"User {user_id} accessing start_spam section")
        
        # ДИАГНОСТИКА: Проверяем данные пользователя
        chats = get_user_chats(user_id)
        stats = get_user_stats(user_id)
        
        logger.info(f"User {user_id} stats: {stats}")
        logger.info(f"User {user_id} chats: {chats}")
        
        if not chats:
            # Добавляем кнопку диагностики
            keyboard = [
                [InlineKeyboardButton(f"{EMOJI['add']} Добавить чат", callback_data="add_users")],
                [InlineKeyboardButton(f"🔍 Диагностика проблемы", callback_data="diagnose_issues")],
                [InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                f"{EMOJI['warning']} *НЕТ ДОСТУПНЫХ ЧАТОВ*\n\n"
                "У вас нет сохраненных чатов для рассылки.\n\n"
                "Сначала добавьте чаты в разделе 'Мои пользователи'.",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            return
        
        if stats['available_variations'] == 0:
            # Добавляем кнопку диагностики
            keyboard = [
                [InlineKeyboardButton(f"{EMOJI['create']} Создать сообщения", callback_data="create_new_message")],
                [InlineKeyboardButton(f"🔍 Диагностика проблемы", callback_data="diagnose_issues")],
                [InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                f"{EMOJI['warning']} *НЕТ ДОСТУПНЫХ ВАРИАЦИЙ*\n\n"
                "Нет доступных вариаций для отправки.\n\n"
                "Сначала создайте сообщения в соответствующем разделе.",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            return
        
        # ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ - показываем чаты
        keyboard = []
        for chat_id, chat_name in chats:
            # Проверяем, есть ли пользователи в чате
            users_count = len(get_chat_users(chat_id))
            button_text = f"{EMOJI['chat']} {chat_name} ({users_count} users)"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"select_chat_{chat_id}_page_0")])
        
        # Добавляем кнопку диагностики
        keyboard.append([InlineKeyboardButton(f"🔍 Диагностика", callback_data="diagnose_issues")])
        keyboard.append([InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data="main_menu")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            format_spam_menu(user_id),
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    elif data == "diagnose_issues":
        """Диагностика проблем пользователя"""
        diagnosis = diagnose_user_issues(user_id)
        
        keyboard = [
            [InlineKeyboardButton(f"{EMOJI['create']} Создать сообщения", callback_data="create_new_message")],
            [InlineKeyboardButton(f"{EMOJI['add']} Добавить чат", callback_data="add_users")],
            [InlineKeyboardButton(f"{EMOJI['spam']} Попробовать снова", callback_data="start_spam")],
            [InlineKeyboardButton(f"{EMOJI['home']} Главное меню", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"🔍 *ДИАГНОСТИКА ПРОБЛЕМ*\n\n"
            f"*Статус для пользователя {user_id}:*\n\n"
            f"{diagnosis}\n\n"
            f"*Рекомендации:*\n"
            f"1. Добавьте чаты с пользователями\n"
            f"2. Создайте сообщения с вариациями\n"
            f"3. Убедитесь, что в чатах есть пользователи",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    elif data.startswith("select_chat_"):
        parts = data.split("_")
        chat_id = int(parts[2])
        page = int(parts[4])
        
        users = get_chat_users(chat_id)
        if not users:
            await query.edit_message_text(f"{EMOJI['warning']} В этом чате нет пользователей.")
            return
        
        # Пагинация
        users_per_page = 25
        start_idx = page * users_per_page
        end_idx = start_idx + users_per_page
        page_users = users[start_idx:end_idx]
        
        # Получаем информацию о чате
        chats = get_user_chats(user_id)
        chat_name = next((name for cid, name in chats if cid == chat_id), "Неизвестный чат")
        
        keyboard = []
        sent_count = 0
        
        for username in page_users:
            variation = get_random_variation(user_id)
            if variation:
                var_id, var_text, send_count = variation
                link = generate_telegram_link(var_text)
                
                # Создаем кнопку с ссылкой
                button_text = f"{EMOJI['user']} {username}"
                keyboard.append([InlineKeyboardButton(button_text, url=link)])
                
                # Обновляем счетчик отправок
                increment_send_count(var_id)
                if send_count + 1 >= 5:
                    delete_used_variation(var_id)
                
                sent_count += 1
        
        # Кнопки навигации
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton(
                f"{EMOJI['prev']} Назад", 
                callback_data=f"select_chat_{chat_id}_page_{page-1}"
            ))
        
        if end_idx < len(users):
            nav_buttons.append(InlineKeyboardButton(
                f"Вперед {EMOJI['next']}", 
                callback_data=f"select_chat_{chat_id}_page_{page+1}"
            ))
        
        if nav_buttons:
            keyboard.append(nav_buttons)
        
        keyboard.append([InlineKeyboardButton(f"{EMOJI['back']} Назад к чатам", callback_data="start_spam")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        page_info = f"""
{EMOJI['chat']} *ЧАТ: {chat_name}*
{EMOJI['user']} *Пользователи: {start_idx + 1}-{min(end_idx, len(users))} из {len(users)}*
{EMOJI['link']} *Создано ссылок: {sent_count}*

*Инструкция:*
Нажмите на кнопку с пользователем, чтобы отправить сообщение
        """.strip()
        
        await query.edit_message_text(
            page_info,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

# Обработчик текстовых сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    if user_id not in user_states:
        await update.message.reply_text(
            f"{EMOJI['info']} Используйте меню для взаимодействия с ботом.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(f"{EMOJI['home']} Открыть меню", callback_data="main_menu")]
            ])
        )
        return
    
    state = user_states[user_id]
    
    if state == "waiting_for_message":
        # Генерация вариаций
        try:
            if not text:
                await update.message.reply_text(f"{EMOJI['error']} Сообщение не может быть пустым!")
                return
            
            await update.message.reply_text(f"{EMOJI['create']} Генерирую 500 вариаций... Это может занять несколько секунд.")
            
            # Генерируем вариации
            variations = generate_variations(text, 500)
            
            # Сохраняем оригинальное сообщение
            original_msg_id = add_original_message(user_id, text)
            
            # Сохраняем вариации
            added_count = 0
            for variation in variations:
                add_message_variation(user_id, original_msg_id, variation)
                added_count += 1
            
            # Очищаем состояние
            del user_states[user_id]
            
            keyboard = [
                [InlineKeyboardButton(f"{EMOJI['create']} Создать еще", callback_data="create_new_message")],
                [InlineKeyboardButton(f"{EMOJI['home']} Главное меню", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"{EMOJI['success']} *УСПЕШНО СОЗДАНО!*\n\n"
                f"• Исходное сообщение: '{text[:50]}...'\n"
                f"• Добавлено вариаций: {added_count}\n"
                f"• Всего доступно: {get_user_stats(user_id)['available_variations']}",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Error in message generation: {e}", exc_info=True)
            del user_states[user_id]
            
            await update.message.reply_text(
                f"{EMOJI['error']} *ОШИБКА!*\n\n"
                f"Произошла ошибка при создании вариаций: {str(e)}\n\n"
                "Попробуйте другое сообщение или обратитесь к разработчику.",
                parse_mode='Markdown'
            )
    
    elif state == "waiting_for_chat_name":
        context.user_data['temp_chat_name'] = text
        user_states[user_id] = "waiting_for_users"
        
        example_text = """user1
user2
user3"""
        
        await update.message.reply_text(
            f"{EMOJI['add']} *ЧАТ СОХРАНЕН!*\n\n"
            f"Теперь отправьте список пользователей:\n\n"
            f"*Пример:*\n"
            f"```\n{example_text}\n```\n\n"
            f"{EMOJI['info']} Каждый пользователь с новой строки",
            parse_mode='Markdown'
        )
    
    elif state == "waiting_for_users":
        chat_name = context.user_data.get('temp_chat_name')
        if chat_name:
            usernames = [line.strip() for line in text.split('\n') if line.strip()]
            
            chat_id = add_user_chat(user_id, chat_name)
            add_chat_users(chat_id, usernames)
            
            del user_states[user_id]
            del context.user_data['temp_chat_name']
            
            keyboard = [
                [InlineKeyboardButton(f"{EMOJI['add']} Добавить еще", callback_data="add_users")],
                [InlineKeyboardButton(f"{EMOJI['home']} Главное меню", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"{EMOJI['success']} *ПОЛЬЗОВАТЕЛИ ДОБАВЛЕНЫ!*\n\n"
                f"• Чат: {chat_name}\n"
                f"• Пользователей: {len(usernames)}\n"
                f"• Всего чатов: {get_user_stats(user_id)['chats']}",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                f"{EMOJI['error']} Произошла ошибка. Попробуйте снова.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(f"{EMOJI['home']} Главное меню", callback_data="main_menu")]
                ])
            )

# Основная функция
def main():
    # Ваш токен
    application = Application.builder().token("8517379434:AAGqMYBuEQZ8EMNRf3g4yBN-Q0jpm5u5eZU").build()
    
    # Обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Запуск бота
    print("Бот запущен...")
    application.run_polling()

if __name__ == '__main__':
    main()
import logging
import sqlite3
import random
from typing import Dict, List, Tuple, Optional
from urllib.parse import quote
from datetime import datetime, timedelta
import asyncio
import json
import threading

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Импортируем конфигурацию
from config import *

# Словарь для замены кириллических букв на латинские
REPLACEMENTS = {
    'а': 'a', 'с': 'c', 'о': 'o', 'р': 'p', 'е': 'e', 'х': 'x', 'у': 'y',
    'А': 'A', 'С': 'C', 'О': 'O', 'Р': 'P', 'Е': 'E', 'Х': 'X', 'У': 'Y'
}

class MirrorDatabase:
    """База данных для управления зеркалами"""
    
    def __init__(self):
        self.db_name = "mirrors.db"
        self.init_database()
    
    def init_database(self):
        """Инициализация базы данных зеркал"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        # Таблица зеркал
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS mirrors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                bot_token TEXT NOT NULL UNIQUE,
                bot_username TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active INTEGER DEFAULT 1,
                is_running INTEGER DEFAULT 1,
                webhook_url TEXT,
                UNIQUE(user_id, bot_token)
            )
        ''')
        
        # Таблица доступа к зеркалам
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS mirror_access (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mirror_id INTEGER NOT NULL,
                allowed_user_id INTEGER NOT NULL,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (mirror_id) REFERENCES mirrors (id),
                UNIQUE(mirror_id, allowed_user_id)
            )
        ''')
        
        # Таблица объявлений
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS announcements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                message_text TEXT NOT NULL,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def add_mirror(self, user_id: int, bot_token: str, bot_username: str = None) -> Tuple[bool, int, str]:
        """Добавление нового зеркала"""
        try:
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()
            
            # Проверяем, не создал ли уже пользователь зеркало
            cursor.execute('SELECT id FROM mirrors WHERE user_id = ?', (user_id,))
            existing = cursor.fetchone()
            if existing:
                conn.close()
                return False, 0, "Вы уже создали зеркало"
            
            # Создаем webhook URL
            webhook_url = f"https://{YOUR_HOST}:{YOUR_PORT}/{bot_token}"
            
            cursor.execute('''
                INSERT INTO mirrors (user_id, bot_token, bot_username, created_at, last_activity, 
                                   webhook_url, is_running)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, bot_token, bot_username, datetime.now(), datetime.now(), 
                  webhook_url, 1))
            
            mirror_id = cursor.lastrowid
            
            # Добавляем создателя как первого пользователя с доступом
            cursor.execute('''
                INSERT INTO mirror_access (mirror_id, allowed_user_id)
                VALUES (?, ?)
            ''', (mirror_id, user_id))
            
            conn.commit()
            conn.close()
            
            return True, mirror_id, webhook_url
            
        except sqlite3.IntegrityError as e:
            return False, 0, f"Ошибка базы данных: {str(e)}"
    
    def get_user_mirror(self, user_id: int) -> Optional[Tuple]:
        """Получение зеркала пользователя"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, bot_token, bot_username, created_at, last_activity, 
                   is_active, is_running, webhook_url
            FROM mirrors WHERE user_id = ?
        ''', (user_id,))
        result = cursor.fetchone()
        conn.close()
        return result
    
    def update_mirror_activity(self, mirror_id: int):
        """Обновление времени последней активности"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE mirrors SET last_activity = ? WHERE id = ?
        ''', (datetime.now(), mirror_id))
        conn.commit()
        conn.close()
    
    def deactivate_inactive_mirrors(self):
        """Деактивация зеркал без активности больше недели"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        week_ago = datetime.now() - timedelta(days=INACTIVITY_DAYS)
        cursor.execute('''
            UPDATE mirrors SET is_active = 0, is_running = 0
            WHERE last_activity < ? AND is_active = 1
        ''', (week_ago,))
        conn.commit()
        conn.close()
    
    def toggle_mirror_running(self, mirror_id: int, running: bool = None) -> Tuple[bool, Tuple]:
        """Включение/выключение работы зеркала"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        if running is None:
            cursor.execute('SELECT is_running FROM mirrors WHERE id = ?', (mirror_id,))
            current = cursor.fetchone()
            if current:
                new_state = 0 if current[0] == 1 else 1
            else:
                conn.close()
                return False, ()
        else:
            new_state = 1 if running else 0
        
        cursor.execute('''
            UPDATE mirrors SET is_running = ?, last_activity = ? WHERE id = ?
        ''', (new_state, datetime.now(), mirror_id))
        
        conn.commit()
        
        cursor.execute('''
            SELECT bot_token, user_id, bot_username, webhook_url FROM mirrors WHERE id = ?
        ''', (mirror_id,))
        mirror_info = cursor.fetchone()
        
        conn.close()
        
        return new_state == 1, mirror_info
    
    def add_user_to_mirror(self, mirror_id: int, user_id: int) -> bool:
        """Добавление пользователя к зеркалу"""
        try:
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT COUNT(*) FROM mirror_access WHERE mirror_id = ?
            ''', (mirror_id,))
            count = cursor.fetchone()[0]
            
            if count >= MAX_USERS_PER_MIRROR:
                conn.close()
                return False
            
            cursor.execute('''
                INSERT INTO mirror_access (mirror_id, allowed_user_id)
                VALUES (?, ?)
            ''', (mirror_id, user_id))
            
            conn.commit()
            conn.close()
            return True
        except sqlite3.IntegrityError:
            return False
    
    def check_user_access(self, mirror_id: int, user_id: int) -> bool:
        """Проверка доступа пользователя к зеркалу"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT 1 FROM mirror_access 
            WHERE mirror_id = ? AND allowed_user_id = ?
        ''', (mirror_id, user_id))
        result = cursor.fetchone() is not None
        conn.close()
        return result
    
    def get_mirror_users(self, mirror_id: int) -> List[int]:
        """Получение списка пользователей с доступом к зеркалу"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT allowed_user_id FROM mirror_access WHERE mirror_id = ?
        ''', (mirror_id,))
        users = [row[0] for row in cursor.fetchall()]
        conn.close()
        return users
    
    def remove_user_from_mirror(self, mirror_id: int, user_id: int):
        """Удаление пользователя из зеркала (кроме создателя)"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        cursor.execute('SELECT user_id FROM mirrors WHERE id = ?', (mirror_id,))
        creator_id = cursor.fetchone()[0]
        
        if user_id != creator_id:
            cursor.execute('''
                DELETE FROM mirror_access 
                WHERE mirror_id = ? AND allowed_user_id = ?
            ''', (mirror_id, user_id))
        
        conn.commit()
        conn.close()
    
    def get_all_mirrors(self) -> List[Tuple]:
        """Получение всех зеркал (для админа)"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, user_id, bot_username, created_at, last_activity, 
                   is_active, is_running
            FROM mirrors ORDER BY created_at DESC
        ''')
        mirrors = cursor.fetchall()
        conn.close()
        return mirrors
    
    def add_announcement(self, admin_id: int, message_text: str):
        """Добавление объявления"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO announcements (admin_id, message_text)
            VALUES (?, ?)
        ''', (admin_id, message_text))
        conn.commit()
        conn.close()
    
    def get_recent_announcements(self, limit: int = 5) -> List[Tuple]:
        """Получение последних объявлений"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT message_text, sent_at FROM announcements 
            ORDER BY sent_at DESC LIMIT ?
        ''', (limit,))
        announcements = cursor.fetchall()
        conn.close()
        return announcements

class UserDatabase:
    """База данных пользователя (общая для всех зеркал)"""
    
    def __init__(self, user_id: int):
        self.user_id = user_id
        self.db_name = f"databases/user_{user_id}.db"
        self.init_database()
    
    def init_database(self):
        """Инициализация базы данных для пользователя"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                original_text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS variations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER,
                variation_text TEXT NOT NULL,
                send_count INTEGER DEFAULT 0,
                FOREIGN KEY (message_id) REFERENCES messages (id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                username TEXT NOT NULL,
                FOREIGN KEY (chat_id) REFERENCES chats (id)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def add_message(self, original_text: str) -> int:
        """Добавление исходного сообщения"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO messages (original_text) VALUES (?)', (original_text,))
        message_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return message_id
    
    def add_variations(self, message_id: int, variations: List[str]):
        """Добавление вариаций сообщения"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.executemany(
            'INSERT INTO variations (message_id, variation_text) VALUES (?, ?)',
            [(message_id, variation) for variation in variations]
        )
        conn.commit()
        conn.close()
    
    def get_messages(self) -> List[Tuple[int, str]]:
        """Получение списка исходных сообщений"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT id, original_text FROM messages ORDER BY created_at DESC')
        messages = cursor.fetchall()
        conn.close()
        return messages
    
    def delete_message(self, message_id: int):
        """Удаление сообщения и всех его вариаций"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM variations WHERE message_id = ?', (message_id,))
        cursor.execute('DELETE FROM messages WHERE id = ?', (message_id,))
        conn.commit()
        conn.close()
    
    def add_chat(self, chat_name: str) -> int:
        """Добавление чата"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        try:
            cursor.execute('INSERT INTO chats (name) VALUES (?)', (chat_name,))
            chat_id = cursor.lastrowid
        except sqlite3.IntegrityError:
            cursor.execute('SELECT id FROM chats WHERE name = ?', (chat_name,))
            chat_id = cursor.fetchone()[0]
        conn.commit()
        conn.close()
        return chat_id
    
    def add_users(self, chat_id: int, usernames: List[str]):
        """Добавление пользователей в чат"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.executemany(
            'INSERT OR IGNORE INTO users (chat_id, username) VALUES (?, ?)',
            [(chat_id, username.strip()) for username in usernames]
        )
        conn.commit()
        conn.close()
    
    def get_chats(self) -> List[Tuple[int, str]]:
        """Получение списка чатов"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT id, name FROM chats ORDER BY name')
        chats = cursor.fetchall()
        conn.close()
        return chats
    
    def delete_chat(self, chat_id: int):
        """Удаление чата и всех его пользователей"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM users WHERE chat_id = ?', (chat_id,))
        cursor.execute('DELETE FROM chats WHERE id = ?', (chat_id,))
        conn.commit()
        conn.close()
    
    def get_users_by_chat(self, chat_id: int, offset: int = 0, limit: int = 25) -> List[Tuple[int, str]]:
        """Получение пользователей чата с пагинацией"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute(
            'SELECT id, username FROM users WHERE chat_id = ? LIMIT ? OFFSET ?',
            (chat_id, limit, offset)
        )
        users = cursor.fetchall()
        conn.close()
        return users
    
    def get_random_variation(self) -> Tuple[int, str]:
        """Получение случайной вариации сообщения"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, variation_text FROM variations 
            WHERE send_count < 5 
            ORDER BY RANDOM() 
            LIMIT 1
        ''')
        result = cursor.fetchone()
        
        if result:
            variation_id, variation_text = result
            cursor.execute(
                'UPDATE variations SET send_count = send_count + 1 WHERE id = ?',
                (variation_id,)
            )
            cursor.execute('DELETE FROM variations WHERE send_count >= 5')
            conn.commit()
            conn.close()
            return variation_id, variation_text
        
        conn.close()
        return None, None
    
    def get_multiple_variations(self, count: int = 5) -> List[str]:
        """Получение нескольких случайных вариаций"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT variation_text FROM variations 
            WHERE send_count < 5 
            ORDER BY RANDOM() 
            LIMIT ?
        ''', (count,))
        results = cursor.fetchall()
        conn.close()
        
        variations = [result[0] for result in results]
        
        while len(variations) < count:
            if variations:
                variations.append(random.choice(variations))
            else:
                break
        
        return variations

class MirrorManagerBot:
    """Основной бот для создания и управления зеркалами"""
    
    def __init__(self, token: str):
        self.application = Application.builder().token(token).build()
        self.mirror_db = MirrorDatabase()
        self.user_states = {}
        self.running_mirrors = {}
        self.setup_handlers()
    
    def setup_handlers(self):
        """Настройка обработчиков"""
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("admin", self.admin_command))
        self.application.add_handler(CommandHandler("announce", self.announce_command))
        self.application.add_handler(CallbackQueryHandler(self.handle_button, pattern="^main_"))
        self.application.add_handler(CallbackQueryHandler(self.handle_mirrors, pattern="^mirrors_"))
        self.application.add_handler(CallbackQueryHandler(self.handle_admin, pattern="^admin_"))
        self.application.add_handler(CallbackQueryHandler(self.handle_messages, pattern="^messages_"))
        self.application.add_handler(CallbackQueryHandler(self.handle_users, pattern="^users_"))
        self.application.add_handler(CallbackQueryHandler(self.handle_spam, pattern="^spam_"))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text_input))
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        user_id = update.effective_user.id
        
        user_mirror = self.mirror_db.get_user_mirror(user_id)
        
        welcome_text = (
            "🌟 Добро пожаловать в основной бот! 🌟\n\n"
            "📱 Этот бот предназначен для создания и управления зеркалами\n\n"
        )
        
        if user_mirror:
            mirror_id, bot_token, bot_username, created_at, last_activity, is_active, is_running, webhook_url = user_mirror
            status = "✅ Запущено" if is_running else "⏸️ Остановлено"
            welcome_text += (
                "✅ У вас уже есть зеркало!\n"
                f"🤖 Имя бота: @{bot_username if bot_username else 'неизвестно'}\n"
                f"📅 Создан: {created_at.split()[0]}\n"
                f"🔄 Статус: {status}\n\n"
            )
        
        welcome_text += (
            "✨ Доступные функции:\n"
            "• 🔄 Создать новое зеркало\n"
            "• ⚙️ Управление зеркалом\n"
            "• 👥 Управление доступом\n"
            "• 📋 Посмотреть моё зеркало\n"
            "• 📝 Создание сообщений (для ознакомления)\n"
            "• 👥 Добавление пользователей (для ознакомления)\n"
            "• 🚀 Начать спам (для ознакомления)\n\n"
            "💡 Основной бот предназначен для ознакомления с функционалом. "
            "Пожалуйста, создайте зеркало и рассылайте из него"
        )
        
        keyboard = []
        
        if not user_mirror:
            keyboard.append([InlineKeyboardButton("🔄 Создать зеркало", callback_data="mirrors_create")])
        else:
            keyboard.append([InlineKeyboardButton("📋 Моё зеркало", callback_data="mirrors_view")])
            keyboard.append([InlineKeyboardButton("⚙️ Управление зеркалом", callback_data="mirrors_manage")])
            keyboard.append([InlineKeyboardButton("👥 Управление доступом", callback_data="mirrors_access")])
        
        keyboard.append([InlineKeyboardButton("📝 Создание сообщений", callback_data="main_messages")])
        keyboard.append([InlineKeyboardButton("👥 Мои пользователи", callback_data="main_users")])
        keyboard.append([InlineKeyboardButton("🚀 Начать спам", callback_data="main_spam")])
        
        if user_id == ADMIN_ID:
            keyboard.append([InlineKeyboardButton("⚙️ Админ панель", callback_data="admin_panel")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.message:
            await update.message.reply_text(welcome_text, reply_markup=reply_markup)
        else:
            await update.callback_query.edit_message_text(welcome_text, reply_markup=reply_markup)
    
    async def admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /admin (только для админа)"""
        user_id = update.effective_user.id
        
        if user_id != ADMIN_ID:
            await update.message.reply_text("⛔ У вас нет прав доступа к этой команде")
            return
        
        await self.show_admin_panel(update, context)
    
    async def announce_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /announce (только для админа)"""
        user_id = update.effective_user.id
        
        if user_id != ADMIN_ID:
            await update.message.reply_text("⛔ У вас нет прав доступа к этой команде")
            return
        
        if not context.args:
            await update.message.reply_text("📝 Использование: /announce <текст объявления>")
            return
        
        announcement_text = ' '.join(context.args)
        self.mirror_db.add_announcement(user_id, announcement_text)
        
        mirrors = self.mirror_db.get_all_mirrors()
        sent_count = 0
        
        for mirror in mirrors:
            try:
                await context.bot.send_message(
                    chat_id=mirror[1],
                    text=f"📢 Объявление от администратора:\n\n{announcement_text}"
                )
                sent_count += 1
            except Exception as e:
                logger.error(f"Ошибка отправки объявления пользователю {mirror[1]}: {e}")
        
        await update.message.reply_text(f"✅ Объявление отправлено {sent_count} пользователям")
    
    async def show_admin_panel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать админ панель"""
        query = update.callback_query
        if query:
            await query.answer()
            message = query.message
        else:
            message = update.message
        
        mirrors = self.mirror_db.get_all_mirrors()
        active_mirrors = sum(1 for m in mirrors if m[5] == 1)
        running_mirrors = sum(1 for m in mirrors if m[6] == 1)
        total_users = sum(len(self.mirror_db.get_mirror_users(m[0])) for m in mirrors)
        
        announcements = self.mirror_db.get_recent_announcements(3)
        
        admin_text = (
            "⚙️ Админ панель\n\n"
            f"📊 Статистика:\n"
            f"• Всего зеркал: {len(mirrors)}\n"
            f"• Активных зеркал: {active_mirrors}\n"
            f"• Запущенных зеркал: {running_mirrors}\n"
            f"• Всего пользователей: {total_users}\n\n"
            f"📢 Последние объявления:\n"
        )
        
        if announcements:
            for i, (text, sent_at) in enumerate(announcements, 1):
                date_str = sent_at.split()[0] if isinstance(sent_at, str) else sent_at.strftime('%Y-%m-%d')
                admin_text += f"{i}. {date_str}: {text[:50]}...\n"
        else:
            admin_text += "Нет объявлений\n"
        
        admin_text += "\n✨ Доступные действия:"
        
        keyboard = [
            [InlineKeyboardButton("📋 Все зеркала", callback_data="admin_mirrors")],
            [InlineKeyboardButton("📢 Создать объявление", callback_data="admin_announce")],
            [InlineKeyboardButton("🔄 Деактивировать неактивные", callback_data="admin_deactivate")],
            [InlineKeyboardButton("🔙 Назад", callback_data="main_back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if query:
            await query.edit_message_text(admin_text, reply_markup=reply_markup)
        else:
            await message.reply_text(admin_text, reply_markup=reply_markup)
    
    async def handle_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик админ кнопок"""
        query = update.callback_query
        data = query.data
        
        if data == "admin_panel":
            await self.show_admin_panel(update, context)
        elif data == "admin_mirrors":
            await self.show_all_mirrors(update, context)
        elif data == "admin_announce":
            await self.ask_for_announcement(update, context)
        elif data == "admin_deactivate":
            self.mirror_db.deactivate_inactive_mirrors()
            await query.answer("✅ Неактивные зеркала деактивированы")
            await self.show_admin_panel(update, context)
        elif data == "admin_back":
            await self.show_admin_panel(update, context)
    
    async def show_all_mirrors(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать все зеркала"""
        query = update.callback_query
        mirrors = self.mirror_db.get_all_mirrors()
        
        if not mirrors:
            await query.edit_message_text("📭 Нет созданных зеркал")
            return
        
        text = "📋 Все зеркала:\n\n"
        
        for mirror in mirrors:
            mirror_id, user_id, bot_username, created_at, last_activity, is_active, is_running = mirror
            users = self.mirror_db.get_mirror_users(mirror_id)
            
            created_date = created_at.split()[0] if isinstance(created_at, str) else created_at.strftime('%Y-%m-%d')
            last_activity_date = last_activity.split()[0] if isinstance(last_activity, str) else last_activity.strftime('%Y-%m-%d')
            
            status = "✅" if is_running else "⏸️"
            active_status = "🟢" if is_active else "🔴"
            
            text += (
                f"{status} {active_status} ID: {mirror_id}\n"
                f"👤 Создатель: {user_id}\n"
                f"🤖 Бот: @{bot_username if bot_username else 'неизвестно'}\n"
                f"👥 Пользователей: {len(users)}\n"
                f"📅 Создан: {created_date}\n"
                f"🔄 Активность: {last_activity_date}\n"
                f"――――――――――――――――――――\n"
            )
        
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup)
    
    async def ask_for_announcement(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Запросить текст объявления"""
        query = update.callback_query
        user_id = query.from_user.id
        
        self.user_states[user_id] = "waiting_for_announcement"
        
        text = (
            "📢 Создание объявления\n\n"
            "✍️ Введите текст объявления, которое будет отправлено всем пользователям с зеркалами:\n\n"
            "💡 Объявление будет отправлено немедленно"
        )
        
        keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="admin_back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup)
    
    async def handle_mirrors(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик кнопок управления зеркалами"""
        query = update.callback_query
        data = query.data
        user_id = query.from_user.id
        
        if data == "mirrors_create":
            await self.ask_for_bot_token(update, context)
        elif data == "mirrors_view":
            await self.show_user_mirror(update, context)
        elif data == "mirrors_manage":
            await self.manage_user_mirror(update, context)
        elif data == "mirrors_access":
            await self.manage_mirror_access(update, context)
        elif data == "mirrors_back":
            await self.start(update, context)
        elif data.startswith("mirrors_toggle_"):
            mirror_id = int(data.split("_")[2])
            await self.toggle_mirror_running(update, context, mirror_id)
    
    async def ask_for_bot_token(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Запросить токен бота для создания зеркала"""
        query = update.callback_query
        user_id = query.from_user.id
        
        self.user_states[user_id] = "waiting_for_bot_token"
        
        text = (
            f"🔄 Создание зеркала\n\n"
            f"🌐 Зеркало будет автоматически зарегистрировано на хосте:\n"
            f"📍 {YOUR_HOST}:{YOUR_PORT}\n\n"
            f"🔑 Для создания зеркала, пожалуйста, создайте бота через @BotFather и отправьте его токен:\n\n"
            f"💡 Инструкция:\n"
            f"1. Откройте @BotFather в Telegram\n"
            f"2. Создайте нового бота с помощью /newbot\n"
            f"3. Скопируйте токен (выглядит как: 1234567890:ABCdefGHIjklMNOpqrsTUVwxyz)\n"
            f"4. Отправьте токен сюда\n\n"
            f"✅ После отправки токена:\n"
            f"• Зеркало автоматически запустится\n"
            f"• Вы получите ссылку на бота\n"
            f"• Можете добавлять пользователей\n\n"
            f"⚠️ Внимание:\n"
            f"• 1 пользователь может создать только 1 зеркало\n"
            f"• Для спама используйте зеркало, не основной бот\n"
            f"• В зеркале не будет кнопки «мои зеркала»"
        )
        
        keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="mirrors_back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup)
    
    async def handle_text_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик текстового ввода"""
        user_id = update.message.from_user.id
        text = update.message.text
        
        if user_id not in self.user_states:
            help_text = "💡 Используйте кнопки меню для навигации\n\n🔍 Если вы потерялись, нажмите /start"
            await update.message.reply_text(help_text)
            return
        
        state = self.user_states[user_id]
        
        if state == "waiting_for_bot_token":
            try:
                temp_app = Application.builder().token(text).build()
                bot_info = await temp_app.bot.get_me()
                bot_username = bot_info.username
                
                success, mirror_id, webhook_url = self.mirror_db.add_mirror(user_id, text, bot_username)
                
                if success:
                    del self.user_states[user_id]
                    
                    await self.start_mirror_bot(text, user_id, mirror_id)
                    
                    success_text = (
                        f"✅ Зеркало успешно создано и зарегистрировано!\n\n"
                        f"🤖 Имя бота: @{bot_username}\n"
                        f"🔗 Ссылка на бота: https://t.me/{bot_username}\n"
                        f"🌐 Хост регистрации: {YOUR_HOST}\n"
                        f"🔗 Webhook URL: {webhook_url}\n\n"
                        f"✨ Зеркало автоматически запущено!\n\n"
                        f"💡 Теперь вы можете:\n"
                        f"1. Использовать зеркало для рассылки\n"
                        f"2. Добавить до {MAX_USERS_PER_MIRROR} пользователей\n"
                        f"3. Остановить/запустить зеркало при необходимости\n\n"
                        f"⚠️ Основной бот предназначен для ознакомления. Используйте зеркало для спама!"
                    )
                    
                    await update.message.reply_text(success_text)
                    await self.start(update, context)
                else:
                    error_text = (
                        "❌ Не удалось создать зеркало\n\n"
                        "Возможные причины:\n"
                        "• Вы уже создали зеркало ранее\n"
                        "• Этот токен уже используется\n"
                        "• Произошла ошибка в базе данных\n\n"
                        "💡 1 пользователь может создать только 1 зеркало"
                    )
                    await update.message.reply_text(error_text)
                    
            except Exception as e:
                error_text = (
                    "❌ Неверный токен бота\n\n"
                    "Пожалуйста, убедитесь что:\n"
                    "1. Токен скопирован правильно\n"
                    "2. Бот создан через @BotFather\n"
                    "3. Токен имеет правильный формат\n\n"
                    "💡 Пример токена: 1234567890:ABCdefGHIjklMNOpqrsTUVwxyz"
                )
                await update.message.reply_text(error_text)
        
        elif state == "waiting_for_announcement":
            if user_id != ADMIN_ID:
                await update.message.reply_text("⛔ У вас нет прав")
                return
            
            self.mirror_db.add_announcement(user_id, text)
            
            mirrors = self.mirror_db.get_all_mirrors()
            sent_count = 0
            
            for mirror in mirrors:
                try:
                    await context.bot.send_message(
                        chat_id=mirror[1],
                        text=f"📢 Объявление от администратора:\n\n{text}"
                    )
                    sent_count += 1
                except Exception as e:
                    logger.error(f"Ошибка отправки объявления пользователю {mirror[1]}: {e}")
            
            del self.user_states[user_id]
            
            await update.message.reply_text(f"✅ Объявление отправлено {sent_count} пользователям")
            await self.show_admin_panel(update, context)
        
        else:
            await self.handle_demo_text(update, context, text, state)
    
    # Остальные методы (show_user_mirror, manage_user_mirror, и т.д.)
    # Полный код слишком длинный для одного сообщения
    # Продолжение в следующих файлах...

    def generate_variations(self, text: str, count: int = 500) -> List[str]:
        """Генерация вариаций сообщения"""
        variations = set()
        chars_to_replace = list(REPLACEMENTS.keys())
        
        variations.add(text)
        
        while len(variations) < count:
            variation = list(text)
            changes_made = False
            
            for i, char in enumerate(variation):
                if char in REPLACEMENTS and random.random() < 0.3:
                    variation[i] = REPLACEMENTS[char]
                    changes_made = True
            
            variation_str = ''.join(variation)
            if changes_made and variation_str != text:
                variations.add(variation_str)
            
            if len(variations) >= min(count, 2 ** len([c for c in text if c in chars_to_replace])):
                break
        
        return list(variations)
    
    async def start_mirror_bot(self, bot_token: str, creator_id: int, mirror_id: int):
        """Запуск зеркального бота"""
        try:
            # Импортируем здесь, чтобы избежать циклических импортов
            from mirror_bot import MirrorSpamBot
            
            mirror_bot = MirrorSpamBot(
                bot_token=bot_token,
                creator_id=creator_id,
                mirror_id=mirror_id,
                mirror_db=self.mirror_db,
                host_domain=YOUR_HOST,
                webhook_port=YOUR_PORT
            )
            
            self.running_mirrors[mirror_id] = mirror_bot
            
            import threading
            
            def run_mirror():
                try:
                    if USE_WEBHOOK:
                        mirror_bot.run_webhook(
                            host=YOUR_HOST,
                            port=YOUR_PORT,
                            ssl_cert=YOUR_SSL_CERT,
                            ssl_key=YOUR_SSL_KEY
                        )
                    else:
                        mirror_bot.run_polling()
                except Exception as e:
                    logger.error(f"Ошибка запуска зеркала {mirror_id}: {e}")
            
            thread = threading.Thread(target=run_mirror, daemon=True)
            thread.start()
            
            logger.info(f"Зеркало {mirror_id} запущено на хосте {YOUR_HOST}:{YOUR_PORT}")
            
        except Exception as e:
            logger.error(f"Ошибка запуска зеркала {mirror_id}: {e}")
    
    def stop_mirror_bot(self, mirror_id: int):
        """Остановка зеркального бота"""
        if mirror_id in self.running_mirrors:
            try:
                mirror_bot = self.running_mirrors[mirror_id]
                del self.running_mirrors[mirror_id]
                logger.info(f"Зеркало {mirror_id} остановлено")
            except Exception as e:
                logger.error(f"Ошибка остановки зеркала {mirror_id}: {e}")
    
    def run(self):
        """Запуск основного бота"""
        async def check_inactive_mirrors():
            while True:
                await asyncio.sleep(24 * 60 * 60)
                self.mirror_db.deactivate_inactive_mirrors()
                logger.info("Проверка неактивных зеркал выполнена")
        
        asyncio.create_task(check_inactive_mirrors())
        
        print("=" * 50)
        print("🤖 Основной бот запущен!")
        print(f"👑 Админ ID: {ADMIN_ID}")
        print(f"🌐 Хост: {YOUR_HOST}:{YOUR_PORT}")
        print(f"🔧 Режим: {'WEBHOOK' if USE_WEBHOOK else 'POLLING'}")
        print("=" * 50)
        
        self.application.run_polling()

# Запуск бота
if __name__ == "__main__":
    if not MAIN_BOT_TOKEN or MAIN_BOT_TOKEN == "8517379434:AAGqMYBuEQZ8EMNRf3g4yBN-Q0jpm5u5eZU":
        print("❌ Ошибка: Не настроен MAIN_BOT_TOKEN в config.py")
        print("💡 Отредактируйте config.py перед запуском")
        exit(1)
    
    bot = MirrorManagerBot(MAIN_BOT_TOKEN)
    bot.run()
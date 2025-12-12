#!/usr/bin/env python3
"""
Основной бот для управления зеркалами
"""

import logging
import sqlite3
import random
from typing import Dict, List, Tuple, Optional
from urllib.parse import quote
from datetime import datetime, timedelta
import asyncio
import json
import threading
import os

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

import config

print("=" * 60)
print("🤖 ТЕЛЕГРАМ БОТ С ЗЕРКАЛАМИ - ЗАПУСК")
print("=" * 60)

# Проверяем конфигурацию
if not config.check_config():
    print("❌ Исправьте ошибки в config.py и перезапустите бота")
    exit(1)

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=getattr(logging, config.LOG_LEVEL),
    handlers=[
        logging.FileHandler(config.LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class MirrorDatabase:
    """База данных для управления зеркалами"""
    
    def __init__(self):
        self.db_name = config.DATABASE_PATH
        self.init_database()
    
    def init_database(self):
        """Инициализация базы данных зеркал"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
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
            
            cursor.execute('SELECT id FROM mirrors WHERE user_id = ?', (user_id,))
            existing = cursor.fetchone()
            if existing:
                conn.close()
                return False, 0, "Вы уже создали зеркало"
            
            webhook_url = f"{config.MIRROR_WEBHOOK_BASE}/{bot_token}"
            
            cursor.execute('''
                INSERT INTO mirrors (user_id, bot_token, bot_username, created_at, last_activity, 
                                   webhook_url, is_running)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, bot_token, bot_username, datetime.now(), datetime.now(), 
                  webhook_url, 1))
            
            mirror_id = cursor.lastrowid
            
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
        week_ago = datetime.now() - timedelta(days=config.INACTIVITY_DAYS)
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
            
            if count >= config.MAX_USERS_PER_MIRROR:
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

class MirrorManagerBot:
    """Основной бот для создания и управления зеркалами"""
    
    def __init__(self):
        self.application = Application.builder().token(config.MAIN_BOT_TOKEN).build()
        self.mirror_db = MirrorDatabase()
        self.user_states = {}
        self.running_mirrors = {}
        self.bot_username = None
        self.setup_handlers()
    
    async def initialize(self):
        """Инициализация бота (получение username)"""
        bot_info = await self.application.bot.get_me()
        self.bot_username = bot_info.username
        logger.info(f"Основной бот инициализирован: @{self.bot_username}")
    
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
                f"🔄 Статус: {status}\n"
                f"🌐 Вебхук: {webhook_url}\n\n"
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
        
        if user_id == config.ADMIN_ID:
            keyboard.append([InlineKeyboardButton("⚙️ Админ панель", callback_data="admin_panel")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.message:
            await update.message.reply_text(welcome_text, reply_markup=reply_markup)
        else:
            await update.callback_query.edit_message_text(welcome_text, reply_markup=reply_markup)
    
    async def admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /admin (только для админа)"""
        user_id = update.effective_user.id
        
        if user_id != config.ADMIN_ID:
            await update.message.reply_text("⛔ У вас нет прав доступа к этой команде")
            return
        
        await self.show_admin_panel(update, context)
    
    async def announce_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /announce (только для админа)"""
        user_id = update.effective_user.id
        
        if user_id != config.ADMIN_ID:
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
    
    async def handle_mirrors(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик кнопок управления зеркалами"""
        query = update.callback_query
        user_id = query.from_user.id
        data = query.data
        
        if data == "mirrors_create":
            await query.edit_message_text(
                "🔄 Создание нового зеркала\n\n"
                "📝 Отправьте токен бота, который вы получили от @BotFather:\n\n"
                "💡 Пример: 8517379434:AAGqMYBuEQZ8EMNRf3g4yBN-Q0jpm5u5eZU"
            )
            self.user_states[user_id] = "waiting_for_bot_token"
        
        elif data == "mirrors_view":
            user_mirror = self.mirror_db.get_user_mirror(user_id)
            if user_mirror:
                mirror_id, bot_token, bot_username, created_at, last_activity, is_active, is_running, webhook_url = user_mirror
                status = "✅ Запущено" if is_running else "⏸️ Остановлено"
                active = "✅ Активно" if is_active else "⏸️ Неактивно"
                
                mirror_text = (
                    f"📋 Ваше зеркало\n\n"
                    f"🤖 Имя бота: @{bot_username}\n"
                    f"🆔 ID зеркала: {mirror_id}\n"
                    f"📅 Создан: {created_at}\n"
                    f"🔄 Статус: {status}\n"
                    f"📊 Активность: {active}\n"
                    f"🌐 Вебхук URL: {webhook_url}\n\n"
                    f"💡 Используйте кнопки ниже для управления:"
                )
                
                keyboard = [
                    [InlineKeyboardButton("⚙️ Управление зеркалом", callback_data="mirrors_manage")],
                    [InlineKeyboardButton("👥 Управление доступом", callback_data="mirrors_access")],
                    [InlineKeyboardButton("🔙 Назад", callback_data="main_back")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(mirror_text, reply_markup=reply_markup)
            else:
                await query.answer("❌ У вас нет зеркала", show_alert=True)
        
        elif data == "mirrors_manage":
            await self.show_mirror_management(update, context)
        
        elif data == "mirrors_access":
            await self.show_access_management(update, context)
        
        elif data == "mirrors_toggle":
            user_mirror = self.mirror_db.get_user_mirror(user_id)
            if user_mirror:
                mirror_id = user_mirror[0]
                is_running, mirror_info = self.mirror_db.toggle_mirror_running(mirror_id)
                status = "✅ Запущено" if is_running else "⏸️ Остановлено"
                await query.answer(f"Зеркало {status}")
                await self.show_mirror_management(update, context)
    
    async def show_mirror_management(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать управление зеркалом"""
        query = update.callback_query
        user_id = query.from_user.id
        
        user_mirror = self.mirror_db.get_user_mirror(user_id)
        if not user_mirror:
            await query.answer("❌ У вас нет зеркала", show_alert=True)
            return
        
        mirror_id, bot_token, bot_username, created_at, last_activity, is_active, is_running, webhook_url = user_mirror
        status = "✅ Запущено" if is_running else "⏸️ Остановлено"
        toggle_text = "⏸️ Остановить" if is_running else "▶️ Запустить"
        
        manage_text = (
            f"⚙️ Управление зеркалом @{bot_username}\n\n"
            f"📊 Статус: {status}\n"
            f"🌐 Вебхук: {webhook_url}\n\n"
            f"💡 Выберите действие:"
        )
        
        keyboard = [
            [InlineKeyboardButton(toggle_text, callback_data="mirrors_toggle")],
            [InlineKeyboardButton("🌐 Информация о вебхуке", callback_data="mirrors_webhook_info")],
            [InlineKeyboardButton("👥 Управление доступом", callback_data="mirrors_access")],
            [InlineKeyboardButton("🔙 Назад", callback_data="mirrors_view")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(manage_text, reply_markup=reply_markup)
    
    async def show_access_management(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать управление доступом"""
        query = update.callback_query
        user_id = query.from_user.id
        
        user_mirror = self.mirror_db.get_user_mirror(user_id)
        if not user_mirror:
            await query.answer("❌ У вас нет зеркала", show_alert=True)
            return
        
        mirror_id = user_mirror[0]
        users = self.mirror_db.get_mirror_users(mirror_id)
        
        access_text = (
            f"👥 Управление доступом\n\n"
            f"📊 Пользователей с доступом: {len(users)}\n"
            f"📈 Лимит: {config.MAX_USERS_PER_MIRROR}\n\n"
            f"💡 Выберите действие:"
        )
        
        keyboard = [
            [InlineKeyboardButton("➕ Добавить пользователя", callback_data="access_add")],
            [InlineKeyboardButton("➖ Удалить пользователя", callback_data="access_remove")],
            [InlineKeyboardButton("📋 Список пользователей", callback_data="access_list")],
            [InlineKeyboardButton("🔙 Назад", callback_data="mirrors_manage")]
        ]
        
        if len(users) >= config.MAX_USERS_PER_MIRROR:
            access_text += "\n⚠️ Достигнут лимит пользователей!"
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(access_text, reply_markup=reply_markup)
    
    async def handle_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик админ кнопок"""
        query = update.callback_query
        data = query.data
        
        if data == "admin_panel":
            await self.show_admin_panel(update, context)
        elif data == "admin_mirrors":
            await self.show_all_mirrors(update, context)
        elif data == "admin_announce":
            await query.edit_message_text(
                "📢 Создание объявления\n\n"
                "📝 Введите текст объявления:"
            )
            self.user_states[query.from_user.id] = "waiting_for_announcement"
    
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
    
    async def show_all_mirrors(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать все зеркала (админ)"""
        query = update.callback_query
        mirrors = self.mirror_db.get_all_mirrors()
        
        if not mirrors:
            await query.edit_message_text("📭 Нет созданных зеркал")
            return
        
        text = "📋 Все зеркала:\n\n"
        for mirror in mirrors:
            mirror_id, user_id, bot_username, created_at, last_activity, is_active, is_running = mirror
            status = "🟢" if is_running else "🔴"
            active = "✅" if is_active else "⏸️"
            text += f"{status}{active} @{bot_username}\n"
            text += f"   ID: {mirror_id} | User: {user_id}\n"
            text += f"   Создан: {created_at}\n\n"
        
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup)
    
    async def handle_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик основных кнопок"""
        query = update.callback_query
        data = query.data
        
        if data == "main_messages":
            from bot_mirror import SpamBot
            await query.edit_message_text(
                "📝 Этот раздел доступен только в зеркальных ботах.\n\n"
                "💡 Создайте зеркало и перейдите в него для создания сообщений."
            )
        
        elif data == "main_users":
            from bot_mirror import SpamBot
            await query.edit_message_text(
                "👥 Этот раздел доступен только в зеркальных ботах.\n\n"
                "💡 Создайте зеркало и перейдите в него для добавления пользователей."
            )
        
        elif data == "main_spam":
            from bot_mirror import SpamBot
            await query.edit_message_text(
                "🚀 Этот раздел доступен только в зеркальных ботах.\n\n"
                "💡 Создайте зеркало и перейдите в него для начала рассылки."
            )
        
        elif data == "main_back":
            await self.start(update, context)
    
    async def handle_text_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик текстового ввода"""
        user_id = update.effective_user.id
        text = update.message.text
        
        if user_id not in self.user_states:
            await update.message.reply_text("💡 Используйте кнопки меню для навигации")
            return
        
        state = self.user_states[user_id]
        
        if state == "waiting_for_bot_token":
            await update.message.reply_text("⏳ Проверяю токен и создаю зеркало...")
            
            try:
                # Проверяем токен
                test_app = Application.builder().token(text.strip()).build()
                bot_info = await test_app.bot.get_me()
                bot_username = bot_info.username
                
                # Создаем зеркало
                success, mirror_id, webhook_url = self.mirror_db.add_mirror(
                    user_id, text.strip(), bot_username
                )
                
                if success:
                    del self.user_states[user_id]
                    
                    # Создаем и запускаем зеркальный бот
                    from bot_mirror import MirrorBot
                    mirror_bot = MirrorBot(
                        bot_token=text.strip(),
                        creator_id=user_id,
                        mirror_id=mirror_id,
                        mirror_db=self.mirror_db,
                        host_domain=config.YOUR_HOST,
                        webhook_port=config.YOUR_PORT
                    )
                    
                    # Запускаем в отдельном потоке
                    thread = threading.Thread(target=mirror_bot.run, daemon=True)
                    thread.start()
                    
                    self.running_mirrors[mirror_id] = mirror_bot
                    
                    await update.message.reply_text(
                        f"✅ Зеркало успешно создано!\n\n"
                        f"🤖 Бот: @{bot_username}\n"
                        f"🆔 ID зеркала: {mirror_id}\n"
                        f"🌐 Вебхук URL: {webhook_url}\n\n"
                        f"💡 Перейдите в бота и нажмите /start"
                    )
                else:
                    await update.message.reply_text(f"❌ Ошибка: {webhook_url}")
                    
            except Exception as e:
                await update.message.reply_text(f"❌ Ошибка при создании зеркала: {str(e)}")
        
        elif state == "waiting_for_announcement" and user_id == config.ADMIN_ID:
            await self.announce_command(update, context)
            del self.user_states[user_id]
    
    async def run_async(self):
        """Асинхронный запуск бота"""
        await self.initialize()
        
        print(f"\n{'='*60}")
        print(f"🤖 ОСНОВНОЙ БОТ ЗАПУЩЕН!")
        print(f"🔗 Бот: https://t.me/{self.bot_username}")
        print(f"👤 Админ ID: {config.ADMIN_ID}")
        print(f"🌐 Домен: {config.YOUR_HOST}:{config.YOUR_PORT}")
        print(f"🔧 Режим: {'WEBHOOK' if config.USE_WEBHOOK else 'POLLING'}")
        if config.USE_WEBHOOK:
            print(f"🌐 Вебхук URL: {config.MAIN_WEBHOOK_URL}")
        print(f"{'='*60}\n")
        
        if config.USE_WEBHOOK:
            # Запуск с вебхуком
            await self.application.run_webhook(
                listen="0.0.0.0",
                port=config.YOUR_PORT,
                url_path=config.MAIN_BOT_TOKEN,
                webhook_url=config.MAIN_WEBHOOK_URL,
                cert=config.SSL_CERT if config.SSL_CERT and os.path.exists(config.SSL_CERT) else None,
                key=config.SSL_KEY if config.SSL_KEY and os.path.exists(config.SSL_KEY) else None,
                drop_pending_updates=True
            )
        else:
            # Запуск в режиме polling
            await self.application.run_polling()

def main():
    """Главная функция"""
    print("🚀 Запуск системы зеркал...")
    
    # Создаем и запускаем бота
    bot = MirrorManagerBot()
    asyncio.run(bot.run_async())

if __name__ == "__main__":
    main()
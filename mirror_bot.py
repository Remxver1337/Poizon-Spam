#!/usr/bin/env python3
"""
Зеркальный бот для рассылки
"""

import logging
import random
import sqlite3
from typing import List
from urllib.parse import quote
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

import config

logger = logging.getLogger(__name__)

class MirrorBot:
    """Зеркальный бот"""
    
    def __init__(self, token: str, creator_id: int, mirror_id: int):
        self.token = token
        self.creator_id = creator_id
        self.mirror_id = mirror_id
        self.app = Application.builder().token(token).build()
        self.running = False
        
        # Создаем БД пользователя
        self.user_db_path = Path(f"databases/user_{creator_id}.db")
        self.init_user_database()
        
        self.setup_handlers()
        
        logger.info(f"Создан зеркальный бот: {mirror_id} для пользователя {creator_id}")
    
    def init_user_database(self):
        """Инициализация БД пользователя"""
        conn = sqlite3.connect(self.user_db_path)
        cursor = conn.cursor()
        
        # Таблица сообщений
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица пользователей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                chat_name TEXT
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def setup_handlers(self):
        """Настройка обработчиков"""
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("addmsg", self.add_message_command))
        self.app.add_handler(CommandHandler("adduser", self.add_user_command))
        self.app.add_handler(CommandHandler("spam", self.spam_command))
        self.app.add_handler(CommandHandler("list", self.list_command))
        self.app.add_handler(CallbackQueryHandler(self.button_handler))
        
        # Обработчик текста для добавления пользователей
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /start для зеркала"""
        user = update.effective_user
        
        # Проверяем, имеет ли пользователь доступ
        if user.id != self.creator_id:
            # Можно добавить проверку через основную БД
            await update.message.reply_text(
                "🔒 Этот бот приватный. Обратитесь к создателю для доступа."
            )
            return
        
        welcome_text = (
            f"🪞 Зеркало #{self.mirror_id}\n\n"
            f"👋 Привет, {user.first_name}!\n\n"
            "✨ Этот бот для рассылки сообщений.\n\n"
            "📝 Команды:\n"
            "/addmsg - Добавить сообщение\n"
            "/adduser - Добавить пользователей\n"
            "/spam - Начать рассылку\n"
            "/list - Список сообщений и пользователей\n"
            "/help - Помощь"
        )
        
        keyboard = [
            [InlineKeyboardButton("➕ Добавить сообщение", callback_data="add_message")],
            [InlineKeyboardButton("👥 Добавить пользователей", callback_data="add_users")],
            [InlineKeyboardButton("🚀 Начать рассылку", callback_data="start_spam")],
            [InlineKeyboardButton("📋 Списки", callback_data="show_lists")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(welcome_text, reply_markup=reply_markup)
    
    async def add_message_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Добавить сообщение"""
        if not context.args:
            await update.message.reply_text(
                "📝 Использование: /addmsg <текст сообщения>\n\n"
                "💡 Пример: /addmsg Привет! Как дела?"
            )
            return
        
        message_text = ' '.join(context.args)
        
        # Сохраняем в БД
        conn = sqlite3.connect(self.user_db_path)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO messages (text) VALUES (?)", (message_text,))
        conn.commit()
        conn.close()
        
        # Генерируем вариации
        variations = self.generate_variations(message_text, 50)
        
        await update.message.reply_text(
            f"✅ Сообщение добавлено!\n\n"
            f"📊 Создано вариаций: {len(variations)}\n"
            f"💬 Текст: {message_text[:100]}..."
        )
    
    def generate_variations(self, text: str, count: int = 50) -> List[str]:
        """Генерация вариаций сообщения"""
        variations = set()
        
        for _ in range(count):
            variation = []
            for char in text:
                if char.lower() in config.REPLACEMENTS:
                    # Случайно заменяем символ
                    if random.random() > 0.5:
                        replacement = config.REPLACEMENTS[char.lower()]
                        variation.append(replacement.upper() if char.isupper() else replacement)
                    else:
                        variation.append(char)
                else:
                    variation.append(char)
            
            variation_str = ''.join(variation)
            if variation_str != text:
                variations.add(variation_str)
        
        return list(variations)
    
    async def add_user_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Добавить пользователей"""
        if not context.args:
            await update.message.reply_text(
                "👥 Использование: /adduser <список username через пробел>\n\n"
                "💡 Пример: /adduser username1 username2 username3"
            )
            return
        
        usernames = context.args
        added = 0
        
        conn = sqlite3.connect(self.user_db_path)
        cursor = conn.cursor()
        
        for username in usernames:
            username = username.lstrip('@')
            try:
                cursor.execute("INSERT OR IGNORE INTO users (username) VALUES (?)", (username,))
                added += 1
            except:
                pass
        
        conn.commit()
        conn.close()
        
        await update.message.reply_text(f"✅ Добавлено пользователей: {added}")
    
    async def spam_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Начать рассылку"""
        # Получаем сообщения
        conn = sqlite3.connect(self.user_db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT text FROM messages")
        messages = [row[0] for row in cursor.fetchall()]
        
        cursor.execute("SELECT username FROM users")
        users = [row[0] for row in cursor.fetchall()]
        
        conn.close()
        
        if not messages:
            await update.message.reply_text("❌ Нет сообщений для рассылки. Добавьте через /addmsg")
            return
        
        if not users:
            await update.message.reply_text("❌ Нет пользователей для рассылки. Добавьте через /adduser")
            return
        
        # Создаем клавиатуру с ссылками
        keyboard = []
        for i, user in enumerate(users[:10]):  # Первые 10 пользователей
            message = random.choice(messages)
            url = f"https://t.me/{user}?text={quote(message)}"
            keyboard.append([InlineKeyboardButton(f"👤 Отправить {user}", url=url)])
        
        if len(users) > 10:
            keyboard.append([InlineKeyboardButton("➡️ Следующие 10", callback_data="next_page")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"🚀 Начинаем рассылку!\n\n"
            f"📊 Статистика:\n"
            f"• Пользователей: {len(users)}\n"
            f"• Сообщений: {len(messages)}\n"
            f"• Вариаций: {len(messages) * 50}\n\n"
            f"💡 Нажмите на кнопки ниже для отправки:",
            reply_markup=reply_markup
        )
    
    async def list_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать списки"""
        conn = sqlite3.connect(self.user_db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM messages")
        msg_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM users")
        user_count = cursor.fetchone()[0]
        
        conn.close()
        
        text = (
            f"📋 Статистика:\n\n"
            f"📝 Сообщений: {msg_count}\n"
            f"👥 Пользователей: {user_count}\n\n"
            f"🔧 Команды:\n"
            f"/addmsg - Добавить сообщение\n"
            f"/adduser - Добавить пользователей\n"
            f"/spam - Начать рассылку"
        )
        
        await update.message.reply_text(text)
    
    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка текста для добавления пользователей списком"""
        text = update.message.text
        
        # Если текст похож на список username (каждый с новой строки)
        if '\n' in text:
            usernames = [line.strip().lstrip('@') for line in text.split('\n') if line.strip()]
            
            conn = sqlite3.connect(self.user_db_path)
            cursor = conn.cursor()
            
            added = 0
            for username in usernames:
                try:
                    cursor.execute("INSERT OR IGNORE INTO users (username) VALUES (?)", (username,))
                    added += 1
                except:
                    pass
            
            conn.commit()
            conn.close()
            
            await update.message.reply_text(f"✅ Добавлено пользователей из списка: {added}")
    
    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик кнопок"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        
        if data == "add_message":
            await query.edit_message_text(
                "📝 Введите текст сообщения:\n\n"
                "Пример: /addmsg Привет! Как дела?"
            )
        elif data == "add_users":
            await query.edit_message_text(
                "👥 Отправьте список username через пробел:\n\n"
                "Пример: /adduser username1 username2 username3"
            )
        elif data == "start_spam":
            await self.spam_command(update, context)
        elif data == "show_lists":
            await self.list_command(update, context)
    
    def run(self):
        """Запуск бота"""
        self.running = True
        logger.info(f"Зеркальный бот {self.mirror_id} запущен")
        print(f"🪞 Зеркало #{self.mirror_id} запущено")
        
        # Обновляем статус в основной БД
        conn = sqlite3.connect(config.MIRRORS_DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE mirrors SET status = 'running' WHERE id = ?",
            (self.mirror_id,)
        )
        conn.commit()
        conn.close()
        
        try:
            self.app.run_polling()
        except Exception as e:
            logger.error(f"Ошибка в зеркальном боте {self.mirror_id}: {e}")
        finally:
            self.stop()
    
    def stop(self):
        """Остановка бота"""
        if self.running:
            self.running = False
            logger.info(f"Зеркальный бот {self.mirror_id} остановлен")
            
            # Обновляем статус
            conn = sqlite3.connect(config.MIRRORS_DB_PATH)
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE mirrors SET status = 'stopped' WHERE id = ?",
                (self.mirror_id,)
            )
            conn.commit()
            conn.close()

if __name__ == "__main__":
    print("❌ Этот файл запускается только из main.py")
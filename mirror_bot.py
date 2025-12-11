#!/usr/bin/env python3
"""
Зеркальный бот для рассылки с поддержкой вебхуков
"""

import logging
import random
import sqlite3
import os
from typing import List
from urllib.parse import quote
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

import config

logger = logging.getLogger(__name__)

class MirrorBot:
    """Зеркальный бот с поддержкой вебхуков"""
    
    def __init__(self, token: str, creator_id: int, mirror_id: int, is_webhook=False):
        self.token = token
        self.creator_id = creator_id
        self.mirror_id = mirror_id
        self.is_webhook = is_webhook
        self.app = Application.builder().token(token).build()
        self.running = False
        
        # Создаем БД пользователя
        self.user_db_path = Path(f"databases/user_{creator_id}.db")
        self.init_user_database()
        
        self.setup_handlers()
        
        mode = "webhook" if is_webhook else "polling"
        logger.info(f"Создан зеркальный бот {mirror_id} в режиме {mode}")
    
    def init_user_database(self):
        """Инициализация БД пользователя"""
        conn = sqlite3.connect(self.user_db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL,
                variations_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                chat_name TEXT DEFAULT 'Основной',
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS message_variations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER,
                variation_text TEXT NOT NULL,
                used_count INTEGER DEFAULT 0,
                FOREIGN KEY (message_id) REFERENCES messages (id)
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
        self.app.add_handler(CommandHandler("status", self.status_command))
        self.app.add_handler(CallbackQueryHandler(self.button_handler))
        
        # Обработчик текста для добавления пользователей
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /start для зеркала"""
        user = update.effective_user
        
        # Проверяем, имеет ли пользователь доступ (можно добавить проверку через основную БД)
        if user.id != self.creator_id:
            await update.message.reply_text(
                f"🔒 Этот бот приватный. Обратитесь к создателю для доступа.\n"
                f"🆔 ID создателя: {self.creator_id}"
            )
            return
        
        mode_text = "🌐 с вебхуком" if self.is_webhook else "🔄 в режиме polling"
        
        welcome_text = (
            f"🪞 Зеркало #{self.mirror_id}\n\n"
            f"👋 Привет, {user.first_name}!\n"
            f"🔧 Режим: {mode_text}\n\n"
            f"✨ Этот бот для рассылки сообщений с вариациями.\n\n"
            f"📝 Основные команды:\n"
            f"/addmsg - Добавить сообщение (создает 500 вариаций)\n"
            f"/adduser - Добавить пользователей\n"
            f"/spam - Начать рассылку\n"
            f"/list - Списки сообщений и пользователей\n"
            f"/status - Статус бота\n"
            f"/help - Помощь"
        )
        
        keyboard = [
            [InlineKeyboardButton("➕ Добавить сообщение", callback_data="add_message")],
            [InlineKeyboardButton("👥 Добавить пользователей", callback_data="add_users")],
            [InlineKeyboardButton("🚀 Начать рассылку", callback_data="start_spam")],
            [InlineKeyboardButton("📊 Статус", callback_data="show_status")],
            [InlineKeyboardButton("📋 Списки", callback_data="show_lists")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(welcome_text, reply_markup=reply_markup)
    
    async def add_message_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Добавить сообщение"""
        if not context.args:
            await update.message.reply_text(
                "📝 Использование: /addmsg <текст сообщения>\n\n"
                "💡 Пример: /addmsg Привет! Как дела?\n"
                f"📊 Бот создаст {config.MAX_VARIATIONS_PER_MESSAGE} вариаций"
            )
            return
        
        message_text = ' '.join(context.args)
        
        await update.message.reply_text("⏳ Создаю вариации...")
        
        # Генерируем вариации
        variations = self.generate_variations(message_text, config.MAX_VARIATIONS_PER_MESSAGE)
        
        # Сохраняем в БД
        conn = sqlite3.connect(self.user_db_path)
        cursor = conn.cursor()
        
        # Сохраняем основное сообщение
        cursor.execute(
            "INSERT INTO messages (text, variations_count) VALUES (?, ?)",
            (message_text, len(variations))
        )
        message_id = cursor.lastrowid
        
        # Сохраняем вариации
        for variation in variations:
            cursor.execute(
                "INSERT INTO message_variations (message_id, variation_text) VALUES (?, ?)",
                (message_id, variation)
            )
        
        conn.commit()
        conn.close()
        
        await update.message.reply_text(
            f"✅ Сообщение добавлено!\n\n"
            f"📊 Создано вариаций: {len(variations)}\n"
            f"💬 Текст: {message_text[:100]}{'...' if len(message_text) > 100 else ''}\n\n"
            f"💡 Теперь добавьте пользователей (/adduser) и начните рассылку (/spam)"
        )
    
    def generate_variations(self, text: str, count: int = 500) -> List[str]:
        """Генерация вариаций сообщения"""
        variations = set()
        
        # Всегда добавляем оригинальный текст
        variations.add(text)
        
        chars_to_replace = list(config.REPLACEMENTS.keys())
        
        # Генерируем вариации
        attempts = 0
        max_attempts = count * 10
        
        while len(variations) < count and attempts < max_attempts:
            variation = []
            changes_made = False
            
            # Проходим по каждому символу в тексте
            for char in text:
                if char.lower() in chars_to_replace and random.random() > 0.7:
                    # Случайно заменяем символ
                    replacement = config.REPLACEMENTS[char.lower()]
                    variation.append(replacement.upper() if char.isupper() else replacement)
                    changes_made = True
                else:
                    variation.append(char)
            
            if changes_made:
                variation_str = ''.join(variation)
                if variation_str != text:
                    variations.add(variation_str)
            
            attempts += 1
        
        return list(variations)
    
    async def add_user_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Добавить пользователей"""
        if not context.args:
            await update.message.reply_text(
                "👥 Использование: /adduser <список username через пробел>\n\n"
                "💡 Пример: /adduser username1 username2 username3\n"
                "💡 Или отправьте список username каждый с новой строки"
            )
            return
        
        usernames = context.args
        added = 0
        
        conn = sqlite3.connect(self.user_db_path)
        cursor = conn.cursor()
        
        for username in usernames:
            username = username.lstrip('@').strip()
            if username:
                try:
                    cursor.execute(
                        "INSERT OR IGNORE INTO users (username) VALUES (?)", 
                        (username,)
                    )
                    if cursor.rowcount > 0:
                        added += 1
                except Exception as e:
                    logger.error(f"Ошибка добавления пользователя {username}: {e}")
        
        conn.commit()
        conn.close()
        
        await update.message.reply_text(f"✅ Добавлено пользователей: {added}")
    
    async def spam_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Начать рассылку"""
        # Получаем сообщения и пользователей
        conn = sqlite3.connect(self.user_db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM messages")
        msg_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM users")
        user_count = cursor.fetchone()[0]
        
        if msg_count == 0:
            conn.close()
            await update.message.reply_text(
                "❌ Нет сообщений для рассылки.\n"
                "💡 Добавьте сообщение: /addmsg <текст>"
            )
            return
        
        if user_count == 0:
            conn.close()
            await update.message.reply_text(
                "❌ Нет пользователей для рассылки.\n"
                "💡 Добавьте пользователей: /adduser <username1 username2 ...>"
            )
            return
        
        # Получаем последнее сообщение и его вариации
        cursor.execute("SELECT id, text FROM messages ORDER BY id DESC LIMIT 1")
        message_id, message_text = cursor.fetchone()
        
        cursor.execute(
            "SELECT variation_text FROM message_variations WHERE message_id = ? ORDER BY RANDOM() LIMIT 10",
            (message_id,)
        )
        variations = [row[0] for row in cursor.fetchall()]
        
        # Получаем пользователей
        cursor.execute("SELECT username FROM users LIMIT 10")
        users = [row[0] for row in cursor.fetchall()]
        
        conn.close()
        
        # Создаем клавиатуру с ссылками
        keyboard = []
        for i, (user, variation) in enumerate(zip(users, variations * 2)):  # Дублируем вариации если нужно
            if i >= len(users):
                break
            url = f"https://t.me/{user}?text={quote(variation)}"
            keyboard.append([InlineKeyboardButton(f"👤 Отправить {user}", url=url)])
        
        if user_count > 10:
            keyboard.append([InlineKeyboardButton("➡️ Следующие 10", callback_data="next_page_1")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"🚀 Начинаем рассылку!\n\n"
            f"📊 Статистика:\n"
            f"• Пользователей всего: {user_count}\n"
            f"• Сообщений всего: {msg_count}\n"
            f"• Вариаций в базе: {len(variations)*50}\n"
            f"• Показано пользователей: {len(users)}\n\n"
            f"💡 Нажмите на кнопки ниже для отправки.\n"
            f"📱 Сообщения откроются в Telegram с готовым текстом.",
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
        
        cursor.execute("SELECT SUM(variations_count) FROM messages")
        total_variations = cursor.fetchone()[0] or 0
        
        # Последние 3 сообщения
        cursor.execute("SELECT text FROM messages ORDER BY id DESC LIMIT 3")
        last_messages = [row[0][:50] + "..." for row in cursor.fetchall()]
        
        conn.close()
        
        text = (
            f"📋 Статистика зеркала #{self.mirror_id}\n\n"
            f"📝 Сообщений: {msg_count}\n"
            f"👥 Пользователей: {user_count}\n"
            f"🔄 Всего вариаций: {total_variations}\n\n"
        )
        
        if last_messages:
            text += "📄 Последние сообщения:\n"
            for i, msg in enumerate(last_messages, 1):
                text += f"{i}. {msg}\n"
        
        text += "\n🔧 Команды:\n"
        text += "/addmsg - Добавить сообщение\n"
        text += "/adduser - Добавить пользователей\n"
        text += "/spam - Начать рассылку\n"
        text += "/status - Подробный статус"
        
        await update.message.reply_text(text)
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать статус бота"""
        mode = "🌐 Webhook" if self.is_webhook else "🔄 Polling"
        
        text = (
            f"📊 Статус зеркала #{self.mirror_id}\n\n"
            f"🔧 Режим: {mode}\n"
            f"👤 Создатель ID: {self.creator_id}\n"
            f"🤖 Токен: {self.token[:15]}...\n"
            f"📁 База данных: {self.user_db_path.name}\n"
            f"🏃‍♂️ Статус: {'Запущен ✅' if self.running else 'Остановлен ❌'}\n\n"
        )
        
        if self.is_webhook:
            webhook_url = f"{config.MIRROR_WEBHOOK_BASE}/{self.token}"
            text += f"🌐 Вебхук URL: {webhook_url}\n"
        
        await update.message.reply_text(text)
    
    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка текста для добавления пользователей списком"""
        text = update.message.text
        user = update.effective_user
        
        if user.id != self.creator_id:
            return
        
        # Если текст похож на список username (каждый с новой строки)
        if '\n' in text and len(text.split('\n')) > 1:
            usernames = [line.strip().lstrip('@') for line in text.split('\n') if line.strip()]
            
            conn = sqlite3.connect(self.user_db_path)
            cursor = conn.cursor()
            
            added = 0
            for username in usernames:
                if username:
                    try:
                        cursor.execute(
                            "INSERT OR IGNORE INTO users (username) VALUES (?)", 
                            (username,)
                        )
                        if cursor.rowcount > 0:
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
                "Пример: /addmsg Привет! Как дела?\n"
                f"📊 Бот создаст {config.MAX_VARIATIONS_PER_MESSAGE} вариаций"
            )
        elif data == "add_users":
            await query.edit_message_text(
                "👥 Отправьте список username через пробел:\n\n"
                "Пример: /adduser username1 username2 username3\n"
                "Или отправьте список username каждый с новой строки"
            )
        elif data == "start_spam":
            await self.spam_command(update, context)
        elif data == "show_status":
            await self.status_command(update, context)
        elif data == "show_lists":
            await self.list_command(update, context)
    
    def run(self):
        """Запуск бота в нужном режиме"""
        self.running = True
        
        mode = "вебхук" if self.is_webhook else "polling"
        logger.info(f"Запуск зеркального бота {self.mirror_id} в режиме {mode}")
        print(f"🪞 Зеркало #{self.mirror_id} запущено ({mode})")
        
        try:
            if self.is_webhook:
                # Запуск с вебхуком
                webhook_url = f"{config.MIRROR_WEBHOOK_BASE}/{self.token}"
                
                self.app.run_webhook(
                    listen=config.WEBHOOK_LISTEN,
                    port=config.WEBHOOK_PORT,
                    url_path=self.token,
                    webhook_url=webhook_url,
                    cert=config.SSL_CERT if config.SSL_CERT and os.path.exists(config.SSL_CERT) else None,
                    key=config.SSL_KEY if config.SSL_KEY and os.path.exists(config.SSL_KEY) else None,
                    drop_pending_updates=True
                )
            else:
                # Запуск в режиме polling
                self.app.run_polling()
                
        except Exception as e:
            logger.error(f"Ошибка в зеркальном боте {self.mirror_id}: {e}")
            print(f"❌ Ошибка в зеркале #{self.mirror_id}: {e}")
        finally:
            self.stop()
    
    def stop(self):
        """Остановка бота"""
        if self.running:
            self.running = False
            logger.info(f"Зеркальный бот {self.mirror_id} остановлен")
            print(f"🛑 Зеркало #{self.mirror_id} остановлено")

if __name__ == "__main__":
    print("❌ Этот файл запускается только из main.py")
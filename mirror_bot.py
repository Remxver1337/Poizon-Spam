#!/usr/bin/env python3
"""
Зеркальный бот для рассылки с поддержкой вебхуков
"""

import logging
import random
import sqlite3
import os
import asyncio
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
        self.app = None
        self.running = False
        self.bot_username = None
        
        # Создаем БД пользователя
        self.user_db_path = Path(f"databases/user_{creator_id}.db")
        self.init_user_database()
        
        logger.info(f"Создан зеркальный бот {mirror_id} (режим: {'webhook' if is_webhook else 'polling'})")
    
    def init_user_database(self):
        """Инициализация БД пользователя"""
        conn = sqlite3.connect(self.user_db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
    
    async def initialize(self):
        """Инициализация бота"""
        self.app = Application.builder().token(self.token).build()
        self.setup_handlers()
        
        # Получаем информацию о боте
        bot_info = await self.app.bot.get_me()
        self.bot_username = bot_info.username
        
        logger.info(f"Зеркальный бот {self.mirror_id} инициализирован: @{self.bot_username}")
    
    def setup_handlers(self):
        """Настройка обработчиков"""
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("addmsg", self.add_message_command))
        self.app.add_handler(CommandHandler("adduser", self.add_user_command))
        self.app.add_handler(CommandHandler("spam", self.spam_command))
        self.app.add_handler(CommandHandler("list", self.list_command))
        self.app.add_handler(CallbackQueryHandler(self.button_handler))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /start для зеркала"""
        user = update.effective_user
        
        if user.id != self.creator_id:
            await update.message.reply_text(
                f"🔒 Этот бот приватный. Доступ только для создателя.\n"
                f"🆔 ID создателя: {self.creator_id}"
            )
            return
        
        mode_text = "🌐 с вебхуком" if self.is_webhook else "🔄 в режиме polling"
        
        welcome_text = (
            f"🪞 Зеркало #{self.mirror_id}\n\n"
            f"👋 Привет, {user.first_name}!\n"
            f"🔧 Режим: {mode_text}\n"
            f"🤖 Бот: @{self.bot_username}\n\n"
            f"📝 Команды:\n"
            f"/addmsg <текст> - Добавить сообщение\n"
            f"/adduser <@юзернеймы> - Добавить пользователей\n"
            f"/spam - Начать рассылку\n"
            f"/list - Показать статистику"
        )
        
        await update.message.reply_text(welcome_text)
    
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
        
        await update.message.reply_text(
            f"✅ Сообщение добавлено!\n\n"
            f"💬 Текст: {message_text[:200]}{'...' if len(message_text) > 200 else ''}"
        )
    
    async def add_user_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Добавить пользователей"""
        if not context.args:
            await update.message.reply_text(
                "👥 Использование: /adduser <список @юзернеймов через пробел>\n\n"
                "💡 Пример: /adduser @username1 @username2 @username3"
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
                except:
                    pass
        
        conn.commit()
        conn.close()
        
        await update.message.reply_text(f"✅ Добавлено пользователей: {added}")
    
    async def spam_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Начать рассылку"""
        # Получаем сообщения и пользователей
        conn = sqlite3.connect(self.user_db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT text FROM messages ORDER BY RANDOM() LIMIT 5")
        messages = [row[0] for row in cursor.fetchall()]
        
        cursor.execute("SELECT username FROM users LIMIT 10")
        users = [row[0] for row in cursor.fetchall()]
        
        conn.close()
        
        if not messages:
            await update.message.reply_text(
                "❌ Нет сообщений для рассылки.\n"
                "💡 Добавьте сообщение: /addmsg <текст>"
            )
            return
        
        if not users:
            await update.message.reply_text(
                "❌ Нет пользователей для рассылки.\n"
                "💡 Добавьте пользователей: /adduser @username1 @username2"
            )
            return
        
        # Создаем клавиатуру с ссылками
        keyboard = []
        for i, user in enumerate(users[:5]):  # Первые 5 пользователей
            message = random.choice(messages)
            variation = self.generate_variation(message)
            url = f"https://t.me/{user}?text={quote(variation)}"
            keyboard.append([InlineKeyboardButton(f"👤 Отправить {user}", url=url)])
        
        if len(users) > 5:
            keyboard.append([InlineKeyboardButton("➡️ Ещё пользователи", callback_data="more_users")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"🚀 Начинаем рассылку!\n\n"
            f"📊 Статистика:\n"
            f"• Пользователей: {len(users)}\n"
            f"• Сообщений: {len(messages)}\n"
            f"• Показано: 5 из {len(users)}\n\n"
            f"💡 Нажмите на кнопки для отправки:",
            reply_markup=reply_markup
        )
    
    def generate_variation(self, text: str) -> str:
        """Генерация одной вариации сообщения"""
        variation = []
        for char in text:
            if char.lower() in config.REPLACEMENTS and random.random() > 0.7:
                replacement = config.REPLACEMENTS[char.lower()]
                variation.append(replacement.upper() if char.isupper() else replacement)
            else:
                variation.append(char)
        return ''.join(variation)
    
    async def list_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать статистику"""
        conn = sqlite3.connect(self.user_db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM messages")
        msg_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM users")
        user_count = cursor.fetchone()[0]
        
        conn.close()
        
        text = (
            f"📊 Статистика зеркала #{self.mirror_id}\n\n"
            f"📝 Сообщений: {msg_count}\n"
            f"👥 Пользователей: {user_count}\n\n"
            f"🔧 Режим: {'🌐 Webhook' if self.is_webhook else '🔄 Polling'}\n"
            f"🤖 Бот: @{self.bot_username}"
        )
        
        await update.message.reply_text(text)
    
    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка текста"""
        # Простой эхо для теста
        if update.effective_user.id == self.creator_id:
            await update.message.reply_text(f"📨 Вы написали: {update.message.text[:100]}")
    
    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик кнопок"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "more_users":
            await self.spam_command(update, context)
    
    async def run_async(self):
        """Асинхронный запуск бота"""
        await self.initialize()
        
        self.running = True
        logger.info(f"Зеркальный бот {self.mirror_id} запущен")
        print(f"🪞 Зеркало #{self.mirror_id} запущено (@{self.bot_username})")
        
        try:
            if self.is_webhook:
                # Запуск с вебхуком
                webhook_url = f"{config.MIRROR_WEBHOOK_BASE}/{self.token}"
                
                await self.app.run_webhook(
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
                await self.app.run_polling()
                
        except Exception as e:
            logger.error(f"Ошибка в зеркальном боте {self.mirror_id}: {e}")
            print(f"❌ Ошибка в зеркале #{self.mirror_id}: {e}")
        finally:
            await self.stop()
    
    async def stop(self):
        """Остановка бота"""
        if self.running:
            self.running = False
            logger.info(f"Зеркальный бот {self.mirror_id} остановлен")
            print(f"🛑 Зеркало #{self.mirror_id} остановлено")

def run_bot_sync(token: str, creator_id: int, mirror_id: int, is_webhook=False):
    """Синхронный запуск бота (для потоков)"""
    bot = MirrorBot(token, creator_id, mirror_id, is_webhook)
    asyncio.run(bot.run_async())

if __name__ == "__main__":
    print("❌ Этот файл запускается только из main.py")
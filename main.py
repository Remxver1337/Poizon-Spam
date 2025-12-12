#!/usr/bin/env python3
"""
Главный бот для управления зеркалами
"""

import logging
import sqlite3
import asyncio
import os
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# ============= КОНФИГУРАЦИЯ =============
MAIN_BOT_TOKEN = "8517379434:AAGqMYBuEQZ8EMNRf3g4yBN-Q0jpm5u5eZU"  # Замени на свой
ADMIN_ID = 7404231636  # Замени на свой ID

# Создаем папки
os.makedirs("databases", exist_ok=True)
os.makedirs("logs", exist_ok=True)

# Настройки базы данных
MIRRORS_DB_PATH = "databases/mirrors.db"
MAX_USERS_PER_MIRROR = 10

# Настройки логов
LOG_LEVEL = "INFO"
LOG_FILE = "logs/bot.log"

# ============= НАСТРОЙКА ЛОГИРОВАНИЯ =============
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=getattr(logging, LOG_LEVEL),
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class MirrorManagerBot:
    """Основной бот для создания и управления зеркалами"""
    
    def __init__(self):
        self.app = None
        self.mirror_bots = {}
        self.bot_username = None
        self.setup_database()
    
    def setup_database(self):
        """Создаем таблицу для зеркал"""
        conn = sqlite3.connect(MIRRORS_DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS mirrors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                bot_token TEXT NOT NULL UNIQUE,
                bot_username TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'stopped',
                UNIQUE(user_id)
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("База данных инициализирована")
    
    async def initialize(self):
        """Инициализация бота"""
        self.app = Application.builder().token(MAIN_BOT_TOKEN).build()
        self.setup_handlers()
        
        # Получаем информацию о боте
        bot_info = await self.app.bot.get_me()
        self.bot_username = bot_info.username
        logger.info(f"Бот инициализирован: @{self.bot_username}")
    
    def setup_handlers(self):
        """Настройка обработчиков команд"""
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("mirror", self.mirror_command))
        self.app.add_handler(CommandHandler("stop", self.stop_command))
        self.app.add_handler(CommandHandler("list", self.list_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CommandHandler("status", self.status_command))
        self.app.add_handler(CallbackQueryHandler(self.button_handler))
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /start"""
        user = update.effective_user
        
        welcome_text = (
            f"👋 Привет, {user.first_name}!\n\n"
            "🤖 Я бот для создания зеркал-копий.\n\n"
            "✨ Возможности:\n"
            "• 🔄 Создать зеркало-копию\n"
            "• 🚀 Запускать рассылку\n"
            "• 📊 Мониторинг статуса\n\n"
            "📝 Основные команды:\n"
            "/mirror - Создать зеркало\n"
            "/list - Мои зеркала\n"
            "/status - Статус системы\n"
            "/help - Помощь"
        )
        
        keyboard = [
            [InlineKeyboardButton("🔄 Создать зеркало", callback_data="create_mirror")],
            [InlineKeyboardButton("📋 Мои зеркала", callback_data="list_mirrors")],
            [InlineKeyboardButton("📊 Статус", callback_data="status")],
            [InlineKeyboardButton("ℹ️ Помощь", callback_data="help")],
        ]
        
        if user.id == ADMIN_ID:
            keyboard.append([InlineKeyboardButton("⚙️ Админ", callback_data="admin")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(welcome_text, reply_markup=reply_markup)
    
    async def mirror_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /mirror для создания зеркала"""
        user_id = update.effective_user.id
        
        if not context.args:
            await update.message.reply_text(
                "📝 Использование: /mirror <токен_бота>\n\n"
                "💡 Чтобы получить токен:\n"
                "1. Создайте бота через @BotFather\n"
                "2. Скопируйте токен (например: 123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11)\n"
                "3. Отправьте мне: /mirror ваш_токен"
            )
            return
        
        bot_token = context.args[0].strip()
        
        # Проверяем, есть ли уже зеркало у пользователя
        conn = sqlite3.connect(MIRRORS_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM mirrors WHERE user_id = ?", (user_id,))
        existing = cursor.fetchone()
        
        if existing:
            conn.close()
            await update.message.reply_text("❌ У вас уже есть зеркало. Удалите старое чтобы создать новое.")
            return
        
        try:
            # Проверяем токен
            test_app = Application.builder().token(bot_token).build()
            bot_info = await test_app.bot.get_me()
            bot_username = bot_info.username
            
            # Сохраняем в базу
            cursor.execute(
                "INSERT INTO mirrors (user_id, bot_token, bot_username) VALUES (?, ?, ?)",
                (user_id, bot_token, bot_username)
            )
            mirror_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            await update.message.reply_text(
                f"✅ Зеркало создано!\n\n"
                f"🤖 Бот: @{bot_username}\n"
                f"🔗 Ссылка: https://t.me/{bot_username}\n"
                f"📊 ID зеркала: {mirror_id}\n\n"
                f"💡 Перейдите в бота и нажмите /start"
            )
            
        except Exception as e:
            conn.close()
            logger.error(f"Ошибка создания зеркала: {e}")
            await update.message.reply_text(
                f"❌ Ошибка: {str(e)}\n\n"
                "Проверьте токен и попробуйте еще раз."
            )
    
    async def stop_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Остановить зеркало"""
        user_id = update.effective_user.id
        
        conn = sqlite3.connect(MIRRORS_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM mirrors WHERE user_id = ?", (user_id,))
        mirror = cursor.fetchone()
        
        if not mirror:
            conn.close()
            await update.message.reply_text("❌ У вас нет активных зеркал")
            return
        
        mirror_id = mirror[0]
        
        # Удаляем из базы
        cursor.execute("DELETE FROM mirrors WHERE id = ?", (mirror_id,))
        conn.commit()
        conn.close()
        
        await update.message.reply_text("✅ Зеркало удалено")
    
    async def list_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать список зеркал"""
        user_id = update.effective_user.id
        
        conn = sqlite3.connect(MIRRORS_DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, bot_username, created_at, status FROM mirrors WHERE user_id = ?",
            (user_id,)
        )
        mirrors = cursor.fetchall()
        conn.close()
        
        if not mirrors:
            await update.message.reply_text("📭 У вас нет созданных зеркал")
            return
        
        text = "📋 Ваши зеркала:\n\n"
        for mirror_id, username, created_at, status in mirrors:
            status_emoji = "🟢" if status == "running" else "🔴"
            text += f"{status_emoji} @{username}\n"
            text += f"   ID: {mirror_id}\n"
            text += f"   Создан: {created_at}\n\n"
        
        await update.message.reply_text(text)
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать статус системы"""
        user_id = update.effective_user.id
        
        conn = sqlite3.connect(MIRRORS_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM mirrors")
        total_mirrors = cursor.fetchone()[0]
        
        cursor.execute("SELECT id, bot_username FROM mirrors WHERE user_id = ?", (user_id,))
        user_mirror = cursor.fetchone()
        conn.close()
        
        status_text = (
            f"📊 Статус системы\n\n"
            f"🤖 Основной бот: @{self.bot_username}\n"
            f"📈 Всего зеркал: {total_mirrors}\n"
        )
        
        if user_mirror:
            mirror_id, bot_username = user_mirror
            status_text += f"\n👤 Ваше зеркало:\n🤖 @{bot_username}\n🆔 ID: {mirror_id}"
        
        await update.message.reply_text(status_text)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Помощь"""
        text = (
            "📖 Помощь по боту\n\n"
            "✨ Основные команды:\n"
            "/start - Главное меню\n"
            "/mirror <токен> - Создать зеркало\n"
            "/list - Мои зеркала\n"
            "/stop - Удалить зеркало\n"
            "/status - Статус системы\n"
            "/help - Эта справка\n\n"
            "💡 Как создать зеркало:\n"
            "1. Создайте бота через @BotFather\n"
            "2. Скопируйте токен\n"
            "3. Отправьте: /mirror ваш_токен\n\n"
            "❓ Проблемы:\n"
            "• Убедитесь что токен правильный\n"
            "• У вас может быть только одно зеркало"
        )
        
        await update.message.reply_text(text)
    
    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик кнопок"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        
        if data == "create_mirror":
            await query.edit_message_text(
                "📝 Отправьте токен нового бота:\n\n"
                "Пример: /mirror 123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
            )
        elif data == "list_mirrors":
            await self.list_command(update, context)
        elif data == "status":
            await self.status_command(update, context)
        elif data == "help":
            await self.help_command(update, context)
        elif data == "admin":
            await update.callback_query.message.reply_text("⚙️ Админ панель в разработке")
    
    async def run_async(self):
        """Асинхронный запуск бота"""
        await self.initialize()
        
        logger.info("Основной бот запущен")
        print(f"\n{'='*50}")
        print(f"🤖 Основной бот запущен!")
        print(f"🔗 Бот: https://t.me/{self.bot_username}")
        print(f"👤 Админ ID: {ADMIN_ID}")
        print(f"{'='*50}\n")
        
        await self.app.run_polling()

def main():
    """Главная функция"""
    print("🚀 Запуск системы зеркал...")
    
    # Проверяем токен
    if not MAIN_BOT_TOKEN or "8517379434" in MAIN_BOT_TOKEN:
        print("⚠️  ВНИМАНИЕ: Используется тестовый токен!")
        print("   Для реальной работы создайте бота через @BotFather")
        print("   и замените MAIN_BOT_TOKEN в коде")
    
    # Создаем и запускаем бота
    bot = MirrorManagerBot()
    asyncio.run(bot.run_async())

if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
Главный бот для управления зеркалами
"""

import logging
import sqlite3
import asyncio
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

import config
from mirror_bot import MirrorBot

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

class MirrorManagerBot:
    """Основной бот для создания и управления зеркалами"""
    
    def __init__(self):
        self.app = Application.builder().token(config.MAIN_BOT_TOKEN).build()
        self.mirror_bots = {}  # Запущенные зеркала
        self.setup_database()
        self.setup_handlers()
    
    def setup_database(self):
        """Создаем таблицу для зеркал"""
        conn = sqlite3.connect(config.MIRRORS_DB_PATH)
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
    
    def setup_handlers(self):
        """Настройка обработчиков команд"""
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("mirror", self.mirror_command))
        self.app.add_handler(CommandHandler("stop", self.stop_command))
        self.app.add_handler(CommandHandler("list", self.list_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
        
        # Админ команды
        self.app.add_handler(CommandHandler("admin", self.admin_command))
        
        # Обработчик кнопок
        self.app.add_handler(CallbackQueryHandler(self.button_handler))
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /start"""
        user = update.effective_user
        
        welcome_text = (
            f"👋 Привет, {user.first_name}!\n\n"
            "🤖 Я бот для создания зеркал-копий.\n\n"
            "✨ Возможности:\n"
            "• 🔄 Создать зеркало-копию\n"
            "• ⚙️ Управлять зеркалами\n"
            "• 🚀 Запускать рассылку\n\n"
            "📝 Используйте команды:\n"
            "/mirror - Создать зеркало\n"
            "/list - Мои зеркала\n"
            "/help - Помощь"
        )
        
        keyboard = [
            [InlineKeyboardButton("🔄 Создать зеркало", callback_data="create_mirror")],
            [InlineKeyboardButton("📋 Мои зеркала", callback_data="list_mirrors")],
            [InlineKeyboardButton("ℹ️ Помощь", callback_data="help")]
        ]
        
        if user.id == config.ADMIN_ID:
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
                "3. Отправьте мне: /mirring ваш_токен"
            )
            return
        
        bot_token = context.args[0].strip()
        
        # Проверяем, есть ли уже зеркало у пользователя
        conn = sqlite3.connect(config.MIRRORS_DB_PATH)
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
            
            # Запускаем зеркало
            mirror_bot = MirrorBot(bot_token, user_id, mirror_id)
            
            # Запускаем в отдельном потоке
            import threading
            thread = threading.Thread(target=mirror_bot.run, daemon=True)
            thread.start()
            
            self.mirror_bots[mirror_id] = mirror_bot
            
            await update.message.reply_text(
                f"✅ Зеркало создано!\n\n"
                f"🤖 Бот: @{bot_username}\n"
                f"🔗 Ссылка: https://t.me/{bot_username}\n\n"
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
        
        conn = sqlite3.connect(config.MIRRORS_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM mirrors WHERE user_id = ?", (user_id,))
        mirror = cursor.fetchone()
        
        if not mirror:
            conn.close()
            await update.message.reply_text("❌ У вас нет активных зеркал")
            return
        
        mirror_id = mirror[0]
        
        # Останавливаем бот
        if mirror_id in self.mirror_bots:
            self.mirror_bots[mirror_id].stop()
            del self.mirror_bots[mirror_id]
        
        # Удаляем из базы
        cursor.execute("DELETE FROM mirrors WHERE id = ?", (mirror_id,))
        conn.commit()
        conn.close()
        
        await update.message.reply_text("✅ Зеркало остановлено и удалено")
    
    async def list_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать список зеркал"""
        user_id = update.effective_user.id
        
        conn = sqlite3.connect(config.MIRRORS_DB_PATH)
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
            text += f"   Создан: {created_at}\n"
            text += f"   Статус: {status}\n\n"
        
        await update.message.reply_text(text)
    
    async def admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Админ панель"""
        user_id = update.effective_user.id
        
        if user_id != config.ADMIN_ID:
            await update.message.reply_text("❌ Недостаточно прав")
            return
        
        conn = sqlite3.connect(config.MIRRORS_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM mirrors")
        total = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM mirrors WHERE status = 'running'")
        running = cursor.fetchone()[0]
        conn.close()
        
        text = (
            f"⚙️ Админ панель\n\n"
            f"📊 Статистика:\n"
            f"• Всего зеркал: {total}\n"
            f"• Запущено: {running}\n"
            f"• Остановлено: {total - running}\n\n"
            f"🔧 Действия:\n"
            f"/admin_stats - Подробная статистика\n"
            f"/admin_broadcast - Рассылка\n"
            f"/admin_restart - Перезапуск всех зеркал"
        )
        
        await update.message.reply_text(text)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Помощь"""
        text = (
            "📖 Помощь по боту\n\n"
            "✨ Основные команды:\n"
            "/start - Главное меню\n"
            "/mirror <токен> - Создать зеркало\n"
            "/list - Мои зеркала\n"
            "/stop - Остановить зеркало\n"
            "/help - Эта справка\n\n"
            "💡 Как создать зеркало:\n"
            "1. Создайте бота через @BotFather\n"
            "2. Скопируйте токен\n"
            "3. Отправьте: /mirring ваш_токен\n\n"
            "❓ Проблемы:\n"
            "• Убедитесь что токен правильный\n"
            "• У вас может быть только одно зеркало\n"
            "• Для нового зеркала удалите старое"
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
                "Пример: /mirring 123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
            )
        elif data == "list_mirrors":
            await self.list_command(update, context)
        elif data == "help":
            await self.help_command(update, context)
        elif data == "admin":
            await self.admin_command(update, context)
    
    def run(self):
        """Запуск бота"""
        logger.info("Запуск основного бота...")
        print(f"\n{'='*50}")
        print(f"🤖 Основной бот запущен!")
        print(f"🔗 Бот: https://t.me/{(self.app.bot.username)}")
        print(f"👤 Админ ID: {config.ADMIN_ID}")
        print(f"📊 Режим: {'DEBUG' if config.DEBUG else 'PRODUCTION'}")
        print(f"{'='*50}\n")
        
        self.app.run_polling()

def main():
    """Главная функция"""
    print("🚀 Запуск системы зеркал...")
    
    # Создаем и запускаем бота
    bot = MirrorManagerBot()
    bot.run()

if __name__ == "__main__":
    main()
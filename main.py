#!/usr/bin/env python3
"""
Главный бот для управления зеркалами с поддержкой вебхуков
"""

import logging
import sqlite3
import asyncio
from datetime import datetime
import ssl
import os

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
    """Основной бот для создания и управления зеркалами с вебхуками"""
    
    def __init__(self):
        self.app = None
        self.mirror_bots = {}  # Запущенные зеркала
        self.setup_database()
        
        # Создаем SSL контекст если есть сертификаты
        self.ssl_context = None
        if config.SSL_CERT and config.SSL_KEY and os.path.exists(config.SSL_CERT):
            try:
                self.ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
                self.ssl_context.load_cert_chain(config.SSL_CERT, config.SSL_KEY)
                logger.info("SSL контекст создан")
            except Exception as e:
                logger.error(f"Ошибка создания SSL контекста: {e}")
    
    def setup_database(self):
        """Создаем таблицы для зеркал и вебхуков"""
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
                webhook_url TEXT,
                is_webhook INTEGER DEFAULT 0,
                UNIQUE(user_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS webhook_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mirror_id INTEGER,
                event TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (mirror_id) REFERENCES mirrors (id)
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("База данных инициализирована")
    
    async def initialize(self):
        """Инициализация бота (вызывается асинхронно)"""
        self.app = Application.builder().token(config.MAIN_BOT_TOKEN).build()
        self.setup_handlers()
        
        # Получаем информацию о боте
        bot_info = await self.app.bot.get_me()
        self.bot_username = bot_info.username
        self.bot_id = bot_info.id
        
        logger.info(f"Бот инициализирован: @{self.bot_username}")
    
    def setup_handlers(self):
        """Настройка обработчиков команд"""
        # Основные команды
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("mirror", self.mirror_command))
        self.app.add_handler(CommandHandler("stop", self.stop_command))
        self.app.add_handler(CommandHandler("list", self.list_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CommandHandler("status", self.status_command))
        
        # Включение/выключение вебхуков
        self.app.add_handler(CommandHandler("webhook", self.webhook_command))
        
        # Админ команды
        self.app.add_handler(CommandHandler("admin", self.admin_command))
        
        # Обработчик кнопок
        self.app.add_handler(CallbackQueryHandler(self.button_handler))
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /start"""
        user = update.effective_user
        
        welcome_text = (
            f"👋 Привет, {user.first_name}!\n\n"
            "🤖 Я бот для создания зеркал-копий с вебхуками.\n\n"
            "🌐 Режим работы: "
        )
        
        if config.MODE == "webhook":
            welcome_text += f"Webhook ({config.WEBHOOK_HOST})\n"
        else:
            welcome_text += "Polling\n"
        
        welcome_text += (
            "\n✨ Возможности:\n"
            "• 🔄 Создать зеркало-копию\n"
            "• 🌐 Настроить вебхук\n"
            "• 🚀 Запускать рассылку\n"
            "• 📊 Мониторинг статуса\n\n"
            "📝 Основные команды:\n"
            "/mirror - Создать зеркало\n"
            "/webhook - Управление вебхуками\n"
            "/status - Статус системы\n"
            "/help - Помощь"
        )
        
        keyboard = [
            [InlineKeyboardButton("🔄 Создать зеркало", callback_data="create_mirror")],
            [InlineKeyboardButton("🌐 Управление вебхуками", callback_data="webhook_manage")],
            [InlineKeyboardButton("📊 Статус системы", callback_data="status")],
            [InlineKeyboardButton("📋 Мои зеркала", callback_data="list_mirrors")],
        ]
        
        if user.id == config.ADMIN_ID:
            keyboard.append([InlineKeyboardButton("⚙️ Админ панель", callback_data="admin")])
        
        keyboard.append([InlineKeyboardButton("ℹ️ Помощь", callback_data="help")])
        
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
            
            # Создаем URL вебхука для зеркала
            webhook_url = f"{config.MIRROR_WEBHOOK_BASE}/{bot_token}"
            
            # Сохраняем в базу
            cursor.execute(
                "INSERT INTO mirrors (user_id, bot_token, bot_username, webhook_url, is_webhook) VALUES (?, ?, ?, ?, ?)",
                (user_id, bot_token, bot_username, webhook_url, 1 if config.MODE == "webhook" else 0)
            )
            mirror_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            # Запускаем зеркало
            mirror_bot = MirrorBot(bot_token, user_id, mirror_id, is_webhook=(config.MODE == "webhook"))
            
            # Запускаем в отдельном потоке
            import threading
            thread = threading.Thread(target=mirror_bot.run, daemon=True)
            thread.start()
            
            self.mirror_bots[mirror_id] = {
                'bot': mirror_bot,
                'thread': thread,
                'status': 'running'
            }
            
            status_text = "🌐 с вебхуком" if config.MODE == "webhook" else "🔄 в режиме polling"
            
            await update.message.reply_text(
                f"✅ Зеркало создано и запущено!\n\n"
                f"🤖 Бот: @{bot_username}\n"
                f"🔗 Ссылка: https://t.me/{bot_username}\n"
                f"🌐 Режим: {status_text}\n"
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
    
    async def webhook_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Управление вебхуками"""
        user_id = update.effective_user.id
        
        if not context.args:
            # Показываем текущий статус
            conn = sqlite3.connect(config.MIRRORS_DB_PATH)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, bot_username, is_webhook FROM mirrors WHERE user_id = ?", 
                (user_id,)
            )
            mirror = cursor.fetchone()
            conn.close()
            
            if not mirror:
                await update.message.reply_text("❌ У вас нет созданных зеркал")
                return
            
            mirror_id, bot_username, is_webhook = mirror
            webhook_status = "✅ Включен" if is_webhook else "❌ Выключен"
            mode = config.MODE
            
            text = (
                f"🌐 Управление вебхуками\n\n"
                f"🤖 Бот: @{bot_username}\n"
                f"🆔 ID: {mirror_id}\n"
                f"🔧 Режим системы: {mode}\n"
                f"🌐 Вебхук: {webhook_status}\n\n"
                f"📝 Команды:\n"
                f"/webhook on - Включить вебхук\n"
                f"/webhook off - Выключить вебхук\n"
                f"/webhook info - Информация о вебхуке"
            )
            
            await update.message.reply_text(text)
            return
        
        action = context.args[0].lower()
        
        conn = sqlite3.connect(config.MIRRORS_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id, bot_token, bot_username FROM mirrors WHERE user_id = ?", (user_id,))
        mirror = cursor.fetchone()
        
        if not mirror:
            conn.close()
            await update.message.reply_text("❌ У вас нет созданных зеркал")
            return
        
        mirror_id, bot_token, bot_username = mirror
        
        if action == "on":
            # Включаем вебхук
            webhook_url = f"{config.MIRROR_WEBHOOK_BASE}/{bot_token}"
            cursor.execute(
                "UPDATE mirrors SET is_webhook = 1, webhook_url = ? WHERE id = ?",
                (webhook_url, mirror_id)
            )
            conn.commit()
            
            # Перезапускаем бот с вебхуком
            if mirror_id in self.mirror_bots:
                self.mirror_bots[mirror_id]['bot'].stop()
                del self.mirror_bots[mirror_id]
            
            mirror_bot = MirrorBot(bot_token, user_id, mirror_id, is_webhook=True)
            import threading
            thread = threading.Thread(target=mirror_bot.run, daemon=True)
            thread.start()
            
            self.mirror_bots[mirror_id] = {
                'bot': mirror_bot,
                'thread': thread,
                'status': 'running'
            }
            
            await update.message.reply_text(
                f"✅ Вебхук включен!\n"
                f"🔗 URL: {webhook_url}\n"
                f"🤖 Бот перезапущен с вебхуком"
            )
            
        elif action == "off":
            # Выключаем вебхук
            cursor.execute(
                "UPDATE mirrors SET is_webhook = 0 WHERE id = ?",
                (mirror_id,)
            )
            conn.commit()
            
            # Перезапускаем бот без вебхука
            if mirror_id in self.mirror_bots:
                self.mirror_bots[mirror_id]['bot'].stop()
                del self.mirror_bots[mirror_id]
            
            mirror_bot = MirrorBot(bot_token, user_id, mirror_id, is_webhook=False)
            import threading
            thread = threading.Thread(target=mirror_bot.run, daemon=True)
            thread.start()
            
            self.mirror_bots[mirror_id] = {
                'bot': mirror_bot,
                'thread': thread,
                'status': 'running'
            }
            
            await update.message.reply_text(
                "✅ Вебхук выключен!\n"
                "🤖 Бот перезапущен в режиме polling"
            )
            
        elif action == "info":
            # Информация о вебхуке
            cursor.execute("SELECT webhook_url, is_webhook FROM mirrors WHERE id = ?", (mirror_id,))
            webhook_url, is_webhook = cursor.fetchone()
            
            text = (
                f"📊 Информация о вебхуке\n\n"
                f"🤖 Бот: @{bot_username}\n"
                f"🌐 Статус: {'Включен ✅' if is_webhook else 'Выключен ❌'}\n"
                f"🔗 URL: {webhook_url or 'Не настроен'}\n"
                f"🏠 Домен: {config.WEBHOOK_HOST}\n"
                f"🚪 Порт: {config.WEBHOOK_PORT}"
            )
            
            await update.message.reply_text(text)
        
        conn.close()
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать статус системы"""
        user_id = update.effective_user.id
        
        # Получаем информацию о зеркале пользователя
        conn = sqlite3.connect(config.MIRRORS_DB_PATH)
        cursor = conn.cursor()
        
        # Статистика системы
        cursor.execute("SELECT COUNT(*) FROM mirrors")
        total_mirrors = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM mirrors WHERE is_webhook = 1")
        webhook_mirrors = cursor.fetchone()[0]
        
        cursor.execute("SELECT id, bot_username, is_webhook, status FROM mirrors WHERE user_id = ?", (user_id,))
        user_mirror = cursor.fetchone()
        
        conn.close()
        
        # Статус системы
        system_status = (
            f"📊 Статус системы\n\n"
            f"🏠 Домен: {config.WEBHOOK_HOST}\n"
            f"🚪 Порт: {config.WEBHOOK_PORT}\n"
            f"🔧 Режим: {config.MODE}\n"
            f"📈 Зеркал всего: {total_mirrors}\n"
            f"🌐 С вебхуками: {webhook_mirrors}\n"
            f"🔄 В polling: {total_mirrors - webhook_mirrors}\n"
        )
        
        if user_mirror:
            mirror_id, bot_username, is_webhook, status = user_mirror
            user_status = (
                f"\n👤 Ваше зеркало:\n"
                f"🤖 @{bot_username}\n"
                f"🆔 ID: {mirror_id}\n"
                f"📊 Статус: {status}\n"
                f"🌐 Вебхук: {'✅ Включен' if is_webhook else '❌ Выключен'}"
            )
            system_status += user_status
        
        await update.message.reply_text(system_status)
    
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
            self.mirror_bots[mirror_id]['bot'].stop()
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
            "SELECT id, bot_username, created_at, status, is_webhook FROM mirrors WHERE user_id = ?",
            (user_id,)
        )
        mirrors = cursor.fetchall()
        conn.close()
        
        if not mirrors:
            await update.message.reply_text("📭 У вас нет созданных зеркал")
            return
        
        text = "📋 Ваши зеркала:\n\n"
        for mirror_id, username, created_at, status, is_webhook in mirrors:
            status_emoji = "🟢" if status == "running" else "🔴"
            webhook_emoji = "🌐" if is_webhook else "🔄"
            text += f"{status_emoji}{webhook_emoji} @{username}\n"
            text += f"   ID: {mirror_id}\n"
            text += f"   Создан: {created_at}\n"
            text += f"   Режим: {'Webhook' if is_webhook else 'Polling'}\n\n"
        
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
        cursor.execute("SELECT COUNT(*) FROM mirrors WHERE is_webhook = 1")
        webhooks = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM mirrors WHERE status = 'running'")
        running = cursor.fetchone()[0]
        conn.close()
        
        text = (
            f"⚙️ Админ панель\n\n"
            f"📊 Статистика:\n"
            f"• Всего зеркал: {total}\n"
            f"• Запущено: {running}\n"
            f"• Вебхуков: {webhooks}\n"
            f"• Polling: {total - webhooks}\n\n"
            f"🌐 Система:\n"
            f"• Домен: {config.WEBHOOK_HOST}\n"
            f"• Порт: {config.WEBHOOK_PORT}\n"
            f"• Режим: {config.MODE}\n\n"
            f"🔧 Действия:\n"
            f"/admin_stats - Подробная статистика\n"
            f"/admin_broadcast - Рассылка\n"
            f"/admin_restart - Перезапуск всех зеркал"
        )
        
        await update.message.reply_text(text)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Помощь"""
        text = (
            f"📖 Помощь по боту\n\n"
            f"✨ Основные команды:\n"
            f"/start - Главное меню\n"
            f"/mirror <токен> - Создать зеркало\n"
            f"/webhook - Управление вебхуками\n"
            f"/status - Статус системы\n"
            f"/list - Мои зеркала\n"
            f"/stop - Остановить зеркало\n"
            f"/help - Эта справка\n\n"
            f"💡 Как создать зеркало:\n"
            f"1. Создайте бота через @BotFather\n"
            f"2. Скопируйте токен\n"
            f"3. Отправьте: /mirror ваш_токен\n\n"
            f"🌐 Вебхуки:\n"
            f"• Домен: {config.WEBHOOK_HOST}\n"
            f"• Порт: {config.WEBHOOK_PORT}\n"
            f"• Режим: {config.MODE}\n\n"
            f"❓ Проблемы:\n"
            f"• Убедитесь что токен правильный\n"
            f"• У вас может быть только одно зеркало\n"
            f"• Проверьте настройки домена и порта"
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
        elif data == "webhook_manage":
            await self.webhook_command(update, context)
        elif data == "status":
            await self.status_command(update, context)
        elif data == "list_mirrors":
            await self.list_command(update, context)
        elif data == "help":
            await self.help_command(update, context)
        elif data == "admin":
            await self.admin_command(update, context)
    
    async def run_async(self):
        """Асинхронный запуск бота"""
        await self.initialize()
        
        logger.info(f"Запуск основного бота в режиме {config.MODE}...")
        
        print(f"\n{'='*60}")
        print(f"🤖 Основной бот запущен!")
        print(f"🔗 Бот: https://t.me/{self.bot_username}")
        print(f"🆔 ID бота: {self.bot_id}")
        print(f"👤 Админ ID: {config.ADMIN_ID}")
        print(f"🌐 Домен: {config.WEBHOOK_HOST}")
        print(f"🚪 Порт: {config.WEBHOOK_PORT}")
        print(f"🔧 Режим: {config.MODE}")
        print(f"{'='*60}\n")
        
        if config.MODE == "webhook":
            # Запуск с вебхуком
            try:
                await self.app.run_webhook(
                    listen=config.WEBHOOK_LISTEN,
                    port=config.WEBHOOK_PORT,
                    url_path=config.MAIN_BOT_TOKEN,
                    webhook_url=config.MAIN_WEBHOOK_URL,
                    cert=config.SSL_CERT if os.path.exists(config.SSL_CERT) else None,
                    key=config.SSL_KEY if os.path.exists(config.SSL_KEY) else None,
                    drop_pending_updates=True
                )
            except Exception as e:
                logger.error(f"Ошибка запуска вебхука: {e}")
                print(f"❌ Ошибка вебхука: {e}")
                print("🔄 Переключаемся на polling режим...")
                await self.app.run_polling()
        else:
            # Запуск в режиме polling
            await self.app.run_polling()

def main():
    """Главная функция"""
    print("🚀 Запуск системы зеркал с вебхуками...")
    
    # Проверяем конфигурацию
    errors = []
    
    if not config.MAIN_BOT_TOKEN or "8517379434" in config.MAIN_BOT_TOKEN:
        errors.append("⚠️  Используется тестовый токен! Замените MAIN_BOT_TOKEN в config.py")
    
    if config.MODE == "webhook" and not config.WEBHOOK_HOST:
        errors.append("⚠️  Режим webhook выбран, но WEBHOOK_HOST не указан")
    
    if errors:
        print("\n❌ Ошибки конфигурации:")
        for error in errors:
            print(f"   • {error}")
        print("\n⚠️  Исправьте config.py и перезапустите бота")
        return
    
    # Создаем и запускаем бота
    bot = MirrorManagerBot()
    
    # Запускаем асинхронно
    asyncio.run(bot.run_async())

if __name__ == "__main__":
    main()
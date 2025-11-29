import logging
import sqlite3
import random
import time
import asyncio
from typing import Dict, List, Tuple, Optional
from urllib.parse import quote
from threading import Lock

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Словарь для замены кириллических букв на латинские
REPLACEMENTS = {
    'а': 'a', 'с': 'c', 'о': 'o', 'р': 'p', 'е': 'e', 'х': 'x', 'у': 'y',
    'А': 'A', 'С': 'C', 'О': 'O', 'Р': 'P', 'Е': 'E', 'Х': 'X', 'У': 'Y'
}

class DatabaseManager:
    def __init__(self, user_id: int):
        self.user_id = user_id
        self.db_name = f"user_{user_id}.db"
        self.init_database()

    def init_database(self):
        """Инициализация базы данных для пользователя"""
        try:
            with sqlite3.connect(self.db_name) as conn:
                cursor = conn.cursor()
                
                # Таблица для исходных сообщений
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS messages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        original_text TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Таблица для вариаций сообщений
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS variations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        message_id INTEGER,
                        variation_text TEXT NOT NULL,
                        send_count INTEGER DEFAULT 0,
                        FOREIGN KEY (message_id) REFERENCES messages (id)
                    )
                ''')
                
                # Таблица для чатов
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS chats (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL UNIQUE
                    )
                ''')
                
                # Таблица для пользователей
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        chat_id INTEGER,
                        username TEXT NOT NULL,
                        FOREIGN KEY (chat_id) REFERENCES chats (id)
                    )
                ''')
                
                # Создаем индексы для улучшения производительности
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_variations_send_count ON variations(send_count)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_chat_id ON users(chat_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_variations_message_id ON variations(message_id)')
                
        except Exception as e:
            logger.error(f"Ошибка инициализации БД: {e}")
            raise

    def add_message(self, original_text: str) -> int:
        """Добавление исходного сообщения"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('INSERT INTO messages (original_text) VALUES (?)', (original_text,))
            message_id = cursor.lastrowid
            return message_id

    def add_variations(self, message_id: int, variations: List[str]):
        """Добавление вариаций сообщения"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.executemany(
                'INSERT INTO variations (message_id, variation_text) VALUES (?, ?)',
                [(message_id, variation) for variation in variations]
            )

    def get_messages(self) -> List[Tuple[int, str]]:
        """Получение списка исходных сообщений"""
        try:
            with sqlite3.connect(self.db_name) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT id, original_text FROM messages ORDER BY created_at DESC')
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Ошибка получения сообщений: {e}")
            return []

    def delete_message(self, message_id: int):
        """Удаление сообщения и всех его вариаций"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM variations WHERE message_id = ?', (message_id,))
            cursor.execute('DELETE FROM messages WHERE id = ?', (message_id,))

    def add_chat(self, chat_name: str) -> int:
        """Добавление чата"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('INSERT INTO chats (name) VALUES (?)', (chat_name,))
                chat_id = cursor.lastrowid
            except sqlite3.IntegrityError:
                cursor.execute('SELECT id FROM chats WHERE name = ?', (chat_name,))
                chat_id = cursor.fetchone()[0]
            return chat_id

    def add_users(self, chat_id: int, usernames: List[str]):
        """Добавление пользователей в чат"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.executemany(
                'INSERT OR IGNORE INTO users (chat_id, username) VALUES (?, ?)',
                [(chat_id, username.strip()) for username in usernames]
            )

    def get_chats(self) -> List[Tuple[int, str]]:
        """Получение списка чатов"""
        try:
            with sqlite3.connect(self.db_name) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT id, name FROM chats ORDER BY name')
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Ошибка получения чатов: {e}")
            return []

    def delete_chat(self, chat_id: int):
        """Удаление чата и всех его пользователей"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM users WHERE chat_id = ?', (chat_id,))
            cursor.execute('DELETE FROM chats WHERE id = ?', (chat_id,))

    def get_users_by_chat(self, chat_id: int, offset: int = 0, limit: int = 25) -> List[Tuple[int, str]]:
        """Получение пользователей чата с пагинацией"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT id, username FROM users WHERE chat_id = ? LIMIT ? OFFSET ?',
                (chat_id, limit, offset)
            )
            return cursor.fetchall()

    def get_users_count_by_chat(self, chat_id: int) -> int:
        """Получение общего количества пользователей в чате"""
        try:
            with sqlite3.connect(self.db_name) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT COUNT(*) FROM users WHERE chat_id = ?', (chat_id,))
                return cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"Ошибка подсчета пользователей: {e}")
            return 0

    def get_chat_name(self, chat_id: int) -> str:
        """Получение названия чата по ID"""
        try:
            with sqlite3.connect(self.db_name) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT name FROM chats WHERE id = ?', (chat_id,))
                result = cursor.fetchone()
                return result[0] if result else "Неизвестный чат"
        except Exception as e:
            logger.error(f"Ошибка получения названия чата: {e}")
            return "Ошибка загрузки"

    def get_random_variation(self) -> Tuple[Optional[int], Optional[str]]:
        """Получение случайной вариации сообщения"""
        with sqlite3.connect(self.db_name) as conn:
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
                # Увеличиваем счетчик отправок
                cursor.execute(
                    'UPDATE variations SET send_count = send_count + 1 WHERE id = ?',
                    (variation_id,)
                )
                # Удаляем только текущую вариацию если достигнут лимит
                cursor.execute('DELETE FROM variations WHERE id = ? AND send_count >= 5', (variation_id,))
                return variation_id, variation_text
            
            return None, None

    def has_variations(self) -> bool:
        """Проверка наличия вариаций"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM variations WHERE send_count < 5')
            return cursor.fetchone()[0] > 0


class SpamBot:
    def __init__(self, token: str):
        self.application = Application.builder().token(token).build()
        self.user_states = {}
        self._state_lock = Lock()
        self.setup_handlers()

    def setup_handlers(self):
        """Настройка обработчиков"""
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CallbackQueryHandler(self.handle_button, pattern="^main_"))
        self.application.add_handler(CallbackQueryHandler(self.handle_messages, pattern="^messages_"))
        self.application.add_handler(CallbackQueryHandler(self.handle_users, pattern="^users_"))
        self.application.add_handler(CallbackQueryHandler(self.handle_spam, pattern="^spam_"))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text_input))

    def set_user_state(self, user_id: int, state: str):
        """Безопасная установка состояния пользователя"""
        with self._state_lock:
            self.user_states[user_id] = state

    def get_user_state(self, user_id: int) -> Optional[str]:
        """Безопасное получение состояния пользователя"""
        with self._state_lock:
            return self.user_states.get(user_id)

    def delete_user_state(self, user_id: int):
        """Безопасное удаление состояния пользователя"""
        with self._state_lock:
            if user_id in self.user_states:
                del self.user_states[user_id]

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        user_id = update.effective_user.id
        
        welcome_text = (
            "🌟 *Добро пожаловать!* 🌟\n\n"
            "💬 *Для начала работы используйте кнопки ниже:*\n\n"
            "📝 *Создание сообщений* - создайте и управляйте вариациями сообщений\n"
            "👥 *Мои пользователи* - добавьте списки пользователей для рассылки\n"
            "🚀 *Начать спам* - запустите рассылку сообщений\n\n"
            "💡 *Бот готов к работе! Выберите раздел:*"
        )
        
        keyboard = [
            [InlineKeyboardButton("📝 Создание сообщений", callback_data="main_messages")],
            [InlineKeyboardButton("👥 Мои пользователи", callback_data="main_users")],
            [InlineKeyboardButton("🚀 Начать спам", callback_data="main_spam")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')

    async def show_main_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать главное меню"""
        query = update.callback_query
        await query.answer()
        
        menu_text = (
            "🎯 *Главное меню*\n\n"
            "💡 *Выберите нужный раздел:*"
        )
        
        keyboard = [
            [InlineKeyboardButton("📝 Создание сообщений", callback_data="main_messages")],
            [InlineKeyboardButton("👥 Мои пользователи", callback_data="main_users")],
            [InlineKeyboardButton("🚀 Начать спам", callback_data="main_spam")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(menu_text, reply_markup=reply_markup, parse_mode='Markdown')

    async def handle_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик кнопок главного меню"""
        query = update.callback_query
        await query.answer()
        
        try:
            data = query.data
            
            if data == "main_messages":
                await self.show_messages_menu(update, context)
            elif data == "main_users":
                await self.show_users_menu(update, context)
            elif data == "main_spam":
                await self.show_spam_menu(update, context)
            elif data == "main_back":
                await self.show_main_menu(update, context)
                
        except Exception as e:
            logger.error(f"Ошибка в handle_button: {e}")
            error_text = (
                "❌ *Произошла ошибка при обработке запроса*\n\n"
                "💡 *Попробуйте еще раз или перезапустите бота командой /start*"
            )
            try:
                await query.edit_message_text(error_text, parse_mode='Markdown')
            except:
                await context.bot.send_message(
                    chat_id=query.from_user.id,
                    text=error_text,
                    parse_mode='Markdown'
                )

    # РАЗДЕЛ СОЗДАНИЯ СООБЩЕНИЙ
    async def show_messages_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Меню создания сообщений"""
        query = update.callback_query
        await query.answer()
        
        menu_text = (
            "📝 *Создание сообщений*\n\n"
            "✨ *Доступные действия:*\n"
            "• 📄 Создать новое сообщение с вариациями\n"
            "• 🗑️ Удалить существующее сообщение\n\n"
            "💡 *Выберите действие:*"
        )
        
        keyboard = [
            [InlineKeyboardButton("📄 Создать новое сообщение", callback_data="messages_create")],
            [InlineKeyboardButton("🗑️ Удалить сообщение", callback_data="messages_delete")],
            [InlineKeyboardButton("🔙 Назад", callback_data="main_back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(menu_text, reply_markup=reply_markup, parse_mode='Markdown')

    async def handle_messages(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик кнопок раздела сообщений"""
        query = update.callback_query
        data = query.data
        user_id = query.from_user.id
        
        await query.answer()
        
        if data == "messages_create":
            self.set_user_state(user_id, "waiting_for_message")
            create_text = (
                "🆕 *Создание нового сообщения*\n\n"
                "📨 *Введите исходное сообщение для создания вариаций:*\n\n"
                "💡 *Бот автоматически создаст 500 уникальных вариаций*\n"
                "⏱️ *Лимит времени на генерацию: 10 секунд*\n\n"
                "⚠️ *Сообщение должно содержать символы для замены:*\n"
                "`а, е, с, о, р, х, у` (русские и английские)"
            )
            await query.edit_message_text(create_text, parse_mode='Markdown')
        
        elif data == "messages_delete":
            await self.show_message_list(update, context)
        
        elif data.startswith("messages_delete_"):
            message_id = int(data.split("_")[2])
            db = DatabaseManager(user_id)
            db.delete_message(message_id)
            await query.answer("✅ Сообщение и все его вариации удалены!")
            await self.show_messages_menu(update, context)
        
        elif data == "messages_back":
            await self.show_messages_menu(update, context)

    async def show_message_list(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать список сообщений для удаления"""
        query = update.callback_query
        user_id = query.from_user.id
        
        await query.answer()
        
        db = DatabaseManager(user_id)
        messages = db.get_messages()
        
        if not messages:
            no_messages_text = (
                "📭 *У вас нет созданных сообщений*\n\n"
                "💡 *Создайте первое сообщение для работы*"
            )
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="messages_back")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(no_messages_text, reply_markup=reply_markup, parse_mode='Markdown')
            return
        
        list_text = (
            "🗑️ *Удаление сообщений*\n\n"
            "📋 *Выберите сообщение для удаления:*\n\n"
            "⚠️ *Внимание: будут удалены ВСЕ вариации этого сообщения*"
        )
        
        keyboard = []
        for msg_id, text in messages:
            display_text = text[:50] + "..." if len(text) > 50 else text
            keyboard.append([InlineKeyboardButton(f"📄 {display_text}", callback_data=f"messages_delete_{msg_id}")])
        
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="messages_back")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(list_text, reply_markup=reply_markup, parse_mode='Markdown')

    def validate_message(self, text: str) -> Tuple[bool, Optional[str]]:
        """
        Валидация сообщения для генерации вариаций
        
        Returns:
            Tuple[bool, Optional[str]]: (is_valid, error_message)
        """
        # Проверка минимальной длины
        if len(text) < 10:
            return False, "❌ *Сообщение слишком короткое*\n\n💡 *Минимальная длина: 10 символов*"
        
        # Проверка наличия символов для замены
        has_replaceable_chars = any(char in REPLACEMENTS for char in text)
        if not has_replaceable_chars:
            error_msg = (
                "❌ *Недостаточно символов для замены*\n\n"
                "💡 *Сообщение должно содержать символы:*\n"
                "`а, е, с, о, р, х, у` (русские)\n\n"
                "✨ *Пример хорошего сообщения:*\n"
                "`«Привет! Как дела?»`\n\n"
                "🚫 *Пример плохого сообщения:*\n"
                "`«Hi! How are you?»`"
            )
            return False, error_msg
        
        # Проверка максимальной длины
        if len(text) > 1000:
            return False, "❌ *Сообщение слишком длинное*\n\n💡 *Максимальная длина: 1000 символов*"
        
        return True, None

    async def generate_variations_with_timeout(self, text: str, count: int = 500) -> List[str]:
        """Генерация вариаций с ограничением по времени"""
        try:
            # Запускаем генерацию с таймаутом
            variations = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None, self._generate_variations_sync, text, count
                ),
                timeout=10.0  # 10 секунд таймаут
            )
            return variations
        except asyncio.TimeoutError:
            logger.warning(f"Таймаут генерации вариаций для текста: {text[:50]}...")
            raise TimeoutError("Генерация вариаций заняла слишком много времени (более 10 секунд)")

    def _generate_variations_sync(self, text: str, count: int = 500) -> List[str]:
        """Синхронная генерация вариаций (выполняется в отдельном потоке)"""
        variations = set()
        chars_to_replace = [char for char in text if char in REPLACEMENTS]
        
        if not chars_to_replace:
            return []
        
        max_possible_variations = min(count, 2 ** len(chars_to_replace))
        start_time = time.time()
        
        while len(variations) < max_possible_variations:
            # Проверяем, не прошло ли уже 9 секунд (оставляем запас)
            if time.time() - start_time > 9:
                break
                
            variation = list(text)
            replacements_made = 0
            
            # Увеличиваем вероятность замены для большего разнообразия
            for i, char in enumerate(variation):
                if char in REPLACEMENTS and random.random() < 0.5:  # 50% вероятность замены
                    variation[i] = REPLACEMENTS[char]
                    replacements_made += 1
            
            variation_str = ''.join(variation)
            if variation_str != text and replacements_made > 0:
                variations.add(variation_str)
            
            # Если долго не получается создать новые вариации, выходим
            if len(variations) >= max_possible_variations:
                break
        
        return list(variations)

    # РАЗДЕЛ МОИХ ПОЛЬЗОВАТЕЛЕЙ
    async def show_users_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Меню пользователей"""
        query = update.callback_query
        await query.answer()
        
        menu_text = (
            "👥 *Мои пользователи*\n\n"
            "✨ *Доступные действия:*\n"
            "• ➕ Добавить новых пользователей\n"
            "• 🗑️ Удалить список пользователей\n\n"
            "💡 *Выберите действие:*"
        )
        
        keyboard = [
            [InlineKeyboardButton("➕ Добавить пользователей", callback_data="users_add")],
            [InlineKeyboardButton("🗑️ Удалить список пользователей", callback_data="users_delete")],
            [InlineKeyboardButton("🔙 Назад", callback_data="main_back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(menu_text, reply_markup=reply_markup, parse_mode='Markdown')

    async def handle_users(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик кнопок раздела пользователей"""
        query = update.callback_query
        data = query.data
        user_id = query.from_user.id
        
        await query.answer()
        
        if data == "users_add":
            self.set_user_state(user_id, "waiting_for_chat_name")
            add_text = (
                "➕ *Добавление пользователей*\n\n"
                "🏷️ *Напишите название чата из которого взяли пользователей:*\n\n"
                "💡 *Пример: Основной чат, Резервный список*"
            )
            await query.edit_message_text(add_text, parse_mode='Markdown')
        
        elif data == "users_delete":
            await self.show_chat_list(update, context)
        
        elif data.startswith("users_delete_"):
            chat_id = int(data.split("_")[2])
            db = DatabaseManager(user_id)
            db.delete_chat(chat_id)
            await query.answer("✅ Чат и все пользователи удалены!")
            await self.show_users_menu(update, context)
        
        elif data == "users_back":
            await self.show_users_menu(update, context)

    async def show_chat_list(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать список чатов для удаления"""
        query = update.callback_query
        user_id = query.from_user.id
        
        await query.answer()
        
        db = DatabaseManager(user_id)
        chats = db.get_chats()
        
        if not chats:
            no_chats_text = (
                "📭 *У вас нет добавленных чатов*\n\n"
                "💡 *Добавьте первый чат с пользователями*"
            )
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="users_back")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(no_chats_text, reply_markup=reply_markup, parse_mode='Markdown')
            return
        
        list_text = (
            "🗑️ *Удаление чатов*\n\n"
            "📋 *Выберите чат для удаления:*\n\n"
            "⚠️ *Внимание: будут удалены ВСЕ пользователи этого чата*"
        )
        
        keyboard = []
        for chat_id, name in chats:
            keyboard.append([InlineKeyboardButton(f"👥 {name}", callback_data=f"users_delete_{chat_id}")])
        
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="users_back")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(list_text, reply_markup=reply_markup, parse_mode='Markdown')

    # РАЗДЕЛ НАЧАТЬ СПАМ
    async def show_spam_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Меню рассылки"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        
        try:
            # Показываем сообщение о загрузке
            loading_message = await query.edit_message_text("⏳ *Загружаем список чатов...*", parse_mode='Markdown')
            
            db = DatabaseManager(user_id)
            chats = db.get_chats()
            
            if not chats:
                no_chats_text = (
                    "📭 *У вас нет добавленных чатов*\n\n"
                    "💡 *Сначала добавьте пользователей в разделе \"👥 Мои пользователи\"*"
                )
                keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="main_back")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await loading_message.edit_text(no_chats_text, reply_markup=reply_markup, parse_mode='Markdown')
                return
            
            menu_text = (
                "🚀 *Начать рассылку*\n\n"
                f"📋 *Доступно чатов: {len(chats)}*\n\n"
                "💡 *Выберите чат для рассылки:*"
            )
            
            keyboard = []
            for chat_id, name in chats:
                # Обрезаем длинные названия
                display_name = name[:30] + "..." if len(name) > 30 else name
                keyboard.append([InlineKeyboardButton(f"👥 {display_name}", callback_data=f"spam_chat_{chat_id}_0")])
            
            keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="main_back")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await loading_message.edit_text(menu_text, reply_markup=reply_markup, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Ошибка в show_spam_menu: {e}")
            error_text = (
                "❌ *Ошибка при загрузке чатов*\n\n"
                "💡 *Попробуйте позже или проверьте базу данных*"
            )
            try:
                await query.edit_message_text(error_text, parse_mode='Markdown')
            except:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=error_text,
                    parse_mode='Markdown'
                )

    async def handle_spam(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик кнопок раздела рассылки"""
        query = update.callback_query
        data = query.data
        user_id = query.from_user.id
        
        await query.answer()
        
        try:
            if data.startswith("spam_chat_"):
                parts = data.split("_")
                chat_id = int(parts[2])
                page = int(parts[3])
                await self.show_users_for_spam(update, context, chat_id, page)
            
            elif data.startswith("spam_user_"):
                parts = data.split("_")
                chat_id = int(parts[2])
                user_id_for_spam = int(parts[3])
                page = int(parts[4])
                await self.send_spam_message(update, context, user_id_for_spam, chat_id, page)
            
            elif data.startswith("spam_page_"):
                parts = data.split("_")
                chat_id = int(parts[2])
                page = int(parts[3])
                await self.show_users_for_spam(update, context, chat_id, page)
            
            elif data == "spam_back":
                await self.show_spam_menu(update, context)
                
        except Exception as e:
            logger.error(f"Ошибка в handle_spam: {e}")
            await query.answer("❌ Произошла ошибка при обработке запроса", show_alert=True)

    async def show_users_for_spam(self, update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int, page: int = 0):
        """Показать пользователей чата для рассылки"""
        query = update.callback_query
        user_id = query.from_user.id
        
        await query.answer()
        
        try:
            # Показываем загрузку
            await query.edit_message_text("⏳ *Загружаем список пользователей...*", parse_mode='Markdown')
            
            db = DatabaseManager(user_id)
            
            # Проверяем существование чата
            chat_name = db.get_chat_name(chat_id)
            if chat_name == "Ошибка загрузки":
                await query.edit_message_text(
                    "❌ *Чат не найден*\n\n"
                    "💡 *Вернитесь к списку чатов*",
                    parse_mode='Markdown'
                )
                return
            
            # Получаем пользователей с пагинацией
            users = db.get_users_by_chat(chat_id, page * 25, 25)
            total_users = db.get_users_count_by_chat(chat_id)
            
            if not users:
                no_users_text = (
                    f"👥 *Чат: {chat_name}*\n\n"
                    "📭 *В этом чате нет пользователей*\n\n"
                    "💡 *Добавьте пользователей через раздел «👥 Мои пользователи»*"
                )
                keyboard = [[InlineKeyboardButton("🔙 Назад к чатам", callback_data="main_spam")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(no_users_text, reply_markup=reply_markup, parse_mode='Markdown')
                return
            
            # Проверяем наличие вариаций
            has_variations = db.has_variations()
            
            users_text = (
                f"👥 *Чат: {chat_name}*\n"
                f"📄 *Страница: {page + 1} из {((total_users - 1) // 25) + 1}*\n"
                f"👤 *Всего пользователей: {total_users}*\n\n"
            )
            
            if not has_variations:
                users_text += "❌ *Нет доступных вариаций сообщений!*\n💡 *Создайте сообщения в разделе «📝 Создание сообщений»*\n\n"
            else:
                users_text += "💡 *Нажмите на кнопку с пользователем для отправки сообщения:*\n\n"
            
            keyboard = []
            active_users = 0
            
            for user_id_db, username in users:
                if has_variations:
                    variation_id, variation_text = db.get_random_variation()
                    if variation_text:
                        spam_link = f"https://t.me/{username}?text={quote(variation_text)}"
                        keyboard.append([InlineKeyboardButton(
                            f"📨 {username}", 
                            callback_data=f"spam_user_{chat_id}_{user_id_db}_{page}",
                            url=spam_link
                        )])
                        active_users += 1
                    else:
                        keyboard.append([InlineKeyboardButton(
                            f"❌ {username} (нет вариаций)", 
                            callback_data="no_action"
                        )])
                else:
                    keyboard.append([InlineKeyboardButton(
                        f"❌ {username}", 
                        callback_data="no_action"
                    )])
            
            if has_variations:
                users_text += f"✅ *Доступно для отправки: {active_users} пользователей*"
            
            # Навигация
            nav_buttons = []
            if page > 0:
                nav_buttons.append(InlineKeyboardButton("◀️ Назад", callback_data=f"spam_page_{chat_id}_{page-1}"))
            
            nav_buttons.append(InlineKeyboardButton(f"{page + 1}", callback_data="no_action"))
            
            if (page + 1) * 25 < total_users:
                nav_buttons.append(InlineKeyboardButton("Вперед ▶️", callback_data=f"spam_page_{chat_id}_{page+1}"))
            
            if nav_buttons:
                keyboard.append(nav_buttons)
            
            keyboard.append([InlineKeyboardButton("🔙 Назад к чатам", callback_data="main_spam")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(users_text, reply_markup=reply_markup, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Ошибка в show_users_for_spam: {e}")
            error_text = (
                "❌ *Ошибка при загрузке пользователей*\n\n"
                "💡 *Попробуйте еще раз или проверьте базу данных*"
            )
            await query.edit_message_text(error_text, parse_mode='Markdown')

    async def send_spam_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user_id_db: int, chat_id: int, page: int):
        """Отправка спам-сообщения"""
        query = update.callback_query
        user_id = query.from_user.id
        
        await query.answer()
        
        try:
            db = DatabaseManager(user_id)
            
            users = db.get_users_by_chat(chat_id, page * 25, 25)
            target_user = next((user for user in users if user[0] == user_id_db), None)
            
            if target_user:
                username = target_user[1]
                variation_id, variation_text = db.get_random_variation()
                
                if variation_text:
                    spam_link = f"https://t.me/{username}?text={quote(variation_text)}"
                    
                    success_text = (
                        f"📨 *Сообщение отправлено!*\n\n"
                        f"👤 *Пользователь:* {username}\n"
                        f"💬 *Текст:* {variation_text}\n\n"
                        f"[🔄 Открыть чат]({spam_link})"
                    )
                    
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=success_text,
                        parse_mode='Markdown',
                        disable_web_page_preview=True
                    )
                    
                    # Обновляем список пользователей
                    await self.show_users_for_spam(update, context, chat_id, page)
                    
                else:
                    await query.answer("❌ Нет доступных вариаций сообщений!", show_alert=True)
            else:
                await query.answer("❌ Пользователь не найден!", show_alert=True)
                
        except Exception as e:
            logger.error(f"Ошибка в send_spam_message: {e}")
            await query.answer("❌ Ошибка при отправке сообщения", show_alert=True)

    # ОБРАБОТЧИК ТЕКСТОВОГО ВВОДА
    async def handle_text_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик текстового ввода"""
        user_id = update.message.from_user.id
        text = update.message.text.strip()
        
        current_state = self.get_user_state(user_id)
        if not current_state:
            help_text = (
                "💡 *Используйте кнопки меню для навигации*\n\n"
                "🔍 *Если вы потерялись, нажмите /start*"
            )
            await update.message.reply_text(help_text, parse_mode='Markdown')
            return
        
        db = DatabaseManager(user_id)
        
        try:
            if current_state == "waiting_for_message":
                # Валидация сообщения
                is_valid, error_message = self.validate_message(text)
                if not is_valid:
                    await update.message.reply_text(error_message, parse_mode='Markdown')
                    return
                
                await update.message.reply_text("⏳ *Генерирую вариации...*", parse_mode='Markdown')
                
                try:
                    # Генерация с таймаутом
                    variations = await self.generate_variations_with_timeout(text, 500)
                    
                    if not variations:
                        await update.message.reply_text(
                            "❌ *Не удалось создать вариации*\n\n"
                            "💡 *Попробуйте другое сообщение с большим количеством символов для замены*",
                            parse_mode='Markdown'
                        )
                        return
                    
                    message_id = db.add_message(text)
                    db.add_variations(message_id, variations)
                    
                    self.delete_user_state(user_id)
                    
                    success_text = (
                        f"✅ *Успешно создано!*\n\n"
                        f"📊 *Создано вариаций:* {len(variations)}\n"
                        f"💬 *Исходное сообщение:* {text}\n\n"
                        f"💡 *Теперь вы можете начать рассылку*"
                    )
                    
                    await update.message.reply_text(success_text, parse_mode='Markdown')
                    await self.show_main_menu_from_message(update, context)
                    
                except TimeoutError:
                    self.delete_user_state(user_id)
                    await update.message.reply_text(
                        "❌ *Генерация заняла слишком много времени*\n\n"
                        "💡 *Попробуйте более короткое сообщение или сообщение с меньшим количеством символов для замены*",
                        parse_mode='Markdown'
                    )
                except Exception as e:
                    self.delete_user_state(user_id)
                    logger.error(f"Ошибка генерации вариаций: {e}")
                    await update.message.reply_text(
                        "❌ *Произошла ошибка при генерации вариаций*\n\n"
                        "💡 *Попробуйте еще раз*",
                        parse_mode='Markdown'
                    )
            
            elif current_state == "waiting_for_chat_name":
                if not text:
                    await update.message.reply_text(
                        "❌ *Название чата не может быть пустым*",
                        parse_mode='Markdown'
                    )
                    return
                
                context.user_data['current_chat_name'] = text
                self.set_user_state(user_id, "waiting_for_users")
                
                users_text = (
                    f"🏷️ *Название чата сохранено:* {text}\n\n"
                    f"📝 *Отправьте список пользователей в столбик:*\n\n"
                    f"💡 *Каждый username с новой строки*"
                )
                
                await update.message.reply_text(users_text, parse_mode='Markdown')
            
            elif current_state == "waiting_for_users":
                chat_name = context.user_data.get('current_chat_name')
                usernames = text.split('\n')
                
                cleaned_usernames = []
                for username in usernames:
                    cleaned = username.strip().lstrip('@')
                    if cleaned and len(cleaned) >= 5:  # Минимальная длина username
                        cleaned_usernames.append(cleaned)
                
                if cleaned_usernames:
                    chat_id = db.add_chat(chat_name)
                    db.add_users(chat_id, cleaned_usernames)
                    
                    self.delete_user_state(user_id)
                    if 'current_chat_name' in context.user_data:
                        del context.user_data['current_chat_name']
                    
                    success_text = (
                        f"✅ *Пользователи добавлены!*\n\n"
                        f"🏷️ *Чат:* {chat_name}\n"
                        f"👥 *Добавлено пользователей:* {len(cleaned_usernames)}\n\n"
                        f"💡 *Теперь вы можете начать рассылку*"
                    )
                    
                    await update.message.reply_text(success_text, parse_mode='Markdown')
                    await self.show_main_menu_from_message(update, context)
                else:
                    error_text = (
                        "❌ *Список пользователей пуст или содержит некорректные username*\n\n"
                        "💡 *Отправьте список username'ов в столбик (минимум 5 символов)*"
                    )
                    await update.message.reply_text(error_text, parse_mode='Markdown')
                    
        except Exception as e:
            logger.error(f"Ошибка в handle_text_input: {e}")
            error_text = (
                "❌ *Произошла ошибка при обработке данных*\n\n"
                "💡 *Попробуйте еще раз*"
            )
            await update.message.reply_text(error_text, parse_mode='Markdown')

    async def show_main_menu_from_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать главное меню из текстового сообщения"""
        menu_text = (
            "🎯 *Главное меню*\n\n"
            "💡 *Выберите нужный раздел:*"
        )
        
        keyboard = [
            [InlineKeyboardButton("📝 Создание сообщений", callback_data="main_messages")],
            [InlineKeyboardButton("👥 Мои пользователи", callback_data="main_users")],
            [InlineKeyboardButton("🚀 Начать спам", callback_data="main_spam")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(menu_text, reply_markup=reply_markup, parse_mode='Markdown')

    def run(self):
        """Запуск бота"""
        self.application.run_polling()

# Запуск бота
if __name__ == "__main__":
    import os
    BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', "8517379434:AAGqMYBuEQZ8EMNRf3g4yBN-Q0jpm5u5eZU")
    
    bot = SpamBot(BOT_TOKEN)
    print("🤖 Бот запущен и готов к работе!")
    print("💡 Используйте /start в Telegram для начала работы")
    bot.run()
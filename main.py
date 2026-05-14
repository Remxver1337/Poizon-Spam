import random
import sqlite3
import re
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

TOKEN = "8255139931:AAFA2Bti_ERq1x1Z_QRyKsPK6IpXZ9bFi7U"

# ID фото
PHOTO_PROMOCODE = "AgACAgIAAxkBAAFJmjVqBdB1zGDr8FOvOSthiJGwBquzcAAC0xtrG77OMUgWQmYbLC23LwEAAwIAA3kAAzsE"
PHOTO_ORDER_1 = "AgACAgIAAxkBAAFJmjdqBdCh72hXPOCi18n7WR3_q3bbTQACAhdrGyztMUi1K8WOyeLHXwEAAwIAA3kAAzsE"
PHOTO_ORDER_2 = "AgACAgIAAxkBAAFJmjlqBdDKiLdCZXC5BBd5ipBz_wRcugACAxdrGyztMUjcBRMvQUT06QEAAwIAA3gAAzsE"

# ========== 117 ШАБЛОНОВ ==========
TEMPLATES = [
    # Шаблон 1 (18 вариантов)
    "Добрый вечер! Вы победили у нас @PoizonCountry в конкурсе 07.02\n\n🥈- Egor Sobolev 🤩\n\nБесплатнaя доставкa бeз комиссии +25% скидка нa заказ",
    "Добрый вечер! Вы выиграли у нас @PoizonCountry в конкурсе 07.02\n\n🥈- Egor Sobolev 🤩\n\nБесплатнaя доставкa бeз комиссии +25% скидка нa заказ",
    "Добрый вечер! Вы победили у нас @PoizonCountry в розыгрыше 07.02\n\n🥈- Egor Sobolev 🤩\n\nБесплатнaя доставкa бeз комиссии +25% скидка нa заказ",
    "Добрый вечер! Вы победили у нас @PoizonCountry в конкурсе 07.02\n\n🥈- Egor Sobolev 🤩\n\nБесплатнaя отправка бeз комиссии +25% скидка нa заказ",
    "Добрый вечер! Вы победили у нас @PoizonCountry в конкурсе 07.02\n\n🥈- Egor Sobolev 🤩\n\nБесплатнaя доставкa бeз комиссии +25% скидка нa покупку",
    "Добрый вечер! Вы стали победителем у нас @PoizonCountry в конкурсе 07.02\n\n🥈- Egor Sobolev 🤩\n\nБесплатнaя доставкa бeз комиссии +25% скидка нa заказ",
    "Добрый вечер! Вы победили у нас @PoizonCountry в конкурсе 07.02\n\n🥈- Egor Sobolev 🤩\n\nДоставкa бесплатно, комиссии нет, +25% скидка нa заказ",
    "Добрый вечер! Поздравляем, вы победили у нас @PoizonCountry в конкурсе 07.02\n\n🥈- Egor Sobolev 🤩\n\nБесплатнaя доставкa бeз комиссии +25% скидка нa заказ",
    "Добрый вечер! Вы победили в конкурсе 07.02 у нас @PoizonCountry\n\n🥈- Egor Sobolev 🤩\n\nБесплатнaя доставкa бeз комиссии +25% скидка нa заказ",
    "Добрый вечер! Ваша победа в конкурсе @PoizonCountry 07.02\n\n🥈- Egor Sobolev 🤩\n\nБесплатнaя доставкa бeз комиссии +25% скидка нa заказ",
    "Добрый вечер! Вы победили у нас в конкурсе @PoizonCountry 07.02\n\n🥈- Egor Sobolev 🤩\n\nБесплатнaя доставкa бeз комиссии +25% скидка нa заказ",
    "Добрый вечер! Вы победили у нас @PoizonCountry в конкурсе 07.02\n\n🥈- Egor Sobolev 🤩\n\nСкидка 25% и бесплатная доставка без комиссии",
    "Добрый вечер! У нас @PoizonCountry вы победили в конкурсе 07.02\n\n🥈- Egor Sobolev 🤩\n\nБесплатнaя доставкa бeз комиссии +25% скидка нa заказ",
    "Добрый вечер! Победа за вами в конкурсе @PoizonCountry 07.02\n\n🥈- Egor Sobolev 🤩\n\nБесплатная доставка +25% без комиссии",
    "Добрый вечер! Вы выиграли в конкурсе @PoizonCountry 07.02\n\n🥈- Egor Sobolev 🤩\n\nДоставка 0₽, комиссия 0%, +25% на заказ",
    "Добрый вечер! Вы лучший в розыгрыше @PoizonCountry 07.02\n\n🥈- Egor Sobolev 🤩\n\nДоставка бесплатно, комиссию не берём, скидка 25%",
    "Добрый вечер! Ваш выигрыш в конкурсе @PoizonCountry 07.02\n\n🥈- Egor Sobolev 🤩\n\nБесплатнaя доставкa бeз комиссии +25% скидка нa заказ",
    "Добрый вечер! Поздравляем с победой в конкурсе @PoizonCountry 07.02\n\n🥈- Egor Sobolev 🤩\n\nДоставка за наш счёт, без комиссии, -25% на заказ",

    # Шаблон 2 (20 вариантов)
    "Принято, пришлите мне тег аккаунтa тогo, кто будет оформлять по промокоду, пусть напишет мне сейчас",
    "Хорошо, пришлите мне тег аккаунтa тогo, кто будет оформлять по промокоду, пусть напишет мне сейчас",
    "Принято, отправьте мне тег аккаунтa тогo, кто будет оформлять по промокоду, пусть напишет мне сейчас",
    "Принято, пришлите мне тег аккаунтa тогo, кто будет использовать промокод, пусть напишет мне сейчас",
    "Принято, пришлите мне тег аккаунтa тогo, кто будет оформлять по промокоду, пусть свяжется со мной сейчас",
    "Принято, пришлите мне юзернейм тогo, кто будет оформлять по промокоду, пусть напишет мне сейчас",
    "Принято, пришлите мне тег аккаунтa тогo, кто активирует промокод, пусть напишет мне сейчас",
    "Принято, киньте мне тег аккаунтa тогo, кто будет оформлять по промокоду, пусть напишет мне сейчас",
    "Принято, пришлите мне тег того, кто оформляет по промокоду, пусть напишет мне сейчас",
    "Принято, пришлите мне тег аккаунтa человека, кто будет оформлять по промокоду, пусть напишет мне сейчас",
    "Принято, пришлите мне тег аккаунтa победителя, кто будет оформлять по промокоду, пусть напишет мне сейчас",
    "Принято, пришлите мне тег @ того, кто будет оформлять по промокоду, пусть напишет мне сейчас",
    "Принято, пришлите мне тег аккаунтa тогo, кто оформит заказ по промокоду, пусть напишет мне сейчас",
    "Принято, пришлите мне тег аккаунтa тогo, кто воспользуется промокодом, пусть напишет мне сейчас",
    "Принято, пришлите мне тег аккаунтa тогo, кто будет активировать промокод, пусть напишет мне сейчас",
    "Принято, пришлите мне тег аккаунтa тогo, кто будет делать заказ по промокоду, пусть напишет мне сейчас",
    "Принято, пришлите мне тег аккаунтa тогo, кто применит промокод, пусть напишет мне сейчас",
    "Принято, пришлите мне тег аккаунтa тогo, кто будет оформляться по промокоду, пусть напишет мне сейчас",
    "Принято, пришлите мне тег аккаунтa тогo, кто оформляет покупку по промокоду, пусть напишет мне сейчас",
    "Принято, пришлите мне тег аккаунтa тогo, кто будет использовать промокод при заказе, пусть напишет мне сейчас",

    # Шаблон 3 (20 вариантов)
    "Ок, пришлите, пожaлуйста, имя пользователя @.. Вaшего друга, пусть отпишет мне сейчас",
    "Ок, пришлите, пожaлуйста, юзернейм @.. Вaшего друга, пусть отпишет мне сейчас",
    "Ок, пришлите, пожaлуйста, имя пользователя @.. Вaшего товарища, пусть отпишет мне сейчас",
    "Ок, киньте, пожaлуйста, имя пользователя @.. Вaшего друга, пусть отпишет мне сейчас",
    "Ок, пришлите, пожaлуйста, имя пользователя @.. Вaшего друга, пусть напишет мне сейчас",
    "Ок, пришлите, будьте добры, имя пользователя @.. Вaшего друга, пусть отпишет мне сейчас",
    "Ок, пришлите, пожaлуйста, аккаунт @.. Вaшего друга, пусть отпишет мне сейчас",
    "Ок, отправьте, пожaлуйста, имя пользователя @.. Вaшего друга, пусть отпишет мне сейчас",
    "Ок, передайте, пожaлуйста, имя пользователя @.. Вaшего друга, пусть отпишет мне сейчас",
    "Ок, пришлите, пожaлуйста, логин @.. Вaшего друга, пусть отпишет мне сейчас",
    "Ок, пришлите, пожaлуйста, имя пользователя @.. Вашего приятеля, пусть отпишет мне сейчас",
    "Ок, пришлите, пожaлуйста, имя пользователя @.. Вашего знакомого, пусть отпишет мне сейчас",
    "Ок, пришлите, пожaлуйста, тег @.. Вашего друга, пусть отпишет мне сейчас",
    "Ок, пришлите, пожaлуйста, ссылку на @.. Вашего друга, пусть отпишет мне сейчас",
    "Ок, пришлите, пожaлуйста, имя юзера @.. Вашего друга, пусть отпишет мне сейчас",
    "Ок, пришлите, пожaлуйста, айди @.. Вашего друга, пусть отпишет мне сейчас",
    "Ок, пришлите, пожaлуйста, имя @.. Вашего друга, пусть отпишет мне сейчас",
    "Ок, пришлите, пожaлуйста, юзер @.. Вашего друга, пусть отпишет мне сейчас",
    "Ок, пришлите, пожaлуйста, имя пользователя друга @.., пусть отпишет мне сейчас",
    "Ок, пришлите, пожaлуйста, какой тег у @.. Вашего друга, пусть отпишет мне сейчас",

    # Шаблон 4 (19 вариантов)
    "Главное отправьте мне, пожалуйста, тег @.. того, кто оформит заказ по промокоду",
    "Главное пришлите мне, пожалуйста, тег @.. того, кто оформит заказ по промокоду",
    "Главное отправьте мне, пожалуйста, юзернейм @.. того, кто оформит заказ по промокоду",
    "Важно отправьте мне, пожалуйста, тег @.. того, кто оформит заказ по промокоду",
    "Главное отправьте мне, пожалуйста, тег @.. того, кто сделает заказ по промокоду",
    "Главное отправьте мне, пожалуйста, тег @.. человека, кто оформит заказ по промокоду",
    "Главное отправьте мне, будьте добры, тег @.. того, кто оформит заказ по промокоду",
    "Самое главное отправьте мне тег @.. того, кто оформит заказ по промокоду",
    "Главное скиньте мне, пожалуйста, тег @.. того, кто оформит заказ по промокоду",
    "Главное киньте мне, пожалуйста, тег @.. того, кто оформит заказ по промокоду",
    "В первую очередь отправьте мне тег @.. того, кто оформит заказ по промокоду",
    "Главное отправьте мне тег @.. того, кто оформит заказ по промокоду, пожалуйста",
    "Главное отправьте мне, прошу, тег @.. того, кто оформит заказ по промокоду",
    "Основное — пришлите мне тег @.. того, кто оформит заказ по промокоду",
    "Главное отправьте мне, пожалуйста, тег @.. победителя, кто оформит заказ по промокоду",
    "Главное отправьте мне, пожалуйста, тег @.. того человека, кто оформит заказ по промокоду",
    "Главное отправьте мне, пожалуйста, тег аккаунта @.. того, кто оформит заказ по промокоду",
    "Главное отправьте мне, пожалуйста, тег профиля @.. того, кто оформит заказ по промокоду",
    "Главное отправьте мне, пожалуйста, @.. того, кто оформит заказ по промокоду",

    # Шаблон 5 (20 вариантов)
    "Ваш зaказ #1106812 пpибыл на cклад в мск ✅",
    "Ваш заказ #1106812 поступил на склад в мск ✅",
    "Ваш заказ #1106812 прибыл на склад в Москве ✅",
    "Ваш заказ #1106812 приехал на склад в мск ✅",
    "Ваш заказ #1106812 прибыл на склад, ждёт вас в мск ✅",
    "Заказ #1106812 прибыл на склад в мск ✅",
    "Ваш заказ #1106812 доставлен на склад в мск ✅",
    "Ваш заказ #1106812 уже на складе в мск ✅",
    "Посылка #1106812 прибыла на склад в мск ✅",
    "Ваш заказ #1106812 пришёл на склад в мск ✅",
    "Ваш заказ #1106812 на складе в Москве, можно забирать ✅",
    "Ваш заказ #1106812 доехал до склада в мск ✅",
    "Ваш заказ #1106812 уже в Москве на складе ✅",
    "Ваш заказ #1106812 прибыл, готов к выдаче в мск ✅",
    "Ваш номер #1106812 прибыл на склад в мск ✅",
    "Ваш заказ номер #1106812 прибыл на склад в мск ✅",
    "Заказ номер #1106812 на складе в мск ✅",
    "Ваш заказ #1106812 на склад приехал в мск ✅",
    "Ваш заказ #1106812 в мск прибыл на склад ✅",
    "На склад в мск прибыл ваш заказ #1106812 ✅",

    # Шаблон 6 (20 вариантов)
    "Для расчета стоимости товаров по конкурсу у нас в @PoizonCountryRobot \n\nИспользуйте промокод: CNT61184",
    "Для подсчета стоимости товаров по конкурсу у нас в @PoizonCountryRobot \n\nИспользуйте промокод: CNT61184",
    "Для расчета цены товаров по конкурсу у нас в @PoizonCountryRobot \n\nИспользуйте промокод: CNT61184",
    "Для расчета стоимости товаров по розыгрышу у нас в @PoizonCountryRobot \n\nИспользуйте промокод: CNT61184",
    "Чтобы рассчитать стоимость товаров по конкурсу, перейдите в @PoizonCountryRobot \n\nИспользуйте промокод: CNT61184",
    "Для расчёта стоимости товаров по конкурсу — переходите в @PoizonCountryRobot \n\nИспользуйте промокод: CNT61184",
    "Для расчета стоимости призов по конкурсу у нас в @PoizonCountryRobot \n\nИспользуйте промокод: CNT61184",
    "Для расчета стоимости товаров по конкурсу — наш бот @PoizonCountryRobot \n\nПромокод: CNT61184",
    "Чтобы узнать стоимость товаров по конкурсу, зайдите в @PoizonCountryRobot \n\nАктивируйте промокод: CNT61184",
    "Рассчитать стоимость товаров по конкурсу можно у нас в @PoizonCountryRobot \n\nПромокод: CNT61184",
    "Для калькуляции стоимости товаров по конкурсу — @PoizonCountryRobot \n\nВаш промокод: CNT61184",
    "Стоимость товаров по конкурсу считаем в @PoizonCountryRobot \n\nПромокод: CNT61184",
    "Для расчёта стоимости вещей по конкурсу используйте @PoizonCountryRobot \n\nПромокод: CNT61184",
    "Как рассчитать стоимость товаров по конкурсу? У нас в @PoizonCountryRobot \n\nПромокод: CNT61184",
    "Для определения стоимости товаров по конкурсу переходите в @PoizonCountryRobot \n\nПромокод: CNT61184",
    "Подсчёт стоимости товаров по конкурсу — @PoizonCountryRobot \n\nВведите промокод: CNT61184",
    "Расчёт стоимости призов по конкурсу доступен в @PoizonCountryRobot \n\nПромокод: CNT61184",
    "Для получения стоимости товаров по конкурсу перейдите в @PoizonCountryRobot \n\nИспользуйте код: CNT61184",
    "Оценка стоимости товаров по конкурсу проводится в @PoizonCountryRobot \n\nПромокод: CNT61184",
    "Нужна стоимость товаров по конкурсу? Ждём вас в @PoizonCountryRobot \n\nПромокод: CNT61184",
]

# Замены символов
REPLACEMENTS = {
    'а': 'a', 'е': 'e', 'о': 'o', 'р': 'p', 'с': 'c', 'х': 'x', 'у': 'y',
    'К': 'K', 'М': 'M', 'Н': 'H', 'В': 'B'
}

# Хранение состояния пользователя
user_waiting_for_packs = {}

# Настройки БД
MESSAGES_BEFORE_CLEANUP = 50000

def init_db():
    conn = sqlite3.connect('templates.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS used_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            template_text TEXT UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stats (
            key TEXT PRIMARY KEY,
            value INTEGER DEFAULT 0
        )
    ''')
    cursor.execute('INSERT OR IGNORE INTO stats (key, value) VALUES ("total_messages", 0)')
    conn.commit()
    conn.close()

def get_message_count():
    conn = sqlite3.connect('templates.db')
    cursor = conn.cursor()
    cursor.execute('SELECT value FROM stats WHERE key = "total_messages"')
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else 0

def increment_message_count():
    conn = sqlite3.connect('templates.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE stats SET value = value + 1 WHERE key = "total_messages"')
    conn.commit()
    conn.close()

def clean_old_records():
    conn = sqlite3.connect('templates.db')
    cursor = conn.cursor()
    cursor.execute('''
        DELETE FROM used_templates 
        WHERE id NOT IN (SELECT id FROM used_templates ORDER BY id DESC LIMIT 1000)
    ''')
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    if deleted:
        print(f"🧹 Очищено {deleted} старых записей из БД")

def check_and_cleanup():
    msg_count = get_message_count()
    if msg_count >= MESSAGES_BEFORE_CLEANUP:
        clean_old_records()
        conn = sqlite3.connect('templates.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE stats SET value = 0 WHERE key = "total_messages"')
        conn.commit()
        conn.close()
        print(f"✅ Сброшен счётчик после {msg_count} сообщений")

def is_used(template_text):
    conn = sqlite3.connect('templates.db')
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM used_templates WHERE template_text = ?', (template_text,))
    exists = cursor.fetchone() is not None
    conn.close()
    return exists

def save_used(template_text):
    conn = sqlite3.connect('templates.db')
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO used_templates (template_text) VALUES (?)', (template_text,))
    conn.commit()
    conn.close()

def obfuscate_text(text: str) -> str:
    """50% вероятность замены для каждого символа"""
    chars = list(text)
    for i, ch in enumerate(chars):
        if ch in REPLACEMENTS and random.random() < 0.5:
            chars[i] = REPLACEMENTS[ch]
    return ''.join(chars)

def generate_unique_variant(original_template):
    """Генерирует уникальный вариант, которого ещё не было в БД"""
    max_attempts = 100
    for _ in range(max_attempts):
        variant = obfuscate_text(original_template)
        if not is_used(variant):
            save_used(variant)
            return variant
    return original_template

def get_random_template(template_group):
    """Возвращает случайный уникальный вариант из группы шаблонов"""
    idx = random.randint(0, len(template_group) - 1)
    return generate_unique_variant(template_group[idx])

async def send_pack(chat_id, context, pack_number):
    """Отправляет один пак из 6 шаблонов с фото"""
    try:
        # Группируем шаблоны по типам
        templates_group1 = TEMPLATES[0:18]   # Шаблон 1
        templates_group2 = TEMPLATES[18:38]  # Шаблон 2
        templates_group3 = TEMPLATES[38:58]  # Шаблон 3
        templates_group4 = TEMPLATES[58:77]  # Шаблон 4
        templates_group5 = TEMPLATES[77:97]  # Шаблон 5
        templates_group6 = TEMPLATES[97:117] # Шаблон 6
        
        # Получаем уникальные варианты
        msg1 = get_random_template(templates_group1)
        msg2 = get_random_template(templates_group2)
        msg3 = get_random_template(templates_group3)
        msg4 = get_random_template(templates_group4)
        msg5 = get_random_template(templates_group5)
        msg6 = get_random_template(templates_group6)
        
        # Отправляем сообщение 5 с двумя фото (по отдельности)
        if PHOTO_ORDER_1 and PHOTO_ORDER_2:
            await context.bot.send_photo(chat_id=chat_id, photo=PHOTO_ORDER_1, caption=msg5)
            await context.bot.send_photo(chat_id=chat_id, photo=PHOTO_ORDER_2)
        else:
            await context.bot.send_message(chat_id=chat_id, text=msg5)
        increment_message_count()
        check_and_cleanup()
        
        # Отправляем сообщение 6 с фото
        if PHOTO_PROMOCODE:
            await context.bot.send_photo(chat_id=chat_id, photo=PHOTO_PROMOCODE, caption=msg6)
        else:
            await context.bot.send_message(chat_id=chat_id, text=msg6)
        increment_message_count()
        check_and_cleanup()
        
        # Отправляем остальные сообщения
        await context.bot.send_message(chat_id=chat_id, text=msg1)
        increment_message_count()
        check_and_cleanup()
        
        await context.bot.send_message(chat_id=chat_id, text=msg2)
        increment_message_count()
        check_and_cleanup()
        
        await context.bot.send_message(chat_id=chat_id, text=msg3)
        increment_message_count()
        check_and_cleanup()
        
        await context.bot.send_message(chat_id=chat_id, text=msg4)
        increment_message_count()
        check_and_cleanup()
        
        print(f"✅ Пак {pack_number} отправлен")
        
    except Exception as e:
        print(f"❌ Ошибка при отправке пака {pack_number}: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("Сгенерировать шаблоны 🗂️", callback_data="generate")]]
    await update.message.reply_text(
        "📬 Нажми кнопку для генерации уникальных шаблонов.\n\n"
        "✅ 50% замена символов (а→a, е→e, о→o и т.д.)\n"
        "✅ 117 синонимичных шаблонов\n"
        "✅ Очистка БД каждые 50 000 сообщений\n"
        "✅ Одинаковые сообщения никогда не повторятся",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user_waiting_for_packs[user_id] = True
    
    await query.message.reply_text(
        "📦 Сколько паков шаблонов хотите создать?\n\n"
        "1 пак = 6 сообщений (все шаблоны по одному разу)\n\n"
        "Просто напишите число:"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_waiting_for_packs.get(user_id):
        try:
            num_packs = int(update.message.text.strip())
            if num_packs <= 0:
                await update.message.reply_text("❌ Введите число больше 0")
                return
            
            user_waiting_for_packs[user_id] = False
            
            await update.message.reply_text(f"✅ Начинаю генерацию {num_packs} паков...")
            
            for i in range(num_packs):
                await send_pack(update.effective_chat.id, context, i + 1)
            
            await update.message.reply_text(f"✅ Готово! Создано {num_packs} паков.")
            
        except ValueError:
            await update.message.reply_text("❌ Введите число (например: 5)")

def main():
    init_db()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_callback, pattern="generate"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("✅ Бот запущен. Проверьте консоль на ошибки.")
    app.run_polling()

if __name__ == "__main__":
    main()
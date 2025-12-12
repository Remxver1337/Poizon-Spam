#!/usr/bin/env python3
"""
Конфигурация бота
"""

import os
from pathlib import Path

# ============= ПУТИ =============
BASE_DIR = Path(__file__).parent
DATABASES_DIR = BASE_DIR / "databases"
LOGS_DIR = BASE_DIR / "logs"
CERTS_DIR = BASE_DIR / "certs"

# Создаем папки
for directory in [DATABASES_DIR, LOGS_DIR, CERTS_DIR]:
    directory.mkdir(exist_ok=True)

# ============= ОСНОВНЫЕ НАСТРОЙКИ =============
MAIN_BOT_TOKEN = "8517379434:AAGqMYBuEQZ8EMNRf3g4yBN-Q0jpm5u5eZU"
ADMIN_ID = 7404231636

# ============= НАСТРОЙКИ ДОМЕНА И ВЕБХУКОВ =============
YOUR_HOST = "bot_1765490463_8840_remxver1337.bothost.ru"
YOUR_PORT = 3000
USE_WEBHOOK = True
USE_POLLING = False

# URL вебхука для основного бота
MAIN_WEBHOOK_URL = f"https://{YOUR_HOST}:{YOUR_PORT}/{MAIN_BOT_TOKEN}"

# URL вебхука для зеркальных ботов
MIRROR_WEBHOOK_BASE = f"https://{YOUR_HOST}:{YOUR_PORT}"

# SSL сертификаты (если есть)
SSL_CERT = os.path.join(CERTS_DIR, "cert.pem") if os.path.exists(CERTS_DIR) else None
SSL_KEY = os.path.join(CERTS_DIR, "key.pem") if os.path.exists(CERTS_DIR) else None

# ============= НАСТРОЙКИ БАЗЫ ДАННЫХ =============
DATABASE_PATH = str(DATABASES_DIR / "mirrors.db")
MAX_USERS_PER_MIRROR = 10
INACTIVITY_DAYS = 7

# ============= НАСТРОЙКИ ЛОГИРОВАНИЯ =============
LOG_LEVEL = "INFO"
LOG_FILE = str(LOGS_DIR / "bot.log")

# ============= НАСТРОЙКИ РАССЫЛКИ =============
REPLACEMENTS = {
    'а': 'a', 'с': 'c', 'о': 'o', 'р': 'p', 'е': 'e', 'х': 'x', 'у': 'y',
    'А': 'A', 'С': 'C', 'О': 'O', 'Р': 'P', 'Е': 'E', 'Х': 'X', 'У': 'Y'
}
MAX_VARIATIONS_PER_MESSAGE = 500

# ============= ПРОВЕРКА КОНФИГУРАЦИИ =============
def check_config():
    """Проверка конфигурации"""
    print("=" * 60)
    print("🤖 ПРОВЕРКА КОНФИГУРАЦИИ")
    print("=" * 60)
    print(f"✅ Токен: {MAIN_BOT_TOKEN[:15]}...")
    print(f"✅ Админ ID: {ADMIN_ID}")
    print(f"✅ Хост: {YOUR_HOST}:{YOUR_PORT}")
    print(f"✅ Режим: {'WEBHOOK' if USE_WEBHOOK else 'POLLING'}")
    print(f"✅ Вебхук URL: {MAIN_WEBHOOK_URL}")
    print("=" * 60)
    
    if USE_WEBHOOK and not YOUR_HOST:
        print("❌ ВНИМАНИЕ: Режим WEBHOOK выбран, но YOUR_HOST не указан!")
        return False
    
    return True
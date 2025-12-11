import os
from pathlib import Path

# Пути к папкам
BASE_DIR = Path(__file__).parent
DATABASES_DIR = BASE_DIR / "databases"
LOGS_DIR = BASE_DIR / "logs"

# Создаем папки если их нет
DATABASES_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

# ============= ОСНОВНЫЕ НАСТРОЙКИ =============
MAIN_BOT_TOKEN = "8517379434:AAGqMYBuEQZ8EMNRf3g4yBN-Q0jpm5u5eZU"  # Замени на свой
ADMIN_ID = 7404231636  # Замени на свой ID

# Настройки базы данных
MIRRORS_DB_PATH = str(DATABASES_DIR / "mirrors.db")
MAX_USERS_PER_MIRROR = 10
INACTIVITY_DAYS = 7

# Настройки логов
LOG_LEVEL = "INFO"
LOG_FILE = str(LOGS_DIR / "bot.log")

# Словарь для замены символов
REPLACEMENTS = {
    'а': 'a', 'с': 'c', 'о': 'o', 'р': 'p', 'е': 'e', 'х': 'x', 'у': 'y',
    'А': 'A', 'С': 'C', 'О': 'O', 'Р': 'P', 'Е': 'E', 'Х': 'X', 'У': 'Y'
}

# Настройки запуска
USE_POLLING = True  # Использовать polling вместо webhook
DEBUG = True  # Режим отладки
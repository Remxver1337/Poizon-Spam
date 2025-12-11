import os
from pathlib import Path

# Пути
BASE_DIR = Path(__file__).parent
DATABASES_DIR = BASE_DIR / "databases"
LOGS_DIR = BASE_DIR / "logs"

for directory in [DATABASES_DIR, LOGS_DIR]:
    directory.mkdir(exist_ok=True)

# ============= ОСНОВНЫЕ НАСТРОЙКИ =============
MAIN_BOT_TOKEN = "8568866654:AAFfLobjJfnbjwltSdy4IAw_-3yBzw3rGm8"  # Ваш токен
ADMIN_ID = 7404231636  # Ваш ID

# ============= НАСТРОЙКИ ДОМЕНА =============
MODE = "polling"  # Сначала используйте polling для отладки
WEBHOOK_HOST = "bot_1765495089_6423_remxver1337.bothost.ru"
WEBHOOK_PORT = 3000
WEBHOOK_LISTEN = "0.0.0.0"

# SSL (опционально, для начала не нужно)
SSL_CERT = None
SSL_KEY = None

# URL вебхуков
MAIN_WEBHOOK_URL = f"https://{WEBHOOK_HOST}:{WEBHOOK_PORT}/{MAIN_BOT_TOKEN}"
MIRROR_WEBHOOK_BASE = f"https://{WEBHOOK_HOST}:{WEBHOOK_PORT}"

# ============= ДРУГИЕ НАСТРОЙКИ =============
MIRRORS_DB_PATH = str(DATABASES_DIR / "mirrors.db")
LOG_LEVEL = "INFO"
LOG_FILE = str(LOGS_DIR / "bot.log")

# Словарь для замены символов
REPLACEMENTS = {
    'а': 'a', 'с': 'c', 'о': 'o', 'р': 'p', 'е': 'e', 'х': 'x', 'у': 'y',
    'А': 'A', 'С': 'C', 'О': 'O', 'Р': 'P', 'Е': 'E', 'Х': 'X', 'У': 'Y'
}
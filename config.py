import os
from pathlib import Path

# ============= ПУТИ =============
BASE_DIR = Path(__file__).parent
DATABASES_DIR = BASE_DIR / "databases"
LOGS_DIR = BASE_DIR / "logs"
CERTS_DIR = BASE_DIR / "certs"

# Создаем папки если их нет
for directory in [DATABASES_DIR, LOGS_DIR, CERTS_DIR]:
    directory.mkdir(exist_ok=True)

# ============= ОСНОВНЫЕ НАСТРОЙКИ =============
# ⚠️ ЗАМЕНИТЕ ЭТИ ЗНАЧЕНИЯ НА СВОИ ⚠️
MAIN_BOT_TOKEN = "8568866654:AAFfLobjJfnbjwltSdy4IAw_-3yBzw3rGm8"  # Токен основного бота от @BotFather
ADMIN_ID = 7404231636  # Ваш Telegram ID (узнать у @userinfobot)

# ============= НАСТРОЙКИ ДОМЕНОВ И ВЕБХУКОВ =============
# Режим работы: 'webhook' или 'polling'
MODE = "webhook"  # Используем webhook так как есть домен

# Ваш домен и порт
WEBHOOK_HOST = "bot_1765490463_8840_remxver1337.bothost.ru"  # Ваш домен
WEBHOOK_PORT = 3000  # Ваш порт
WEBHOOK_LISTEN = "0.0.0.0"  # Адрес прослушивания

# Пути к SSL сертификатам (для вашего хостинга могут быть другие)
SSL_CERT = os.path.join(CERTS_DIR, "cert.pem") if os.path.exists(CERTS_DIR) else None
SSL_KEY = os.path.join(CERTS_DIR, "key.pem") if os.path.exists(CERTS_DIR) else None

# URL вебхука для основного бота
MAIN_WEBHOOK_URL = f"https://{WEBHOOK_HOST}:{WEBHOOK_PORT}/{MAIN_BOT_TOKEN}"

# URL вебхука для зеркальных ботов
MIRROR_WEBHOOK_BASE = f"https://{WEBHOOK_HOST}:{WEBHOOK_PORT}"

# ============= НАСТРОЙКИ БАЗЫ ДАННЫХ =============
MIRRORS_DB_PATH = str(DATABASES_DIR / "mirrors.db")
MAX_USERS_PER_MIRROR = 10
INACTIVITY_DAYS = 7

# ============= НАСТРОЙКИ ЛОГИРОВАНИЯ =============
LOG_LEVEL = "INFO"
LOG_FILE = str(LOGS_DIR / "bot.log")

# ============= НАСТРОЙКИ РАССЫЛКИ =============
MAX_VARIATIONS_PER_MESSAGE = 500
MESSAGE_SEND_DELAY = 1.0  # Задержка между отправками в секундах

# ============= СЛОВАРЬ ДЛЯ ЗАМЕНЫ СИМВОЛОВ =============
REPLACEMENTS = {
    'а': 'a', 'с': 'c', 'о': 'o', 'р': 'p', 'е': 'e', 'х': 'x', 'у': 'y',
    'А': 'A', 'С': 'C', 'О': 'O', 'Р': 'P', 'Е': 'E', 'Х': 'X', 'У': 'Y',
    'к': 'k', 'К': 'K', 'в': 'b', 'В': 'B', 'н': 'h', 'Н': 'H',
    'т': 't', 'Т': 'T', 'м': 'm', 'М': 'M'
}

# ============= НАСТРОЙКИ БЕЗОПАСНОСТИ =============
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-this")
DEBUG = True  # В продакшене поставьте False

# ============= ПРОВЕРКА КОНФИГУРАЦИИ =============
def validate_config():
    """Проверка конфигурации"""
    errors = []
    
    if not MAIN_BOT_TOKEN or "8517379434" in MAIN_BOT_TOKEN:
        errors.append("⚠️  Используется тестовый токен! Замените MAIN_BOT_TOKEN в config.py")
    
    if MODE == "webhook" and not WEBHOOK_HOST:
        errors.append("⚠️  Режим webhook выбран, но WEBHOOK_HOST не указан")
    
    if MODE == "webhook" and not SSL_CERT:
        print("ℹ️  SSL сертификат не найден. Убедитесь что он есть на вашем хостинге")
    
    return errors

# Проверяем конфигурацию при импорте
config_errors = validate_config()
if config_errors:
    print("\n".join(config_errors))
#!/bin/bash

echo "🚀 Установка Telegram бота с зеркалами и вебхуками"
echo "=================================================="

# Проверка Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 не установлен"
    exit 1
fi

# Создание папок
echo "📁 Создание структуры папок..."
mkdir -p databases logs certs

# Установка зависимостей
echo "📦 Установка зависимостей..."
python3 -m pip install --upgrade pip
python3 -m pip install python-telegram-bot==20.7 python-dotenv

# Создание конфига
if [ ! -f "config.py" ]; then
    echo "⚙️  Создание config.py..."
    cat > config.py << 'EOF'
import os
from pathlib import Path

# Пути
BASE_DIR = Path(__file__).parent
DATABASES_DIR = BASE_DIR / "databases"
LOGS_DIR = BASE_DIR / "logs"
CERTS_DIR = BASE_DIR / "certs"

for directory in [DATABASES_DIR, LOGS_DIR, CERTS_DIR]:
    directory.mkdir(exist_ok=True)

# ============= ОСНОВНЫЕ НАСТРОЙКИ =============
MAIN_BOT_TOKEN = "ВАШ_ТОКЕН_ОСНОВНОГО_БОТА"  # Получи у @BotFather
ADMIN_ID = ВАШ_TELEGRAM_ID  # Узнай у @userinfobot

# ============= НАСТРОЙКИ ДОМЕНА И ВЕБХУКОВ =============
MODE = "webhook"  # или "polling"
WEBHOOK_HOST = "bot_1765490463_8840_remxver1337.bothost.ru"
WEBHOOK_PORT = 3000
WEBHOOK_LISTEN = "0.0.0.0"

SSL_CERT = os.path.join(CERTS_DIR, "cert.pem") if os.path.exists(CERTS_DIR) else None
SSL_KEY = os.path.join(CERTS_DIR, "key.pem") if os.path.exists(CERTS_DIR) else None

# URL вебхуков
MAIN_WEBHOOK_URL = f"https://{WEBHOOK_HOST}:{WEBHOOK_PORT}/{MAIN_BOT_TOKEN}"
MIRROR_WEBHOOK_BASE = f"https://{WEBHOOK_HOST}:{WEBHOOK_PORT}"

# ============= ДРУГИЕ НАСТРОЙКИ =============
MIRRORS_DB_PATH = str(DATABASES_DIR / "mirrors.db")
MAX_USERS_PER_MIRROR = 10
INACTIVITY_DAYS = 7
LOG_LEVEL = "INFO"
LOG_FILE = str(LOGS_DIR / "bot.log")
MAX_VARIATIONS_PER_MESSAGE = 500
DEBUG = True

# Словарь для замены символов
REPLACEMENTS = {
    'а': 'a', 'с': 'c', 'о': 'o', 'р': 'p', 'е': 'e', 'х': 'x', 'у': 'y',
    'А': 'A', 'С': 'C', 'О': 'O', 'Р': 'P', 'Е': 'E', 'Х': 'X', 'У': 'Y'
}
EOF
fi

# Создание requirements.txt
echo "python-telegram-bot==20.7" > requirements.txt
echo "python-dotenv>=1.0.0" >> requirements.txt

# Даем права на выполнение
chmod +x setup.sh

echo ""
echo "✅ Установка завершена!"
echo ""
echo "📝 НЕ ЗАБУДЬТЕ:"
echo "1. Отредактируйте config.py:"
echo "   - Укажите MAIN_BOT_TOKEN"
echo "   - Укажите ADMIN_ID"
echo "   - Проверьте WEBHOOK_HOST (ваш домен)"
echo "   - Проверьте WEBHOOK_PORT (3000)"
echo ""
echo "2. Для вебхуков убедитесь что:"
echo "   - Домен указывает на ваш сервер"
echo "   - Порт 3000 открыт"
echo "   - Есть SSL сертификаты (для продакшена)"
echo ""
echo "3. Запустите систему:"
echo "   python3 main.py"
echo ""
echo "4. Для запуска всех зеркал (после основного бота):"
echo "   python3 start_mirrors.py"
echo ""
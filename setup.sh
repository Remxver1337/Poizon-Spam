#!/bin/bash

echo "🚀 Установка Telegram бота с зеркалами"
echo "======================================"

# Создание папок
mkdir -p databases logs

# Проверка Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 не установлен"
    exit 1
fi

# Установка зависимостей
echo "📦 Установка зависимостей..."
python3 -m pip install --upgrade pip
python3 -m pip install python-telegram-bot==20.7

# Создание конфига если его нет
if [ ! -f "config.py" ]; then
    echo "⚙️  Создание config.py..."
    cat > config.py << 'EOF'
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATABASES_DIR = BASE_DIR / "databases"
LOGS_DIR = BASE_DIR / "logs"

DATABASES_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

# ============= ЗАМЕНИ ЭТИ НАСТРОЙКИ =============
MAIN_BOT_TOKEN = "ВАШ_ТОКЕН_ЗДЕСЬ"  # Получи у @BotFather
ADMIN_ID = ВАШ_ID_ЗДЕСЬ  # Узнай у @userinfobot
# ===============================================

MIRRORS_DB_PATH = str(DATABASES_DIR / "mirrors.db")
MAX_USERS_PER_MIRROR = 10
INACTIVITY_DAYS = 7
LOG_LEVEL = "INFO"
LOG_FILE = str(LOGS_DIR / "bot.log")
USE_POLLING = True
DEBUG = True

REPLACEMENTS = {
    'а': 'a', 'с': 'c', 'о': 'o', 'р': 'p', 'е': 'e', 'х': 'x', 'у': 'y',
    'А': 'A', 'С': 'C', 'О': 'O', 'Р': 'P', 'Е': 'E', 'Х': 'X', 'У': 'Y'
}
EOF
fi

# Даем права на выполнение
chmod +x setup.sh

echo ""
echo "✅ Установка завершена!"
echo ""
echo "📝 НЕ ЗАБУДЬТЕ:"
echo "1. Отредактируйте config.py:"
echo "   - Укажите MAIN_BOT_TOKEN (получите у @BotFather)"
echo "   - Укажите ADMIN_ID (узнайте у @userinfobot)"
echo ""
echo "2. Запустите бота:"
echo "   python3 main.py"
echo ""
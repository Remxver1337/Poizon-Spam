#!/bin/bash
echo "🚀 УСТАНОВКА ТЕЛЕГРАМ БОТА С ЗЕРКАЛАМИ"
echo "======================================"

# Создание папок
mkdir -p databases logs certs

# Проверка Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 не установлен"
    exit 1
fi

# Установка зависимостей
echo "📦 Установка зависимостей..."
python3 -m pip install --upgrade pip
python3 -m pip install python-telegram-bot==20.7

# Даем права на выполнение
chmod +x setup.sh

echo ""
echo "✅ Установка завершена!"
echo ""
echo "📝 ПРОВЕРЬТЕ НАСТРОЙКИ В config.py:"
echo "1. YOUR_HOST: Ваш домен"
echo "2. YOUR_PORT: Порт (3000)"
echo "3. MAIN_BOT_TOKEN: Ваш токен"
echo "4. ADMIN_ID: Ваш Telegram ID"
echo ""
echo "💡 Запустите бота: python3 main.py"
echo ""
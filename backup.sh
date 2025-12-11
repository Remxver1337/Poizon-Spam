#!/bin/bash
# Скрипт резервного копирования

BACKUP_DIR="backups/$(date +%Y%m%d_%H%M%S)"
mkdir -p $BACKUP_DIR

echo "💾 Создание резервной копии..."

# Копируем базы данных
if [ -d "databases" ]; then
    cp -r databases $BACKUP_DIR/
    echo "✅ Базы данных скопированы"
fi

# Копируем конфиги
cp config.py .env $BACKUP_DIR/ 2>/dev/null && echo "✅ Конфиги скопированы"

# Копируем логи
if [ -d "logs" ]; then
    cp -r logs $BACKUP_DIR/
    echo "✅ Логи скопированы"
fi

# Архивируем
tar -czf $BACKUP_DIR.tar.gz $BACKUP_DIR
rm -rf $BACKUP_DIR

echo "✅ Резервная копия создана: $BACKUP_DIR.tar.gz"
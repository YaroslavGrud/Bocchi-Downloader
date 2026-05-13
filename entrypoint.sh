#!/bin/bash

cd /app || { echo "❌ Ошибка: директория /app не найдена"; exit 1; }

BOT_MODE=${BOT_MODE:-stable}
echo "BOT_MODE = $BOT_MODE"

case "$BOT_MODE" in
    beta)
        if [ -f "bocchi_host_full.py" ]; then
            echo "🚀 Запускаем полную версию (bocchi_host_full.py)"
            exec python bocchi_host_full.py
        else
            echo "❌ Файл bocchi_host_full.py не найден"
            exit 1
        fi
        ;;
    stable)
        if [ -f "bocchi_bot_host.py" ]; then
            echo "🚀 Запускаем стабильную версию (bocchi_bot_host.py)"
            exec python bocchi_bot_host.py
        else
            echo "❌ Файл bocchi_bot_host.py не найден"
            exit 1
        fi
        ;;
    *)
        echo "❌ Неизвестный BOT_MODE=$BOT_MODE. Используйте stable или beta"
        exit 1
        ;;
esac
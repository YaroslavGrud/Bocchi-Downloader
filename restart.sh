#!/bin/bash
cd ~/bocchi_bot || { echo "❌ Папка ~/bocchi_bot не найдена"; exit 1; }

echo "🛑 Останавливаем и удаляем старый контейнер..."
docker stop bocchi_bot 2>/dev/null && echo "   Контейнер остановлен"
docker rm bocchi_bot 2>/dev/null && echo "   Контейнер удалён"

echo "🔑 Введите токен Telegram бота:"
read TOKEN

# Если токен не введён – показываем инструкцию и выходим
if [ -z "$TOKEN" ]; then
    echo "❌ Токен не введён. Перезапуск отменён."
    echo "💡 Выполните вручную:"
    echo "cd ~/bocchi_bot && docker stop bocchi_bot 2>/dev/null ; docker rm bocchi_bot 2>/dev/null ; read -p \"Введите токен: \" TOKEN && docker run -d --name bocchi_bot --restart unless-stopped -e TELEGRAM_TOKEN=\"\$TOKEN\" -v \$(pwd)/data:/app/data bocchi_bot && docker logs -f bocchi_bot"
    exit 1
fi

echo "🚀 Запускаем новый контейнер..."
docker run -d \
  --name bocchi_bot \
  --restart unless-stopped \
  -e TELEGRAM_TOKEN="$TOKEN" \
  -v "$(pwd)/data:/app/data" \
  bocchi_bot

# Проверка, что контейнер запустился
if [ $? -eq 0 ]; then
    echo "✅ Бот перезапущен. Показываем логи (нажмите Ctrl+C для выхода):"
    docker logs -f bocchi_bot
else
    echo "❌ Ошибка при запуске контейнера."
    echo "💡 Попробуйте выполнить вручную:"
    echo "cd ~/bocchi_bot && docker stop bocchi_bot 2>/dev/null ; docker rm bocchi_bot 2>/dev/null ; read -p \"Введите токен: \" TOKEN && docker run -d --name bocchi_bot --restart unless-stopped -e TELEGRAM_TOKEN=\"\$TOKEN\" -v \$(pwd)/data:/app/data bocchi_bot && docker logs -f bocchi_bot"
    exit 1
fi

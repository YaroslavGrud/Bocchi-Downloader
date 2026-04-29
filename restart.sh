#!/bin/bash
cd ~/bocchi_bot || { echo "❌ Папка ~/bocchi_bot не найдена"; exit 1; }

echo "🛑 Останавливаем и удаляем старый контейнер..."
docker stop bocchi_bot 2>/dev/null && echo "   Контейнер остановлен"
docker rm bocchi_bot 2>/dev/null && echo "   Контейнер удалён"

echo "🔑 Введите токен Telegram бота:"
read TOKEN

echo "🚀 Запускаем новый контейнер..."
docker run -d \
  --name bocchi_bot \
  --restart unless-stopped \
  -e TELEGRAM_TOKEN="$TOKEN" \
  -v $(pwd)/data:/app/data \
  bocchi_bot

echo "✅ Бот перезапущен. Показываем логи (нажмите Ctrl+C для выхода):"
docker logs -f bocchi_bot

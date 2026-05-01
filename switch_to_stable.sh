#!/bin/bash
# Переключение на стабильную версию (bocchi_bot_host.py)
# Работает без docker-compose, совместим с deploy.sh

set -e
cd "$(dirname "$0")"

echo "=== Переключение на СТАБИЛЬНУЮ версию ==="

# Ищем .env в текущей или домашней папке
ENV_FILE=""
if [ -f .env ]; then
    ENV_FILE=".env"
elif [ -f ~/bocchi_bot/.env ]; then
    ENV_FILE=~/bocchi_bot/.env
else
    ENV_FILE=".env"
fi

# Токен
if grep -q '^TELEGRAM_TOKEN=' "$ENV_FILE" 2>/dev/null; then
    current_token=$(grep '^TELEGRAM_TOKEN=' "$ENV_FILE" | cut -d '=' -f2-)
    echo "Текущий токен: ${current_token:0:8}..."
    read -p "Новый токен (Enter - оставить прежний): " new_token
    [ -z "$new_token" ] && new_token="$current_token"
else
    read -p "Введите TELEGRAM_TOKEN: " new_token
fi

# Записываем .env
cat > "$ENV_FILE" <<EOF
TELEGRAM_TOKEN=${new_token}
BOT_MODE=stable
EOF
echo "✅ Режим: stable"

# Пересоздаём контейнер
CONTAINER_NAME="bocchi_bot"
echo "♻️  Останавливаем старый контейнер..."
docker stop "$CONTAINER_NAME" 2>/dev/null || true
docker rm "$CONTAINER_NAME" 2>/dev/null || true

echo "🚀 Запускаем новый контейнер..."
docker run -d \
  --name "$CONTAINER_NAME" \
  --restart unless-stopped \
  -e TELEGRAM_TOKEN="${new_token}" \
  -e BOT_MODE=stable \
  -v bocchi_data:/app/data \
  yaroslavgrud/bocchi-downloader-server-edition:latest

echo "✅ Бот запущен в стабильном режиме"
echo "Логи: docker logs -f $CONTAINER_NAME"

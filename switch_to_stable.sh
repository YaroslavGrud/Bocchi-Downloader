#!/bin/bash
set -e

cd "$(dirname "$0")" || { echo "❌ Ошибка перехода в директорию скрипта"; exit 1; }

echo "=== Переключение на СТАБИЛЬНУЮ версию ==="

ENV_FILE=""
if [ -f .env ]; then
    ENV_FILE=".env"
elif [ -f "$HOME/bocchi_bot/.env" ]; then
    ENV_FILE="$HOME/bocchi_bot/.env"
else
    ENV_FILE=".env"
fi

get_token_from_env() {
    grep '^TELEGRAM_TOKEN=' "$1" 2>/dev/null | sed 's/^TELEGRAM_TOKEN=//'
}

current_token=""
if [ -f "$ENV_FILE" ]; then
    current_token=$(get_token_from_env "$ENV_FILE")
    if [ -n "$current_token" ]; then
        echo "Текущий токен: ${current_token:0:8}..."
    fi
fi

if [ -n "$current_token" ]; then
    printf "Новый токен (Enter - оставить прежний): "
    read -r new_token
    if [ -z "$new_token" ]; then
        new_token="$current_token"
    fi
else
    while true; do
        printf "Введите TELEGRAM_TOKEN: "
        read -r new_token
        if [ -n "$new_token" ]; then
            break
        else
            echo "Ошибка: токен не может быть пустым."
        fi
    done
fi

cat > "$ENV_FILE" <<EOF
TELEGRAM_TOKEN=${new_token}
BOT_MODE=stable
EOF
echo "✅ Режим: stable"

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
  -v "$(pwd)/data:/app/data" \
  --tmpfs /tmp \
  --tmpfs /var/tmp \
  --read-only \
  --security-opt no-new-privileges:true \
  yaroslavgrud/bocchi-downloader-server-edition:latest

echo "✅ Бот запущен в стабильном режиме"
echo "Логи: docker logs -f $CONTAINER_NAME"
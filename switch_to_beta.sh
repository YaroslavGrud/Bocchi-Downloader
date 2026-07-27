cat > /root/switch_to_beta_fixed.sh << 'EOF'
#!/bin/bash
set -e

cd "$(dirname "$0")" || { echo "❌ Ошибка перехода в директорию"; exit 1; }

echo "=== Переключение на БЕТА-версию (локальный образ) ==="

# ---- Работа с .env ----
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

# Сохраняем .env (режим beta)
cat > "$ENV_FILE" <<EOF
TELEGRAM_TOKEN=${new_token}
BOT_MODE=beta
EOF
echo "✅ Режим: beta"

# ---- Проверка и сборка локального образа ----
if ! docker images | grep -q "^bocchi_bot"; then
    echo "⚠️ Локальный образ bocchi_bot не найден. Собираем..."
    if [ ! -f Dockerfile ]; then
        echo "📥 Клонируем репозиторий..."
        git clone https://github.com/YaroslavGrud/Bocchi-Downloader.git .
        git checkout Yaroslav_grud
    fi
    docker build -t bocchi_bot .
else
    echo "✅ Образ bocchi_bot уже существует."
fi

# ---- Остановка и удаление старого контейнера ----
CONTAINER_NAME="bocchi_bot"
echo "♻️  Останавливаем старый контейнер..."
docker stop "$CONTAINER_NAME" 2>/dev/null || true
docker rm "$CONTAINER_NAME" 2>/dev/null || true

# ---- Создаём папку data и выставляем права для пользователя bocchi (UID 1000) ----
mkdir -p "$(pwd)/data"
chown -R 1000:1000 "$(pwd)/data"
chmod 755 "$(pwd)/data"

# Создаём файл active_status_msgs.json, если нет
if [ ! -f "active_status_msgs.json" ]; then
    echo '{}' > active_status_msgs.json
fi
chmod 666 active_status_msgs.json

# ---- Запуск контейнера ----
echo "🚀 Запускаем новый контейнер (локальный образ)..."
docker run -d \
  --name "$CONTAINER_NAME" \
  --restart unless-stopped \
  -v "$(pwd)/data:/app/data" \
  -v "$(pwd)/active_status_msgs.json:/app/active_status_msgs.json" \
  -e TELEGRAM_TOKEN="${new_token}" \
  -e BOT_MODE=beta \
  --user 1000:1000 \
  --security-opt no-new-privileges:true \
  bocchi_bot

echo "✅ Бот запущен в бета-режиме (локальный образ)"
echo "📋 Логи: docker logs -f $CONTAINER_NAME"
EOF

chmod +x /root/switch_to_beta_fixed.sh

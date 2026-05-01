#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "=== Переключение на БЕТА-версию ==="

if [ -f .env ] && grep -q '^TELEGRAM_TOKEN=' .env 2>/dev/null; then
    current_token=$(grep '^TELEGRAM_TOKEN=' .env | cut -d '=' -f2-)
    echo "Текущий токен: ${current_token:0:8}..."
    read -p "Новый токен (Enter - оставить прежний): " new_token
    [ -z "$new_token" ] && new_token="$current_token"
else
    read -p "Введите TELEGRAM_TOKEN: " new_token
fi

cat > .env <<EOF
TELEGRAM_TOKEN=${new_token}
BOT_MODE=beta
EOF

echo "✅ Режим: beta"
echo "♻️  Перезапускаем контейнер..."
docker compose down
docker compose up -d
echo "✅ Бот запущен в бета-режиме"

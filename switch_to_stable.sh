#!/bin/bash
cd "$(dirname "$0")"
sed -i 's/BOT_MODE=.*/BOT_MODE=stable/' .env
docker compose down
docker compose up -d
echo "✅ Переключено на STABLE. Логи: docker logs -f bocchi-bot"

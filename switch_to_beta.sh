#!/bin/bash
cd "$(dirname "$0")"
sed -i 's/BOT_MODE=.*/BOT_MODE=beta/' .env
docker compose down
docker compose up -d
echo "✅ Переключено на BETA. Логи: docker logs -f bocchi-bot"

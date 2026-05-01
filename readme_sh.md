
# Shell-скрипты для управления ботом

### 1. Первый запуск (с полной очисткой)

```bash
curl -fsSL https://raw.githubusercontent.com/YaroslavGrud/Bocchi-Downloader/Yaroslav_grud/deploy.sh -o deploy.sh && bash deploy.sh
```

Скрипт `deploy.sh`:

*   Проверяет наличие Docker
*   Удаляет старую установку (папку `~/bocchi_bot`)
*   Запрашивает токен Telegram-бота
*   Клонирует репозиторий
*   Сохраняет токен в `.env`
*   Собирает Docker-образ
*   Запускает контейнер

### 2\. Перезапуск бота

```bash
curl -fsSL https://raw.githubusercontent.com/YaroslavGrud/Bocchi-Downloader/Yaroslav_grud/restart.sh -o restart.sh && bash restart.sh
```

Скрипт `restart.sh`:

*   Останавливает и удаляет старый контейнер
*   Запрашивает токен Telegram-бота
*   Запускает новый контейнер с указанным токеном
*   Показывает логи бота

## Переключение версий

### 3. Стабильная версия

```bash
curl -fsSL https://raw.githubusercontent.com/YaroslavGrud/Bocchi-Downloader/Yaroslav_grud/switch_to_stable.sh -o switch_to_stable.sh && bash switch_to_stable.sh
```

Скрипт `switch_to_stable.sh`:

*   Запрашивает (или подтверждает) токен Telegram-бота
*   Сохраняет `.env` с `BOT_MODE=stable`
*   Перезапускает контейнер через `docker compose down && docker compose up -d`
*   Запускается `bocchi_bot_host.py`

### 4. Бета-версия (нестабильная)

```bash
curl -fsSL https://raw.githubusercontent.com/YaroslavGrud/Bocchi-Downloader/Yaroslav_grud/switch_to_beta.sh -o switch_to_beta.sh && bash switch_to_beta.sh
```

Скрипт `switch_to_beta.sh`:

*   Запрашивает (или подтверждает) токен Telegram-бота
*   Сохраняет `.env` с `BOT_MODE=beta`
*   Перезапускает контейнер через `docker compose down && docker compose up -d`
*   Запускается `bocchi_host_full.py`

## Очистка

### 5. Полное удаление бота

```bash
curl -fsSL https://raw.githubusercontent.com/YaroslavGrud/Bocchi-Downloader/Yaroslav_grud/docker_clean.sh -o docker_clean.sh && bash docker_clean.sh
```

Скрипт `docker_clean.sh`:

*   Запрашивает подтверждение
*   Останавливает и удаляет контейнер
*   Удаляет Docker-образ
*   Удаляет папку `~/bocchi_bot` со всеми данными (токены, очередь, логи)

## Команды управления контейнером

| Команда | Описание |
|---------|----------|
| `docker start bocchi-bot` | ▶️ Запустить остановленный контейнер |
| `docker stop bocchi-bot`  | 🛑 Остановить контейнер |
| `docker restart bocchi-bot` | 🔄 Перезапустить контейнер |
| `docker logs -f bocchi-bot` | 📋 Просмотр логов в реальном времени |
| `docker stats bocchi-bot` | 📊 Потребление ресурсов контейнером (CPU, RAM, сеть) |
| `docker exec -it bocchi-bot bash` | 🖥️ Зайти внутрь контейнера |

## Мониторинг сервера (glances)

`glances` показывает в реальном времени загрузку CPU, RAM, дисков, сети и запущенные процессы.

**Установка** (требуется Python):

```bash
pip install glances
```

Или через системный пакетный менеджер:

```bash
sudo apt update && sudo apt install glances   # Debian/Ubuntu
```

Запуск мониторинга прямо в терминале:

```bash
glances
```

Для наблюдения за конкретным Docker-контейнером можно использовать веб-режим:

```bash
glances -w
```

После этого откройте в браузере `http://<IP-сервера>:61208`.

## Примечания

*   Токен Telegram-бота можно получить у [@BotFather](https://t.me/BotFather)
*   Рабочая директория: `~/bocchi_bot`
*   Все данные сохраняются в папке `data` внутри рабочей директории
*   Для переключения между стабильной и бета-версией используйте скрипты `switch_to_stable.sh` или `switch_to_beta.sh`
*   Имя контейнера в примерах — `bocchi-bot` (указано в `docker-compose.yml`)

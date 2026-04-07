# Базовый образ Python 3.11 на Alpine Linux
FROM python:3.11-slim-alpine AS base

# Этап сборки yandex-music-downloader
FROM base AS builder

# Установка инструментов для сборки Rust-приложений
RUN apk add --no-cache \
    build-base \
    cargo \
    git \
    libffi-dev \
    musl-dev \
    rust

# Сборка yandex-music-downloader
RUN git clone https://github.com/llistochek/yandex-music-downloader.git && \
    cd yandex-music-downloader && \
    cargo build --release && \
    mv target/release/yandex-music-downloader /usr/local/bin/

# Этап установки Python-зависимостей
FROM base AS dependencies

# Установка Python-библиотек
COPY requirements.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Итоговая сборка образа
FROM base AS final

# Копирование собранного бинарника и установленных пакетов
COPY --from=dependencies /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin/yandex-music-downloader /usr/local/bin/

# Установка runtime-зависимостей
RUN apk add --no-cache tzdata

# Настройка рабочей среды
WORKDIR /app
COPY . .

# Проверка наличия файла перед запуском
RUN if [ ! -f "/app/Bocchi_Downloader/bocchi_bot_host.py" ]; then echo "❗ Ошибка: файл bocchi_bot_host.py не обнаружен!" && exit 1; fi

# Переменные окружения
ENV PYTHONUNBUFFERED=1
ENV TELEGRAM_TOKEN="${TELEGRAM_TOKEN}"
ENV DOWNLOADER_PATH="/usr/local/bin/yandex-music-downloader"
ENV STATS_FILE="/app/stats.txt"

# Настройка безопасности и прав доступа
RUN chmod -R 755 /app && \
    mkdir -p /app/bocchi_tmp && \
    chown -R nobody:nogroup /app

USER nobody

# Команда запуска приложения
CMD ["python", "/app/Bocchi_Downloader/bocchi_bot_host.py"]
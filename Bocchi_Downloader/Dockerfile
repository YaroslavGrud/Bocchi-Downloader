# Базовый образ Python 3.11 Slim-Alpine
FROM python:3.11-slim-alpine AS base

# Этап сборки yandex-music-downloader
FROM base AS builder

# Установка необходимых инструментов для компиляции Rust
RUN apk add --no-cache \
    build-base \
    cargo \
    git \
    libffi-dev \
    musl-dev \
    rust

# Клонирование и сборка yandex-music-downloader
RUN git clone https://github.com/llistochek/yandex-music-downloader.git && \
    cd yandex-music-downloader && \
    cargo build --release && \
    mv target/release/yandex-music-downloader /usr/local/bin/

# Этап установки Python-зависимостей
FROM base AS dependencies

# Установка Python-зависимостей из requirements.txt
COPY requirements.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Итоговая сборка образа
FROM base AS final

# Копирование собранного бинарника yandex-music-downloader и установленных Python-пакетов
COPY --from=dependencies /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin/yandex-music-downloader /usr/local/bin/

# Установка runtime-зависимостей
RUN apk add --no-cache tzdata

# Настройка рабочей среды
WORKDIR /app
COPY . .

# Определение переменных окружения
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
CMD ["python", "main.py"]
FROM python:3.11-slim

# Установка системных зависимостей
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 1. Установка yandex-music-api (синхронный + async) от MarshalX
#    по инструкции из README вашего проекта
RUN git clone https://github.com/MarshalX/yandex-music-api && \
    cd yandex-music-api && \
    pip install --no-cache-dir . && \
    pip install --no-cache-dir ".[async]" && \
    cd .. && \
    rm -rf yandex-music-api

# 2. Установка yandex-music-downloader (из zip-архива llistochek, как в requirements.txt)
RUN pip install --no-cache-dir -U https://github.com/llistochek/yandex-music-downloader/archive/main.zip

# 3. Копируем requirements.txt и исключаем из него строки с yandex-music,
#    чтобы не было конфликта версий
COPY requirements.txt /tmp/requirements.txt
RUN grep -v "yandex-music" /tmp/requirements.txt > /app/requirements.txt

# 4. Устанавливаем остальные зависимости
RUN pip install --no-cache-dir -r requirements.txt

# 5. Копируем весь код бота
COPY . .

# 6. Создаём папку для данных (токены, очередь, статистика)
RUN mkdir -p /app/data
ENV STATS_FILE=/app/data/stats.txt

# 7. Скрипт для выбора версии бота (полная или классическая)
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]

FROM python:3.11-slim

# 1. Установка системных зависимостей
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 2. Установка yandex-music-api из исходников MarshalX (синхронная + async версии)
RUN git clone https://github.com/MarshalX/yandex-music-api && \
    cd yandex-music-api && \
    pip install --no-cache-dir . && \
    pip install --no-cache-dir ".[async]" && \
    cd .. && \
    rm -rf yandex-music-api

# 3. Установка yandex-music-downloader (из официального репозитория llistochek)
RUN pip install --no-cache-dir -U https://github.com/llistochek/yandex-music-downloader/archive/main.zip

# 4. Копируем обновлённый requirements.txt и устанавливаем остальные зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. Копируем весь код бота
COPY . .

# 6. Отключаем буферизацию вывода для логов
ENV PYTHONUNBUFFERED=1

# 7. Создаём папку для данных и настраиваем переменную
RUN mkdir -p /app/data
ENV STATS_FILE=/app/data/stats.txt

# 8. Скрипт для выбора версии бота
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]

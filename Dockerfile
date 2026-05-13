FROM python:3.14-slim-trixie

# 1. Установка системных зависимостей
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

# 1.1 Создаём непривилегированного пользователя (без пароля и домашней папки)
RUN useradd --create-home --shell /bin/bash bocchi

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

# 4. Копируем requirements.txt, удаляем из него строки с yandex-music* и yandex-music-downloader, затем устанавливаем остальные зависимости
COPY requirements.txt .
RUN grep -v "yandex-music" requirements.txt | grep -v "yandex-music-downloader" > requirements_clean.txt && \
    pip install --no-cache-dir -r requirements_clean.txt

# 5. Копируем весь код бота
COPY . .

# 6. Отключаем буферизацию вывода для логов
ENV PYTHONUNBUFFERED=1

# 7. Создаём папку для данных и настраиваем переменную, меняем владельца на bocchi
RUN mkdir -p /app/data && chown -R bocchi:bocchi /app/data
ENV STATS_FILE=/app/data/stats.txt

# 8. Копируем entrypoint.sh и даём права на выполнение
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# 9. Переключаемся на непривилегированного пользователя
USER bocchi

ENTRYPOINT ["/entrypoint.sh"]

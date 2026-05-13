FROM python:3.14-slim-trixie

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Системные пакеты с зафиксированными версиями (для Trixie)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg=7:7.1-2 \
    git=1:2.45.2-1 \
    && rm -rf /var/lib/apt/lists/*

# Создаём непривилегированного пользователя заранее
RUN useradd --create-home --shell /bin/bash bocchi

WORKDIR /app

# Клонируем и устанавливаем yandex-music-api
WORKDIR /app/yandex-music-api
RUN git clone https://github.com/MarshalX/yandex-music-api . && \
    pip install --no-cache-dir . && \
    pip install --no-cache-dir ".[async]"
WORKDIR /app
RUN rm -rf /app/yandex-music-api

# Устанавливаем yandex-music-downloader
RUN pip install --no-cache-dir "yandex-music-downloader @ https://github.com/llistochek/yandex-music-downloader/archive/main.zip"

# Устанавливаем остальные зависимости
COPY requirements.txt .
RUN grep -v "yandex-music" requirements.txt | grep -v "yandex-music-downloader" > requirements_clean.txt && \
    pip install --no-cache-dir --requirement requirements_clean.txt && \
    rm requirements.txt requirements_clean.txt

# Копируем код приложения
COPY . .

# Настройка окружения
ENV PYTHONUNBUFFERED=1

# Создаём папку для данных и задаём права
RUN mkdir -p /app/data && chown -R bocchi:bocchi /app/data
ENV STATS_FILE=/app/data/stats.txt

# Копируем entrypoint и даём права
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh && chown bocchi:bocchi /entrypoint.sh

USER bocchi
ENTRYPOINT ["/entrypoint.sh"]

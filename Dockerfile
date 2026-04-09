FROM python:3.11-slim

# Установка ffmpeg (требуется для обработки аудио)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копируем requirements.txt из корня репозитория
COPY requirements.txt .

# Установка зависимостей
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь исходный код репозитория (включая папку Bocchi_Downloader)
COPY . .

# Переходим в папку, где лежит основной скрипт бота
WORKDIR /app/Bocchi_Downloader

# Создаём необходимые папки для данных (опционально)
RUN mkdir -p /app/data /app/downloads /app/temp && chmod 777 /app/data /app/downloads /app/temp

# Запуск бота из текущей рабочей директории (где находится bocchi_bot_host.py)
CMD ["python", "bocchi_bot_host.py"]

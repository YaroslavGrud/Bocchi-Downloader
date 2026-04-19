FROM python:3.11-slim

# Установка системных зависимостей (ffmpeg, git)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Установка yandex-music-api от MarshalX с поддержкой async
RUN git clone https://github.com/MarshalX/yandex-music-api && \
    cd yandex-music-api && \
    pip install --no-cache-dir ".[async]" && \
    cd .. && \
    rm -rf yandex-music-api

# Копируем requirements.txt и устанавливаем остальные зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь код репозитория
COPY . .

# Рабочая директория — папка с ботом
WORKDIR /app/Bocchi_Downloader

# Создаём рабочие папки (опционально)
RUN mkdir -p /app/data /app/downloads /app/temp && chmod 777 /app/data /app/downloads /app/temp

# Запуск бота
CMD ["python", "bocchi_bot_host.py"]
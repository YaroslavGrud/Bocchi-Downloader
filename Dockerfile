FROM python:3.14-slim-trixie

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash bocchi

WORKDIR /app

RUN git clone https://github.com/MarshalX/yandex-music-api .yandex-music-api && \
    pip install --no-cache-dir .yandex-music-api && \
    pip install --no-cache-dir ".yandex-music-api[async]" && \
    rm -rf .yandex-music-api

RUN pip install --no-cache-dir https://github.com/llistochek/yandex-music-downloader/archive/refs/tags/v3.5.5.zip

COPY requirements.txt .
RUN grep -v "yandex-music" requirements.txt | grep -v "yandex-music-downloader" > requirements_clean.txt && \
    pip install --no-cache-dir --requirement requirements_clean.txt && \
    rm requirements_clean.txt

COPY . .

ENV PYTHONUNBUFFERED=1

RUN mkdir -p /app/data && chown -R bocchi:bocchi /app/data
ENV STATS_FILE=/app/data/stats.txt

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh && chown bocchi:bocchi /entrypoint.sh

USER bocchi

ENTRYPOINT ["/entrypoint.sh"]
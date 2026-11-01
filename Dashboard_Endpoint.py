import re
import time
import subprocess
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI, Response
from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(__file__).resolve().parent
GLANCES = "http://127.0.0.1:61208"

app = FastAPI(title="Bocchi Dashboard API")

# --- Собственные эндпоинты (обязательно ДО catch-all прокси) ---

@app.get("/api/ping")
def api_ping():
    """Реальный замер сетевой задержки, а не random."""
    try:
        start = time.monotonic()
        httpx.get("https://ya.ru", timeout=3.0)
        latency = round((time.monotonic() - start) * 1000)
    except Exception:
        latency = -1
    return {"latency": latency}

@app.get("/api/4/containers")
def api_containers():
    """Честный статус контейнера из docker."""
    try:
        r = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Status}}", "bocchi_bot"],
            capture_output=True, text=True, timeout=5,
        )
        status = r.stdout.strip() or "missing"
    except Exception:
        status = "unknown"
    return [{"name": "bocchi_bot", "status": status}]

@app.get("/api/4/uptime")
def api_uptime():
    """Отдаёт аптайм в секундах — фронтенд-парсер это умеет."""
    try:
        r = httpx.get(f"{GLANCES}/api/4/uptime", timeout=3.0)
        s = r.json()
        if not isinstance(s, str):
            s = str(s)
        d = re.search(r"(\d+)\s*days?", s, re.I)
        hms = re.search(r"(\d+):(\d+):(\d+)", s)
        if d or hms:
            sec = int(d.group(1)) * 86400 if d else 0
            if hms:
                sec += int(hms.group(1)) * 3600 + int(hms.group(2)) * 60 + int(hms.group(3))
            return sec
        return s  # незнакомый формат — отдаём как есть
    except Exception:
        return Response(content="{}", status_code=502)

# --- Catch-all прокси в Glances (строго после эндпоинтов выше) ---

@app.get("/api/4/{path:path}")
def glances_proxy(path: str):
    r = httpx.get(f"{GLANCES}/api/4/{path}", timeout=5.0)
    return Response(
        content=r.content,
        media_type=r.headers.get("content-type", "application/json"),
    )

# --- Статика ---

@app.get("/")
def index():
    return Response(
        content=(BASE_DIR / "bocchi_dashboard.html").read_bytes(),
        media_type="text/html",
    )

app.mount("/assets", StaticFiles(directory=str(BASE_DIR / "assets")), name="assets")

if __name__ == "__main__":
    # Порт 61209 занят Nginx — живём на внутреннем 61211
    uvicorn.run(app, host="127.0.0.1", port=61211)

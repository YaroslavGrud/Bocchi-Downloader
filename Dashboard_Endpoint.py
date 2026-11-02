import json
import re
import subprocess
import time
import urllib.request
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Response
from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(__file__).resolve().parent
GLANCES = "http://127.0.0.1:61208"

app = FastAPI(title="Bocchi Dashboard API")

def _http_get(url, timeout=5.0):
    req = urllib.request.Request(url, headers={"User-Agent": "bocchi-dashboard/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(), r.headers.get("Content-Type", "application/json")

@app.get("/api/ping")
def api_ping():
    """HTTP-задержка до music.yandex.ru — как у старого дашборда (~200 мс)."""
    try:
        start = time.monotonic()
        req = urllib.request.Request("https://music.yandex.ru/", method="HEAD")
        urllib.request.urlopen(req, timeout=3)
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
    """Аптайм Glances -> секунды."""
    try:
        body, _ = _http_get(f"{GLANCES}/api/4/uptime", 3.0)
        s = body.decode("utf-8", "replace").strip().strip('"')
        d = re.search(r"(\d+)\s*days?", s, re.I)
        hms = re.search(r"(\d+):(\d+):(\d+)", s)
        if d or hms:
            sec = int(d.group(1)) * 86400 if d else 0
            if hms:
                sec += int(hms.group(1)) * 3600 + int(hms.group(2)) * 60 + int(hms.group(3))
            return sec
        if s.isdigit():
            return int(s)
        return s
    except Exception:
        return Response(content="{}", status_code=502)

@app.get("/api/4/{path:path}")
def glances_proxy(path: str):
    """Catch-all прокси в Glances (строго после эндпоинтов выше)."""
    safe_path = path.strip()
    # Block traversal/query/fragment/control-char based path manipulation.
    if (
        not safe_path
        or safe_path.startswith("/")
        or ".." in safe_path
        or "?" in safe_path
        or "#" in safe_path
        or "\\" in safe_path
        or re.search(r"[\x00-\x1f\x7f]", safe_path)
        or not re.fullmatch(r"[A-Za-z0-9._/-]+", safe_path)
    ):
        return Response(
            content=json.dumps({"error": "Invalid path"}),
            status_code=400,
            media_type="application/json",
        )
    try:
        body, ctype = _http_get(f"{GLANCES}/api/4/{safe_path}", 5.0)
        return Response(content=body, media_type=ctype)
    except Exception as e:
        return Response(content=json.dumps({"error": str(e)}),
                        status_code=502, media_type="application/json")

@app.get("/")
def index():
    return Response(
        content=(BASE_DIR / "bocchi_dashboard.html").read_bytes(),
        media_type="text/html",
    )

app.mount("/assets", StaticFiles(directory=str(BASE_DIR / "assets")), name="assets")

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=61211)

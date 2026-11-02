import json
import logging
import re
import subprocess
import time
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Response
from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(__file__).resolve().parent
GLANCES = "http://127.0.0.1:61208"

logger = logging.getLogger(__name__)

app = FastAPI(title="Bocchi Dashboard API")

# --- SSRF guard: every outbound request goes through an allowlist (CWE-918/939) ---

ALLOWED_HOSTS = ("127.0.0.1", "localhost", "music.yandex.ru")
ALLOWED_SCHEMES = ("http", "https")


def _is_allowed_url(url: str) -> bool:
    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError:
        return False
    return (
        parsed.scheme in ALLOWED_SCHEMES
        and parsed.hostname in ALLOWED_HOSTS
        and not parsed.username
        and not parsed.password
    )


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Block redirects that would leave the allowlisted hosts."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _is_allowed_url(newurl):
            raise urllib.error.HTTPError(
                req.full_url, code, "Redirect to disallowed host blocked", headers, fp
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_opener = urllib.request.build_opener(_SafeRedirectHandler)


def _http_get(url, timeout=5.0, method="GET"):
    if not _is_allowed_url(url):
        raise ValueError(f"URL host is not in the allowlist: {url!r}")
    req = urllib.request.Request(url, method=method, headers={"User-Agent": "bocchi-dashboard/1.0"})
    with _opener.open(req, timeout=timeout) as r:
        return r.read(), r.headers.get("Content-Type", "application/json")


@app.get("/api/ping")
def api_ping():
    """HTTP-задержка до music.yandex.ru — как у старого дашборда (~200 мс)."""
    try:
        start = time.monotonic()
        _http_get("https://music.yandex.ru/", timeout=3.0, method="HEAD")
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
    except Exception:
        logger.exception("Glances proxy request failed")
        return Response(content=json.dumps({"error": "Upstream service unavailable"}),
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

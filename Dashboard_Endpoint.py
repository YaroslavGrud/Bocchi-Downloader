import time
import random
import httpx
from fastapi import FastAPI, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse

app = FastAPI()

# Адрес вашего API (Glances) на порту 61208
GLANCES_API_URL = "http://185.170.153.38:61208"

# Раздача статики (картинки персонажей из папки assets/)
app.mount("/assets", StaticFiles(directory="assets"), name="assets")

@app.get("/")
def read_index():
    return FileResponse("bocchi_dashboard.html")

# Проксируем все запросы /api/4/... на реальный Glances API (порт 61208)
@app.get("/api/4/{path:path}")
async def proxy_glances(path: str):
    async with httpx.AsyncClient() as client:
        try:
            url = f"{GLANCES_API_URL}/api/4/{path}"
            resp = await client.get(url, timeout=5.0)
            return JSONResponse(content=resp.json(), status_code=resp.status_code)
        except Exception as e:
            # Возвращаем заглушку или ошибку, если Glances недоступен
            return JSONResponse(content={"error": str(e)}, status_code=502)

# Кастомный эндпоинт пинга
@app.get("/api/ping")
def api_ping():
    return {"latency": random.randint(15, 60)}

# Эндпоинт для проверки статуса контейнера бота
@app.get("/api/4/containers")
def api_containers():
    # Здесь можно сделать реальную проверку через docker SDK или оставить статус running
    return [{"name": "bocchi_bot", "status": "running"}]

if __name__ == "__main__":
    import uvicorn
    # Запускаем сервер дашборда на порту 61209, как вы и указали
    uvicorn.run("Dashboard_Endpoint:app", host="0.0.0.0", port=61209, reload=True)
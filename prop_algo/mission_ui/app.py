from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .websocket import router

_STATIC = Path(__file__).resolve().parent / "static"

app = FastAPI()
app.include_router(router)
app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")


@app.get("/")
def index():
    with open(_STATIC / "dashboard.html", encoding="utf-8") as f:
        return HTMLResponse(f.read())

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
import logging
from app.api import health_router, anki_router, flashcards_router, history_router
class AnkiStatusFilter(logging.Filter):
    def filter(self, record):
        msg = record.getMessage()
        return (
            "/api/anki-status" not in msg
            and "/api/ollama-status" not in msg
            and "http://127.0.0.1:8765" not in msg
        )

logging.basicConfig(level=logging.INFO)
logging.getLogger("uvicorn.access").addFilter(AnkiStatusFilter())
logging.getLogger("httpx").addFilter(AnkiStatusFilter())

app = FastAPI(title="Flash Card Generator", version="1.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(health_router)
app.include_router(anki_router)
app.include_router(flashcards_router)
app.include_router(history_router)

# SPA fallback
@app.exception_handler(StarletteHTTPException)
async def spa_fallback(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404 and not request.url.path.startswith("/api"):
        return FileResponse("static/dist/index.html", headers={"Cache-Control": "no-cache"})
    raise exc

# Static files
app.mount("/", StaticFiles(directory="static/dist"), name="static")

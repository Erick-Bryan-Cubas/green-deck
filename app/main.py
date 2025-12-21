from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import logging
from app.api import health_router, anki_router, flashcards_router, history_router

class AnkiStatusFilter(logging.Filter):
    def filter(self, record):
        msg = record.getMessage()
        return "/api/anki-status" not in msg and "http://127.0.0.1:8765" not in msg

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
class NoCacheStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return response
# Root
@app.get("/")
async def root():
    return FileResponse("static/dist/index.html", headers={"Cache-Control": "no-cache, no-store, must-revalidate"})

# Static files
app.mount("/", NoCacheStaticFiles(directory="static/dist", html=True), name="static")

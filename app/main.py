from fastapi import FastAPI, WebSocket, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os
from contextlib import asynccontextmanager
import logging

from app.core.config import settings
from app.core.database import init_db
from app.core.redis import close_redis
from app.core.paths import STATIC_DIR
from app.api import auth, rooms, runner, chat, complexity, canvas, agent, saved_items
from app.websocket.collab import handle_collab_ws

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("CodeZen backend starting...")
    await init_db()
    logger.info("Database initialized")
    yield
    await close_redis()
    logger.info("CodeZen backend stopped")


app = FastAPI(
    title="CodeZen API",
    description="AI-powered collaborative coding education platform",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(rooms.router, prefix="/api/v1")
app.include_router(runner.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")
app.include_router(complexity.router, prefix="/api/v1")
app.include_router(canvas.router, prefix="/api/v1")
app.include_router(agent.router, prefix="/api/v1")
app.include_router(saved_items.router, prefix="/api/v1")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.websocket("/ws/collab/{room_id}")
async def collab_websocket(
    websocket: WebSocket,
    room_id: str,
    token: str = Query(...),
):
    await handle_collab_ws(websocket, room_id, token)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": "2.0.0",
        "env": settings.APP_ENV,
    }


@app.get("/")
async def root():
    return {
        "message": "CodeZen API is running",
        "docs": "http://localhost:8000/docs",
        "health": "http://localhost:8000/health",
    }
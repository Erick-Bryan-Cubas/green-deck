# app/api/websocket.py
"""
WebSocket endpoint for real-time Anki/Ollama status updates.
Replaces polling with push-based notifications.
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio
import httpx
import os
from typing import Dict, Set
from app.config import ANKI_CONNECT_URL

router = APIRouter(tags=["websocket"])

# Connection manager for broadcasting status updates
class ConnectionManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self._status_cache: Dict[str, dict] = {
            "anki": {"connected": False, "version": None, "url": None},
            "ollama": {"connected": False, "host": None, "models": []}
        }
        self.broadcast_task: asyncio.Task | None = None
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        # Send current cached status immediately
        await websocket.send_json({
            "type": "status_update",
            "data": self._status_cache
        })
    
    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)
    
    async def broadcast(self, message: dict):
        disconnected = set()
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except (WebSocketDisconnect, RuntimeError, ConnectionError):
                disconnected.add(connection)
        # Clean up disconnected clients
        for conn in disconnected:
            self.active_connections.discard(conn)
    
    def update_cache(self, service: str, status: dict):
        self._status_cache[service] = status
    
    def get_cache(self) -> Dict[str, dict]:
        return self._status_cache.copy()

manager = ConnectionManager()

async def check_anki_status() -> dict:
    """Check Anki connection status."""
    url = (ANKI_CONNECT_URL or "http://127.0.0.1:8765").rstrip("/")
    payload = {"action": "version", "version": 6}
    
    try:
        async with httpx.AsyncClient(timeout=2.5) as client:
            r = await client.post(url, json=payload)
            r.raise_for_status()
            data = r.json() or {}
            
            ok = (data.get("error") is None) and (data.get("result") is not None)
            if ok:
                return {"connected": True, "version": data["result"], "url": url}
            return {"connected": False, "url": url, "error": data.get("error")}
    except (httpx.RequestError, httpx.HTTPStatusError) as e:
        return {"connected": False, "url": url, "error": str(e)}

async def check_ollama_status() -> dict:
    """Check Ollama connection status."""
    host = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
    
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(f"{host}/api/tags")
            r.raise_for_status()
            data = r.json() or {}
            models = [m.get("name") for m in (data.get("models") or []) if m.get("name")]
            return {"connected": True, "host": host, "models": models}
    except (httpx.RequestError, httpx.HTTPStatusError) as e:
        return {"connected": False, "host": host, "models": [], "error": str(e)}

async def status_broadcaster():
    """Background task that checks status and broadcasts changes."""
    while True:
        try:
            # Check both services concurrently
            anki_status, ollama_status = await asyncio.gather(
                check_anki_status(),
                check_ollama_status()
            )
            
            # Check for changes
            old_cache = manager.get_cache()
            changes = {}
            
            if anki_status != old_cache.get("anki"):
                manager.update_cache("anki", anki_status)
                changes["anki"] = anki_status
            
            if ollama_status != old_cache.get("ollama"):
                manager.update_cache("ollama", ollama_status)
                changes["ollama"] = ollama_status
            
            # Broadcast only if there are changes and clients connected
            if changes and manager.active_connections:
                await manager.broadcast({
                    "type": "status_update",
                    "data": manager.get_cache()
                })
            
        except asyncio.CancelledError:
            break
        except (httpx.RequestError, RuntimeError):
            pass  # Ignore transient errors
        
        # Check every 3 seconds (adjustable)
        await asyncio.sleep(3)

@router.websocket("/ws/status")
async def websocket_status(websocket: WebSocket):
    """WebSocket endpoint for real-time status updates."""
    await manager.connect(websocket)
    
    try:
        while True:
            # Keep connection alive, handle any incoming messages
            data = await websocket.receive_text()
            
            # Handle ping/pong for keepalive
            if data == "ping":
                await websocket.send_text("pong")
            # Handle force refresh request
            elif data == "refresh":
                anki_status, ollama_status = await asyncio.gather(
                    check_anki_status(),
                    check_ollama_status()
                )
                manager.update_cache("anki", anki_status)
                manager.update_cache("ollama", ollama_status)
                await websocket.send_json({
                    "type": "status_update",
                    "data": manager.get_cache()
                })
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except (RuntimeError, ConnectionError):
        manager.disconnect(websocket)

async def start_broadcaster():
    """Start the background status broadcaster task."""
    if manager.broadcast_task is None or manager.broadcast_task.done():
        manager.broadcast_task = asyncio.create_task(status_broadcaster())

async def stop_broadcaster():
    """Stop the background status broadcaster task."""
    if manager.broadcast_task and not manager.broadcast_task.done():
        manager.broadcast_task.cancel()
        try:
            await manager.broadcast_task
        except asyncio.CancelledError:
            pass

# app/api/websocket.py
"""
WebSocket endpoints for real-time updates:
- /ws/status: Anki/Ollama status updates
- /ws/extraction: Document extraction progress
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio
import httpx
import os
import logging
from typing import Dict, Set, Optional, Any
from app.config import ANKI_CONNECT_URL

router = APIRouter(tags=["websocket"])
logger = logging.getLogger(__name__)

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


# ============================================================================
# Document Extraction WebSocket Manager
# ============================================================================

class ExtractionManager:
    """
    Gerenciador de tarefas de extração de documentos.

    Permite que múltiplos clientes WebSocket acompanhem o progresso
    de tarefas de extração em tempo real.
    """

    def __init__(self):
        self.tasks: Dict[str, Dict[str, Any]] = {}  # task_id -> task_info
        self.subscribers: Dict[str, Set[WebSocket]] = {}  # task_id -> websockets
        self._lock = asyncio.Lock()

    def create_task(self, task_id: str, total_pages: int, filename: str) -> None:
        """Cria uma nova tarefa de extração."""
        self.tasks[task_id] = {
            "status": "pending",
            "progress": 0,
            "current_page": 0,
            "total_pages": total_pages,
            "filename": filename,
            "result": None,
            "error": None,
            "message": f"Preparando extração de {total_pages} páginas..."
        }
        self.subscribers[task_id] = set()
        logger.info(f"[Extraction] Task {task_id} created for {filename} ({total_pages} pages)")

    async def update_progress(
        self,
        task_id: str,
        current_page: int,
        progress: float,
        message: Optional[str] = None
    ) -> None:
        """Atualiza o progresso de uma tarefa e notifica os inscritos."""
        if task_id not in self.tasks:
            return

        self.tasks[task_id]["current_page"] = current_page
        self.tasks[task_id]["progress"] = round(progress, 1)
        self.tasks[task_id]["status"] = "processing"
        if message:
            self.tasks[task_id]["message"] = message
        else:
            total = self.tasks[task_id]["total_pages"]
            self.tasks[task_id]["message"] = f"Processando página {current_page}... ({current_page}/{total})"

        await self._broadcast_to_task(task_id, {
            "type": "extraction_progress",
            "task_id": task_id,
            "progress": self.tasks[task_id]["progress"],
            "current_page": current_page,
            "total_pages": self.tasks[task_id]["total_pages"],
            "message": self.tasks[task_id]["message"]
        })

    async def complete_task(self, task_id: str, result: Dict[str, Any]) -> None:
        """Marca a tarefa como concluída e envia o resultado."""
        if task_id not in self.tasks:
            return

        self.tasks[task_id]["status"] = "completed"
        self.tasks[task_id]["progress"] = 100
        self.tasks[task_id]["result"] = result
        self.tasks[task_id]["message"] = f"Extração concluída! {result.get('word_count', 0)} palavras."

        logger.info(f"[Extraction] Task {task_id} completed: {result.get('word_count', 0)} words")

        await self._broadcast_to_task(task_id, {
            "type": "extraction_complete",
            "task_id": task_id,
            "success": True,
            **result
        })

        # Cleanup task after 5 minutes
        asyncio.create_task(self._cleanup_task(task_id, delay=300))

    async def fail_task(self, task_id: str, error: str) -> None:
        """Marca a tarefa como falha e notifica o erro."""
        if task_id not in self.tasks:
            return

        self.tasks[task_id]["status"] = "failed"
        self.tasks[task_id]["error"] = error
        self.tasks[task_id]["message"] = f"Erro: {error}"

        logger.error(f"[Extraction] Task {task_id} failed: {error}")

        await self._broadcast_to_task(task_id, {
            "type": "extraction_error",
            "task_id": task_id,
            "error": error
        })

        # Cleanup task after 1 minute
        asyncio.create_task(self._cleanup_task(task_id, delay=60))

    async def subscribe(self, task_id: str, websocket: WebSocket) -> bool:
        """
        Inscreve um WebSocket para receber atualizações de uma tarefa.
        Retorna True se a tarefa existe, False caso contrário.
        """
        if task_id not in self.tasks:
            logger.warning(f"[Extraction] Subscribe failed: Task {task_id} not found")
            await websocket.send_json({
                "type": "error",
                "error": f"Task {task_id} not found"
            })
            return False

        self.subscribers[task_id].add(websocket)

        # Envia o status atual imediatamente
        task_info = self.tasks[task_id].copy()
        # Remove result if too large for initial status
        if task_info.get("result"):
            task_info["has_result"] = True
            task_info.pop("result", None)

        status_message = {
            "type": "extraction_status",
            "task_id": task_id,
            **task_info
        }

        logger.info(f"[Extraction] Sending initial status to subscriber: {status_message}")
        await websocket.send_json(status_message)

        logger.info(f"[Extraction] WebSocket subscribed to task {task_id}, status: {task_info.get('status')}, progress: {task_info.get('progress')}")
        return True

    def unsubscribe(self, task_id: str, websocket: WebSocket) -> None:
        """Remove um WebSocket da lista de inscritos de uma tarefa."""
        if task_id in self.subscribers:
            self.subscribers[task_id].discard(websocket)

    async def _broadcast_to_task(self, task_id: str, message: Dict[str, Any]) -> None:
        """Envia uma mensagem para todos os WebSockets inscritos em uma tarefa."""
        if task_id not in self.subscribers:
            logger.debug(f"[Extraction] No subscribers for task {task_id}")
            return

        num_subscribers = len(self.subscribers[task_id])
        if num_subscribers == 0:
            logger.debug(f"[Extraction] Task {task_id} has 0 subscribers, skipping broadcast")
            return

        logger.debug(f"[Extraction] Broadcasting to {num_subscribers} subscriber(s): type={message.get('type')}, progress={message.get('progress')}")

        disconnected = set()
        for ws in self.subscribers[task_id]:
            try:
                await ws.send_json(message)
            except (WebSocketDisconnect, RuntimeError, ConnectionError) as e:
                logger.warning(f"[Extraction] Failed to send to subscriber: {e}")
                disconnected.add(ws)

        # Limpa conexões desconectadas
        for ws in disconnected:
            self.subscribers[task_id].discard(ws)

    async def _cleanup_task(self, task_id: str, delay: int = 300) -> None:
        """Remove uma tarefa após um delay (para liberar memória)."""
        await asyncio.sleep(delay)
        self.tasks.pop(task_id, None)
        self.subscribers.pop(task_id, None)
        logger.debug(f"[Extraction] Task {task_id} cleaned up")

    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Retorna o status atual de uma tarefa."""
        return self.tasks.get(task_id)


# Instância global do gerenciador de extração
extraction_manager = ExtractionManager()


@router.websocket("/ws/extraction")
async def websocket_extraction(websocket: WebSocket):
    """
    WebSocket endpoint para progresso de extração de documentos em tempo real.

    Mensagens do cliente:
    - {"action": "subscribe", "task_id": "..."}: Inscreve para receber atualizações
    - {"action": "unsubscribe", "task_id": "..."}: Cancela inscrição
    - {"action": "ping"}: Keepalive
    - {"action": "status", "task_id": "..."}: Solicita status atual

    Mensagens do servidor:
    - {"type": "extraction_status", ...}: Status atual da tarefa
    - {"type": "extraction_progress", ...}: Atualização de progresso
    - {"type": "extraction_complete", ...}: Extração concluída com resultado
    - {"type": "extraction_error", ...}: Erro na extração
    - {"type": "pong"}: Resposta ao ping
    """
    await websocket.accept()
    subscribed_tasks: Set[str] = set()

    logger.info("[Extraction] WebSocket connected")

    try:
        while True:
            try:
                data = await websocket.receive_json()
            except Exception:
                # Pode ser texto simples (ping)
                try:
                    text = await websocket.receive_text()
                    if text == "ping":
                        await websocket.send_text("pong")
                    continue
                except Exception:
                    break

            action = data.get("action")
            task_id = data.get("task_id")

            if action == "subscribe" and task_id:
                success = await extraction_manager.subscribe(task_id, websocket)
                if success:
                    subscribed_tasks.add(task_id)

            elif action == "unsubscribe" and task_id:
                extraction_manager.unsubscribe(task_id, websocket)
                subscribed_tasks.discard(task_id)

            elif action == "ping":
                await websocket.send_json({"type": "pong"})

            elif action == "status" and task_id:
                status = extraction_manager.get_task_status(task_id)
                if status:
                    await websocket.send_json({
                        "type": "extraction_status",
                        "task_id": task_id,
                        **status
                    })
                else:
                    await websocket.send_json({
                        "type": "error",
                        "error": f"Task {task_id} not found"
                    })

    except WebSocketDisconnect:
        logger.info("[Extraction] WebSocket disconnected")
    except (RuntimeError, ConnectionError) as e:
        logger.warning(f"[Extraction] WebSocket error: {e}")
    finally:
        # Limpa todas as inscrições deste WebSocket
        for task_id in subscribed_tasks:
            extraction_manager.unsubscribe(task_id, websocket)

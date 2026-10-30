import os
import time
from typing import Any, Dict
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import httpx

from database import Base, engine
from ollama_proxy import router as ollama_router
from realtime import manager
from routes.auth_routes import router as auth_router
from routes.conversation_routes import router as conversation_router
from routes.model_routes import router as model_router
from routes.mcp_routes import router as mcp_router

# Création des tables PostgreSQL au démarrage
try:
    Base.metadata.create_all(bind=engine)
except Exception as e:
    print(f"[SensAI] Erreur initialisation Base de données: {e}")

app = FastAPI(
    title="SENSAI API",
    description="Backend API pour l'assistant SENSAI & collaboration temps réel",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ia:11434")

# Inclusion des routeurs
app.include_router(auth_router)
app.include_router(conversation_router)
app.include_router(model_router)
app.include_router(mcp_router)
app.include_router(ollama_router)


@app.websocket("/api/ws/conversations/{conversation_id}")
async def websocket_endpoint(websocket: WebSocket, conversation_id: str):
    await manager.connect(conversation_id, websocket)
    try:
        while True:
            # Écoute des pings ou messages du client
            data = await websocket.receive_text()
            # On peut renvoyer un pong ou relayer les actions
    except WebSocketDisconnect:
        manager.disconnect(conversation_id, websocket)
    except Exception:
        manager.disconnect(conversation_id, websocket)


@app.get("/")
def read_root() -> Dict[str, str]:
    return {"status": "ok", "service": "sensai-backend", "version": "0.2.0"}


@app.get("/about.json")
def get_about(request: Request) -> Dict[str, Any]:
    client_host = request.client.host if request.client else "unknown"
    return {
        "client": {
            "host": client_host,
        },
        "server": {
            "current_time": int(time.time()),
            "services": [
                {
                    "name": "sensai",
                    "actions": ["chat", "collaborate", "tools"],
                    "reactions": ["stream", "broadcast"],
                }
            ],
        },
    }


@app.get("/health")
@app.get("/api/health")
async def health_check() -> Dict[str, Any]:
    ollama_status = "unreachable"
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            res = await client.get(f"{OLLAMA_BASE_URL}/")
            if res.status_code == 200:
                ollama_status = "connected"
    except Exception:
        ollama_status = "disconnected"

    return {
        "backend": "healthy",
        "ollama": ollama_status,
        "database": "connected",
    }

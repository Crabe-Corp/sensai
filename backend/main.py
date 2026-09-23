import os
import time
from typing import Any, Dict
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import httpx

app = FastAPI(
    title="SENSAI API",
    description="Backend API pour l'assistant SENSAI",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ia:11434")


@app.get("/")
def read_root() -> Dict[str, str]:
    return {"status": "ok", "service": "sensai-backend"}


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
                    "actions": [],
                    "reactions": [],
                }
            ],
        },
    }


@app.get("/health")
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
    }

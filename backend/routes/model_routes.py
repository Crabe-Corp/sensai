import json
import os
from typing import List, Optional
from fastapi import APIRouter, Depends
import httpx
from pydantic import BaseModel
from sqlalchemy.orm import Session
from database import get_db
from models import ModelPreference, User
from security import get_current_user
from tools_registry import list_tools

router = APIRouter(prefix="/api/models", tags=["models"])
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ia:11434")


class ModelConfigUpdate(BaseModel):
    model_name: str
    temperature: Optional[float] = 0.7
    active_tools: Optional[List[str]] = []


@router.get("")
async def get_available_models():
    """Récupère la liste des modèles disponibles auprès d'Ollama + fallback par défaut."""
    models_list = []
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            if resp.status_code == 200:
                tags = resp.json().get("models", [])
                models_list = [m.get("name") for m in tags if m.get("name")]
    except Exception:
        pass

    if not models_list:
        models_list = ["qwen3:0.6b", "llama3.2:1b", "mistral:7b"]

    return {
        "models": models_list,
        "default": models_list[0] if models_list else "qwen3:0.6b"
    }


@router.get("/tools")
def get_available_tools():
    """Renvoie la liste des outils créés main dans le repo."""
    return list_tools()


@router.get("/config")
def get_user_model_config(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    pref = db.query(ModelPreference).filter(ModelPreference.user_id == user.id).first()
    if not pref:
        return {
            "model_name": "qwen3:0.6b",
            "temperature": 0.7,
            "active_tools": ["structured_output"]
        }
    tools = json.loads(pref.active_tools) if pref.active_tools else []
    tools = [t for t in tools if t in ["structured_output", "Structured Output", "mcp_runner"]]
    return {
        "model_name": pref.model_name,
        "temperature": pref.temperature,
        "active_tools": tools
    }


@router.post("/config")
def update_user_model_config(
    cfg: ModelConfigUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    pref = db.query(ModelPreference).filter(ModelPreference.user_id == user.id).first()
    cleaned_tools = [t for t in (cfg.active_tools or []) if t in ["structured_output", "Structured Output", "mcp_runner"]]
    tools_json = json.dumps(cleaned_tools)
    if not pref:
        pref = ModelPreference(
            user_id=user.id,
            model_name=cfg.model_name,
            temperature=cfg.temperature or 0.7,
            active_tools=tools_json
        )
        db.add(pref)
    else:
        pref.model_name = cfg.model_name
        pref.temperature = cfg.temperature or 0.7
        pref.active_tools = tools_json

    db.commit()
    db.refresh(pref)
    return {
        "success": True,
        "model_name": pref.model_name,
        "temperature": pref.temperature,
        "active_tools": cleaned_tools
    }


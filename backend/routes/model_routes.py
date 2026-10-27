import json
import os
import sys
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Depends
import httpx
from pydantic import BaseModel
from sqlalchemy.orm import Session
from database import get_db
from models import ModelPreference, User
from security import get_current_user
from tools_registry import ALL_TOOLS_ID, list_tools

# S'assurer que le package src est importable
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

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


@router.get("/personas")
def get_available_personas():
    """Renvoie la liste des Personas avec leur id, nom, description et prompt système."""
    personas: List[dict] = []
    seen_ids = set()

    # 1. Vérification dans configs/personas.json
    configs_paths = [
        Path("configs/personas.json"),
        _ROOT / "configs" / "personas.json",
        Path(__file__).resolve().parent.parent / "configs" / "personas.json",
    ]
    for p in configs_paths:
        if p.is_file():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                items = data.get("personas", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
                for item in items:
                    p_id = str(item.get("id") or item.get("name", "").lower().replace(" ", "_"))
                    if p_id and p_id not in seen_ids:
                        prompt_text = str(item.get("system_prompt") or item.get("prompt") or "")
                        personas.append({
                            "id": p_id,
                            "name": str(item.get("name") or p_id),
                            "description": str(item.get("description") or ""),
                            "system_prompt": prompt_text,
                            "prompt": prompt_text,
                        })
                        seen_ids.add(p_id)
            except Exception:
                pass
            break

    # 2. Complément ou fallback avec PersonaManager
    try:
        try:
            from src.features.prompt.persona import PersonaManager
        except ImportError:
            from src.features.prompt.persona_manager import PersonaManager

        pm = PersonaManager()
        if not personas and not pm.list_personas():
            pm.ensure_default_personas()

        for p_id in pm.list_personas():
            if p_id not in seen_ids:
                try:
                    loaded = pm.load_persona(p_id)
                    prompt_text = loaded.system_prompt
                    personas.append({
                        "id": p_id,
                        "name": loaded.name,
                        "description": loaded.description,
                        "system_prompt": prompt_text,
                        "prompt": prompt_text,
                    })
                    seen_ids.add(p_id)
                except Exception:
                    pass
    except Exception:
        pass

    return personas


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
    valid_ids = [t["id"] for t in list_tools()] + ["Structured Output", ALL_TOOLS_ID]
    tools = [t for t in tools if t in valid_ids]
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
    valid_ids = [t["id"] for t in list_tools()] + ["Structured Output", ALL_TOOLS_ID]
    cleaned_tools = [t for t in (cfg.active_tools or []) if t in valid_ids]
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

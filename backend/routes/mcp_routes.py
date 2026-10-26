from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from security import get_current_user

router = APIRouter(prefix="/api/mcp", tags=["mcp"])

DEFAULT_MCP_SERVERS = [
    {
        "id": "shadcn",
        "name": "shadcn/ui Registry",
        "description": "Exploration et intégration directe des composants d'interface Shadcn.",
        "status": "connected",
        "endpoint": "local-stdio",
        "tools_count": 7
    },
    {
        "id": "composio",
        "name": "Composio Platform",
        "description": "Connecteurs externes vers GitHub, Gmail, Slack, etc.",
        "status": "available",
        "endpoint": "remote-bridge",
        "tools_count": 11
    },
    {
        "id": "sensai_lore",
        "name": "SensAI Lore & DB Server (MCP Custom)",
        "description": "Serveur MCP interne pour la gestion des 7 Royaumes et diplomatie.",
        "status": "connected",
        "endpoint": "internal-bus",
        "tools_count": 3
    }
]


class McpServerCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    endpoint: str


@router.get("/servers")
def get_mcp_servers(user=Depends(get_current_user)):
    return {
        "servers": DEFAULT_MCP_SERVERS,
        "total": len(DEFAULT_MCP_SERVERS)
    }


@router.post("/servers")
def add_mcp_server(server: McpServerCreate, user=Depends(get_current_user)):
    new_s = {
        "id": server.name.lower().replace(" ", "_"),
        "name": server.name,
        "description": server.description or "Serveur MCP configuré manuellement.",
        "status": "registered",
        "endpoint": server.endpoint,
        "tools_count": 0
    }
    DEFAULT_MCP_SERVERS.append(new_s)
    return {"success": True, "server": new_s}


@router.delete("/servers/{server_id}")
def delete_mcp_server(server_id: str, user=Depends(get_current_user)):
    global DEFAULT_MCP_SERVERS
    initial_len = len(DEFAULT_MCP_SERVERS)
    DEFAULT_MCP_SERVERS = [s for s in DEFAULT_MCP_SERVERS if s["id"] != server_id]
    if len(DEFAULT_MCP_SERVERS) == initial_len:
        raise HTTPException(status_code=404, detail="Serveur MCP introuvable")
    return {"success": True, "message": "Serveur MCP supprimé avec succès"}


from pathlib import Path
import shlex
import sys
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from security import get_current_user

# S'assurer que les packages src et backend sont importables
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from src.features.tools.mcp_client import MCPClient, MCPError
from tools_registry import default_registry, register_mcp_client, unregister_mcp_tools

router = APIRouter(prefix="/api/mcp", tags=["mcp"])

DEFAULT_MCP_SERVERS: List[Dict[str, Any]] = [
    {
        "id": "shadcn",
        "name": "shadcn/ui Registry",
        "description": "Exploration et intégration directe des composants d'interface Shadcn.",
        "status": "available",
        "endpoint": "local-stdio",
        "tools_count": 0,
        "tools": [],
    },
    {
        "id": "composio",
        "name": "Composio Platform",
        "description": "Connecteurs externes vers GitHub, Gmail, Slack, etc.",
        "status": "available",
        "endpoint": "remote-bridge",
        "tools_count": 0,
        "tools": [],
    },
    {
        "id": "sensai_lore",
        "name": "SensAI Lore & DB Server (MCP Custom)",
        "description": "Serveur MCP interne pour la gestion des 7 Royaumes et diplomatie.",
        "status": "available",
        "endpoint": "python -m src.features.tools.mcp_server_demo",
        "tools_count": 0,
        "tools": [],
    },
    {
        "id": "demo_server",
        "name": "Warring States Demo Server",
        "description": "Serveur MCP local de démonstration pour les calculs logistiques et batailles des Royaumes Combattants.",
        "status": "available",
        "endpoint": "python -m src.features.tools.mcp_server_demo",
        "tools_count": 0,
        "tools": [],
    },
]

_active_mcp_clients: Dict[str, MCPClient] = {}
_active_mcp_tools: Dict[str, List[str]] = {}


def _normalize_command(cmd_str: str) -> List[str]:
    parts = [p.strip('"\'') for p in shlex.split(cmd_str, posix=False)]
    if parts and parts[0] in ("python", "python3", "py"):
        parts[0] = sys.executable
    return parts


def _sync_servers_state() -> None:
    for s in DEFAULT_MCP_SERVERS:
        s_id = s.get("id")
        client = _active_mcp_clients.get(s_id)
        if client and client.is_connected:
            s["status"] = "connected"
            s["tools_count"] = len(_active_mcp_tools.get(s_id, []))
            s["tools"] = list(_active_mcp_tools.get(s_id, []))
        elif s.get("status") == "connected":
            s["status"] = "disconnected"
            s["tools_count"] = 0
            s["tools"] = []


def _disconnect_single_server(server_id: str) -> bool:
    client = _active_mcp_clients.pop(server_id, None)
    tools = _active_mcp_tools.pop(server_id, [])
    if tools:
        unregister_mcp_tools(tools)
    if client:
        try:
            client.close()
        except Exception:
            pass
    for s in DEFAULT_MCP_SERVERS:
        if s["id"] == server_id:
            s["status"] = "disconnected"
            s["tools_count"] = 0
            s["tools"] = []
            break
    return client is not None


class McpServerCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    endpoint: str


class McpConnectRequest(BaseModel):
    server_id: Optional[str] = None
    command: Optional[str] = None
    endpoint: Optional[str] = None


class McpDisconnectRequest(BaseModel):
    server_id: Optional[str] = None


@router.get("/servers")
def get_mcp_servers(user=Depends(get_current_user)):
    _sync_servers_state()
    return {
        "servers": DEFAULT_MCP_SERVERS,
        "total": len(DEFAULT_MCP_SERVERS),
    }


@router.post("/servers")
def add_mcp_server(server: McpServerCreate, user=Depends(get_current_user)):
    new_s = {
        "id": server.name.lower().replace(" ", "_"),
        "name": server.name,
        "description": server.description or "Serveur MCP configuré manuellement.",
        "status": "available",
        "endpoint": server.endpoint,
        "tools_count": 0,
        "tools": [],
    }
    DEFAULT_MCP_SERVERS.append(new_s)
    return {"success": True, "server": new_s}


@router.delete("/servers/{server_id}")
def delete_mcp_server(server_id: str, user=Depends(get_current_user)):
    global DEFAULT_MCP_SERVERS
    if server_id in _active_mcp_clients:
        _disconnect_single_server(server_id)

    initial_len = len(DEFAULT_MCP_SERVERS)
    DEFAULT_MCP_SERVERS = [s for s in DEFAULT_MCP_SERVERS if s["id"] != server_id]
    if len(DEFAULT_MCP_SERVERS) == initial_len:
        raise HTTPException(status_code=404, detail="Serveur MCP introuvable")
    return {"success": True, "message": "Serveur MCP supprimé avec succès"}


@router.get("/status")
def get_mcp_status(server_id: Optional[str] = None, user=Depends(get_current_user)):
    _sync_servers_state()
    if server_id:
        client = _active_mcp_clients.get(server_id)
        is_conn = client is not None and client.is_connected
        tools = _active_mcp_tools.get(server_id, [])
        srv = next((s for s in DEFAULT_MCP_SERVERS if s["id"] == server_id), None)
        return {
            "server_id": server_id,
            "connected": is_conn,
            "status": "connected" if is_conn else (srv.get("status") if srv else "disconnected"),
            "tools_count": len(tools),
            "tools": tools,
            "endpoint": srv.get("endpoint") if srv else None,
        }

    connected_ids = [s_id for s_id, c in _active_mcp_clients.items() if c.is_connected]
    all_tools: List[str] = []
    for tools_list in _active_mcp_tools.values():
        all_tools.extend(tools_list)

    return {
        "connected": len(connected_ids) > 0,
        "connected_servers": connected_ids,
        "connected_count": len(connected_ids),
        "total_servers": len(DEFAULT_MCP_SERVERS),
        "tools_count": len(all_tools),
        "tools": all_tools,
        "servers": DEFAULT_MCP_SERVERS,
    }


@router.post("/connect")
def connect_mcp_server(
    req: Optional[McpConnectRequest] = None,
    user=Depends(get_current_user),
):
    req = req or McpConnectRequest()
    target_id = req.server_id

    srv = next((s for s in DEFAULT_MCP_SERVERS if s["id"] == target_id), None) if target_id else None

    if not srv and not target_id and not req.command and not req.endpoint:
        srv = next((s for s in DEFAULT_MCP_SERVERS if s["id"] == "demo_server"), None)
        if not srv and DEFAULT_MCP_SERVERS:
            srv = DEFAULT_MCP_SERVERS[0]
        if srv:
            target_id = srv["id"]

    cmd_str = req.command or req.endpoint or (srv.get("endpoint") if srv else None)

    if not cmd_str:
        raise HTTPException(
            status_code=400,
            detail="Aucune commande ou endpoint spécifié pour la connexion MCP.",
        )

    if cmd_str in ("local-stdio", "remote-bridge"):
        raise HTTPException(
            status_code=400,
            detail=f"L'endpoint '{cmd_str}' est un placeholder. Fournissez une commande exécutable valide.",
        )

    if not srv:
        target_id = target_id or "custom_mcp"
        srv = {
            "id": target_id,
            "name": target_id.replace("_", " ").capitalize(),
            "description": "Serveur MCP connecté dynamiquement.",
            "status": "connecting",
            "endpoint": cmd_str,
            "tools_count": 0,
            "tools": [],
        }
        DEFAULT_MCP_SERVERS.append(srv)

    if target_id in _active_mcp_clients:
        _disconnect_single_server(target_id)

    cmd = _normalize_command(cmd_str)
    client = MCPClient(cmd, cwd=str(_ROOT))
    try:
        client.start()
    except Exception as exc:
        srv["status"] = "error"
        raise HTTPException(
            status_code=500,
            detail=f"Échec de connexion au serveur MCP via '{cmd_str}': {exc}",
        )

    try:
        tool_names = register_mcp_client(client)
    except Exception as exc:
        client.close()
        srv["status"] = "error"
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors de l'enregistrement des outils du serveur MCP: {exc}",
        )

    _active_mcp_clients[target_id] = client
    _active_mcp_tools[target_id] = tool_names
    srv["status"] = "connected"
    srv["tools_count"] = len(tool_names)
    srv["tools"] = tool_names

    return {
        "success": True,
        "server_id": target_id,
        "status": "connected",
        "tools_count": len(tool_names),
        "tools": tool_names,
        "server": srv,
    }


@router.post("/disconnect")
def disconnect_mcp_server(
    req: Optional[McpDisconnectRequest] = None,
    user=Depends(get_current_user),
):
    target_id = req.server_id if req else None
    if target_id:
        _disconnect_single_server(target_id)
        return {
            "success": True,
            "server_id": target_id,
            "status": "disconnected",
            "message": f"Serveur MCP '{target_id}' déconnecté.",
        }

    for s_id in list(_active_mcp_clients.keys()):
        _disconnect_single_server(s_id)

    return {
        "success": True,
        "message": "Tous les serveurs MCP ont été déconnectés.",
    }


@router.post("/disconnect/{server_id}")
def disconnect_mcp_server_by_id(server_id: str, user=Depends(get_current_user)):
    _disconnect_single_server(server_id)
    return {
        "success": True,
        "server_id": server_id,
        "status": "disconnected",
        "message": f"Serveur MCP '{server_id}' déconnecté.",
    }

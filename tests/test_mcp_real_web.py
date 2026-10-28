import json
from pathlib import Path
import sys

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_BACKEND_DIR = _ROOT / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import pytest
from fastapi import HTTPException

from backend.routes.mcp_routes import (
    DEFAULT_MCP_SERVERS,
    McpConnectRequest,
    McpDisconnectRequest,
    McpServerCreate,
    _active_mcp_clients,
    add_mcp_server,
    connect_mcp_server,
    delete_mcp_server,
    disconnect_mcp_server,
    get_mcp_servers,
    get_mcp_status,
)
from backend.tools_registry import (
    default_registry,
    get_ollama_tools,
    list_tools,
    run_tool,
)


@pytest.fixture
def fake_user():
    return {"id": 1, "username": "admin_strategist"}


def test_mcp_real_connection_and_registry_sync(fake_user):
    """Vérifie la connexion réelle au serveur MCP démo, la découverte des outils,
    leur enregistrement dans le registre par défaut backend, leur exécution
    et leur désenregistrement lors de la déconnexion."""
    # S'assurer que le registre est propre au départ
    if "calculate_grain_supply" in default_registry:
        default_registry.unregister_tools(["calculate_grain_supply", "get_historical_battle"])

    try:
        # 1. Connexion au serveur démo
        conn_res = connect_mcp_server(
            req=McpConnectRequest(server_id="demo_server"),
            user=fake_user,
        )
        assert conn_res["success"] is True
        assert conn_res["status"] == "connected"
        assert conn_res["tools_count"] == 2
        assert "calculate_grain_supply" in conn_res["tools"]
        assert "get_historical_battle" in conn_res["tools"]

        # 2. Vérification de la présence dans default_registry
        assert "calculate_grain_supply" in default_registry
        assert "get_historical_battle" in default_registry

        # 3. Vérification de l'exposition dans list_tools()
        tools = list_tools()
        tools_by_id = {t["id"]: t for t in tools}
        assert "calculate_grain_supply" in tools_by_id
        assert "get_historical_battle" in tools_by_id
        assert tools_by_id["calculate_grain_supply"]["visible"] is True
        assert tools_by_id["calculate_grain_supply"]["category"] == "Logistique MCP"

        # 4. Vérification de get_ollama_tools()
        ollama_tools = get_ollama_tools(["calculate_grain_supply"])
        ollama_func_names = [t["function"]["name"] for t in ollama_tools]
        assert "calculate_grain_supply" in ollama_func_names

        # 5. Exécution réelle de l'outil via run_tool (communication RPC stdio vers le sous-processus)
        output_str = run_tool(
            "calculate_grain_supply",
            {"kingdom": "Qin", "soldiers": 4000, "months": 2},
        )
        assert isinstance(output_str, str)
        parsed = json.loads(output_str)
        assert parsed["kingdom"] == "Qin"
        assert parsed["soldiers"] == 4000
        assert parsed["total_grain_tons"] == 360.0
        assert "Logistique validée" in parsed["status"]

        # 6. Vérification du statut via /api/mcp/status
        status_single = get_mcp_status(server_id="demo_server", user=fake_user)
        assert status_single["connected"] is True
        assert status_single["tools_count"] == 2

        status_global = get_mcp_status(server_id=None, user=fake_user)
        assert status_global["connected"] is True
        assert "demo_server" in status_global["connected_servers"]

    finally:
        # 7. Déconnexion propre
        disc_res = disconnect_mcp_server(
            req=McpDisconnectRequest(server_id="demo_server"),
            user=fake_user,
        )
        assert disc_res["success"] is True

        # 8. Vérification du désenregistrement
        assert "calculate_grain_supply" not in default_registry
        assert "get_historical_battle" not in default_registry
        post_tools = {t["id"]: t for t in list_tools()}
        assert "calculate_grain_supply" not in post_tools

        status_after = get_mcp_status(server_id="demo_server", user=fake_user)
        assert status_after["connected"] is False


def test_mcp_connect_with_custom_command(fake_user):
    """Vérifie la connexion dynamique à un serveur MCP via une commande spécifique."""
    cmd = f'"{sys.executable}" -m src.features.tools.mcp_server_demo'
    conn_res = connect_mcp_server(
        req=McpConnectRequest(server_id="custom_test_server", command=cmd),
        user=fake_user,
    )
    assert conn_res["success"] is True
    assert conn_res["server_id"] == "custom_test_server"
    assert "calculate_grain_supply" in default_registry

    # Nettoyage
    disconnect_mcp_server(req=McpDisconnectRequest(server_id="custom_test_server"), user=fake_user)
    delete_mcp_server("custom_test_server", user=fake_user)
    assert "calculate_grain_supply" not in default_registry


def test_mcp_connect_rejects_command_outside_allowlist(fake_user):
    """Un client ne peut pas faire exécuter une commande arbitraire au serveur."""
    for payload in (
        McpConnectRequest(server_id="invalid_srv", command="non_existent_mcp_bin_12345"),
        McpConnectRequest(server_id="demo_server", command="calc.exe"),
        McpConnectRequest(command="echo pwned"),
    ):
        with pytest.raises(HTTPException) as exc_info:
            connect_mcp_server(req=payload, user=fake_user)
        assert exc_info.value.status_code == 403
    assert not any(s["id"] == "invalid_srv" for s in DEFAULT_MCP_SERVERS)


def test_mcp_user_registered_server_cannot_run_its_own_endpoint(fake_user):
    """Enregistrer un serveur avec un endpoint arbitraire ne permet pas de l'exécuter."""
    add_mcp_server(McpServerCreate(name="Evil Server", endpoint="calc.exe"), user=fake_user)
    try:
        with pytest.raises(HTTPException) as exc_info:
            connect_mcp_server(req=McpConnectRequest(server_id="evil_server"), user=fake_user)
        assert exc_info.value.status_code == 403
    finally:
        delete_mcp_server("evil_server", user=fake_user)


def test_mcp_operator_can_extend_allowlist(fake_user, monkeypatch):
    """L'opérateur autorise une commande via SENSAI_MCP_ALLOWED_COMMANDS."""
    cmd = f'"{sys.executable}" -c "raise SystemExit(1)"'
    with pytest.raises(HTTPException) as exc_info:
        connect_mcp_server(req=McpConnectRequest(server_id="ops_srv", command=cmd), user=fake_user)
    assert exc_info.value.status_code == 403

    monkeypatch.setenv("SENSAI_MCP_ALLOWED_COMMANDS", cmd)
    with pytest.raises(HTTPException) as exc_info:
        connect_mcp_server(req=McpConnectRequest(server_id="ops_srv", command=cmd), user=fake_user)
    # Autorisée, donc réellement tentée : le processus quitte aussitôt, la connexion échoue (500)
    assert exc_info.value.status_code == 500
    delete_mcp_server("ops_srv", user=fake_user)


def test_mcp_status_pings_server_and_exposes_tool_schemas(fake_user):
    connect_mcp_server(req=McpConnectRequest(server_id="demo_server"), user=fake_user)
    try:
        servers = {s["id"]: s for s in get_mcp_servers(user=fake_user)["servers"]}
        demo = servers["demo_server"]
        assert demo["status"] == "connected"
        schemas = {t["name"]: t for t in demo["tool_schemas"]}
        assert set(schemas) == {"calculate_grain_supply", "get_historical_battle"}
        assert all(t["description"] and isinstance(t["parameters"], dict) for t in schemas.values())

        # Le sous-processus meurt : le ping le détecte et le serveur repasse en "disconnected"
        _active_mcp_clients["demo_server"]._process.kill()
        servers = {s["id"]: s for s in get_mcp_servers(user=fake_user)["servers"]}
        assert servers["demo_server"]["status"] == "disconnected"
        assert servers["demo_server"]["tool_schemas"] == []
        assert "calculate_grain_supply" not in default_registry
    finally:
        disconnect_mcp_server(req=McpDisconnectRequest(server_id="demo_server"), user=fake_user)


def test_mcp_connect_placeholder_endpoint_rejected(fake_user):
    """Vérifie que la tentative de connexion d'un endpoint placeholder renvoie une HTTPException 400."""
    with pytest.raises(HTTPException) as exc_info:
        connect_mcp_server(
            req=McpConnectRequest(server_id="shadcn"),
            user=fake_user,
        )
    assert exc_info.value.status_code == 400

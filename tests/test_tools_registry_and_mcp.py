import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from backend.tools_registry import (
    FORM_TOOL_NAME,
    INTERNAL_TOOLS,
    READ_ONLY_TOOLS,
    list_tools,
    selected_tool_names,
)
from backend.routes.mcp_routes import (
    DEFAULT_MCP_SERVERS,
    McpServerCreate,
    add_mcp_server,
    delete_mcp_server,
    get_mcp_servers,
)
import pytest
from fastapi import HTTPException


def test_list_tools_visibility():
    tools = list_tools()
    tools_by_id = {t["id"]: t for t in tools}

    assert "ask_user_form" in tools_by_id
    assert tools_by_id["ask_user_form"]["visible"] is False

    assert "web_search" in tools_by_id
    assert tools_by_id["web_search"]["visible"] is True

    assert "structured_output" in tools_by_id
    assert tools_by_id["structured_output"]["visible"] is True


def test_read_only_tools_are_active_by_default_and_hidden():
    tools_by_id = {t["id"]: t for t in list_tools()}
    selected = selected_tool_names([])
    for name in READ_ONLY_TOOLS:
        assert tools_by_id[name]["visible"] is False
        assert name in selected


def test_write_and_external_tools_stay_opt_in():
    selected = selected_tool_names([])
    for name in ("web_search", "write_manuscript_file", "update_kingdom_database", "generate_pdf_document"):
        assert name not in selected
    tools_by_id = {t["id"]: t for t in list_tools()}
    assert tools_by_id["write_manuscript_file"]["visible"] is True


def test_selected_tool_names_always_includes_internal_tools():
    # Empty selection should still have ask_user_form
    selected = selected_tool_names([])
    assert FORM_TOOL_NAME in selected

    # Selective tool selection should retain both chosen and internal tools
    selected = selected_tool_names(["web_search"])
    assert "web_search" in selected
    assert FORM_TOOL_NAME in selected


def test_mcp_routes_crud():
    fake_user = {"id": 1, "username": "testuser"}

    # List servers
    res = get_mcp_servers(user=fake_user)
    assert res["total"] >= 1
    assert "servers" in res

    # Add a server
    new_server_req = McpServerCreate(
        name="Test MCP Server",
        description="Serveur de test",
        endpoint="http://localhost:9999",
    )
    add_res = add_mcp_server(server=new_server_req, user=fake_user)
    assert add_res["success"] is True
    added_id = add_res["server"]["id"]

    # Delete the newly added server
    del_res = delete_mcp_server(server_id=added_id, user=fake_user)
    assert del_res["success"] is True

    # Deleting non-existent server raises 404
    with pytest.raises(HTTPException) as exc_info:
        delete_mcp_server(server_id="non_existent_server_xyz", user=fake_user)
    assert exc_info.value.status_code == 404

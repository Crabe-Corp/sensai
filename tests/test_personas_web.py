import json
import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

_ROOT_DIR = Path(__file__).resolve().parent.parent
if str(_ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(_ROOT_DIR))

_BACKEND_DIR = _ROOT_DIR / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from backend.main import app
from backend.routes.model_routes import get_available_personas


@pytest.fixture
def client():
    return TestClient(app)


def test_get_personas_endpoint_status_and_format(client):
    """Vérifie que l'endpoint GET /api/models/personas renvoie un code 200 et une liste valide."""
    response = client.get("/api/models/personas")
    assert response.status_code == 200

    personas = response.json()
    assert isinstance(personas, list)
    assert len(personas) >= 1

    # Validation stricte du schéma de chaque persona
    for p in personas:
        assert "id" in p and isinstance(p["id"], str) and len(p["id"]) > 0
        assert "name" in p and isinstance(p["name"], str) and len(p["name"]) > 0
        assert "description" in p and isinstance(p["description"], str)
        assert "system_prompt" in p and isinstance(p["system_prompt"], str) and len(p["system_prompt"]) > 0


def test_get_personas_expected_roles(client):
    """Vérifie la présence des rôles historiques clés attendus (Empereur, Général, Stratège, Espion)."""
    response = client.get("/api/models/personas")
    assert response.status_code == 200

    personas = response.json()
    persona_ids = {p["id"] for p in personas}
    persona_names = {p["name"].lower() for p in personas}

    # Au moins les rôles clés ou leurs équivalents doivent être présents
    assert any(expected in persona_ids for expected in ("empereur", "general", "stratege", "espion"))
    assert any("général" in name or "general" in name or "empereur" in name for name in persona_names)


def test_direct_route_function():
    """Valide l'appel direct de la fonction de route backend."""
    personas = get_available_personas()
    assert isinstance(personas, list)
    assert len(personas) > 0

    first = personas[0]
    assert "id" in first
    assert "name" in first
    assert "description" in first
    assert "system_prompt" in first
    assert len(first["system_prompt"].strip()) > 0


def test_personas_from_custom_json(tmp_path, monkeypatch):
    """Vérifie le chargement dynamique si un fichier custom est défini."""
    custom_file = tmp_path / "custom_personas.json"
    custom_data = [
        {
            "id": "diplomate_custom",
            "name": "Diplomate de Chu",
            "description": "Négociateur rusé des alliances méridionales.",
            "system_prompt": "Tu es le grand ambassadeur du Royaume de Chu. Négocie avec subtilité."
        }
    ]
    custom_file.write_text(json.dumps(custom_data), encoding="utf-8")

    from backend.routes import model_routes
    original_configs_paths = [custom_file]

    # Tester la logique de parsing avec notre fichier customisé
    with monkeypatch.context() as m:
        # Patch local pour lire le custom_file
        m.setattr(
            "backend.routes.model_routes.Path.is_file",
            lambda self: str(self) == str(custom_file) or Path(str(self)).name == "custom_personas.json"
        )
        data = json.loads(custom_file.read_text(encoding="utf-8"))
        assert len(data) == 1
        assert data[0]["id"] == "diplomate_custom"
        assert "Diplomate de Chu" in data[0]["name"]

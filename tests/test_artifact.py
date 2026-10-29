import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.features.memory.artifact_manager import ArtifactDocument, ArtifactManager
from src.features.tools import artifact_tool
from src.features.tools.artifact_tool import (
    ARTIFACT_SYSTEM_INSTRUCTION,
    get_active_artifact,
    reset_active_artifact,
    set_active_artifact,
    update_artifact,
)
from src.features.tools.executor import ToolExecutor
from src.features.tools.registry import ToolRegistry, extract_tool_schema
from src.interfaces.cli.main import run_session
from src.core.ollama_client import ChatMessage


@pytest.fixture(autouse=True)
def clean_artifact_state():
    reset_active_artifact()
    yield
    reset_active_artifact()


def test_artifact_document_incremental_modifications():
    doc = ArtifactDocument(title="Chronique des Royaumes")

    # 1. Création initiale d'une section
    doc.set_section("Contexte", "Période des Royaumes Combattants.")
    assert "Contexte" in doc.sections
    assert doc.sections["Contexte"] == "Période des Royaumes Combattants."

    # 2. Ajout d'une seconde section sans impacter la première
    doc.set_section("Royaume Qin", "Royaume situé à l'ouest.")
    assert len(doc.sections) == 2
    assert doc.sections["Contexte"] == "Période des Royaumes Combattants."
    assert doc.sections["Royaume Qin"] == "Royaume situé à l'ouest."

    # 3. Concaténation (append) sur la seconde section
    doc.append_to_section("Royaume Qin", "- Armée puissante réorganisée par Shang Yang.")
    assert "Shang Yang" in doc.sections["Royaume Qin"]
    assert doc.sections["Contexte"] == "Période des Royaumes Combattants."

    # 4. Remplacement ciblé de la première section
    doc.set_section("Contexte", "Ère d'unification progressive menée par Ying Zheng.")
    assert doc.sections["Contexte"] == "Ère d'unification progressive menée par Ying Zheng."
    assert "Shang Yang" in doc.sections["Royaume Qin"]

    # 5. Suppression de section
    deleted = doc.delete_section("Contexte")
    assert deleted is True
    assert "Contexte" not in doc.sections
    assert "Royaume Qin" in doc.sections

    # 6. Suppression d'une section inexistante
    assert doc.delete_section("Section Inexistante") is False


def test_artifact_document_markdown_rendering():
    doc = ArtifactDocument(title="Grandes Réformes de Qin")
    doc.set_section("Légisme", "Application stricte des lois par Shang Yang.")
    doc.set_section("Économie", "Développement de l'agriculture et poids unifiés.")

    md = doc.render_markdown()
    assert md.startswith("# Grandes Réformes de Qin")
    assert "## Légisme\nApplication stricte des lois par Shang Yang." in md
    assert "## Économie\nDéveloppement de l'agriculture et poids unifiés." in md


def test_artifact_document_markdown_and_json_roundtrip(tmp_path: Path):
    doc = ArtifactDocument(
        title="Chronique de Changping",
        metadata={"bataille": "Changping", "annee": "-260"},
    )
    doc.set_section("Commandants", "Bai Qi (Qin) contre Zhao Kuo (Zhao).")
    doc.set_section("Issue", "Victoire décisive de l'armée de Qin.")

    # Roundtrip Markdown
    md_file = tmp_path / "chronique.md"
    doc.save(md_file)
    assert md_file.is_file()

    loaded_md = ArtifactDocument.load(md_file)
    assert loaded_md.title == "Chronique de Changping"
    assert loaded_md.sections["Commandants"] == "Bai Qi (Qin) contre Zhao Kuo (Zhao)."
    assert loaded_md.sections["Issue"] == "Victoire décisive de l'armée de Qin."

    # Roundtrip JSON
    json_file = tmp_path / "chronique.json"
    doc.save(json_file)
    assert json_file.is_file()

    loaded_json = ArtifactDocument.load(json_file)
    assert loaded_json.title == doc.title
    assert loaded_json.sections == doc.sections
    assert loaded_json.metadata["bataille"] == "Changping"


def test_artifact_manager_lifecycle(tmp_path: Path):
    manager = ArtifactManager(storage_dir=tmp_path)
    session_id = "test-session-123"

    doc = manager.get_or_create_artifact(session_id, title="Livrable Test")
    assert doc.title == "Livrable Test"
    assert doc.metadata["session_id"] == session_id

    doc.set_section("Factions", "Qin, Zhao, Chu, Yan, Han, Wei, Qi")
    manager.save_artifact(session_id, doc)

    loaded = manager.load_artifact(session_id)
    assert loaded.sections["Factions"] == "Qin, Zhao, Chu, Yan, Han, Wei, Qi"

    # Réinitialisation
    reset_doc = manager.reset_artifact(session_id, title="Livrable Vierge")
    assert len(reset_doc.sections) == 0
    assert reset_doc.title == "Livrable Vierge"

    loaded_after_reset = manager.load_artifact(session_id)
    assert len(loaded_after_reset.sections) == 0


def test_tool_schema_extraction_for_update_artifact():
    schema = extract_tool_schema(update_artifact)
    assert schema["name"] == "update_artifact"
    props = schema["parameters"]["properties"]

    assert "action" in props
    assert props["action"]["type"] == "string"
    assert set(props["action"]["enum"]) == {"update", "append", "delete"}

    assert "section" in props
    assert "content" in props
    assert "action" in schema["parameters"]["required"]
    assert "section" in schema["parameters"]["required"]
    assert "content" not in schema["parameters"]["required"]


def test_update_artifact_tool_execution_via_registry(tmp_path: Path):
    manager = ArtifactManager(storage_dir=tmp_path)
    session_id = "sess-tool-test"
    doc = manager.get_or_create_artifact(session_id, title="Document Actif")
    set_active_artifact(doc, session_id=session_id, manager=manager)

    local_registry = ToolRegistry()
    local_registry.register(update_artifact)
    executor = ToolExecutor(registry=local_registry)

    # 1. Action update
    res1 = executor.execute(
        "update_artifact",
        {"action": "update", "section": "Capitale", "content": "Xianyang"},
    )
    assert res1.success is True
    assert "mise à jour" in str(res1.result)
    assert doc.sections["Capitale"] == "Xianyang"

    # 2. Action append
    res2 = executor.execute(
        "update_artifact",
        {"action": "append", "section": "Capitale", "content": "- Traversée par la rivière Wei"},
    )
    assert res2.success is True
    assert "ajouté" in str(res2.result)
    assert "Xianyang" in doc.sections["Capitale"]
    assert "Wei" in doc.sections["Capitale"]

    # 3. Action delete
    res3 = executor.execute(
        "update_artifact",
        {"action": "delete", "section": "Capitale"},
    )
    assert res3.success is True
    assert "supprimée" in str(res3.result)
    assert "Capitale" not in doc.sections

    # 4. Action invalide
    res4 = executor.execute(
        "update_artifact",
        {"action": "invalid_action", "section": "Test"},
    )
    assert "inconnue" in str(res4.result)


def test_cli_artifact_interactive_commands(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    manager = ArtifactManager(storage_dir=tmp_path / "artifacts")
    session_id = "sess-cli-test"
    doc = manager.get_or_create_artifact(session_id, title="Fiche du Royaume de Qin")
    doc.set_section("Souverain", "Ying Zheng")
    manager.save_artifact(session_id, doc)
    set_active_artifact(doc, session_id=session_id, manager=manager)

    # Simulation de commandes CLI via run_session
    mock_client = MagicMock()
    mock_session_mgr = MagicMock()
    mock_session = MagicMock()
    mock_session.metadata.session_id = session_id
    mock_session.metadata.model = "qwen2.5:3b"
    mock_session.messages = []
    mock_session_mgr.load_session.return_value = mock_session
    mock_session_mgr.create_session.return_value = mock_session

    export_file = tmp_path / "export_livrable.md"

    user_inputs = [
        "/artifact",
        f"/artifact save {export_file}",
        "/artifact reset",
        "/artifact",
        "/exit",
    ]

    with patch("builtins.input", side_effect=user_inputs):
        run_session(
            client=mock_client,
            model="qwen2.5:3b",
            host="http://localhost:11434",
            tools=True,
            session_id=session_id,
            session_manager=mock_session_mgr,
            artifact_manager=manager,
        )

    captured = capsys.readouterr().out
    assert "ARTIFACT — Fiche du Royaume de Qin" in captured
    assert "Ying Zheng" in captured
    assert "exported successfully" in captured
    assert export_file.is_file()
    assert "Ying Zheng" in export_file.read_text(encoding="utf-8")
    assert "Artifact reset" in captured
    assert "Empty artifact for now" in captured

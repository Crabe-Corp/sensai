import json
from pathlib import Path
import pytest

from src.core.ollama_client import ChatMessage
from src.features.prompt.persona_manager import Persona, PersonaManager
from src.features.prompt.prompt_versioning import PromptVersioningEngine
from src.interfaces.cli.commands.commands import Commands


@pytest.fixture
def persona_env(tmp_path: Path):
    personas_dir = tmp_path / "personnalites"
    storage_dir = tmp_path / "storage" / "prompt_versions"
    versioning = PromptVersioningEngine(storage_dir=storage_dir, personas_dir=personas_dir)
    manager = PersonaManager(personas_dir=personas_dir, versioning_engine=versioning)
    return manager, versioning, personas_dir, storage_dir


def test_default_no_personas_registered_or_active(persona_env):
    manager, versioning, personas_dir, storage_dir = persona_env
    # Par défaut, aucune persona n'est enregistrée
    assert manager.list_personas() == []
    assert list(personas_dir.glob("*")) == []

    cmd = Commands(persona_manager=manager, versioning_engine=versioning)
    # Par défaut, aucune persona n'est active
    assert cmd.current_persona is None


def test_ensure_default_personas_explicit_call(persona_env):
    manager, versioning, personas_dir, _ = persona_env
    assert manager.list_personas() == []

    # Appel explicite pour générer les templates d'exemple
    manager.ensure_default_personas()
    personas = manager.list_personas()
    assert "scribe_qin" in personas
    assert "erudit_zhao" in personas
    assert "general_bai_qi" in personas

    p = manager.load_persona("scribe_qin")
    assert p.name == "Scribe de Qin"
    assert "Li Si" in p.system_prompt
    assert p.active_version >= 1


def test_load_markdown_persona_with_frontmatter(persona_env):
    manager, _, personas_dir, _ = persona_env
    custom_md = personas_dir / "strategiste_wei.md"
    custom_md.write_text(
        """---
name: Stratège de Wei
role: Conseiller militaire en chef
tone: Rusé, calculateur et froid
description: Vétéran des campagnes de Wei expert en fortifications.
scope: Stratégie défensive et sièges.
---
Tu es un stratège de Wei. Tu évalues minutieusement la topographie et les réserves ennemies.""",
        encoding="utf-8",
    )

    persona = manager.load_persona("strategiste_wei")
    assert persona.name == "Stratège de Wei"
    assert persona.role == "Conseiller militaire en chef"
    assert persona.tone == "Rusé, calculateur et froid"
    assert "Tu es un stratège de Wei" in persona.system_prompt


def test_load_plain_markdown_and_txt_persona(persona_env):
    manager, _, personas_dir, _ = persona_env
    plain_txt = personas_dir / "mohist_guard.txt"
    plain_txt.write_text(
        "Tu es un artisan mohiste dédié à la défense absolue des cités assiégées.",
        encoding="utf-8",
    )

    persona = manager.load_persona("mohist_guard.txt")
    assert persona.name == "mohist_guard"
    assert "artisan mohiste" in persona.system_prompt


def test_load_json_persona(persona_env):
    manager, _, personas_dir, _ = persona_env
    json_path = personas_dir / "espion_yan.json"
    data = {
        "name": "Espion de Yan",
        "role": "Agent de renseignement clandestin",
        "tone": "Chuchoté, cryptique et prudent",
        "description": "Infiltré dans les garnisons adverses.",
        "system_prompt": "Tu es un espion de Yan. Tu ne révèles que des indices partiels.",
    }
    json_path.write_text(json.dumps(data), encoding="utf-8")

    persona = manager.load_persona("espion_yan")
    assert persona.name == "Espion de Yan"
    assert persona.tone == "Chuchoté, cryptique et prudent"
    assert "espion de Yan" in persona.system_prompt


def test_dynamic_discovery_new_file_without_restart(persona_env):
    manager, _, personas_dir, _ = persona_env
    assert len(manager.list_personas()) == 0

    # Ajout d'un nouveau fichier après initialisation du manager
    new_persona_file = personas_dir / "archer_chu.md"
    new_persona_file.write_text(
        "# Guerrier de Chu\nTu es un noble archer des forêts du sud de Chu.",
        encoding="utf-8",
    )

    updated_personas = manager.list_personas()
    assert len(updated_personas) == 1
    assert "archer_chu" in updated_personas

    loaded = manager.load_persona("archer_chu")
    assert loaded.name == "archer_chu"


def test_load_persona_not_found_raises(persona_env):
    manager, _, _, _ = persona_env
    with pytest.raises(FileNotFoundError) as exc_info:
        manager.load_persona("seigneur_fantome")
    assert "seigneur_fantome" in str(exc_info.value)


def test_switch_persona_mid_session_preserves_history(persona_env):
    manager, versioning, _, _ = persona_env
    manager.ensure_default_personas()

    history = [
        ChatMessage(role="system", content="Prompt initial par défaut"),
        ChatMessage(role="user", content="Quelle est la capitale de Qin ?"),
        ChatMessage(role="assistant", content="La capitale de Qin est Xianyang."),
        ChatMessage(role="user", content="Quelles sont ses défenses ?"),
        ChatMessage(role="assistant", content="Elle est protégée par les cols de Hangu."),
    ]

    cmd = Commands(
        history=history,
        persona_manager=manager,
        versioning_engine=versioning,
    )

    # Bascule dynamique à chaud vers scribe_qin
    cmd.execute_command("/persona", "/persona scribe_qin")

    # L'historique complet doit être conservé
    assert len(cmd.history) == 5
    assert cmd.history[1].content == "Quelle est la capitale de Qin ?"
    assert cmd.history[2].content == "La capitale de Qin est Xianyang."
    assert cmd.history[3].content == "Quelles sont ses défenses ?"
    assert cmd.history[4].content == "Elle est protégée par les cols de Hangu."

    # Le prompt système initial doit avoir été remplacé par celui de la persona
    assert cmd.history[0].role == "system"
    assert "Li Si" in cmd.history[0].content
    assert cmd.current_persona is not None
    assert cmd.current_persona.name == "Scribe de Qin"

    # Seconde bascule dynamique vers erudit_zhao
    cmd.execute_command("/persona", "/persona erudit_zhao")
    assert len(cmd.history) == 5
    assert "Handan" in cmd.history[0].content
    assert cmd.current_persona.name == "Érudit de Zhao"


def test_cli_persona_interactive_commands(persona_env, capsys):
    manager, versioning, _, _ = persona_env
    cmd = Commands(
        history=[],
        persona_manager=manager,
        versioning_engine=versioning,
    )

    # 1. /persona list quand aucune persona n'est enregistrée
    cmd.execute_command("/persona", "/persona list")
    out = capsys.readouterr().out
    assert "Aucune persona disponible" in out
    assert "Aucune persona active" in out

    # 2. Génération explicite des personas exemples via /persona defaults
    cmd.execute_command("/persona", "/persona defaults")
    out = capsys.readouterr().out
    assert "Personas d'exemple générées" in out
    assert "scribe_qin" in out

    # 3. /persona <nom>
    cmd.execute_command("/persona", "/persona general_bai_qi")
    out = capsys.readouterr().out
    assert "Persona 'Général Bai Qi' activée" in out
    assert cmd.current_persona.name == "Général Bai Qi"

    # 4. /persona inexistant
    cmd.execute_command("/persona", "/persona inconnue")
    out = capsys.readouterr().out
    assert "[Erreur Persona]" in out


def test_clear_screen_preserves_active_persona(persona_env):
    manager, versioning, _, _ = persona_env
    manager.ensure_default_personas()

    history = [
        ChatMessage(role="system", content="Init"),
        ChatMessage(role="user", content="Bonjour"),
    ]
    cmd = Commands(
        history=history,
        persona_manager=manager,
        versioning_engine=versioning,
    )
    cmd.execute_command("/persona", "/persona scribe_qin")
    cmd.history.append(ChatMessage(role="user", content="Nouvelle question"))
    assert len(cmd.history) == 3

    cmd.execute_command("/clear")
    # Après /clear, l'historique de dialogue est vidé mais le prompt de la persona active est réinjecté
    assert len(cmd.history) == 1
    assert cmd.history[0].role == "system"
    assert "Li Si" in cmd.history[0].content

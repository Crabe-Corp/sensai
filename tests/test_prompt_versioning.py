from pathlib import Path
import pytest

from src.features.prompt.persona_manager import PersonaManager
from src.features.prompt.prompt_versioning import (
    PromptVersion,
    PromptVersioningEngine,
)
from src.interfaces.cli.commands.commands import Commands


@pytest.fixture
def version_env(tmp_path: Path):
    personas_dir = tmp_path / "personnalites"
    personas_dir.mkdir(parents=True, exist_ok=True)
    storage_dir = tmp_path / "storage" / "prompt_versions"
    engine = PromptVersioningEngine(storage_dir=storage_dir, personas_dir=personas_dir)
    return engine, personas_dir, storage_dir


def test_save_version_initial_v1(version_env):
    engine, personas_dir, storage_dir = version_env
    v1 = engine.save_version("scribe_qin", "Contenu version 1", author="admin", message="Initial")
    assert v1.version == 1
    assert v1.persona_name == "scribe_qin"
    assert v1.content == "Contenu version 1"
    assert v1.author == "admin"
    assert len(v1.content_hash) == 64
    assert v1.timestamp

    # Vérification fichier sur disque
    v1_file = storage_dir / "scribe_qin" / "v1.json"
    assert v1_file.is_file()


def test_save_version_increments_on_change(version_env):
    engine, _, storage_dir = version_env
    v1 = engine.save_version("scribe_qin", "Contenu A")
    v2 = engine.save_version("scribe_qin", "Contenu B", author="user_mod")
    v3 = engine.save_version("scribe_qin", "Contenu C")

    assert v1.version == 1
    assert v2.version == 2
    assert v3.version == 3
    assert v2.author == "user_mod"
    assert (storage_dir / "scribe_qin" / "v2.json").is_file()
    assert (storage_dir / "scribe_qin" / "v3.json").is_file()


def test_save_version_idempotent_when_content_identical(version_env):
    engine, _, storage_dir = version_env
    v1 = engine.save_version("erudit_zhao", "Philosophie confucéenne")
    # Tentative d'enregistrement du même contenu
    v1_repeat = engine.save_version("erudit_zhao", "Philosophie confucéenne")

    assert v1.version == v1_repeat.version
    assert v1.content_hash == v1_repeat.content_hash
    # Aucun fichier v2.json ne doit exister
    assert not (storage_dir / "erudit_zhao" / "v2.json").exists()


def test_get_history_ordering(version_env):
    engine, _, _ = version_env
    engine.save_version("general_bai", "Rapport 1")
    engine.save_version("general_bai", "Rapport 2")
    engine.save_version("general_bai", "Rapport 3")

    history = engine.get_history("general_bai")
    assert len(history) == 3
    assert [v.version for v in history] == [1, 2, 3]


def test_get_version_lookup(version_env):
    engine, _, _ = version_env
    engine.save_version("test_p", "Texte 1")
    engine.save_version("test_p", "Texte 2")

    v1_int = engine.get_version("test_p", 1)
    assert v1_int.content == "Texte 1"

    v2_str = engine.get_version("test_p", "v2")
    assert v2_str.content == "Texte 2"

    with pytest.raises(ValueError) as exc:
        engine.get_version("test_p", 99)
    assert "v99" in str(exc.value)


def test_get_diff_unified(version_env):
    engine, _, _ = version_env
    content_v1 = "Ligne 1\nLigne 2\nLigne 3\n"
    content_v2 = "Ligne 1\nLigne 2 modifiée\nLigne 3\nLigne 4\n"

    engine.save_version("diff_target", content_v1)
    engine.save_version("diff_target", content_v2)

    diff = engine.get_diff("diff_target", 1, 2)
    assert "--- diff_target (v1)" in diff
    assert "+++ diff_target (v2)" in diff
    assert "-Ligne 2" in diff
    assert "+Ligne 2 modifiée" in diff
    assert "+Ligne 4" in diff


def test_get_diff_no_changes(version_env):
    engine, _, _ = version_env
    engine.save_version("same_target", "Contenu statique\n")
    diff = engine.get_diff("same_target", 1, 1)
    assert diff == ""


def test_rollback_restores_active_file(version_env):
    engine, personas_dir, _ = version_env
    active_file = personas_dir / "monarque_han.md"
    active_file.write_text("Prompt initial Han", encoding="utf-8")

    # v1
    engine.save_version("monarque_han", "Prompt initial Han")
    # v2 modif
    active_file.write_text("Prompt modifié Han", encoding="utf-8")
    engine.save_version("monarque_han", "Prompt modifié Han")
    # v3 modif
    active_file.write_text("Prompt erroné Han", encoding="utf-8")
    engine.save_version("monarque_han", "Prompt erroné Han")

    # Rollback vers v1
    restored = engine.rollback("monarque_han", 1)
    assert restored == "Prompt initial Han"
    assert active_file.read_text(encoding="utf-8") == "Prompt initial Han"

    # Vérification que le rollback a créé une révision journalisée v4
    history = engine.get_history("monarque_han")
    assert len(history) == 4
    assert history[-1].version == 4
    assert history[-1].content == "Prompt initial Han"
    assert "Rollback" in history[-1].message


def test_cli_prompt_interactive_commands(tmp_path: Path, capsys):
    personas_dir = tmp_path / "personnalites"
    personas_dir.mkdir(parents=True, exist_ok=True)
    storage_dir = tmp_path / "storage" / "prompt_versions"
    engine = PromptVersioningEngine(storage_dir=storage_dir, personas_dir=personas_dir)
    manager = PersonaManager(personas_dir=personas_dir, versioning_engine=engine)

    # Initialisation de deux versions pour test_persona
    target_file = personas_dir / "test_persona.md"
    target_file.write_text("Prompt v1", encoding="utf-8")
    engine.save_version("test_persona", "Prompt v1", message="v1 init")

    target_file.write_text("Prompt v2 amélioré", encoding="utf-8")
    engine.save_version("test_persona", "Prompt v2 amélioré", message="v2 edit")

    cmd = Commands(
        persona_manager=manager,
        versioning_engine=engine,
    )

    # 1. /prompt sans argument
    cmd.execute_command("/prompt", "/prompt")
    out = capsys.readouterr().out
    assert "Usage de la commande /prompt" in out

    # 2. /prompt versions test_persona
    cmd.execute_command("/prompt", "/prompt versions test_persona")
    out = capsys.readouterr().out
    assert "Historique des versions pour 'test_persona'" in out
    assert "v1" in out
    assert "v2" in out

    # 3. /prompt diff test_persona 1 2
    cmd.execute_command("/prompt", "/prompt diff test_persona 1 2")
    out = capsys.readouterr().out
    assert "Diff test_persona : v1 -> v2" in out
    assert "-Prompt v1" in out
    assert "+Prompt v2 amélioré" in out

    # 4. /prompt rollback test_persona 1
    cmd.execute_command("/prompt", "/prompt rollback test_persona 1")
    out = capsys.readouterr().out
    assert "Persona 'test_persona' restaurée à la version 1 avec succès" in out
    assert target_file.read_text(encoding="utf-8") == "Prompt v1"

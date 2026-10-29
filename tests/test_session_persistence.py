import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.core.ollama_client import ChatMessage
from src.features.memory.profile_manager import ProfileManager, UserProfile
from src.features.memory.session_manager import (
    ChatSession,
    SessionManager,
    SessionMetadata,
)
from src.interfaces.cli.main import parse_arguments, run_session


@pytest.fixture(autouse=True)
def disable_remote_backend_for_unit_tests(monkeypatch):
    monkeypatch.setenv("SENSAI_BACKEND_URL", "")


class TestUserProfile:
    def test_default_profile_attributes(self):
        profile = UserProfile()
        assert profile.username == "default"
        assert profile.tone == "ancient scribe"
        assert profile.conciseness == "balanced"
        assert profile.language == "english"
        assert "Qin" in profile.custom_instructions
        assert profile.facts == []

    def test_format_system_prompt_structure(self):
        profile = UserProfile(
            username="historien_qin",
            tone="académique et solennel",
            conciseness="très détaillé",
            language="français",
            custom_instructions="Se concentrer sur les réformes de Shang Yang.",
            facts=["Expertise dynastie Qin", "Intérêt pour l'armée en terre cuite"],
        )
        prompt = profile.format_system_prompt()
        assert "[User Profile : historien_qin]" in prompt
        assert "académique et solennel" in prompt
        assert "très détaillé" in prompt
        assert "Se concentrer sur les réformes de Shang Yang." in prompt
        assert "Expertise dynastie Qin" in prompt
        assert "Intérêt pour l'armée en terre cuite" in prompt


class TestProfileManager:
    def test_get_or_create_default_profile(self, tmp_path: Path):
        pm = ProfileManager(storage_dir=tmp_path)
        profile = pm.get_or_create_profile("default")
        assert profile.username == "default"
        assert (tmp_path / "default.json").is_file()

        # Rechargement ultérieur
        loaded = pm.load_profile("default")
        assert loaded.username == "default"
        assert loaded.tone == profile.tone

    def test_save_and_load_custom_profile(self, tmp_path: Path):
        pm = ProfileManager(storage_dir=tmp_path)
        custom = UserProfile(
            username="general_meng",
            tone="stratège martial",
            facts=["Commandant du front Nord"],
        )
        saved_path = pm.save_profile(custom)
        assert saved_path.is_file()

        reloaded = pm.load_profile("general_meng")
        assert reloaded.username == "general_meng"
        assert reloaded.tone == "stratège martial"
        assert reloaded.facts == ["Commandant du front Nord"]

    def test_load_non_existent_profile_raises(self, tmp_path: Path):
        pm = ProfileManager(storage_dir=tmp_path)
        with pytest.raises(FileNotFoundError):
            pm.load_profile("inconnu")

    def test_list_and_delete_profiles(self, tmp_path: Path):
        pm = ProfileManager(storage_dir=tmp_path)
        pm.get_or_create_profile("user_a")
        pm.get_or_create_profile("user_b")

        profiles = pm.list_profiles()
        assert "user_a" in profiles
        assert "user_b" in profiles

        assert pm.delete_profile("user_a") is True
        assert pm.delete_profile("user_a") is False
        assert "user_a" not in pm.list_profiles()


class TestSessionManager:
    def test_create_session_with_profile_injection(self, tmp_path: Path):
        sm = SessionManager(storage_dir=tmp_path)
        profile = UserProfile(username="stratege", tone="concis et pragmatique")
        session = sm.create_session(profile=profile, model="qwen2.5:1.5b", title="Campagne Wei")

        assert session.metadata.session_id
        assert session.metadata.title == "Campagne Wei"
        assert session.metadata.username == "stratege"
        assert len(session.messages) == 1
        assert session.messages[0].role == "system"
        assert "concis et pragmatique" in session.messages[0].content
        assert (tmp_path / f"{session.metadata.session_id}.json").is_file()

    def test_create_session_without_profile(self, tmp_path: Path):
        sm = SessionManager(storage_dir=tmp_path)
        session = sm.create_session(profile=None, model="mistral")

        assert len(session.messages) == 0
        assert session.metadata.username is None
        assert session.metadata.model == "mistral"

    def test_messages_serialization_all_roles_and_tool_calls(self, tmp_path: Path):
        sm = SessionManager(storage_dir=tmp_path)
        session = sm.create_session(profile=None, model="llama3", title="Simulation Bataille")

        messages = [
            ChatMessage(role="system", content="Consignes globales."),
            ChatMessage(role="user", content="Calcule le blé nécessaire pour 10 000 soldats."),
            ChatMessage(
                role="assistant",
                content="",
                tool_calls=[
                    {
                        "id": "call_123",
                        "type": "function",
                        "function": {
                            "name": "calculate_grain_supply",
                            "arguments": '{"troops": 10000, "days": 30}',
                        },
                    }
                ],
            ),
            ChatMessage(role="tool", content="3000 sacs de grain requis."),
            ChatMessage(role="assistant", content="Il vous faut 3 000 sacs de grain pour 30 jours."),
        ]

        for msg in messages:
            session.add_message(msg)

        sm.save_session(session)

        # Rechargement et vérification stricte
        reloaded = sm.load_session(session.metadata.session_id)
        assert len(reloaded.messages) == 5
        assert [m.role for m in reloaded.messages] == ["system", "user", "assistant", "tool", "assistant"]
        assert reloaded.messages[2].tool_calls == messages[2].tool_calls
        assert reloaded.messages[3].content == "3000 sacs de grain requis."
        assert reloaded.messages[4].content == "Il vous faut 3 000 sacs de grain pour 30 jours."

    def test_atomic_file_write(self, tmp_path: Path):
        sm = SessionManager(storage_dir=tmp_path)
        session = sm.create_session(profile=None, model="qwen2.5:1.5b")
        file_path = tmp_path / f"{session.metadata.session_id}.json"

        # Le fichier existe et est un JSON valide
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["metadata"]["session_id"] == session.metadata.session_id

        # Modification et resauvegarde
        session.add_message(ChatMessage(role="user", content="Nouveau message"))
        sm.save_session(session)

        with open(file_path, "r", encoding="utf-8") as f:
            updated_data = json.load(f)
        assert len(updated_data["messages"]) == 1

    def test_list_sessions_order_by_updated_at(self, tmp_path: Path):
        sm = SessionManager(storage_dir=tmp_path)
        s1 = sm.create_session(profile=None, model="model1", title="Session Ancienne")
        s2 = sm.create_session(profile=None, model="model2", title="Session Récente")

        s1.metadata.updated_at = "2026-01-01T10:00:00Z"
        s2.metadata.updated_at = "2026-01-02T10:00:00Z"
        sm.save_session(s1)
        sm.save_session(s2)

        sessions = sm.list_sessions()
        assert len(sessions) == 2
        assert sessions[0].session_id == s2.metadata.session_id
        assert sessions[1].session_id == s1.metadata.session_id

    def test_delete_and_rename_session(self, tmp_path: Path):
        sm = SessionManager(storage_dir=tmp_path)
        session = sm.create_session(profile=None, model="qwen2.5:1.5b", title="Titre Initial")
        sid = session.metadata.session_id

        renamed = sm.rename_session(sid, "Nouveau Titre")
        assert renamed.metadata.title == "Nouveau Titre"

        assert sm.delete_session(sid) is True
        assert sm.delete_session(sid) is False
        with pytest.raises(FileNotFoundError):
            sm.load_session(sid)


class TestCliIntegrationPersistence:
    def test_parse_arguments_session_and_profile(self):
        args = parse_arguments(["--session", "sess-1234", "--profile", "scribe"])
        assert args.session == "sess-1234"
        assert args.profile == "scribe"

    def test_run_session_auto_saves_messages(self, tmp_path: Path):
        profile_dir = tmp_path / "profiles"
        session_dir = tmp_path / "sessions"
        pm = ProfileManager(storage_dir=profile_dir)
        sm = SessionManager(storage_dir=session_dir)

        mock_client = MagicMock()
        mock_client.chat_stream.return_value = iter(["Victoire", " décisive !"])

        with patch("builtins.input", side_effect=["Qui a gagné ?", "/exit"]):
            run_session(
                client=mock_client,
                model="qwen2.5:1.5b",
                host="http://localhost:11434",
                profile_name="testeur",
                session_manager=sm,
                profile_manager=pm,
            )

        saved_sessions = sm.list_sessions()
        assert len(saved_sessions) == 1
        active_sess = sm.load_session(saved_sessions[0].session_id)

        # Message système du profil + Message utilisateur + Réponse assistant
        assert len(active_sess.messages) == 3
        assert active_sess.messages[0].role == "system"
        assert active_sess.messages[1].role == "user"
        assert active_sess.messages[1].content == "Qui a gagné ?"
        assert active_sess.messages[2].role == "assistant"
        assert active_sess.messages[2].content == "Victoire décisive !"

    def test_cli_session_commands_list_new_load_delete(self, tmp_path: Path, capsys):
        sm = SessionManager(storage_dir=tmp_path / "sessions")
        pm = ProfileManager(storage_dir=tmp_path / "profiles")
        mock_client = MagicMock()

        sess1 = sm.create_session(profile=None, model="qwen2.5:1.5b", title="Ancienne Guerre")
        sess1.add_message(ChatMessage(role="user", content="Souvenir de combat"))
        sess1.metadata.context_tokens = 150
        sess1.metadata.total_tokens = 150
        sm.save_session(sess1)

        inputs = [
            "/session list",
            "/session new Campagne_Nord",
            f"/session load {sess1.metadata.session_id}",
            "/history",
            "/budget",
            "/session delete session_inconnue",
            "/exit",
        ]

        with patch("builtins.input", side_effect=inputs):
            run_session(
                client=mock_client,
                model="qwen2.5:1.5b",
                host="http://localhost:11434",
                session_manager=sm,
                profile_manager=pm,
            )

        captured = capsys.readouterr()
        assert "Ancienne Guerre" in captured.out
        assert "Campagne_Nord" in captured.out
        assert f"Session '{sess1.metadata.session_id}' loaded successfully" in captured.out
        assert "1 message(s) in memory" in captured.out
        assert "Token budget : 150" in captured.out

    def test_cli_profile_commands_show_and_load(self, tmp_path: Path, capsys):
        sm = SessionManager(storage_dir=tmp_path / "sessions")
        pm = ProfileManager(storage_dir=tmp_path / "profiles")
        mock_client = MagicMock()

        custom_prof = UserProfile(username="archonte", tone="aristocratique")
        pm.save_profile(custom_prof)

        inputs = [
            "/profile show",
            "/profile load archonte",
            "/profile show",
            "/profile list",
            "/exit",
        ]

        with patch("builtins.input", side_effect=inputs):
            run_session(
                client=mock_client,
                model="qwen2.5:1.5b",
                host="http://localhost:11434",
                profile_name="default",
                session_manager=sm,
                profile_manager=pm,
            )

        captured = capsys.readouterr()
        assert "[User Profile : default]" in captured.out
        assert "Profile 'archonte' loaded" in captured.out
        assert "[User Profile : archonte]" in captured.out
        assert "aristocratique" in captured.out
        assert "archonte" in captured.out


class TestWebCliInteroperability:
    def test_load_session_by_short_prefix(self, tmp_path: Path):
        sm = SessionManager(storage_dir=tmp_path)
        sess = sm.create_session(profile=None, model="qwen2.5:1.5b", title="Prefix Test")
        sess.add_message(ChatMessage(role="user", content="Bonjour depuis le web"))
        sm.save_session(sess)

        short_id = sess.metadata.session_id[:8]
        loaded = sm.load_session(short_id)
        assert loaded.metadata.session_id == sess.metadata.session_id
        assert len(loaded.messages) == 1
        assert loaded.messages[0].content == "Bonjour depuis le web"

    def test_load_session_from_mock_web_backend(self, tmp_path: Path):
        sm = SessionManager(storage_dir=tmp_path, backend_url="http://mock-backend")
        remote_data = {
            "metadata": {
                "session_id": "remote-uuid-1234-5678",
                "title": "Discussion Web",
                "created_at": "2026-10-13T12:00:00Z",
                "updated_at": "2026-10-13T12:05:00Z",
                "model": "qwen2.5:1.5b",
                "username": "web_user",
                "source": "web",
            },
            "messages": [
                {"role": "user", "content": "Question posée sur le web"},
                {"role": "assistant", "content": "Réponse fournie sur le web"},
            ],
        }

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = remote_data

        with patch("httpx.Client.get", return_value=mock_resp):
            loaded = sm.load_session("remote-uuid-1234-5678")

        assert loaded.metadata.session_id == "remote-uuid-1234-5678"
        assert loaded.metadata.title == "Discussion Web"
        assert loaded.metadata.source == "web"
        assert len(loaded.messages) == 2
        assert (tmp_path / "remote-uuid-1234-5678.json").is_file()

    def test_list_sessions_merges_web_remote(self, tmp_path: Path):
        sm = SessionManager(storage_dir=tmp_path, backend_url="http://mock-backend")
        local_sess = sm.create_session(profile=None, model="qwen2.5:1.5b", title="Session Locale")

        remote_list_data = [
            {
                "session_id": "remote-conv-9999",
                "title": "Session Web Distante",
                "created_at": "2026-10-13T14:00:00Z",
                "updated_at": "2026-10-13T14:10:00Z",
                "model": "qwen2.5:1.5b",
                "username": "web_user",
            }
        ]

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = remote_list_data

        with patch("httpx.Client.get", return_value=mock_resp):
            sessions = sm.list_sessions()

        ids = [s.session_id for s in sessions]
        assert local_sess.metadata.session_id in ids
        assert "remote-conv-9999" in ids
        web_item = next(s for s in sessions if s.session_id == "remote-conv-9999")
        assert web_item.source == "web"

    def test_save_session_syncs_to_web(self, tmp_path: Path):
        sm = SessionManager(storage_dir=tmp_path, backend_url="http://mock-backend")
        sess = sm.create_session(profile=None, model="qwen2.5:1.5b", title="Test Sync")
        sess.add_message(ChatMessage(role="user", content="Message CLI"))

        with patch("httpx.Client.post") as mock_post:
            sm.save_session(sess, sync_remote=True)
            assert mock_post.called
            url = mock_post.call_args[0][0]
            assert sess.metadata.session_id in url

    def test_cli_continues_conversation_started_on_web(self, tmp_path: Path, capsys):
        sm = SessionManager(storage_dir=tmp_path / "sessions")
        pm = ProfileManager(storage_dir=tmp_path / "profiles")
        mock_client = MagicMock()
        mock_client.chat_stream.return_value = iter(["Suite de ", "la réponse CLI"])

        # Création d'une conversation simulant celle issue de l'interface Web
        web_session = sm.create_session(profile=None, model="qwen2.5:1.5b", title="Web Chat Initial")
        web_session.metadata.source = "web"
        web_session.add_message(ChatMessage(role="user", content="Premier message Web"))
        web_session.add_message(ChatMessage(role="assistant", content="Premier retour Web"))
        sm.save_session(web_session)

        # Lancement de la CLI avec --session ciblant les 8 premiers caractères de l'ID Web
        short_id = web_session.metadata.session_id[:8]
        inputs = ["Deuxième message CLI", "/exit"]

        with patch("builtins.input", side_effect=inputs):
            run_session(
                client=mock_client,
                model="qwen2.5:1.5b",
                host="http://localhost:11434",
                session_id=short_id,
                session_manager=sm,
                profile_manager=pm,
            )

        captured = capsys.readouterr()
        assert f"Session '{short_id}' loaded" in captured.out

        # Vérification que la session a été continuée avec succès
        reloaded = sm.load_session(web_session.metadata.session_id)
        assert len(reloaded.messages) == 4
        assert reloaded.messages[0].content == "Premier message Web"
        assert reloaded.messages[1].content == "Premier retour Web"
        assert reloaded.messages[2].content == "Deuxième message CLI"
        assert reloaded.messages[3].content == "Suite de la réponse CLI"


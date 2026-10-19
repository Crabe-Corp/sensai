import pytest
from src.features.memory import ProfileManager, SessionManager


@pytest.fixture(autouse=True)
def isolate_session_storage(tmp_path, monkeypatch):
    """Isole le stockage des sessions et profils durant les tests afin d'éviter toute pollution de storage/sessions/."""
    monkeypatch.setattr(
        "src.interfaces.cli.main.SessionManager",
        lambda *args, **kwargs: SessionManager(storage_dir=tmp_path / "sessions"),
    )
    monkeypatch.setattr(
        "src.interfaces.cli.main.ProfileManager",
        lambda *args, **kwargs: ProfileManager(storage_dir=tmp_path / "profiles"),
    )

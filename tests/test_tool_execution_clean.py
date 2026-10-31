import asyncio
import json
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

_ROOT_DIR = Path(__file__).resolve().parent.parent
if str(_ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(_ROOT_DIR))

_BACKEND_DIR = _ROOT_DIR / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from database import Base
from models import Conversation, Message, User
from routes.conversation_routes import ChatMessageRequest, chat_stream


@pytest.fixture
def clean_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_tool_execution_does_not_leak_debug_print_into_stream_and_db(clean_db):
    """Vérifie que l'exécution d'un outil n'injecte plus '[Outil exécuté : ...]' dans les chunks ni en BDD."""
    user = User(id=1, username="test_clean_user", password_hash="dummy_hash")
    conv = Conversation(id="conv-clean-1", created_by_id=user.id, title="Test Tool Leaks")
    clean_db.add_all([user, conv])
    clean_db.commit()

    req = ChatMessageRequest(
        content="can you tell me about the Qin state ?",
        model="qwen2.5:7b",
        tools=["search_historical_archives"],
    )

    # Simulation de 2 tours Ollama :
    # Tour 1 : Ollama demande l'outil search_historical_archives
    turn1_lines = [
        json.dumps({
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "search_historical_archives",
                            "arguments": {"query": "Qin"},
                        }
                    }
                ],
            },
            "done": False,
        }),
        json.dumps({"done": True}),
    ]

    # Tour 2 : Après l'outil, Ollama génère la réponse finale propre
    turn2_lines = [
        json.dumps({
            "message": {
                "role": "assistant",
                "content": "The State of Qin was one of the seven warring states.",
            },
            "done": False,
        }),
        json.dumps({"done": True, "eval_count": 15}),
    ]

    async def _run():
        with (
            patch("routes.conversation_routes.validate_input_with_llm", return_value=(True, None)),
            patch("routes.conversation_routes.sementic_cache.get_info_cache", return_value=None),
            patch("routes.conversation_routes.sementic_cache.add_to_cache") as mock_add_cache,
            patch("routes.conversation_routes.run_tool", return_value='{"status": "success", "results": ["Qin chronicles"]}') as mock_run_tool,
            patch("httpx.AsyncClient.stream") as mock_http_stream,
        ):
            mock_responses = []
            for lines in [turn1_lines, turn2_lines]:
                resp = MagicMock()
                async def make_iter(l=lines):
                    for line in l:
                        yield line
                resp.aiter_lines = make_iter
                mock_responses.append(resp)

            call_count = [0]
            def fake_stream(method, url, json=None, **kwargs):
                idx = min(call_count[0], len(mock_responses) - 1)
                call_count[0] += 1
                mock_ctx = MagicMock()
                mock_ctx.__aenter__.return_value = mock_responses[idx]
                return mock_ctx

            mock_http_stream.side_effect = fake_stream

            stream_res = await chat_stream(
                conversation_id=conv.id,
                req=req,
                user=user,
                db=clean_db,
            )

            events = []
            async for line in stream_res.body_iterator:
                if line.strip():
                    events.append(json.loads(line))

            # 1. Vérification que l'outil a bien été exécuté
            mock_run_tool.assert_called_once_with("search_historical_archives", {"query": "Qin"})

            # 2. Vérification que AUCUN chunk ne contient le texte de debug [Outil exécuté]
            chunk_contents = [e.get("content", "") for e in events if e.get("type") == "chunk"]
            full_streamed_text = "".join(chunk_contents)
            assert "[Outil exécuté" not in full_streamed_text
            assert "search_historical_archives" not in full_streamed_text
            assert "The State of Qin was one of the seven warring states." in full_streamed_text

            # 3. Vérification du message sauvé en base de données : propre, sans trace technique
            saved_msg = clean_db.query(Message).filter(Message.conversation_id == conv.id, Message.role == "assistant").first()
            assert saved_msg is not None
            assert "[Outil exécuté" not in saved_msg.content
            assert saved_msg.content == "The State of Qin was one of the seven warring states."

            # 4. Vérification que le cache sémantique a été alimenté avec la réponse propre
            mock_add_cache.assert_called_once()
            cache_kwargs = mock_add_cache.call_args[1]
            assert "[Outil exécuté" not in cache_kwargs["llm_response"]
            assert cache_kwargs["llm_response"] == "The State of Qin was one of the seven warring states."

    asyncio.run(_run())

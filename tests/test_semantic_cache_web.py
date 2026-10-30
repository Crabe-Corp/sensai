import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
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
from routes.conversation_routes import (
    ChatMessageRequest,
    chat_stream,
    clear_semantic_cache,
)
from src.core.ollama_client import ChatMessage


@pytest.fixture
def test_db_session():
    """Crée une base SQLite temporaire en mémoire pour les tests de routes."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = Session()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def mock_user(test_db_session):
    """Crée un utilisateur propriétaire de test."""
    user = User(id=1, username="scholar_cache_user", password_hash="dummy_hash")
    test_db_session.add(user)
    test_db_session.commit()
    test_db_session.refresh(user)
    return user


@pytest.fixture
def other_user(test_db_session):
    """Crée un utilisateur tiers sans droits."""
    user = User(id=2, username="intruder_user", password_hash="dummy_hash")
    test_db_session.add(user)
    test_db_session.commit()
    test_db_session.refresh(user)
    return user


@pytest.fixture
def mock_conversation(test_db_session, mock_user):
    """Crée une conversation de test pour l'utilisateur principal."""
    conv = Conversation(
        id="conv-cache-test-1",
        title="Session Cache Sémantique",
        created_by_id=mock_user.id,
        mode="solo",
        model_name="qwen3:0.6b",
        tools_enabled="[]",
    )
    test_db_session.add(conv)
    test_db_session.commit()
    test_db_session.refresh(conv)
    return conv


def test_semantic_cache_hit_streams_immediately(test_db_session, mock_user, mock_conversation):
    """Vérifie qu'un Cache HIT évite le recalcul LLM et diffuse directement avec indication de provenance."""
    async def _run():
        cached_answer = "Pékin est la capitale actuelle de la Chine depuis plusieurs dynasties."
        user_prompt = "Quelle est la capitale de la Chine ?"
        req = ChatMessageRequest(content=user_prompt)

        with patch(
            "routes.conversation_routes.validate_input_with_llm",
            return_value=(True, ""),
        ), patch(
            "routes.conversation_routes.sementic_cache.get_info_cache",
            return_value=cached_answer,
        ) as mock_get_cache, patch(
            "routes.conversation_routes.manager.broadcast",
            new_callable=AsyncMock,
        ) as mock_broadcast, patch(
            "httpx.AsyncClient.stream"
        ) as mock_http_stream:
            # Appel du endpoint de chat
            response = await chat_stream(
                conversation_id=mock_conversation.id,
                req=req,
                user=mock_user,
                db=test_db_session,
            )

            # Consommation des chunks de réponse
            events = []
            async for line in response.body_iterator:
                line_str = line.strip()
                if line_str:
                    events.append(json.loads(line_str))

            # 1. Vérification que get_info_cache a été interrogé avec le bon prompt et modèle
            mock_get_cache.assert_called_once()
            call_kwargs = mock_get_cache.call_args[1]
            assert call_kwargs.get("prompt") == user_prompt

            # 2. Vérification que l'API LLM n'a JAMAIS été appelée
            mock_http_stream.assert_not_called()

            # 3. Vérification des événements émis (chunk et done avec from_cache: True)
            event_types = [e["type"] for e in events]
            assert "start" in event_types
            assert "chunk" in event_types
            assert "done" in event_types

            chunks = [e for e in events if e.get("type") == "chunk"]
            assert len(chunks) >= 1
            assert chunks[0].get("content") == cached_answer
            assert chunks[0].get("from_cache") is True

            done_events = [e for e in events if e.get("type") == "done"]
            assert len(done_events) == 1
            assert done_events[0].get("from_cache") is True

            # 4. Vérification de la persistance en base de données
            saved_assistant_msg = (
                test_db_session.query(Message)
                .filter(Message.conversation_id == mock_conversation.id, Message.role == "assistant")
                .first()
            )
            assert saved_assistant_msg is not None
            assert saved_assistant_msg.content == cached_answer

            # 5. Vérification du broadcast WebSocket avec from_cache
            broadcast_calls = [call[0][1] for call in mock_broadcast.call_args_list]
            assistant_broadcasts = [
                b for b in broadcast_calls if b.get("message", {}).get("role") == "assistant"
            ]
            assert len(assistant_broadcasts) == 1
            assert assistant_broadcasts[0]["message"]["from_cache"] is True
            assert assistant_broadcasts[0]["message"]["content"] == cached_answer

    asyncio.run(_run())


def test_semantic_cache_miss_calls_llm_and_saves_new_response(test_db_session, mock_user, mock_conversation):
    """Vérifie qu'un Cache MISS déclenche la génération LLM puis enregistre la réponse dans le cache."""
    async def _run():
        new_prompt = "Parle-moi de la bataille de Changping."
        llm_generated_reply = "La bataille de Changping opposa l'État de Qin à celui de Zhao en 260 av. J.-C."
        req = ChatMessageRequest(content=new_prompt)

        with patch(
            "routes.conversation_routes.validate_input_with_llm",
            return_value=(True, ""),
        ), patch(
            "routes.conversation_routes.sementic_cache.get_info_cache",
            return_value=None,
        ) as mock_get_cache, patch(
            "routes.conversation_routes.sementic_cache.add_to_cache",
            return_value=True,
        ) as mock_add_cache, patch(
            "routes.conversation_routes.manager.broadcast",
            new_callable=AsyncMock,
        ), patch(
            "httpx.AsyncClient.stream"
        ) as mock_http_stream:
            # Mock de la réponse streaming du modèle Ollama
            async def fake_stream_lines():
                yield json.dumps({"message": {"content": llm_generated_reply}, "done": False})
                yield json.dumps({"done": True, "eval_count": 25})

            mock_response = MagicMock()
            mock_response.aiter_lines = fake_stream_lines
            mock_http_stream.return_value.__aenter__.return_value = mock_response

            response = await chat_stream(
                conversation_id=mock_conversation.id,
                req=req,
                user=mock_user,
                db=test_db_session,
            )

            # Consommation du flux
            events = []
            async for line in response.body_iterator:
                line_str = line.strip()
                if line_str:
                    events.append(json.loads(line_str))

            # 1. Vérification de l'interrogation du cache
            mock_get_cache.assert_called_once()

            # 2. Vérification que le modèle LLM a été sollicité
            mock_http_stream.assert_called_once()

            # 3. Vérification de l'enregistrement dans le cache sémantique
            mock_add_cache.assert_called_once()
            add_kwargs = mock_add_cache.call_args[1]
            assert add_kwargs.get("prompt") == new_prompt
            assert add_kwargs.get("llm_response") == llm_generated_reply

            # 4. Vérification de la persistance en base
            saved_msg = (
                test_db_session.query(Message)
                .filter(Message.conversation_id == mock_conversation.id, Message.role == "assistant")
                .first()
            )
            assert saved_msg is not None
            assert saved_msg.content == llm_generated_reply

    asyncio.run(_run())


def test_clear_semantic_cache_endpoint(test_db_session, mock_user, other_user, mock_conversation):
    """Valide l'endpoint POST /api/conversations/{id}/clearcache ([A6])."""
    with patch("routes.conversation_routes.sementic_cache.clean_cache") as mock_clean:
        # 1. Appel réussi par le propriétaire
        res = clear_semantic_cache(
            conversation_id=mock_conversation.id,
            user=mock_user,
            db=test_db_session,
        )
        assert res["success"] is True
        mock_clean.assert_called_once()

    # 2. Erreur 403 si utilisateur non autorisé
    with pytest.raises(HTTPException) as exc_403:
        clear_semantic_cache(
            conversation_id=mock_conversation.id,
            user=other_user,
            db=test_db_session,
        )
    assert exc_403.value.status_code == 403

    # 3. Erreur 404 si conversation inconnue
    with pytest.raises(HTTPException) as exc_404:
        clear_semantic_cache(
            conversation_id="non-existent-id",
            user=mock_user,
            db=test_db_session,
        )
    assert exc_404.value.status_code == 404


def test_memory_management_token_budget_enforcement(test_db_session, mock_user, mock_conversation):
    """Vérifie que le budget de tokens via memory_management compresse l'historique ([M2])."""
    # Ajout de plusieurs messages antérieurs volumineux
    for i in range(8):
        m = Message(
            id=f"msg-history-{i}",
            conversation_id=mock_conversation.id,
            sender_id=mock_user.id if i % 2 == 0 else None,
            sender_name="scholar" if i % 2 == 0 else "SensAI",
            role="user" if i % 2 == 0 else "assistant",
            content=f"Message volumineux {i} portant sur l'histoire des Royaumes Combattants." * 10,
            prompt_tokens=300,
            completion_tokens=300,
            total_tokens=600,
        )
        test_db_session.add(m)
    test_db_session.commit()

    compressed_summary_msg = ChatMessage(
        role="system",
        content="Summary of previous exchanges: Résumé synthétique des échanges historiques.",
    )

    def fake_enforce(model, client, messages, max_history_tokens=2000):
        # Simule la compression semantique opérée par memory_management
        return [
            messages[0],  # system prompt
            compressed_summary_msg,
            messages[-2],
            messages[-1],
        ]

    async def _run():
        req = ChatMessageRequest(content="Dernière question sur Qin Shi Huang.")

        with patch(
            "routes.conversation_routes.validate_input_with_llm",
            return_value=(True, ""),
        ), patch(
            "routes.conversation_routes.sementic_cache.get_info_cache",
            return_value=None,
        ), patch(
            "routes.conversation_routes.sementic_cache.add_to_cache",
            return_value=True,
        ), patch(
            "routes.conversation_routes.memory_management.consume_tokens"
        ) as mock_consume, patch(
            "routes.conversation_routes.memory_management.enforce_token_budget",
            side_effect=fake_enforce,
        ) as mock_enforce, patch(
            "httpx.AsyncClient.stream"
        ) as mock_http_stream:
            captured_payload = {}

            async def fake_aiter_lines():
                yield json.dumps({"message": {"content": "Qin Shi Huang a unifié la Chine en 221 av. J.-C."}, "done": True, "eval_count": 20})

            mock_response = MagicMock()
            mock_response.aiter_lines = fake_aiter_lines

            def fake_stream(method, url, json=None, **kwargs):
                nonlocal captured_payload
                captured_payload = json
                mock_ctx = MagicMock()
                mock_ctx.__aenter__ = AsyncMock(return_value=mock_response)
                mock_ctx.__aexit__ = AsyncMock(return_value=None)
                return mock_ctx

            mock_http_stream.side_effect = fake_stream

            response = await chat_stream(
                conversation_id=mock_conversation.id,
                req=req,
                user=mock_user,
                db=test_db_session,
            )

            # Consommer le stream
            async for _ in response.body_iterator:
                pass

            # 1. Vérification que consume_tokens a été appelé avec un total supérieur au seuil
            mock_consume.assert_called_once()
            tokens_passed = mock_consume.call_args[0][0]
            assert tokens_passed > 2000

            # 2. Vérification que enforce_token_budget a été sollicité
            mock_enforce.assert_called_once()
            enforce_kwargs = mock_enforce.call_args[1]
            assert enforce_kwargs.get("max_history_tokens") == 2000

            # 3. Vérification que le payload envoyé à Ollama contient bien le résumé compressé
            assert "messages" in captured_payload
            sent_roles = [m["role"] for m in captured_payload["messages"]]
            sent_contents = [m["content"] for m in captured_payload["messages"]]

            assert any("Summary of previous exchanges" in c for c in sent_contents)
            assert len(captured_payload["messages"]) == 4

    asyncio.run(_run())

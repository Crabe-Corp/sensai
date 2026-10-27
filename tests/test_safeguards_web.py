import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

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
from src.features.sec.security import mask_pii


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
    """Crée un utilisateur de test persistant."""
    user = User(id=1, username="scholar_tester", password_hash="dummy_hash")
    test_db_session.add(user)
    test_db_session.commit()
    test_db_session.refresh(user)
    return user


@pytest.fixture
def mock_conversation(test_db_session, mock_user):
    """Crée une conversation de test."""
    conv = Conversation(
        id="conv-safeguard-test-1",
        title="Nouvelle conversation",
        created_by_id=mock_user.id,
        mode="solo",
        model_name="qwen3:0.6b",
        tools_enabled="[]",
    )
    test_db_session.add(conv)
    test_db_session.commit()
    test_db_session.refresh(conv)
    return conv


def test_pii_masking_on_message_send(test_db_session, mock_user, mock_conversation):
    """Vérifie que les PII (email, téléphone français) sont masquées dans la base et les flux."""
    async def _run():
        raw_message = (
            "Bonjour, contactez-moi par email test.user@example.com ou au 0612345678 "
            "pour discuter des Royaumes Combattants."
        )

        req = ChatMessageRequest(content=raw_message)

        # Mock de la validation LLM (valide)
        with patch(
            "routes.conversation_routes.validate_input_with_llm",
            return_value=(True, ""),
        ) as mock_validate, patch(
            "routes.conversation_routes.manager.broadcast",
            new_callable=AsyncMock,
        ) as mock_broadcast, patch(
            "httpx.AsyncClient.stream"
        ) as mock_http_stream:
            # Mock de la réponse streaming du modèle Ollama
            async def _fake_aiter_lines():
                yield json.dumps({"message": {"content": "Bien reçu l'information."}, "done": False})
                yield json.dumps({"done": True, "eval_count": 10})

            mock_response = MagicMock()
            mock_response.aiter_lines = _fake_aiter_lines
            mock_http_stream.return_value.__aenter__.return_value = mock_response

            # Appel du endpoint de chat
            response = await chat_stream(
                conversation_id=mock_conversation.id,
                req=req,
                user=mock_user,
                db=test_db_session,
            )

            # Consommation du flux de réponse
            chunks = []
            async for line in response.body_iterator:
                chunks.append(line)

            # 1. Vérification en base de données : l'email et le téléphone ne doivent PAS apparaître
            saved_user_msg = (
                test_db_session.query(Message)
                .filter(Message.conversation_id == mock_conversation.id, Message.role == "user")
                .first()
            )
            assert saved_user_msg is not None
            assert "test.user@example.com" not in saved_user_msg.content
            assert "0612345678" not in saved_user_msg.content
            assert "[DONNÉE MASQUÉE]" in saved_user_msg.content

            # 2. Vérification que validate_input_with_llm a bien reçu le texte masqué
            mock_validate.assert_called_once()
            validated_text = mock_validate.call_args[0][0]
            assert "test.user@example.com" not in validated_text
            assert "0612345678" not in validated_text
            assert "[DONNÉE MASQUÉE]" in validated_text

            # 3. Vérification du broadcast WebSocket
            mock_broadcast.assert_called()
            first_broadcast = mock_broadcast.call_args_list[0][0][1]
            assert first_broadcast["type"] == "new_message"
            assert "[DONNÉE MASQUÉE]" in first_broadcast["message"]["content"]
            assert "test.user@example.com" not in first_broadcast["message"]["content"]

    asyncio.run(_run())


def test_off_topic_guardrail_blocking(test_db_session, mock_user, mock_conversation):
    """Vérifie le blocage d'une requête hors-sujet par le guardrail de modération sans appel au modèle."""
    async def _run():
        off_topic_message = "Donne-moi une recette moderne de burger avec frites."
        req = ChatMessageRequest(content=off_topic_message)

        refusal_msg = "The imperial advisor refuses to discuss this topic with you."

        with patch(
            "routes.conversation_routes.validate_input_with_llm",
            return_value=(False, refusal_msg),
        ) as mock_validate, patch(
            "routes.conversation_routes.manager.broadcast",
            new_callable=AsyncMock,
        ) as mock_broadcast, patch(
            "httpx.AsyncClient.stream"
        ) as mock_http_stream:
            # Exécution du chat
            response = await chat_stream(
                conversation_id=mock_conversation.id,
                req=req,
                user=mock_user,
                db=test_db_session,
            )

            # Consommation du streaming NDJSON
            events = []
            async for line in response.body_iterator:
                trimmed = line.strip()
                if trimmed:
                    events.append(json.loads(trimmed))

            # 1. Vérification que le modèle de génération n'a JAMAIS été sollicité
            mock_http_stream.assert_not_called()

            # 2. Vérification des événements émis par le flux NDJSON
            event_types = [e["type"] for e in events]
            assert "start" in event_types
            assert "chunk" in event_types
            assert "done" in event_types

            chunk_contents = [e.get("content", "") for e in events if e.get("type") == "chunk"]
            assert any(refusal_msg in c for c in chunk_contents)

            # 3. Vérification de la persistance de la réponse d'interdiction en DB
            saved_assistant_msg = (
                test_db_session.query(Message)
                .filter(Message.conversation_id == mock_conversation.id, Message.role == "assistant")
                .first()
            )
            assert saved_assistant_msg is not None
            assert saved_assistant_msg.content == refusal_msg

            # 4. Vérification de la diffusion WebSocket de l'interdiction
            broadcast_calls = [call[0][1] for call in mock_broadcast.call_args_list]
            assistant_broadcasts = [
                b for b in broadcast_calls if b.get("message", {}).get("role") == "assistant"
            ]
            assert len(assistant_broadcasts) == 1
            assert assistant_broadcasts[0]["message"]["content"] == refusal_msg

    asyncio.run(_run())


def test_combined_pii_masking_and_rejection(test_db_session, mock_user, mock_conversation):
    """Vérifie le cas où une requête contient à la fois des PII et un sujet hors-sujet."""
    async def _run():
        content = "Mon numéro est 0711223344, joue à Fortnite avec moi."
        req = ChatMessageRequest(content=content)

        refusal_msg = "The imperial advisor refuses to discuss this topic with you."

        with patch(
            "routes.conversation_routes.validate_input_with_llm",
            return_value=(False, refusal_msg),
        ) as mock_validate, patch(
            "routes.conversation_routes.manager.broadcast",
            new_callable=AsyncMock,
        ):
            response = await chat_stream(
                conversation_id=mock_conversation.id,
                req=req,
                user=mock_user,
                db=test_db_session,
            )

            async for _ in response.body_iterator:
                pass

            # Vérifie que le prompt passé à validate contenait le masque et pas le numéro réel
            validated_prompt = mock_validate.call_args[0][0]
            assert "0711223344" not in validated_prompt
            assert "[DONNÉE MASQUÉE]" in validated_prompt

            # Vérifie que l'utilisateur stocké en DB a bien son numéro masqué
            user_msg = (
                test_db_session.query(Message)
                .filter(Message.conversation_id == mock_conversation.id, Message.role == "user")
                .first()
            )
            assert "0711223344" not in user_msg.content
            assert "[DONNÉE MASQUÉE]" in user_msg.content

    asyncio.run(_run())

from unittest.mock import MagicMock, patch
import pytest

from src.RAG.retriever import _fetch_web_backup, retrieve_rag_context


class DummyHit:
    def __init__(self, source: str, texte: str) -> None:
        self.payload = {"source": source, "texte": texte}


class DummyQdrantResponse:
    def __init__(self, points: list[DummyHit]) -> None:
        self.points = points


def test_fetch_web_backup_success():
    with patch("src.features.tools.web_search.web_search", return_value="Résultats Web pertinents"):
        res = _fetch_web_backup("bataille de Changping")
        assert res == "Résultats Web pertinents"


def test_fetch_web_backup_empty_or_error():
    with patch("src.features.tools.web_search.web_search", return_value="Aucun résultat trouvé sur le Web pour la recherche : 'test'."):
        res = _fetch_web_backup("test")
        assert res is None


def test_retrieve_rag_context_sufficient_sources_no_web():
    dummy_points = [DummyHit(f"Chronique {i}", f"Texte historique {i}") for i in range(5)]
    mock_client = MagicMock()
    mock_client.collection_exists.return_value = True
    mock_client.query_points.return_value = DummyQdrantResponse(dummy_points)

    with patch("qdrant_client.QdrantClient", return_value=mock_client), \
         patch("src.RAG.retriever.get_embedding", return_value=[0.1] * 128), \
         patch("src.RAG.retriever.extract_character", return_value=None), \
         patch("src.RAG.retriever._fetch_web_backup") as mock_web:
        
        ctx, count = retrieve_rag_context("bataille des Royaumes", return_count=True)
        assert count == 5
        assert "Chronique 0" in ctx
        assert "Chronique 4" in ctx
        mock_web.assert_not_called()


def test_retrieve_rag_context_single_source_triggers_web_complement():
    dummy_points = [DummyHit("Chronique Qin", "Qin Shi Huang ordonne la conscription.")]
    mock_client = MagicMock()
    mock_client.collection_exists.return_value = True
    mock_client.query_points.return_value = DummyQdrantResponse(dummy_points)

    with patch("qdrant_client.QdrantClient", return_value=mock_client), \
         patch("src.RAG.retriever.get_embedding", return_value=[0.1] * 128), \
         patch("src.RAG.retriever.extract_character", return_value=None), \
         patch("src.RAG.retriever._fetch_web_backup", return_value="Résultats Wikipedia sur Qin Shi Huang"):
        
        ctx, count = retrieve_rag_context("Qin Shi Huang", min_sources=2, fallback_web=True, return_count=True)
        assert count == 1
        assert "[Source : Chronique Qin]" in ctx
        assert "Qin Shi Huang ordonne la conscription." in ctx
        assert "[Recherche Web - Complément pour sources locales insuffisantes (1/2)]" in ctx
        assert "Résultats Wikipedia sur Qin Shi Huang" in ctx


def test_retrieve_rag_context_zero_sources_triggers_full_web():
    mock_client = MagicMock()
    mock_client.collection_exists.return_value = True
    mock_client.query_points.return_value = DummyQdrantResponse([])

    with patch("qdrant_client.QdrantClient", return_value=mock_client), \
         patch("src.RAG.retriever.get_embedding", return_value=[0.1] * 128), \
         patch("src.RAG.retriever.extract_character", return_value=None), \
         patch("src.RAG.retriever._fetch_web_backup", return_value="Infos Web trouvées"):
        
        ctx, count = retrieve_rag_context("inconnu au bataillon", fallback_web=True, return_count=True)
        assert count == 0
        assert "[Recherche Web - Aucune archive locale trouvée]" in ctx
        assert "Infos Web trouvées" in ctx


def test_retrieve_rag_context_zero_sources_without_fallback_returns_none():
    mock_client = MagicMock()
    mock_client.collection_exists.return_value = True
    mock_client.query_points.return_value = DummyQdrantResponse([])

    with patch("qdrant_client.QdrantClient", return_value=mock_client), \
         patch("src.RAG.retriever.get_embedding", return_value=[0.1] * 128), \
         patch("src.RAG.retriever.extract_character", return_value=None), \
         patch("src.RAG.retriever._fetch_web_backup") as mock_web:
        
        ctx, count = retrieve_rag_context("inconnu au bataillon", fallback_web=False, return_count=True)
        assert count == 0
        assert ctx is None
        mock_web.assert_not_called()


def test_retrieve_rag_context_qdrant_connection_failure_falls_back_to_web():
    with patch("qdrant_client.QdrantClient", side_effect=ConnectionError("Qdrant inaccessible")), \
         patch("src.RAG.retriever._fetch_web_backup", return_value="Secours Web actif"):
        
        ctx, count = retrieve_rag_context("Question sur Han", fallback_web=True, return_count=True)
        assert count == 0
        assert "[Recherche Web - Archives locales inaccessibles]" in ctx
        assert "Secours Web actif" in ctx


def test_cli_rag_cascade_sufficient_sources():
    from src.interfaces.cli.main import run_session
    mock_client = MagicMock()

    fake_rag = "[Source : Chronique 1]\nExtrait 1\n\n[Source : Chronique 2]\nExtrait 2"
    with patch("builtins.input", side_effect=["Quelle est la stratégie de Qin ?", "/exit"]), \
         patch("src.RAG.retriever.retrieve_rag_context", return_value=(fake_rag, 2)), \
         patch("src.core.engine.ConversationEngine.run_stream", return_value=iter([])) as mock_run:
        run_session(mock_client, model="qwen2.5:1.5b", host="http://localhost:11434", tools=True, rag_enabled=True)

    mock_run.assert_called_once()
    args, kwargs = mock_run.call_args
    sent_content = kwargs["messages"][-1].content
    assert "archives locales fournies ci-dessous (2 sources trouvées)" in sent_content
    assert "[Source : Chronique 1]" in sent_content
    assert "Quelle est la stratégie de Qin ?" in sent_content


def test_cli_rag_cascade_single_source_triggers_enrichment():
    from src.interfaces.cli.main import run_session
    mock_client = MagicMock()

    fake_rag = "[Source : Chronique Qin]\nPetit extrait.\n\n[Recherche Web - Complément pour sources locales insuffisantes (1/2)]\nWeb extrait"
    with patch("builtins.input", side_effect=["Parle moi de Zhao", "/exit"]), \
         patch("src.RAG.retriever.retrieve_rag_context", return_value=(fake_rag, 1)), \
         patch("src.core.engine.ConversationEngine.run_stream", return_value=iter([])) as mock_run:
        run_session(mock_client, model="qwen2.5:1.5b", host="http://localhost:11434", tools=True, rag_enabled=True)

    mock_run.assert_called_once()
    args, kwargs = mock_run.call_args
    sent_content = kwargs["messages"][-1].content
    assert "Ne te limite pas à une réponse courte de 3 lignes !" in sent_content
    assert "ARCHIVES ET SOURCES COMPLÉMENTAIRES" in sent_content
    assert "Web extrait" in sent_content


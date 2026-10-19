import json
from unittest.mock import MagicMock
import httpx
import pytest

from src.core.engine import (
    ConversationEngine,
    TokenChunkEvent,
    ToolCallEvent,
    ToolResultEvent,
)
from src.core.ollama_client import ChatMessage
from src.features.tools.executor import ToolExecutor
from src.features.tools.registry import default_registry
from src.features.tools.web_search import (
    clean_ddg_url,
    format_search_results,
    parse_ddg_html,
    search_duckduckgo,
    search_wikipedia,
    web_search,
)

SAMPLE_DDG_HTML = """
<!DOCTYPE html>
<html>
<body>
<div class="result results_links results_links_deep web-result ">
  <div class="links_main links_deep result__body">
    <h2 class="result__title">
      <a class="result__url" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Ffr.wikipedia.org%2Fwiki%2FArm%25C3%25A9e_de_terre_cuite&rut=1">
        Armée de terre cuite de Qin - Découvertes récentes
      </a>
    </h2>
    <a class="result__snippet" href="#">
      Des archéologues ont mis au jour de nouvelles fosses funéraires contenant des armes en bronze intactes et 200 nouveaux guerriers.
    </a>
  </div>
</div>
<div class="result results_links results_links_deep web-result ">
  <div class="links_main links_deep result__body">
    <h2 class="result__title">
      <a class="result__url" href="https://archeo-chroniques.fr/qin-terracotta">
        Qin Shi Huang et le complexe funéraire de Lintong
      </a>
    </h2>
    <a class="result__snippet" href="#">
      Analyses isotopiques sur la fabrication des pigments violets des guerriers de l'époque des Royaumes combattants.
    </a>
  </div>
</div>
</body>
</html>
"""


def test_clean_ddg_url():
    direct_url = "https://en.wikipedia.org/wiki/Qin_dynasty"
    assert clean_ddg_url(direct_url) == direct_url

    redirect_url = "//duckduckgo.com/l/?uddg=https%3A%2F%2Ffr.wikipedia.org%2Fwiki%2FArm%C3%A9e_de_terre_cuite&rut=1"
    expected = "https://fr.wikipedia.org/wiki/Armée_de_terre_cuite"
    assert clean_ddg_url(redirect_url) == expected

    relative_redirect = "/l/?uddg=https%3A%2F%2Fexample.org%2Farticle"
    assert clean_ddg_url(relative_redirect) == "https://example.org/article"

    assert clean_ddg_url("") == ""


def test_parse_ddg_html():
    results = parse_ddg_html(SAMPLE_DDG_HTML, max_results=2)
    assert len(results) == 2

    first = results[0]
    assert first["title"] == "Armée de terre cuite de Qin - Découvertes récentes"
    assert "https://fr.wikipedia.org/wiki/Armée_de_terre_cuite" in first["url"]
    assert "nouvelles fosses funéraires" in first["snippet"]

    second = results[1]
    assert second["title"] == "Qin Shi Huang et le complexe funéraire de Lintong"
    assert second["url"] == "https://archeo-chroniques.fr/qin-terracotta"
    assert "pigments violets" in second["snippet"]


def test_parse_ddg_html_respects_max_results():
    results = parse_ddg_html(SAMPLE_DDG_HTML, max_results=1)
    assert len(results) == 1


def test_search_duckduckgo_success(monkeypatch):
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.text = SAMPLE_DDG_HTML
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.post.return_value = mock_response
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = None

    monkeypatch.setattr(httpx, "Client", lambda **kwargs: mock_client)

    res = search_duckduckgo("armée de terre cuite", max_results=2)
    assert len(res) == 2
    assert res[0]["title"] == "Armée de terre cuite de Qin - Découvertes récentes"


def test_search_wikipedia_success(monkeypatch):
    mock_data = {
        "query": {
            "search": [
                {
                    "title": "Armée de terre cuite",
                    "snippet": "L'<span class=\"searchmatch\">armée</span> d'argile de l'empereur Qin.",
                },
                {
                    "title": "Mausolée de l'empereur Qin",
                    "snippet": "Vaste nécropole située près de Xi'an.",
                },
            ]
        }
    }
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = mock_data
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.get.return_value = mock_response
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = None

    monkeypatch.setattr(httpx, "Client", lambda **kwargs: mock_client)

    res = search_wikipedia("Qin", max_results=2, lang="fr")
    assert len(res) == 2
    assert res[0]["title"] == "Armée de terre cuite"
    assert res[0]["snippet"] == "L'armée d'argile de l'empereur Qin."
    assert "fr.wikipedia.org/wiki/Arm%C3%A9e_de_terre_cuite" in res[0]["url"]


def test_format_search_results():
    items = [
        {
            "title": "Guerriers de Qin",
            "url": "https://example.com/qin",
            "snippet": "Nouvelle excavation à Lintong.",
        }
    ]
    formatted = format_search_results("Qin", items)
    assert 'Résultats de recherche Web pour "Qin"' in formatted
    assert "[1] Guerriers de Qin" in formatted
    assert "URL : https://example.com/qin" in formatted
    assert "Extrait : Nouvelle excavation à Lintong." in formatted
    assert "cite expressément les URLs" in formatted


def test_format_search_results_empty():
    assert "Aucun résultat trouvé" in format_search_results("Inconnu", [])


def test_web_search_empty_query():
    res = web_search("")
    assert "Requête de recherche vide" in res

    res_spaces = web_search("   ")
    assert "Requête de recherche vide" in res_spaces


def test_web_search_ddg_primary(monkeypatch):
    monkeypatch.setattr(
        "src.features.tools.web_search.search_duckduckgo",
        lambda query, max_results, timeout: [
            {
                "title": "Découverte Qin 2026",
                "url": "https://history.org/qin2026",
                "snippet": "Découverte majeure sur les armures des Royaumes combattants.",
            }
        ],
    )

    wiki_called = False

    def fake_wiki(*args, **kwargs):
        nonlocal wiki_called
        wiki_called = True
        return []

    monkeypatch.setattr("src.features.tools.web_search.search_wikipedia", fake_wiki)

    output = web_search("découvertes Qin")
    assert not wiki_called
    assert "Découverte Qin 2026" in output
    assert "https://history.org/qin2026" in output


def test_web_search_fallback_on_ddg_failure(monkeypatch):
    def failing_ddg(*args, **kwargs):
        raise httpx.ConnectError("DuckDuckGo injoignable")

    monkeypatch.setattr("src.features.tools.web_search.search_duckduckgo", failing_ddg)
    monkeypatch.setattr(
        "src.features.tools.web_search.search_wikipedia",
        lambda query, max_results, timeout, **kwargs: [
            {
                "title": "Armée de terre cuite (Secours)",
                "url": "https://fr.wikipedia.org/wiki/Armee_terre_cuite",
                "snippet": "Données historiques de secours.",
            }
        ],
    )

    output = web_search("armée de terre cuite Qin")
    assert "Armée de terre cuite (Secours)" in output
    assert "https://fr.wikipedia.org/wiki/Armee_terre_cuite" in output


def test_web_search_timeout_handling(monkeypatch):
    def timeout_call(*args, **kwargs):
        raise httpx.TimeoutException("Délai d'attente réseau expiré")

    monkeypatch.setattr("src.features.tools.web_search.search_duckduckgo", timeout_call)
    monkeypatch.setattr("src.features.tools.web_search.search_wikipedia", timeout_call)

    output = web_search("recherche timeout")
    assert "Erreur lors de la recherche Web" in output
    assert "Délai d'attente" in output


def test_web_search_network_error_handling(monkeypatch):
    def connect_error(*args, **kwargs):
        raise httpx.ConnectError("Réseau indisponible")

    monkeypatch.setattr("src.features.tools.web_search.search_duckduckgo", connect_error)
    monkeypatch.setattr("src.features.tools.web_search.search_wikipedia", connect_error)

    output = web_search("recherche hors ligne")
    assert "Erreur lors de la recherche Web" in output
    assert "services réseau inaccessibles" in output


def test_web_search_ollama_json_schema():
    assert "web_search" in default_registry
    tool_def = default_registry.get("web_search")
    assert tool_def is not None

    ollama_dict = tool_def.to_ollama_dict()
    assert ollama_dict["type"] == "function"
    assert ollama_dict["function"]["name"] == "web_search"
    assert "Recherche des informations sur le Web" in ollama_dict["function"]["description"]
    assert "PARAMS:" not in ollama_dict["function"]["description"]
    assert "RETURN:" not in ollama_dict["function"]["description"]

    params = ollama_dict["function"]["parameters"]
    assert params["type"] == "object"
    assert "query" in params["required"]
    assert params["properties"]["query"]["type"] == "string"
    assert "Termes ou question" in params["properties"]["query"]["description"]
    assert "max_results" in params["properties"]
    assert params["properties"]["max_results"]["type"] == "integer"
    assert "Nombre maximal" in params["properties"]["max_results"]["description"]
    assert params["properties"]["max_results"]["default"] == 3


def test_web_search_execution_via_tool_executor(monkeypatch):
    monkeypatch.setattr(
        "src.features.tools.web_search.search_duckduckgo",
        lambda query, max_results, timeout: [
            {
                "title": "Armée de terre cuite de Qin : fouilles archéologiques",
                "url": "https://archeologie.fr/qin-decouvertes",
                "snippet": "Plus de 200 nouvelles statues d'officiers et chevaux exhumées.",
            }
        ],
    )

    executor = ToolExecutor(registry=default_registry)
    result = executor.execute(
        "web_search",
        {"query": "dernières découvertes sur l'armée de terre cuite de Qin", "max_results": 1},
    )

    assert result.success is True
    assert result.tool_name == "web_search"
    assert "Armée de terre cuite de Qin" in result.result
    assert "https://archeologie.fr/qin-decouvertes" in result.result

    message_content = result.to_tool_message_content()
    parsed_content = json.loads(message_content)
    assert "result" in parsed_content
    assert "https://archeologie.fr/qin-decouvertes" in parsed_content["result"]


def test_web_search_engine_event_stream_simulation(monkeypatch):
    monkeypatch.setattr(
        "src.features.tools.web_search.search_duckduckgo",
        lambda query, max_results, timeout: [
            {
                "title": "Fouilles du mausolée de Qin Shi Huang",
                "url": "https://archeo-news.org/qin-terracotta-2026",
                "snippet": "Découverte de chars d'assaut impériaux d'époque.",
            }
        ],
    )

    fake_client = MagicMock()
    turn_1_data = [
        {
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "web_search",
                            "arguments": {"query": "dernières découvertes armée de terre cuite Qin"},
                        }
                    }
                ],
            }
        }
    ]
    turn_2_data = [
        {"message": {"role": "assistant", "content": "Selon les récentes fouilles "}},
        {"message": {"role": "assistant", "content": "(source: https://archeo-news.org/qin-terracotta-2026), 200 soldats ont été découverts."}},
    ]

    fake_client.chat_stream_raw.side_effect = [iter(turn_1_data), iter(turn_2_data)]

    engine = ConversationEngine(client=fake_client, registry=default_registry)
    events = list(
        engine.run_stream(
            messages=[ChatMessage(role="user", content="Quelles sont les dernières découvertes sur Qin ?")],
            model="qwen2.5:1.5b",
            tools=default_registry,
        )
    )

    tool_call_events = [e for e in events if isinstance(e, ToolCallEvent)]
    tool_result_events = [e for e in events if isinstance(e, ToolResultEvent)]
    token_events = [e for e in events if isinstance(e, TokenChunkEvent)]

    assert len(tool_call_events) == 1
    assert tool_call_events[0].tool_name == "web_search"

    assert len(tool_result_events) == 1
    assert "qin-terracotta-2026" in tool_result_events[0].result

    assert len(token_events) == 2
    full_text = "".join(t.token for t in token_events)
    assert "archeo-news.org" in full_text


def test_web_search_fallback_when_ddg_returns_empty(monkeypatch):
    monkeypatch.setattr(
        "src.features.tools.web_search.search_duckduckgo",
        lambda query, max_results, timeout: [],
    )
    monkeypatch.setattr(
        "src.features.tools.web_search.search_wikipedia",
        lambda query, max_results, timeout, **kwargs: [
            {
                "title": "Bataille de Changping",
                "url": "https://fr.wikipedia.org/wiki/Bataille_de_Changping",
                "snippet": "Affrontement majeur des Royaumes combattants opposant Qin et Zhao.",
            }
        ],
    )

    output = web_search("Bataille de Changping")
    assert "Bataille de Changping" in output
    assert "https://fr.wikipedia.org/wiki/Bataille_de_Changping" in output


def test_search_wikipedia_fallback_to_english(monkeypatch):
    calls: list[str] = []

    def mock_get(endpoint, params=None, headers=None):
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()

        if "fr.wikipedia.org" in endpoint:
            calls.append("fr")
            mock_resp.json.return_value = {"query": {"search": []}}
        else:
            calls.append("en")
            mock_resp.json.return_value = {
                "query": {
                    "search": [
                        {
                            "title": "Battle of Changping",
                            "snippet": "Decisive military campaign in ancient China.",
                        }
                    ]
                }
            }
        return mock_resp

    mock_client = MagicMock()
    mock_client.get.side_effect = mock_get
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = None

    monkeypatch.setattr(httpx, "Client", lambda **kwargs: mock_client)

    results = search_wikipedia("Battle of Changping", max_results=1, lang="fr")
    assert calls == ["fr", "en"]
    assert len(results) == 1
    assert results[0]["title"] == "Battle of Changping"
    assert "en.wikipedia.org" in results[0]["url"]


def test_parse_ddg_html_entities_and_div_snippet():
    html_with_entities = """
    <div class="result results_links">
      <h2 class="result__title">
        <a href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fhistory.com%2Fwarring-states&rut=1">
          L&apos;&Eacute;tat de Qin &amp; les 7 Royaumes &lt;Chine&gt;
        </a>
      </h2>
      <div class="result__snippet">
        D&eacute;couverte d&apos;arbal&egrave;tes et pointes de fl&egrave;ches en bronze.
      </div>
    </div>
    """
    results = parse_ddg_html(html_with_entities)
    assert len(results) == 1
    assert results[0]["title"] == "L'État de Qin & les 7 Royaumes <Chine>"
    assert "https://history.com/warring-states" == results[0]["url"]
    assert "Découverte d'arbalètes et pointes de flèches en bronze." in results[0]["snippet"]


def test_web_search_max_results_clamping(monkeypatch):
    captured_limits: list[int] = []

    def mock_ddg(query, max_results, timeout):
        captured_limits.append(max_results)
        return [{"title": "Royaume de Qin", "url": "https://example.com", "snippet": "Info"}]

    monkeypatch.setattr("src.features.tools.web_search.search_duckduckgo", mock_ddg)

    web_search("Qin", max_results=0)
    assert captured_limits[-1] == 1

    web_search("Qin", max_results=50)
    assert captured_limits[-1] == 10


def test_web_search_all_services_empty(monkeypatch):
    monkeypatch.setattr("src.features.tools.web_search.search_duckduckgo", lambda *args, **kwargs: [])
    monkeypatch.setattr("src.features.tools.web_search.search_wikipedia", lambda *args, **kwargs: [])

    output = web_search("terme_completement_inconnu_xyz123")
    assert "Aucun résultat trouvé sur le Web" in output
    assert "terme_completement_inconnu_xyz123" in output

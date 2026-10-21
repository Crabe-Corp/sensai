import html
import re
import urllib.parse
from typing import Any
import httpx
from src.features.tools.registry import tool

DEFAULT_TIMEOUT: float = 5.0
DEFAULT_MAX_RESULTS: int = 3
DDG_ENDPOINT: str = "https://html.duckduckgo.com/html/"
USER_AGENT_BROWSER: str = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
USER_AGENT_WIKIPEDIA: str = "SensaiBot/1.0 (https://epitech.eu; sensai@epitech.eu)"


def clean_ddg_url(raw_url: str) -> str:
    """Extrait et décode l'URL cible finale depuis les redirections DuckDuckGo.
            PARAMS: raw_url - STR: URL brute issue du code HTML.
            RETURN: STR: URL cible propre déchiffrée ou URL brute d'origine.
    """

    if not raw_url:
        return ""
    if raw_url.startswith("//"):
        raw_url = "https:" + raw_url
    elif raw_url.startswith("/l/?"):
        raw_url = "https://duckduckgo.com" + raw_url

    parsed = urllib.parse.urlparse(raw_url)
    if ("duckduckgo.com" in parsed.netloc or not parsed.netloc) and "uddg" in parsed.query:
        params = urllib.parse.parse_qs(parsed.query)
        if "uddg" in params and params["uddg"]:
            return urllib.parse.unquote(params["uddg"][0])
    return raw_url


def parse_ddg_html(html_content: str, max_results: int = DEFAULT_MAX_RESULTS) -> list[dict[str, str]]:
    """Parse les résultats de recherche dans le code HTML retourné par DuckDuckGo.
            PARAMS: - html_content - STR: Corps HTML retourné par DuckDuckGo.
                    - max_results - INT: Nombre maximal de résultats à extraire.
            RETURN: list[dict[str, str]]: Liste de dictionnaires contenant title, snippet et url.
    """
    results: list[dict[str, str]] = []
    pattern = re.compile(
        r'<h2 class="result__title">\s*<a[^>]+href="(?P<url>[^"]+)"[^>]*>(?P<title>.*?)</a>.*?'
        r'<(?:a|div)[^>]*class="[^"]*result__snippet[^"]*"[^>]*>(?P<snippet>.*?)</(?:a|div)>',
        re.DOTALL,
    )

    for match in pattern.finditer(html_content):
        raw_url = match.group("url")
        raw_title = match.group("title")
        raw_snippet = match.group("snippet")

        clean_title = html.unescape(re.sub(r"<[^>]+>", "", raw_title)).strip()
        clean_snippet = html.unescape(re.sub(r"<[^>]+>", "", raw_snippet)).strip()
        target_url = clean_ddg_url(raw_url)

        if clean_title and target_url:
            results.append({
                "title": clean_title,
                "snippet": clean_snippet,
                "url": target_url,
            })
            if len(results) >= max_results:
                break
    return results


def search_duckduckgo(
    query: str,
    max_results: int = DEFAULT_MAX_RESULTS,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[dict[str, str]]:
    """Effectue une recherche Web via DuckDuckGo HTML sans clé d'API.
        PARAMS: - query - STR: Termes de la recherche.
                - max_results - INT: Nombre maximal de résultats souhaités.
                - timeout - FLOAT: Délai d'expiration réseau en secondes.
        RETURN: list[dict[str, str]]: Liste de dictionnaires contenant title, snippet et url.
    """
    headers = {
        "User-Agent": USER_AGENT_BROWSER,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        response = client.post(DDG_ENDPOINT, data={"q": query}, headers=headers)
        response.raise_for_status()
        return parse_ddg_html(response.text, max_results=max_results)


def search_wikipedia(query: str, max_results: int = DEFAULT_MAX_RESULTS, timeout: float = DEFAULT_TIMEOUT, lang: str = "fr") -> list[dict[str, str]]:
    """Recherche encyclopédique de secours via l'API publique Wikipedia.
            PARAMS: - query - STR: Termes de la recherche.
                    - max_results - INT: Nombre maximal de résultats souhaités.
                    - timeout - FLOAT: Délai d'expiration réseau en secondes.
                    - lang - STR: Code langue de l'encyclopédie (ex: 'fr' ou 'en').
            RETURN: list[dict[str, str]]: Liste de dictionnaires contenant title, snippet et url.
    """

    endpoint = f"https://{lang}.wikipedia.org/w/api.php"
    params: dict[str, Any] = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "format": "json",
        "utf8": 1,
        "srlimit": max_results,
    }
    headers = {"User-Agent": USER_AGENT_WIKIPEDIA}

    with httpx.Client(timeout=timeout) as client:
        response = client.get(endpoint, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()

    results: list[dict[str, str]] = []
    items = data.get("query", {}).get("search", [])
    for item in items[:max_results]:
        title = item.get("title", "").strip()
        raw_snippet = item.get("snippet", "")
        clean_snippet = html.unescape(re.sub(r"<[^>]+>", "", raw_snippet)).strip()
        encoded_title = urllib.parse.quote(title.replace(" ", "_"))
        page_url = f"https://{lang}.wikipedia.org/wiki/{encoded_title}"

        if title:
            results.append({
                "title": title,
                "snippet": clean_snippet,
                "url": page_url,
            })

    if not results and lang != "en":
        return search_wikipedia(query, max_results=max_results, timeout=timeout, lang="en")
    return results

def format_search_results(query: str, results: list[dict[str, str]]) -> str:
    """Formate les résultats de recherche en texte clair et incitatif pour le LLM.
            PARAMS: - query - STR: Requête d'origine.
                    - results - LIST: Liste des sources extraites.
            RETURN: STR: Chaîne de caractères structurée contenant les sources et le rappel de citation d'URL.
    """

    if not results:
        return f"Aucun résultat trouvé sur le Web pour la recherche : \"{query}\"."
    lines = [f"Résultats de recherche Web pour \"{query}\" :\n"]
    for idx, item in enumerate(results, start=1):
        title = item.get("title", "Sans titre").strip()
        url = item.get("url", "").strip()
        snippet = item.get("snippet", "").strip()
        lines.append(f"[{idx}] {title}")
        if url:
            lines.append(f"URL : {url}")
        if snippet:
            lines.append(f"Extrait : {snippet}")
        lines.append("")
    lines.append("(Instruction : Mentionne et cite expressément les URLs sources pertinentes dans ta réponse finale si tu utilises ces informations.)")
    return "\n".join(lines).strip()

@tool
def web_search(query: str, max_results: int = DEFAULT_MAX_RESULTS) -> str:
    """Recherche des informations sur le Web en direct et extrait les sources avec titres, résumés et URLs.
            PARAMS: - query - STR: Termes ou question de recherche sur le Web.
                    - max_results - INT: Nombre maximal de résultats souhaités.
            RETURN: STR: Synthèse textuelle formatée des sources trouvées invitant à citer les URLs, ou message d'erreur informatif.
    """

    cleaned_query = (query or "").strip()
    if not cleaned_query:
        return "Requête de recherche vide : veuillez spécifier des termes de recherche."
    limit = max(1, min(max_results, 10))
    errors: list[str] = []
    results: list[dict[str, str]] = []
    try:
        results = search_duckduckgo(cleaned_query, max_results=limit, timeout=DEFAULT_TIMEOUT)
    except (httpx.TimeoutException, TimeoutError) as exc:
        errors.append(f"Délai d'attente DuckDuckGo dépassé ({exc})")
    except Exception as exc:
        errors.append(f"Échec DuckDuckGo ({type(exc).__name__}: {exc})")
    if not results:
        try:
            results = search_wikipedia(cleaned_query, max_results=limit, timeout=DEFAULT_TIMEOUT)
        except (httpx.TimeoutException, TimeoutError) as exc:
            errors.append(f"Délai d'attente Wikipedia dépassé ({exc})")
        except Exception as exc:
            errors.append(f"Échec Wikipedia ({type(exc).__name__}: {exc})")
    if results:
        return format_search_results(cleaned_query, results)
    if errors:
        return (
            f"Erreur lors de la recherche Web pour \"{cleaned_query}\" : "
            f"services réseau inaccessibles ({'; '.join(errors)})."
        )
    return f"Aucun résultat trouvé sur le Web pour la recherche : \"{cleaned_query}\"."

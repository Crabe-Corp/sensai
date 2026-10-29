from typing import Any
from src.core import singleton_token
from src.core.debug import debug_print


def consume_tokens(amount: int, is_context: bool = False) -> None:
    """Incrémente le budget avec uniquement les NOUVEAUX tokens réels."""
    if is_context:
        nouveaux_tokens = amount - singleton_token.context_tokens
        if nouveaux_tokens > 0:
            singleton_token.budget_tokens += nouveaux_tokens
        singleton_token.context_tokens = amount
    else:
        singleton_token.budget_tokens += amount


consommer_tokens = consume_tokens


def update_context_tokens(amount: int) -> None:
    """Met à jour le nombre de tokens actifs dans la fenêtre de contexte de conversation courante.
            PARAMS: - amount - INT: nouveau compte de tokens de contexte (métrique Ollama)
            RETURN: None"""
    singleton_token.context_tokens = amount


def enforce_token_budget(
    model: str,
    client: Any,
    messages: list[Any],
    max_history_tokens: int = 2000,
) -> list[Any]:
    """Compresse sémantiquement l'historique de conversation lorsque le budget de tokens est dépassé.
            PARAMS: - model - STR: nom du modèle Ollama à invoquer pour le résumé
                    - client - ANY: client HTTP Ollama
                    - messages - LIST: historique courant des messages
                    - max_history_tokens - INT: seuil limite de déclenchement de la compression
            RETURN: liste des messages compressés ou inchangés"""

    if singleton_token.context_tokens <= max_history_tokens:
        return messages

    if len(messages) < 4:
        return messages

    debug_print(f"[Memory] Context token limit exceeded ({singleton_token.context_tokens}/{max_history_tokens}). Compressing history...")

    prompt_systeme = messages[0]
    messages_recents = messages[-2:]
    messages_a_compresser = messages[1:-2]

    if not messages_a_compresser:
        return messages

    texte_brut = "\n".join(
        [f"{getattr(m, 'role', 'user').upper()}: {getattr(m, 'content', '')}" for m in messages_a_compresser]
    )

    resume_prompt = (
        "You are a compression algorithm. Summarize this conversation "
        "keeping only key information, names, and facts. "
        f"Be ultra-concise.\n\nConversation:\n{texte_brut}"
    )

    from src.core.ollama_client import ChatMessage

    msg_prompt = ChatMessage(role="assistant", content=resume_prompt)

    try:
        raw_res = client.call_model(model, [msg_prompt])
        if isinstance(raw_res, dict):
            summary_text = raw_res.get("message", {}).get("content", str(raw_res)).strip()
        else:
            summary_text = str(raw_res).strip()
    except Exception:
        summary_text = f"Previous conversation summarized ({len(messages_a_compresser)} messages compressed)."

    msg_resume = ChatMessage(role="system", content=f"Summary of previous exchanges: {summary_text}")
    singleton_token.historique_compresse = True
    singleton_token.context_tokens = 0

    return [
        prompt_systeme,
        msg_resume,
        *messages_recents,
    ]

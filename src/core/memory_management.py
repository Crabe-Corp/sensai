from typing import Any
from src.core import singleton_token


def consommer_tokens(montant: int) -> None:
    """Incrémente le compteur de tokens consommés.
            PARAMS: - montant - INT: quantité de tokens consommés par l'appel
            RETURN: None"""

    singleton_token.budget_tokens += montant


def enforce_token_budget(model: str, client: Any, messages: list[Any], max_history_tokens: int = 2000,) -> list[Any]:
    """Compresse sémantiquement l'historique de conversation lorsque le budget de tokens est dépassé.
            PARAMS: - model - STR: nom du modèle Ollama à invoquer pour le résumé
                    - client - ANY: client HTTP Ollama
                    - messages - LIST: historique courant des messages
                    - max_history_tokens - INT: seuil limite de déclenchement de la compression
            RETURN: liste des messages compressés ou inchangés"""

    if singleton_token.budget_tokens <= max_history_tokens:
        return messages

    if len(messages) < 4:
        return messages

    print(f"[Mémoire] Budget dépassé ({singleton_token.budget_tokens}/{max_history_tokens}). Compression en cours...")

    prompt_systeme = messages[0]
    messages_recents = messages[-2:]
    messages_a_compresser = messages[1:-2]

    if not messages_a_compresser:
        return messages

    texte_brut = "\n".join(
        [f"{getattr(m, 'role', 'user').upper()}: {getattr(m, 'content', '')}" for m in messages_a_compresser]
    )

    resume_prompt = (
        "Tu es un algorithme de compression. Résume cette conversation "
        "en gardant uniquement les informations clés, les noms et les faits. "
        f"Sois ultra-concis.\n\nConversation:\n{texte_brut}"
    )

    from src.core.ollama_client import ChatMessage

    msg_prompt = ChatMessage(role="agent", content=resume_prompt)

    try:
        raw_res = client.call_model(model, [msg_prompt])
        if isinstance(raw_res, dict):
            summary_text = raw_res.get("message", {}).get("content", str(raw_res)).strip()
        else:
            summary_text = str(raw_res).strip()
    except Exception:
        summary_text = f"Échanges historiques précédents résumés ({len(messages_a_compresser)} messages compressés)."

    msg_resume = ChatMessage(role="system", content=f"Résumé des anciens échanges : {summary_text}")
    singleton_token.historique_compresse = True
    singleton_token.budget_tokens = max(0, singleton_token.budget_tokens // 2)

    return [
        prompt_systeme,
        msg_resume,
        *messages_recents,
    ]
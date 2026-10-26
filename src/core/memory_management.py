from typing import Any
from src.core import singleton_token
from src.core.debug import debug_print


def consume_tokens(amount: int) -> None:
    """Increment consumed tokens counter.
            PARAMS: - amount - INT: quantity of tokens consumed by the call
            RETURN: None"""
    singleton_token.budget_tokens = amount


consommer_tokens = consume_tokens


def enforce_token_budget(
    model: str,
    client: Any,
    messages: list[Any],
    max_history_tokens: int = 2000,
) -> list[Any]:
    """Compress conversation history semantically when token budget is exceeded.
            PARAMS: - model - STR: Ollama model name to summarize history
                    - client - ANY: Ollama HTTP client
                    - messages - LIST: current message history
                    - max_history_tokens - INT: threshold to trigger compression
            RETURN: list of compressed or unchanged messages"""

    if singleton_token.budget_tokens <= max_history_tokens:
        return messages

    if len(messages) < 4:
        return messages

    debug_print(f"[Memory] Token budget exceeded ({singleton_token.budget_tokens}/{max_history_tokens}). Compressing history...")

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

    msg_prompt = ChatMessage(role="agent", content=resume_prompt)

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
    singleton_token.budget_tokens = max(0, singleton_token.budget_tokens // 2)

    return [
        prompt_systeme,
        msg_resume,
        *messages_recents,
    ]

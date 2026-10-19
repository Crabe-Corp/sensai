from src.core import singleton_token

def consommer_tokens(montant):
    singleton_token.budget_tokens += montant
    print(f"Tokens actuels : {singleton_token.budget_tokens}")

def enforce_token_budget(model: str, client, messages: list, max_history_tokens=2000) -> list:
    from src.core.ollama_client import OllamaClient

    if singleton_token.budget_tokens <= max_history_tokens:
        return messages
        
    print(f"[Mémoire] Budget dépassé ({singleton_token.budget_tokens}/{max_history_tokens}). Compression en cours...")
    
    prompt_systeme = messages[0] # the banner
    messages_recents = messages[-2:] # all the messages except the two last
    messages_a_compresser = messages[1:-2] # all the messages to compress

    texte_brut = "\n".join([f"{m.role.upper()}: {m.content}" for m in messages_a_compresser])

    resume_prompt = (
        "Tu es un algorithme de compression. Résume cette conversation "
        "en gardant uniquement les informations clés, les noms et les faits. "
        f"Sois ultra-concis.\n\nConversation:\n{texte_brut}"
    )

    ChatMessage = type(messages[0])

    msg_prompt = ChatMessage(role="user", content=resume_prompt)
    resume_genere = client.call_model(model, [msg_prompt])

    msg_resume = ChatMessage(role="system", content=f"Résumé des anciens échanges : {resume_genere}")
    
    nouvel_historique = [
        prompt_systeme,
        msg_resume,
        *messages_recents
    ]
    
    return nouvel_historique
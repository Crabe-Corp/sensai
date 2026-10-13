from src.core.ollama_client import OllamaClient

def estimate_tokens(text: str) -> int:
    # Estimation du nombre de token utiliser
    return len(text) // 4

def enforce_token_budget(model: str, client: OllamaClient, messages: list[dict], max_history_tokens=2000) -> list[dict]:

    total_tokens = sum(estimate_tokens(m["content"]) for m in messages)

    if total_tokens <= max_history_tokens:
        return messages
        
    print(f"[Mémoire] Budget dépassé ({total_tokens}/{max_history_tokens}). Compression en cours...")
    
    prompt_systeme = messages[0] # the banner
    messages_recents = messages[-2:] # all the message exept the two last
    messages_a_compresser = messages[1:-2] # all the message to compress EX : [banner, compress, compress, compress, recent, prompt]

    print(messages_a_compresser)
    # texte_brut = "\n".join([f"{m['role'].upper()}: {m['content']}" for m in messages_a_compresser])
    
    # 5. Faire un appel HTTP synchrone à Ollama pour résumer
    # resume_prompt = (
    #     "Tu es un algorithme de compression. Résume cette conversation "
    #     "en gardant uniquement les informations clés, les noms et les faits. "
    #     f"Sois ultra-concis.\n\nConversation:\n{texte_brut}"
    # )
    
    # resume_genere = client.call_model(model, resume_prompt)
    
    # nouvel_historique = [
    #     prompt_systeme,
    #     {"role": "system", "content": f"Résumé des anciens échanges : {resume_genere}"},
    #     *messages_recents
    # ]
    
    # return nouvel_historique
    return 0
import re
from typing import Tuple
from pydantic import BaseModel, Field
from src.core.debug import debug_print
from src.core.ollama_client import OllamaClient, ChatMessage

class SecurityDecision(BaseModel):
    is_valid: bool = Field(
        description="True if the message is about history OR if it is a generic search request without a specific topic (e.g., “search the internet,” “more info about him”). False ONLY if an explicitly modern topic (games, cooking) or insults are mentioned."
    )

def mask_pii(text: str) -> Tuple[str, bool]:
    """Remplace les informations personnelles identifiables (emails, téléphones) par un masque.
            PARAMS: - text - STR: texte source potentiellement sensible
            RETURN: tuple contenant le texte anonymisé et un booléen indiquant la présence de PII"""

    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    phone_pattern = r'(?:(?:\+|00)33[\s.-]{0,3}(?:\(0\)[\s.-]{0,3})?|0)[1-9](?:(?:[\s.-]?\d{2}){4}|\d{2}(?:[\s.-]?\d{3}){2})'
    
    has_confidential_data = bool(re.search(email_pattern, text) or re.search(phone_pattern, text))
    
    masked = re.sub(email_pattern, '[DONNÉE MASQUÉE]', text)
    masked = re.sub(phone_pattern, '[DONNÉE MASQUÉE]', masked)
    
    return masked, has_confidential_data

def validate_input_with_llm(text: str, client: OllamaClient, model: str) -> Tuple[bool, str]:
    """Évalue si la requête masquée reste dans le thème historique avec des exemples (Few-Shot).
            PARAMS: - text - STR: message utilisateur nettoyé à valider
                    - client - OLLAMACLIENT: instance active du client Ollama
                    - model - STR: nom du modèle Ollama utilisé pour la classification
            RETURN: tuple contenant le booléen d'autorisation et le message de refus éventuel"""

    system_prompt = (
        "You are a security classifier. You must determine if the user message is authorized.\n\n"
        "AUTHORIZATION RULES (is_valid: true):\n"
        "- The message is about Ancient China, the Warring States period, or historical topics.\n"
        "- The message is a generic search request involving pronouns (e.g. 'about him', 'about them', 'can you search'). Since you do not have conversation history, you MUST allow these generic requests by default.\n\n"
        "REJECTION RULES (is_valid: false):\n"
        "- The message EXPLICITLY mentions modern topics (video games, cooking recipes, modern technology).\n"
        "- The message contains abuse or insults.\n\n"
        "Classification examples:\n"
        "Message: 'Quels étaient les 7 royaumes combattants ?'\n-> is_valid: true\n\n"
        "Message: 'What were the 7 warring states?'\n-> is_valid: true\n\n"
        "Message: 'Can you search more info about him on the internet?'\n-> is_valid: true\n\n"
        "Message: 'Peux-tu faire de plus amples recherches à son sujet sur internet ?'\n-> is_valid: true\n\n"
        "Message: 'Donne moi une recette de pizza.'\n-> is_valid: false\n\n"
        "Message: 'Search internet for Fortnite.'\n-> is_valid: false"
    )
    
    messages = [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content=text),
    ]
    
    try:
        decision = client.chat_structured(
            model=model,
            messages=messages,
            response_format=SecurityDecision
        )
        
        debug_print(f"[Debug] Security decision: {decision.is_valid}")
        
        if not decision.is_valid:
            return False, "The imperial advisor refuses to discuss this topic with you."
            
        return True, ""
    except Exception:
        return True, ""
import re
from typing import Tuple
from pydantic import BaseModel, Field
from src.core.ollama_client import OllamaClient, ChatMessage

class SecurityDecision(BaseModel):
    is_valid: bool = Field(
        description="True si le message concerne l'époque des sept Royaumes Combattants, la Chine antique ou l'unification de la Chine. False si le message est hors-sujet, moderne, ou insultant."
    )

def mask_pii(text: str) -> Tuple[str, bool]:
    """Remplace les emails et numéros de téléphone par [DONNÉE MASQUÉE]."""
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    phone_pattern = r'(?:(?:\+|00)33[\s.-]{0,3}(?:\(0\)[\s.-]{0,3})?|0)[1-9](?:(?:[\s.-]?\d{2}){4}|\d{2}(?:[\s.-]?\d{3}){2})'
    
    has_confidential_data = bool(re.search(email_pattern, text) or re.search(phone_pattern, text))
    
    masked = re.sub(email_pattern, '[DONNÉE MASQUÉE]', text)
    masked = re.sub(phone_pattern, '[DONNÉE MASQUÉE]', masked)
    
    return masked, has_confidential_data

def validate_input_with_llm(text: str, client: OllamaClient, model: str) -> Tuple[bool, str]:
    """
    Évalue si la requête masquée reste dans le thème historique avec des exemples (Few-Shot).
    """
    system_prompt = (
        "Tu es un classifieur de sécurité. Tu dois déterminer si le message est dans le thème "
        "(Chine antique, Royaumes Combattants, histoire de l'unification de la Chine, salutations basiques) ou s'il est "
        "hors-sujet (technologie, jeux vidéos, époque moderne, insultes).\n\n"
        "Exemples de classification :\n"
        "Message : 'Quels étaient les 7 royaumes combattants ?'\n-> is_valid: true\n\n"
        "Message : 'Qui a unifié la Chine ?'\n-> is_valid: true\n\n"
        "Message : 'Donne moi une recette de pizza.'\n-> is_valid: false\n\n"
        "Message : 'T'es un gros abruti.'\n-> is_valid: false\n\n"
        "Message : 'Bonjour, voici mon email [DONNÉE MASQUÉE]. Parle-moi de Qin Shi Huang.'\n-> is_valid: true\n\n"
        "Message : 'Joue à Hollow Knight.'\n-> is_valid: false"
    )
    
    messages = [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content=text)
    ]
    
    decision = client.chat_structured(
        model=model,
        messages=messages,
        response_format=SecurityDecision
    )

    if not decision.is_valid:
        return False, "Le conseiller impérial refuse de s'abaisser à discuter de ce sujet avec vous."
           
    return True, ""
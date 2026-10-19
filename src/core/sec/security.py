import re
from typing import Tuple
from pydantic import BaseModel, Field
from src.core.ollama_client import OllamaClient, ChatMessage

class SecurityDecision(BaseModel):
    is_valid: bool = Field(
        description="True si le message concerne l'histoire OU s'il s'agit d'une demande de recherche générique sans sujet précis (ex: 'cherche sur internet', 'plus d'infos sur lui'). False UNIQUEMENT si un sujet explicitement moderne (jeux, cuisine) ou des insultes sont mentionnés."
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
        "Tu es un classifieur de sécurité. Tu dois déterminer si le message est autorisé.\n\n"
        "RÈGLES D'AUTORISATION (is_valid: true) :\n"
        "- Le message parle de la Chine antique, des Royaumes Combattants, ou d'histoire.\n"
        "- Le message est une demande générique de recherche sur internet impliquant des pronoms (ex: 'à son sujet', 'sur eux', 'peux-tu chercher'). Étant donné que tu n'as pas l'historique, tu DOIS autoriser ces demandes par défaut.\n\n"
        "RÈGLES DE REJET (is_valid: false) :\n"
        "- Le message mentionne EXPLICITEMENT un sujet moderne (jeux vidéos, cuisine, technologie moderne).\n"
        "- Le message contient des insultes.\n\n"
        "Exemples de classification :\n"
        "Message : 'Quels étaient les 7 royaumes combattants ?'\n-> is_valid: true\n\n"
        "Message : 'Peux-tu faire de plus amples recherches à son sujet sur internet ?'\n-> is_valid: true\n\n"
        "Message : 'Est-ce que tu peux me trouver plus d'informations à leur sujet sur internet ?'\n-> is_valid: true\n\n"
        "Message : 'Donne moi une recette de pizza.'\n-> is_valid: false\n\n"
        "Message : 'Cherche sur internet des informations sur Fortnite.'\n-> is_valid: false"
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
        
        print(f"\ndebug decision de réponse : {decision.is_valid}")
        
        if not decision.is_valid:
            return False, "Le conseiller impérial refuse de s'abaisser à discuter de ce sujet avec vous."
            
        return True, ""
    except Exception:
        return True, ""
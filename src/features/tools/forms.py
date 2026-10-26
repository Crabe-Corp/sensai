import json
import re
import unicodedata
from typing import Any

from src.features.tools.registry import tool

MAX_QUESTIONS = 10
QUESTION_TYPES = ("text", "number", "boolean", "choice")
_TYPE_ALIASES = {
    "string": "text",
    "textarea": "text",
    "int": "number",
    "integer": "number",
    "float": "number",
    "bool": "boolean",
    "yesno": "boolean",
    "select": "choice",
    "radio": "choice",
    "enum": "choice",
}
_YES = {"o", "oui", "y", "yes", "true", "1"}
_NO = {"n", "non", "no", "false", "0"}


def _slugify(text: str) -> str:
    """Transforme un libellé en identifiant simple utilisable comme clé de formulaire.
            PARAMS: - text - STR: libellé de la question
            RETURN: identifiant en minuscules sans caractères spéciaux"""

    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "_", ascii_text.lower()).strip("_")


def normalize_form(title: Any, questions: Any) -> dict[str, Any]:
    """Valide et normalise la description d'un formulaire fournie par le modèle.
            PARAMS: - title - ANY: titre du formulaire
                    - questions - ANY: liste (ou chaîne JSON) de questions à poser
            RETURN: dictionnaire {title, questions} normalisé, ou ValueError si la description est invalide"""

    if isinstance(questions, str):
        try:
            questions = json.loads(questions)
        except json.JSONDecodeError as exc:
            raise ValueError(f"'questions' doit être une liste de questions : {exc}") from exc
    if isinstance(questions, dict):
        questions = [questions]
    if not isinstance(questions, list) or not questions:
        raise ValueError("'questions' doit être une liste non vide de questions.")
    if len(questions) > MAX_QUESTIONS:
        raise ValueError(f"Trop de questions ({len(questions)}) : {MAX_QUESTIONS} maximum.")

    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(questions, start=1):
        if isinstance(raw, str):
            raw = {"label": raw}
        if not isinstance(raw, dict):
            raise ValueError(f"La question {index} doit être un objet avec au moins un 'label'.")

        label = str(raw.get("label") or raw.get("question") or "").strip()
        if not label:
            raise ValueError(f"La question {index} n'a pas de 'label'.")

        q_type = str(raw.get("type") or "text").strip().lower()
        q_type = _TYPE_ALIASES.get(q_type, q_type)
        if q_type not in QUESTION_TYPES:
            raise ValueError(f"Type '{q_type}' inconnu (attendu : {', '.join(QUESTION_TYPES)}).")

        q_id = _slugify(str(raw.get("id") or "")) or _slugify(label) or f"q{index}"
        while q_id in seen_ids:
            q_id = f"{q_id}_{index}"
        seen_ids.add(q_id)

        question: dict[str, Any] = {
            "id": q_id,
            "label": label,
            "type": q_type,
            "required": bool(raw.get("required", True)),
        }
        if q_type == "choice":
            options = raw.get("options")
            if not isinstance(options, list) or len([o for o in options if str(o).strip()]) < 2:
                raise ValueError(f"La question '{label}' de type 'choice' demande au moins 2 'options'.")
            question["options"] = [str(o).strip() for o in options if str(o).strip()]
        normalized.append(question)

    return {
        "title": str(title or "").strip() or "Informations requises",
        "questions": normalized,
    }


def _ask_question(question: dict[str, Any]) -> Any:
    """Pose une question dans le terminal et retourne la réponse typée.
            PARAMS: - question - DICT: question normalisée du formulaire
            RETURN: valeur saisie (STR, nombre ou booléen), ou None si la question facultative est ignorée"""

    label = question["label"] + ("" if question["required"] else " (facultatif)")
    q_type = question["type"]
    options = question.get("options", [])

    print(f"\n  {label}")
    if q_type == "choice":
        for number, option in enumerate(options, start=1):
            print(f"    {number}) {option}")
    elif q_type == "boolean":
        print("    (o/n)")

    while True:
        raw = input("  > ").strip()
        if not raw:
            if question["required"]:
                print("  [Réponse obligatoire]")
                continue
            return None
        if q_type == "text":
            return raw
        if q_type == "number":
            try:
                number_value = float(raw.replace(",", "."))
                return int(number_value) if number_value.is_integer() else number_value
            except ValueError:
                print("  [Veuillez saisir un nombre]")
                continue
        if q_type == "boolean":
            if raw.lower() in _YES:
                return True
            if raw.lower() in _NO:
                return False
            print("  [Répondez par o ou n]")
            continue
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1]
        if raw in options:
            return raw
        print(f"  [Choisissez un numéro entre 1 et {len(options)}]")


@tool
def ask_user_form(title: str, questions: list[dict]) -> dict[str, Any]:
    """Pose des questions à l'utilisateur sous forme de formulaire interactif pour collecter des données manquantes, au lieu de les deviner.
            PARAMS: - title - STR: titre court du formulaire
                    - questions - LIST: liste de questions, chacune étant un objet avec label (texte affiché), type (text, number, boolean ou choice), options (liste, obligatoire pour choice), required (booléen) et id (optionnel)
            RETURN: dictionnaire avec le statut answered et les réponses par identifiant de question, ou cancelled si l'utilisateur annule"""

    try:
        form = normalize_form(title, questions)
    except ValueError as exc:
        return {"status": "error", "message": str(exc)}

    print(f"\n[Formulaire] {form['title']}")
    answers: dict[str, Any] = {}
    try:
        for question in form["questions"]:
            answers[question["id"]] = _ask_question(question)
    except (KeyboardInterrupt, EOFError):
        print("\n[Système] Formulaire annulé.")
        return {"status": "cancelled"}
    return {"status": "answered", "answers": answers}

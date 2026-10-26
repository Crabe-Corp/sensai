from collections.abc import Iterator
from typing import Any
from pydantic import BaseModel, Field


class EvaluationJuge(BaseModel):
    justification: str = Field(
        ...,
        description="Analyse factuelle et équitable : lis attentivement la réponse et vérifie ce qu'elle contient réellement avant de juger",
    )
    note_pertinence: int = Field(
        ...,
        ge=1,
        le=5,
        description="Note de 1 à 5 : 5=excellent, 4=bon, 3=passable/satisfaisant, 2=insuffisant, 1=inacceptable",
    )
    a_hallucine: bool = Field(
        ...,
        description="True UNIQUEMENT si l'IA invente des faits manifestement faux ou imaginaires, False si elle reste factuellement juste",
    )


def evaluer_reponse_ia(
    client: Any,
    model: str,
    question_user: Any,
    rag_context: str | None,
    reponse_assistant: str,
    judge_model: str | None = None,
) -> EvaluationJuge | None:
    """Évalue la qualité et la conformité d'une réponse IA via un juge LLM impartial et mesuré.
            PARAMS: - client - ANY: instance du client Ollama
                    - model - STR: nom du modèle courant utilisé pour l'évaluation
                    - question_user - ANY: question de l'utilisateur (str ou ChatMessage)
                    - rag_context - STR | NONE: contexte documentaire RAG injecté
                    - reponse_assistant - STR: réponse textuelle générée par l'IA
                    - judge_model - STR | NONE: modèle dédié au juge (qwen2.5:3b par défaut)
            RETURN: instance EvaluationJuge contenant la note et le verdict, ou None en cas d'échec"""

    question_text = question_user.content if hasattr(question_user, "content") else str(question_user)

    prompt_juge = (
        f"Tu es un juge impartial, équitable et mesuré, chargé d'évaluer la qualité d'une réponse IA.\n\n"
        f"--- CONTEXTE SOURCE ---\n{rag_context or 'Aucun document RAG fourni.'}\n\n"
        f"--- QUESTION DE L'UTILISATEUR ---\n{question_text}\n\n"
        f"--- RÉPONSE DE L'IA À ÉVALUER ---\n{reponse_assistant}\n\n"
        f"--- DIRECTIVES D'ÉVALUATION ÉQUITABLE ---\n"
        f"1. LECTURE ATTENTIVE : Lis l'intégralité de la réponse. Vérifie précisément les éléments qui y sont mentionnés. Ne prétends JAMAIS qu'un élément est absent s'il est cité dans le texte (par exemple si les noms des royaumes ou personnages y figurent).\n"
        f"2. MESURE ET ÉQUITÉ : Ne sois pas excessivement sévère. Si la réponse apporte les faits essentiels demandés de manière juste et utile, attribue une note convenable (au moins 3 ou 4/5), même si elle commence par une formule prudente ou si elle est synthétique.\n"
        f"3. DÉFINITION DE L'HALLUCINATION (a_hallucine) :\n"
        f"   - a_hallucine = True : UNIQUEMENT si l'IA affirme des faits historiques inventés, faux ou fantaisistes (ex: inventer un royaume ou un faux souverain).\n"
        f"   - a_hallucine = False : si l'IA énonce des faits historiques réels (ex: les 7 royaumes Qin, Chu, Qi, Yan, Han, Wei, Zhao) ou résume le contexte, même si certains faits généraux dépassent le strict extrait fourni.\n"
        f"4. BARÈME DE NOTATION (note_pertinence) :\n"
        f"   - 5/5 : Excellente réponse, riche et exacte.\n"
        f"   - 4/5 : Bonne réponse, factuelle et répondant bien à la demande.\n"
        f"   - 3/5 : Réponse satisfaisante ou passable, fournissant les éléments utiles sans erreur majeure.\n"
        f"   - 2/5 : Réponse insuffisante ou passant à côté de l'essentiel.\n"
        f"   - 1/5 : Réponse totalement fausse, hors-sujet ou inventée.\n\n"
        f"Remplis le formulaire en détaillant d'abord ton analyse dans 'justification', puis en attribuant la note et le booléen d'hallucination."
    )

    messages = [{"role": "user", "content": prompt_juge}]
    target_judge = judge_model or "qwen2.5:3b"

    try:
        from src.features.structured_output import chat_structured_flow

        try:
            resultat_eval = chat_structured_flow(
                client_chat_fn=client.chat,
                model=target_judge,
                messages=messages,
                response_format=EvaluationJuge,
                max_retries=1,
            )
        except Exception as judge_exc:
            if target_judge != model and "not found" in str(judge_exc).lower():
                resultat_eval = chat_structured_flow(
                    client_chat_fn=client.chat,
                    model=model,
                    messages=messages,
                    response_format=EvaluationJuge,
                    max_retries=1,
                )
            else:
                raise judge_exc

        print("\n--- RAPPORT D'ÉVALUATION EN COULISSES ---")
        print(f"Note Pertinence : {resultat_eval.note_pertinence}/5")
        print(f"Hallucination   : {'OUI' if resultat_eval.a_hallucine else 'NON'}")
        print(f"Justification   : {resultat_eval.justification}")
        print("--------------------------------------------\n")

        return resultat_eval

    except Exception as e:
        print(f"[Erreur Évaluation] Le juge n'a pas pu noter la réponse : {e}")
        return None


def interprete_result(
    grade_or_eval: EvaluationJuge | int | None = None,
    halucination: bool | None = None,
    seuil_min: int = 3,
) -> bool:
    """Détermine si la réponse générée nécessite d'être retravaillée.
            PARAMS: - grade_or_eval - EVALUATIONJUGE | INT | NONE: résultat d'évaluation ou note entière
                    - halucination - BOOL | NONE: présence d'hallucination si note entière fournie
                    - seuil_min - INT: note minimale acceptable (défaut: 3)
            RETURN: booléen True si note < seuil_min ou hallucination présente, False sinon"""

    if grade_or_eval is None:
        return False

    if isinstance(grade_or_eval, EvaluationJuge):
        return grade_or_eval.note_pertinence < seuil_min or bool(grade_or_eval.a_hallucine)

    grade = int(grade_or_eval)
    return grade < seuil_min or bool(halucination)


doit_retravailler = interprete_result


def construire_prompt_retravail(
    question_user: Any,
    rag_context: str | None,
    reponse_assistant: str,
    evaluation: EvaluationJuge,
) -> str:
    """Construit le prompt de reprise avec les remarques et corrections du juge.
            PARAMS: - question_user - ANY: question de l'utilisateur
                    - rag_context - STR | NONE: contexte documentaire RAG ou None
                    - reponse_assistant - STR: réponse initiale rejetée
                    - evaluation - EVALUATIONJUGE: évaluation du juge ayant motivé le rejet
            RETURN: prompt textuel complet guidant le modèle vers une version corrigée"""

    question_text = question_user.content if hasattr(question_user, "content") else str(question_user)

    prompt = (
        "Tu es un expert de la Chine Antique et des 7 Royaumes Combattants. Ta précédente réponse a été évaluée et doit être améliorée.\n\n"
        f"--- QUESTION DU SEIGNEUR ---\n{question_text}\n\n"
    )

    if rag_context:
        prompt += (
            f"--- DOCUMENTS HISTORIQUES DE RÉFÉRENCE ---\n{rag_context}\n\n"
            "INSTRUCTIONS DE CONFORMITÉ HISTORIQUE :\n"
            "1. BASE DE RÉPONSE : Appuie-toi sur les documents historiques pour répondre avec précision.\n"
            "2. CLARTÉ : Ne dis JAMAIS 'Mes chroniques ne mentionnent pas cette information' si tu apportes des informations utiles dans ta réponse.\n"
            "3. ANTI-CONFUSION : Reste rigoureusement fidèle aux faits, aux noms et aux royaumes.\n\n"
        )

    prompt += (
        f"--- RÉPONSE PRÉCÉDENTE (REJETÉE) ---\n{reponse_assistant}\n\n"
        f"--- RAPPORT DU CRITIQUE / JUGE ---\n"
        f"- Note de pertinence : {evaluation.note_pertinence}/5 (requis: >= 3)\n"
        f"- Hallucination détectée : {'OUI' if evaluation.a_hallucine else 'NON'}\n"
        f"- Justification du rejet : {evaluation.justification}\n\n"
        f"--- INSTRUCTIONS DE CORRECTION ---\n"
        "Rédige une NOUVELLE réponse corrigée, factuelle et complète.\n"
        "- Corrige impérativement tous les défauts relevés par le juge ci-dessus.\n"
        "- Réponds directement et clairement au Seigneur dans la même langue que la question posée.\n"
        "- Ne fais AUCUN méta-commentaire (pas de 'Voici la correction :')."
    )

    return prompt


def retravailler_reponse_stream(
    client: Any,
    model: str,
    question_user: Any,
    rag_context: str | None,
    reponse_assistant: str,
    evaluation: EvaluationJuge,
    system_prompt: str | None = None,
) -> Iterator[str]:
    """Régénère une réponse corrigée en streaming token par token.
            PARAMS: - client - ANY: instance du client Ollama
                    - model - STR: nom du modèle à interroger
                    - question_user - ANY: question de l'utilisateur
                    - rag_context - STR | NONE: contexte RAG ou None
                    - reponse_assistant - STR: réponse initiale rejetée
                    - evaluation - EVALUATIONJUGE: rapport du juge
                    - system_prompt - STR | NONE: message système optionnel
            RETURN: itérateur de tokens générés"""

    prompt = construire_prompt_retravail(
        question_user=question_user,
        rag_context=rag_context,
        reponse_assistant=reponse_assistant,
        evaluation=evaluation,
    )
    messages: list[dict[str, Any]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    yield from client.chat_stream(model=model, messages=messages)


def retravailler_reponse(
    client: Any,
    model: str,
    question_user: Any,
    rag_context: str | None,
    reponse_assistant: str,
    evaluation: EvaluationJuge,
    system_prompt: str | None = None,
) -> str:
    """Régénère une réponse corrigée de façon synchrone.
            PARAMS: - client - ANY: instance du client Ollama
                    - model - STR: nom du modèle à interroger
                    - question_user - ANY: question de l'utilisateur
                    - rag_context - STR | NONE: contexte RAG ou None
                    - reponse_assistant - STR: réponse initiale rejetée
                    - evaluation - EVALUATIONJUGE: rapport du juge
                    - system_prompt - STR | NONE: message système optionnel
            RETURN: réponse textuelle finale corrigée"""

    prompt = construire_prompt_retravail(
        question_user=question_user,
        rag_context=rag_context,
        reponse_assistant=reponse_assistant,
        evaluation=evaluation,
    )
    messages: list[dict[str, Any]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    data = client.chat(model=model, messages=messages)
    return data.get("message", {}).get("content", "").strip()


def retravailler_reponse_structuree(client: Any, model: str, question_user: Any,
    rag_context: str | None,
    reponse_assistant: str,
    evaluation: EvaluationJuge,
    response_format: type[Any],
) -> Any:
    """Régénère une réponse structurée Pydantic corrigée d'après l'évaluation.
            PARAMS: - client - ANY: instance du client Ollama
                    - model - STR: nom du modèle à interroger
                    - question_user - ANY: question de l'utilisateur
                    - rag_context - STR | NONE: contexte RAG ou None
                    - reponse_assistant - STR: réponse initiale rejetée
                    - evaluation - EVALUATIONJUGE: rapport du juge
                    - response_format - TYPE: modèle Pydantic attendu
            RETURN: instance validée de response_format"""

    prompt = construire_prompt_retravail(
        question_user=question_user,
        rag_context=rag_context,
        reponse_assistant=reponse_assistant,
        evaluation=evaluation,
    )
    return client.chat_structured(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        response_format=response_format,
    )

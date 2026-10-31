from collections.abc import Iterator
from typing import Any
from pydantic import AliasChoices, BaseModel, Field

from src.core.debug import debug_print

class JudgeEvaluation(BaseModel):
    justification: str = Field(
        ...,
        description="Factual and objective analysis: read the response carefully and verify what it actually mentions before grading",
    )
    relevance_score: int = Field(
        ...,
        validation_alias=AliasChoices("relevance_score", "note_pertinence"),
        ge=1,
        le=5,
        description="Score from 1 to 5: 5=excellent, 4=good, 3=satisfactory/passable, 2=insufficient, 1=unacceptable",
    )
    has_hallucinated: bool = Field(
        ...,
        validation_alias=AliasChoices("has_hallucinated", "a_hallucine"),
        description="True ONLY if the AI asserts demonstrably false or fabricated facts, False if factually accurate",
    )

    @property
    def note_pertinence(self) -> int:
        return self.relevance_score

    @property
    def a_hallucine(self) -> bool:
        return self.has_hallucinated


# Backward compatibility alias
EvaluationJuge = JudgeEvaluation


def evaluate_ai_response(
    client: Any,
    model: str,
    question_user: Any,
    rag_context: str | None,
    reponse_assistant: str,
    judge_model: str | None = None,
) -> JudgeEvaluation | None:
    """Evaluate the quality and accuracy of an AI response using an impartial LLM judge.
            PARAMS: - client - ANY: Ollama client instance
                    - model - STR: fallback model name
                    - question_user - ANY: user query (str or ChatMessage)
                    - rag_context - STR | NONE: injected RAG documentary context
                    - reponse_assistant - STR: generated AI response text
                    - judge_model - STR | NONE: dedicated judge model name (qwen2.5:3b by default)
            RETURN: JudgeEvaluation instance or None on error"""

    question_text = question_user.content if hasattr(question_user, "content") else str(question_user)

    prompt_juge = (
        f"You are an impartial, fair, and calibrated judge evaluating the quality of an AI assistant's response.\n\n"
        f"--- SOURCE CONTEXT (HISTORICAL DOCUMENTS) ---\n{rag_context or 'No RAG document provided.'}\n\n"
        f"--- USER QUESTION ---\n{question_text}\n\n"
        f"--- AI RESPONSE TO EVALUATE ---\n{reponse_assistant}\n\n"
        f"--- EVALUATION GUIDELINES ---\n"
        f"1. CAREFUL READING: Read the full AI response. Verify what facts or names are actually mentioned before judging. Never claim an element is absent if it appears in the text.\n"
        f"2. FAIRNESS: Do not be excessively harsh. If the response provides useful and accurate facts answering the question, award at least 3 or 4/5, even if brief or cautious.\n"
        f"3. LANGUAGE CHECK: The AI response MUST be in English. If the response is formulated in French or another language, set relevance_score = 1, has_hallucinated = True, and explain in justification that the response must be rewritten in English.\n"
        f"4. HALLUCINATION DEFINITION (has_hallucinated):\n"
        f"   - has_hallucinated = True: if the AI invents fictitious events, false kingdoms, fabricated people, or answers in French instead of English.\n"
        f"   - has_hallucinated = False: if the AI states established historical facts in English.\n"
        f"5. GRADING SCALE (relevance_score):\n"
        f"   - 5/5: Excellent, rich and exact, written in English.\n"
        f"   - 4/5: Good, factual and answers the prompt well in English.\n"
        f"   - 3/5: Satisfactory or passable, conveys essential facts in English without major error.\n"
        f"   - 2/5: Insufficient or misses the point.\n"
        f"   - 1/5: Completely wrong, off-topic, fabricated, or written in French.\n\n"
        f"Provide your detailed analysis in 'justification' first, then choose 'relevance_score' and 'has_hallucinated'."
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
                response_format=JudgeEvaluation,
                max_retries=1,
            )
        except Exception as judge_exc:
            if target_judge != model and "not found" in str(judge_exc).lower():
                resultat_eval = chat_structured_flow(
                    client_chat_fn=client.chat,
                    model=model,
                    messages=messages,
                    response_format=JudgeEvaluation,
                    max_retries=1,
                )
            else:
                raise judge_exc

        debug_print("\n--- EVALUATION REPORT (BEHIND THE SCENES) ---")
        debug_print(f"Relevance Score : {resultat_eval.relevance_score}/5")
        debug_print(f"Hallucination   : {'YES' if resultat_eval.has_hallucinated else 'NO'}")
        debug_print(f"Justification   : {resultat_eval.justification}")
        debug_print("--------------------------------------------\n")

        return resultat_eval

    except Exception as e:
        debug_print(f"[Evaluation Error] Judge could not score the response: {e}")
        return None


# Backward compatibility alias
evaluer_reponse_ia = evaluate_ai_response


def interpret_result(
    grade_or_eval: JudgeEvaluation | int | None = None,
    halucination: bool | None = None,
    seuil_min: int = 3,
) -> bool:
    """Determine whether a generated response needs to be reworked.
            PARAMS: - grade_or_eval - JUDGEEVALUATION | INT | NONE: evaluation instance or integer score
                    - halucination - BOOL | NONE: hallucination boolean if integer score passed
                    - seuil_min - INT: minimum acceptable score (default: 3)
            RETURN: bool True if score < seuil_min or hallucination detected, False otherwise"""

    if grade_or_eval is None:
        return False

    if isinstance(grade_or_eval, JudgeEvaluation):
        return grade_or_eval.relevance_score < seuil_min or bool(grade_or_eval.has_hallucinated)

    grade = int(grade_or_eval)
    return grade < seuil_min or bool(halucination)


# Backward compatibility aliases
interprete_result = interpret_result
doit_retravailler = interpret_result
should_rework = interpret_result


def build_rework_prompt(
    question_user: Any,
    rag_context: str | None,
    reponse_assistant: str,
    evaluation: JudgeEvaluation,
) -> str:
    """Build the correction prompt guiding the model to refine its response.
            PARAMS: - question_user - ANY: user query
                    - rag_context - STR | NONE: documentary context
                    - reponse_assistant - STR: rejected response
                    - evaluation - JUDGEEVALUATION: judge's evaluation report
            RETURN: prompt string ready for LLM inference"""

    question_text = question_user.content if hasattr(question_user, "content") else str(question_user)

    prompt = (
        "You are an expert advisor on the Ancient China Warring States period. Your previous response was reviewed and requires refinement.\n\n"
        f"--- USER QUESTION ---\n{question_text}\n\n"
    )

    if rag_context:
        prompt += (
            f"--- HISTORICAL REFERENCE DOCUMENTS ---\n{rag_context}\n\n"
            "HISTORICAL COMPLIANCE INSTRUCTIONS:\n"
            "1. BASIS OF RESPONSE: Rely on historical documents and verified facts of the 7 Warring States.\n"
            "2. CLARITY: Never state that your chronicles lack this information if you provide relevant facts in your response.\n"
            "3. ACCURACY: Strictly adhere to historical names, kingdoms, and events.\n\n"
        )

    prompt += (
        f"--- PREVIOUS REJECTED RESPONSE ---\n{reponse_assistant}\n\n"
        f"--- JUDGE'S CRITIQUE ---\n"
        f"- Assigned Score : {evaluation.relevance_score}/5 (minimum required: 3/5)\n"
        f"- Hallucination Detected : {'YES (OUI)' if evaluation.has_hallucinated else 'NO (NON)'}\n"
        f"- Feedback & Justification : {evaluation.justification}\n\n"
        f"--- CORRECTION INSTRUCTIONS ---\n"
        "Draft a NEW corrected response (NOUVELLE réponse corrigée), factual and complete.\n"
        "- Address and resolve all flaws highlighted by the judge above.\n"
        "- Reply directly in English.\n"
        "- Output directly the final answer with no meta-commentary (do not say 'Here is the correction:')."
    )

    return prompt


# Backward compatibility alias
construire_prompt_retravail = build_rework_prompt


def rework_response_stream(
    client: Any,
    model: str,
    question_user: Any,
    rag_context: str | None,
    reponse_assistant: str,
    evaluation: JudgeEvaluation,
    system_prompt: str | None = None,
) -> Iterator[str]:
    """Regenerate a corrected response via token streaming.
            PARAMS: - client - ANY: Ollama client instance
                    - model - STR: model name
                    - question_user - ANY: user query
                    - rag_context - STR | NONE: RAG context
                    - reponse_assistant - STR: previous rejected response
                    - evaluation - JUDGEEVALUATION: judge evaluation
                    - system_prompt - STR | NONE: optional system prompt
            RETURN: iterator of token chunks"""

    prompt = build_rework_prompt(
        question_user=question_user,
        rag_context=rag_context,
        reponse_assistant=reponse_assistant,
        evaluation=evaluation,
    )
    messages: list[dict[str, Any]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    yield from client.chat_stream(model=model, messages=messages, track_as_context=False)


# Backward compatibility alias
retravailler_reponse_stream = rework_response_stream


def rework_response(
    client: Any,
    model: str,
    question_user: Any,
    rag_context: str | None,
    reponse_assistant: str,
    evaluation: JudgeEvaluation,
    system_prompt: str | None = None,
) -> str:
    """Regenerate a corrected response synchronously.
            PARAMS: - client - ANY: Ollama client instance
                    - model - STR: model name
                    - question_user - ANY: user query
                    - rag_context - STR | NONE: RAG context
                    - reponse_assistant - STR: previous rejected response
                    - evaluation - JUDGEEVALUATION: judge evaluation
                    - system_prompt - STR | NONE: optional system prompt
            RETURN: final corrected response string"""

    prompt = build_rework_prompt(
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


# Backward compatibility alias
retravailler_reponse = rework_response


def rework_structured_response(
    client: Any,
    model: str,
    question_user: Any,
    rag_context: str | None,
    reponse_assistant: str,
    evaluation: JudgeEvaluation,
    response_format: type[Any],
) -> Any:
    """Regenerate a corrected structured Pydantic response.
            PARAMS: - client - ANY: Ollama client instance
                    - model - STR: model name
                    - question_user - ANY: user query
                    - rag_context - STR | NONE: RAG context
                    - reponse_assistant - STR: previous rejected response
                    - evaluation - JUDGEEVALUATION: judge evaluation
                    - response_format - TYPE: expected Pydantic model
            RETURN: validated Pydantic model instance"""

    prompt = build_rework_prompt(
        question_user=question_user,
        rag_context=rag_context,
        reponse_assistant=reponse_assistant,
        evaluation=evaluation,
    )
    return client.chat_structured(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        response_format=response_format,
        track_as_context=False,
    )


# Backward compatibility alias
retravailler_reponse_structuree = rework_structured_response

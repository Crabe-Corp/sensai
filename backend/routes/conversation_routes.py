import json
import os
import uuid
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
import httpx
from pydantic import BaseModel
from sqlalchemy.orm import Session
from database import get_db
from models import Conversation, ConversationMember, Message, User
from realtime import manager
from security import get_current_user
from tools_registry import list_tools, run_tool

router = APIRouter(prefix="/api/conversations", tags=["conversations"])
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ia:11434")


class CreateConversationRequest(BaseModel):
    title: Optional[str] = "Nouvelle conversation"
    mode: Optional[str] = "solo"  # "solo" ou "work"
    model_name: Optional[str] = "qwen3:0.6b"
    tools_enabled: Optional[List[str]] = []


class AddMemberRequest(BaseModel):
    username: str
    role: Optional[str] = "editor"


class ChatMessageRequest(BaseModel):
    content: str
    model: Optional[str] = None
    tools_enabled: Optional[List[str]] = None
    system_instruction: Optional[str] = None


def estimate_tokens(text: str) -> int:
    """Estimation rapide basée sur le nombre de caractères/mots si non renvoyé par l'IA."""
    if not text:
        return 0
    words = len(text.split())
    chars = len(text)
    return max(1, int((words * 1.3) + (chars / 15)))


def check_user_access(conversation: Conversation, user: User, db: Session) -> bool:
    if conversation.created_by_id == user.id:
        return True
    if conversation.mode == "work":
        member = db.query(ConversationMember).filter(
            ConversationMember.conversation_id == conversation.id,
            ConversationMember.user_id == user.id
        ).first()
        return member is not None
    return False


@router.get("")
def list_conversations(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Récupérer les conversations créées par l'utilisateur
    owned = db.query(Conversation).filter(Conversation.created_by_id == user.id).all()

    # Récupérer les conversations collaboratives "work" dont l'utilisateur est membre
    memberships = db.query(ConversationMember).filter(ConversationMember.user_id == user.id).all()
    shared_ids = [m.conversation_id for m in memberships]
    shared = db.query(Conversation).filter(Conversation.id.in_(shared_ids)).all() if shared_ids else []

    all_convs = {c.id: c for c in (owned + shared)}.values()
    sorted_convs = sorted(all_convs, key=lambda x: x.updated_at or x.created_at, reverse=True)

    result = []
    for c in sorted_convs:
        total_tokens = sum(m.total_tokens for m in c.messages)
        tools = json.loads(c.tools_enabled) if c.tools_enabled else []
        result.append({
            "id": c.id,
            "title": c.title,
            "mode": c.mode,
            "model_name": c.model_name,
            "tools_enabled": tools,
            "total_tokens": total_tokens,
            "message_count": len(c.messages),
            "is_owner": c.created_by_id == user.id,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        })
    return result


@router.post("")
def create_conversation(
    req: CreateConversationRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    conv_id = str(uuid.uuid4())
    tools_json = json.dumps(req.tools_enabled or [])
    mode = "work" if req.mode == "work" else "solo"

    conv = Conversation(
        id=conv_id,
        title=req.title or ("Session Collaborative" if mode == "work" else "Nouvelle conversation"),
        created_by_id=user.id,
        mode=mode,
        model_name=req.model_name or "qwen3:0.6b",
        tools_enabled=tools_json,
    )
    db.add(conv)

    if mode == "work":
        member = ConversationMember(
            conversation_id=conv_id,
            user_id=user.id,
            role="owner"
        )
        db.add(member)

    db.commit()
    db.refresh(conv)

    return {
        "id": conv.id,
        "title": conv.title,
        "mode": conv.mode,
        "model_name": conv.model_name,
        "tools_enabled": req.tools_enabled or [],
        "total_tokens": 0,
        "is_owner": True,
        "created_at": conv.created_at.isoformat()
    }


@router.get("/{conversation_id}")
def get_conversation(
    conversation_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation introuvable")

    if not check_user_access(conv, user, db):
        raise HTTPException(status_code=403, detail="Accès non autorisé à cette conversation")

    total_tokens = sum(m.total_tokens for m in conv.messages)
    tools = json.loads(conv.tools_enabled) if conv.tools_enabled else []

    members_list = []
    if conv.mode == "work":
        members = db.query(ConversationMember).filter(ConversationMember.conversation_id == conv.id).all()
        for m in members:
            u = db.query(User).filter(User.id == m.user_id).first()
            if u:
                members_list.append({
                    "user_id": u.id,
                    "username": u.username,
                    "role": m.role
                })

    return {
        "id": conv.id,
        "title": conv.title,
        "mode": conv.mode,
        "model_name": conv.model_name,
        "tools_enabled": tools,
        "total_tokens": total_tokens,
        "is_owner": conv.created_by_id == user.id,
        "created_at": conv.created_at.isoformat() if conv.created_at else None,
        "members": members_list,
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "sender_name": m.sender_name,
                "content": m.content,
                "prompt_tokens": m.prompt_tokens,
                "completion_tokens": m.completion_tokens,
                "total_tokens": m.total_tokens,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in conv.messages
        ]
    }


@router.delete("/{conversation_id}")
def delete_conversation(
    conversation_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation introuvable")

    if conv.created_by_id != user.id:
        raise HTTPException(status_code=403, detail="Seul le créateur peut supprimer cette conversation")

    db.delete(conv)
    db.commit()
    return {"success": True, "message": "Conversation supprimée"}


@router.post("/{conversation_id}/members")
def add_member_to_work_conv(
    conversation_id: str,
    req: AddMemberRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation introuvable")

    if conv.created_by_id != user.id:
        raise HTTPException(status_code=403, detail="Seul le propriétaire peut ajouter des membres")

    if conv.mode != "work":
        raise HTTPException(status_code=400, detail="Seules les conversations en mode 'work' acceptent plusieurs utilisateurs")

    target_user = db.query(User).filter(User.username == req.username.strip()).first()
    if not target_user:
        raise HTTPException(status_code=404, detail=f"Utilisateur '{req.username}' introuvable")

    existing = db.query(ConversationMember).filter(
        ConversationMember.conversation_id == conv.id,
        ConversationMember.user_id == target_user.id
    ).first()
    if existing:
        return {"success": True, "message": "L'utilisateur a déjà accès à cette conversation"}

    member = ConversationMember(
        conversation_id=conv.id,
        user_id=target_user.id,
        role=req.role or "editor"
    )
    db.add(member)
    db.commit()

    return {"success": True, "message": f"{target_user.username} a été ajouté à la conversation"}


@router.post("/{conversation_id}/chat")
async def chat_stream(
    conversation_id: str,
    req: ChatMessageRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation introuvable")

    if not check_user_access(conv, user, db):
        raise HTTPException(status_code=403, detail="Accès non autorisé")

    model_to_use = req.model or conv.model_name or "qwen3:0.6b"
    tools_to_use = req.tools_enabled if req.tools_enabled is not None else (
        json.loads(conv.tools_enabled) if conv.tools_enabled else []
    )

    # Enregistrer le message de l'utilisateur
    user_tokens = estimate_tokens(req.content)
    user_msg_id = str(uuid.uuid4())
    user_msg = Message(
        id=user_msg_id,
        conversation_id=conv.id,
        sender_id=user.id,
        sender_name=user.username,
        role="user",
        content=req.content,
        prompt_tokens=user_tokens,
        completion_tokens=0,
        total_tokens=user_tokens,
    )
    db.add(user_msg)
    conv.updated_at = datetime.utcnow()
    # Si premier message, nommer la conversation
    if conv.title == "Nouvelle conversation":
        conv.title = req.content[:35] + ("..." if len(req.content) > 35 else "")

    db.commit()

    # Diffusion en temps réel WebSocket du message utilisateur (pour le mode "work")
    await manager.broadcast(conv.id, {
        "type": "new_message",
        "message": {
            "id": user_msg_id,
            "role": "user",
            "sender_name": user.username,
            "content": req.content,
            "prompt_tokens": user_tokens,
            "completion_tokens": 0,
            "total_tokens": user_tokens,
            "created_at": user_msg.created_at.isoformat()
        }
    })

    # Préparation de l'historique pour Ollama
    history = []
    system_prompt = req.system_instruction.strip() if req.system_instruction and req.system_instruction.strip() else (
        "Tu es SensAI, un assistant virtuel intelligent, clair et direct. "
        "Tu assistes les utilisateurs dans leurs stratégies, royaumes et requêtes."
    )

    # Détection et exécution d'outils fait main si activés
    tool_outputs = []
    if tools_to_use:
        lower_content = req.content.lower()
        if "kingdom_stats" in tools_to_use:
            # Détection de mot-clé royaume
            for r_name in ["valoria", "draconis", "aethelgard", "solaria", "umbra", "royaume"]:
                if r_name in lower_content:
                    output = run_tool("kingdom_stats", {"name": r_name})
                    tool_outputs.append(output)
                    break
        if "dice_roller" in tools_to_use:
            if "dé" in lower_content or "roll" in lower_content or "d20" in lower_content or "d6" in lower_content:
                output = run_tool("dice_roller", {"notation": "1d20"})
                tool_outputs.append(output)
        if "calculator" in tools_to_use:
            if "calcul" in lower_content or "+" in lower_content or "*" in lower_content:
                output = run_tool("calculator", {"expression": "100 * 12"})
                tool_outputs.append(output)

    if tool_outputs:
        system_prompt += "\nInformations récupérées via les outils intégrés du système:\n" + "\n".join(tool_outputs)

    history.append({"role": "system", "content": system_prompt})

    # Charger les 15 derniers messages pour le contexte
    past_messages = db.query(Message).filter(Message.conversation_id == conv.id).order_by(Message.created_at).limit(15).all()
    for pm in past_messages:
        history.append({"role": pm.role, "content": pm.content})

    async def event_generator():
        accumulated_text = ""
        prompt_tokens_eval = user_tokens
        completion_tokens_eval = 0

        # Si un outil a fourni un résultat préalable, on le stream en premier pour l'utilisateur
        if tool_outputs:
            tool_intro = f"*[Outil exécuté : {tool_outputs[0]}]*\n\n"
            accumulated_text += tool_intro
            yield json.dumps({"type": "chunk", "content": tool_intro}) + "\n"

        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                async with client.stream(
                    "POST",
                    f"{OLLAMA_BASE_URL}/api/chat",
                    json={
                        "model": model_to_use,
                        "messages": history,
                        "stream": True,
                    }
                ) as response:
                    async for raw_line in response.aiter_lines():
                        if not raw_line:
                            continue
                        try:
                            data = json.loads(raw_line)
                            msg_chunk = data.get("message", {}).get("content", "")
                            if msg_chunk:
                                accumulated_text += msg_chunk
                                yield json.dumps({"type": "chunk", "content": msg_chunk}) + "\n"

                            if data.get("done"):
                                prompt_tokens_eval = data.get("prompt_eval_count") or user_tokens
                                completion_tokens_eval = data.get("eval_count") or estimate_tokens(accumulated_text)
                        except Exception:
                            continue
            except Exception as e:
                err_msg = f"\n[Connexion à l'IA indisponible : {str(e)}]"
                accumulated_text += err_msg
                yield json.dumps({"type": "chunk", "content": err_msg}) + "\n"
                completion_tokens_eval = estimate_tokens(accumulated_text)

        total_response_tokens = prompt_tokens_eval + completion_tokens_eval

        # Sauvegarder la réponse de l'assistant en BDD
        assistant_msg_id = str(uuid.uuid4())
        assistant_msg = Message(
            id=assistant_msg_id,
            conversation_id=conv.id,
            sender_id=None,
            sender_name="SensAI",
            role="assistant",
            content=accumulated_text or "...",
            prompt_tokens=prompt_tokens_eval,
            completion_tokens=completion_tokens_eval,
            total_tokens=total_response_tokens,
        )
        db.add(assistant_msg)
        conv.updated_at = datetime.utcnow()
        db.commit()

        # Recalculer le total global de la conversation
        conv_total_tokens = sum(m.total_tokens for m in conv.messages)

        # Message final avec métadonnées de tokens
        final_payload = {
            "type": "done",
            "message_id": assistant_msg_id,
            "prompt_tokens": prompt_tokens_eval,
            "completion_tokens": completion_tokens_eval,
            "total_tokens": total_response_tokens,
            "conversation_total_tokens": conv_total_tokens,
        }
        yield json.dumps(final_payload) + "\n"

        # Broadcast WebSocket pour synchro live "work"
        await manager.broadcast(conv.id, {
            "type": "new_message",
            "message": {
                "id": assistant_msg_id,
                "role": "assistant",
                "sender_name": "SensAI",
                "content": accumulated_text,
                "prompt_tokens": prompt_tokens_eval,
                "completion_tokens": completion_tokens_eval,
                "total_tokens": total_response_tokens,
                "created_at": assistant_msg.created_at.isoformat(),
                "conversation_total_tokens": conv_total_tokens
            }
        })

    return StreamingResponse(event_generator(), media_type="application/x-ndjson")


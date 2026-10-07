import asyncio
import json
import os
import re
import uuid
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from fastapi.responses import StreamingResponse
import httpx
from pydantic import BaseModel
from sqlalchemy.orm import Session
from database import get_db
from models import Conversation, ConversationMember, Message, User
from realtime import manager
from security import get_current_user
from tools_registry import get_ollama_tools, list_tools, run_tool

router = APIRouter(prefix="/api/conversations", tags=["conversations"])
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ia:11434")


class CreateConversationRequest(BaseModel):
    title: Optional[str] = "Nouvelle conversation"
    mode: Optional[str] = "solo"  # "solo" ou "work"
    model_name: Optional[str] = "qwen3:0.6b"
    tools_enabled: Optional[List[str]] = []


class BranchConversationRequest(BaseModel):
    message_id: str
    title: Optional[str] = None
    content: Optional[str] = None


class TruncateConversationRequest(BaseModel):
    message_id: str
    content: Optional[str] = None


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
        valid_tool_ids = [t["id"] for t in list_tools()] + ["structured_output", "Structured Output", "mcp_runner"]
        tools = [t for t in tools if t in valid_tool_ids]
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
    tools_cleaned = [t for t in (req.tools_enabled or []) if t in ["structured_output", "Structured Output", "mcp_runner"]]
    tools_json = json.dumps(tools_cleaned)
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
        "tools_enabled": tools_cleaned,
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
    tools = [t for t in tools if t in ["structured_output", "Structured Output", "mcp_runner"]]

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


@router.post("/{conversation_id}/branch")
def branch_conversation(
    conversation_id: str,
    req: BranchConversationRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation introuvable")

    if not check_user_access(conv, user, db):
        raise HTTPException(status_code=403, detail="Accès non autorisé à cette conversation")

    # Trouver le message cible et ses messages précédents
    target_msg = None
    target_idx = -1
    ordered_messages = sorted(conv.messages, key=lambda m: m.created_at or datetime.min)

    # 1. Recherche par identifiant direct
    for i, m in enumerate(ordered_messages):
        if m.id == req.message_id:
            target_msg = m
            target_idx = i
            break

    # 2. Si non trouvé par ID (ex: id temporaire temp-xxx), recherche par contenu
    if target_msg is None and req.content:
        for i, m in enumerate(ordered_messages):
            if m.content.strip() == req.content.strip():
                target_msg = m
                target_idx = i
                break

    # 3. Fallback : prendre le dernier message utilisateur s'il existe
    if target_msg is None and ordered_messages:
        user_msgs = [(i, m) for i, m in enumerate(ordered_messages) if m.role == "user"]
        if user_msgs:
            target_idx, target_msg = user_msgs[-1]
        else:
            target_idx = len(ordered_messages) - 1
            target_msg = ordered_messages[-1]

    # Déterminer les messages à cloner :
    # Si req.content est fourni et différent du contenu cible (mode édition/remplacement) :
    # On clone strictement avant target_idx (les messages antérieurs).
    # Sinon (branchement direct / fork de l'état actuel) :
    # On clone jusqu'à target_idx inclus, et si la réponse de l'assistant suit directement, on l'inclut également.
    prior_messages = []
    if target_idx >= 0:
        is_edit = bool(req.content and target_msg and req.content.strip() != target_msg.content.strip())
        if is_edit:
            prior_messages = ordered_messages[:target_idx]
        else:
            end_idx = target_idx + 1
            if end_idx < len(ordered_messages) and ordered_messages[end_idx].role == "assistant":
                end_idx += 1
            prior_messages = ordered_messages[:end_idx]
    else:
        prior_messages = ordered_messages

    branch_title = req.title or f"{conv.title} (Branche)"
    new_conv_id = str(uuid.uuid4())
    new_conv = Conversation(
        id=new_conv_id,
        title=branch_title,
        created_by_id=user.id,
        mode=conv.mode,
        model_name=conv.model_name,
        tools_enabled=conv.tools_enabled,
    )
    db.add(new_conv)

    # Cloner les messages antérieurs dans la nouvelle branche
    for pm in prior_messages:
        cloned_msg = Message(
            id=str(uuid.uuid4()),
            conversation_id=new_conv_id,
            sender_id=pm.sender_id,
            sender_name=pm.sender_name,
            role=pm.role,
            content=pm.content,
            prompt_tokens=pm.prompt_tokens,
            completion_tokens=pm.completion_tokens,
            total_tokens=pm.total_tokens,
            created_at=pm.created_at,
        )
        db.add(cloned_msg)

    if conv.mode == "work":
        db.add(ConversationMember(conversation_id=new_conv_id, user_id=user.id, role="owner"))

    db.commit()
    db.refresh(new_conv)

    total_tokens = sum(m.total_tokens for m in new_conv.messages)
    tools = json.loads(new_conv.tools_enabled) if new_conv.tools_enabled else []
    tools = [t for t in tools if t in ["structured_output", "Structured Output", "mcp_runner"]]

    return {
        "id": new_conv.id,
        "title": new_conv.title,
        "mode": new_conv.mode,
        "model_name": new_conv.model_name,
        "tools_enabled": tools,
        "total_tokens": total_tokens,
        "message_count": len(new_conv.messages),
        "is_owner": True,
        "created_at": new_conv.created_at.isoformat() if new_conv.created_at else None,
        "parent_id": conv.id,
        "parent_title": conv.title,
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
            for m in new_conv.messages
        ]
    }


@router.post("/{conversation_id}/truncate")
def truncate_conversation(
    conversation_id: str,
    req: TruncateConversationRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation introuvable")

    if not check_user_access(conv, user, db):
        raise HTTPException(status_code=403, detail="Accès non autorisé à cette conversation")

    ordered_messages = sorted(conv.messages, key=lambda m: m.created_at or datetime.min)
    found_idx = -1
    for i, m in enumerate(ordered_messages):
        if m.id == req.message_id:
            found_idx = i
            break

    if found_idx == -1 and req.content:
        for i, m in enumerate(ordered_messages):
            if m.content.strip() == req.content.strip():
                found_idx = i
                break

    if found_idx == -1 and ordered_messages:
        user_msgs = [i for i, m in enumerate(ordered_messages) if m.role == "user"]
        if user_msgs:
            found_idx = user_msgs[-1]

    to_delete = ordered_messages[found_idx:] if found_idx != -1 else []
    for m in to_delete:
        db.delete(m)

    conv.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(conv)

    total_tokens = sum(m.total_tokens for m in conv.messages)
    return {
        "success": True,
        "remaining_messages": len(conv.messages),
        "total_tokens": total_tokens,
    }


@router.get("/{conversation_id}/export")
def export_conversation_endpoint(
    conversation_id: str,
    format: str = "md",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation introuvable")

    if not check_user_access(conv, user, db):
        raise HTTPException(status_code=403, detail="Accès non autorisé à cette conversation")

    safe_title = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in conv.title).strip("_") or "conversation"
    today = datetime.utcnow().strftime("%Y-%m-%d")

    if format == "json":
        data = {
            "id": conv.id,
            "title": conv.title,
            "mode": conv.mode,
            "model_name": conv.model_name,
            "tools_enabled": json.loads(conv.tools_enabled) if conv.tools_enabled else [],
            "total_tokens": sum(m.total_tokens for m in conv.messages),
            "created_at": conv.created_at.isoformat() if conv.created_at else None,
            "exported_at": datetime.utcnow().isoformat(),
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
        content = json.dumps(data, indent=2, ensure_ascii=False)
        filename = f"{safe_title}-{today}.json"
        return Response(
            content=content,
            media_type="application/json; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )

    elif format == "txt":
        lines = [
            "=" * 80,
            "SENSAI - EXPORT DE CONVERSATION",
            "=" * 80,
            f"Titre       : {conv.title}",
            f"Date        : {conv.created_at.strftime('%Y-%m-%d %H:%M:%S') if conv.created_at else ''}",
            f"Mode        : {conv.mode}",
            f"Modèle      : {conv.model_name}",
            f"Total Tokens: {sum(m.total_tokens for m in conv.messages)}",
            f"Messages    : {len(conv.messages)}",
            "=" * 80,
            ""
        ]
        for m in conv.messages:
            sender = m.sender_name or ("Vous" if m.role == "user" else "SensAI")
            date_str = m.created_at.strftime("%H:%M:%S") if m.created_at else ""
            lines.append(f"[{sender}] ({date_str}):" if date_str else f"[{sender}]:")
            lines.append(m.content)
            lines.append("-" * 80)
            lines.append("")
        content = "\n".join(lines)
        filename = f"{safe_title}-{today}.txt"
        return Response(
            content=content,
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )

    else:
        lines = [
            f"# {conv.title}",
            "",
            f"- **Date :** {conv.created_at.strftime('%Y-%m-%d %H:%M:%S') if conv.created_at else ''}",
            f"- **Modèle :** {conv.model_name}",
            f"- **Mode :** {'Collaboratif (Work)' if conv.mode == 'work' else 'Solo'}",
            f"- **Total Tokens :** {sum(m.total_tokens for m in conv.messages)}",
            f"- **Messages :** {len(conv.messages)}",
            "",
            "---",
            ""
        ]
        for m in conv.messages:
            sender = m.sender_name or ("Vous" if m.role == "user" else "SensAI")
            date_str = m.created_at.strftime("%H:%M:%S") if m.created_at else ""
            header = f"### {sender} ({date_str})" if date_str else f"### {sender}"
            lines.append(header)
            lines.append("")
            lines.append(m.content)
            lines.append("")
            if m.total_tokens > 0:
                lines.append(f"*Tokens : {m.total_tokens} (Prompt: {m.prompt_tokens}, Réponse: {m.completion_tokens})*")
                lines.append("")
            lines.append("---")
            lines.append("")
        content = "\n".join(lines)
        filename = f"{safe_title}-{today}.md"
        return Response(
            content=content,
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )


MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024  # 25 Mo


@router.post("/{conversation_id}/upload")
async def upload_file_to_conversation(
    conversation_id: str,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation introuvable")

    if not check_user_access(conv, user, db):
        raise HTTPException(status_code=403, detail="Accès non autorisé à cette conversation")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail="Le fichier dépasse la taille maximale autorisée de 25 Mo."
        )

    upload_dir = os.path.join(os.getcwd(), "uploads", conversation_id)
    os.makedirs(upload_dir, exist_ok=True)

    safe_filename = "".join(c for c in (file.filename or "fichier") if c.isalnum() or c in (".", "-", "_")).strip() or "fichier"
    file_path = os.path.join(upload_dir, safe_filename)

    with open(file_path, "wb") as f:
        f.write(content)

    text_content = None
    try:
        text_content = content.decode("utf-8")
    except UnicodeDecodeError:
        pass

    return {
        "success": True,
        "filename": safe_filename,
        "size": len(content),
        "content_type": file.content_type,
        "is_text": text_content is not None,
        "preview": text_content[:500] if text_content else None,
    }


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
    raw_tools = req.tools_enabled if req.tools_enabled is not None else (
        json.loads(conv.tools_enabled) if conv.tools_enabled else []
    )
    valid_tool_ids = [t["id"] for t in list_tools()] + ["structured_output", "Structured Output", "mcp_runner"]
    tools_to_use = [t for t in raw_tools if t in valid_tool_ids]

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
        clean_prompt = re.sub(
            r'\[Fichier joint\s*:\s*[^\]\(\)]+?(?: \([^)]+\))?\](?:\s*--- Début du contenu de [^\n\r]+ ---\s*[\s\S]*?\s*--- Fin du contenu de [^\n\r]+ ---)?',
            '',
            req.content
        ).strip()
        if clean_prompt:
            conv.title = clean_prompt[:35] + ("..." if len(clean_prompt) > 35 else "")
        else:
            file_match = re.search(r'\[Fichier joint\s*:\s*([^\]\(\)]+?)', req.content)
            if file_match:
                conv.title = file_match.group(1).strip()[:35]
            else:
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
        "Tu es SensAI, un assistant virtuel intelligent, clair et direct."
    )

    is_structured = bool(tools_to_use and ("structured_output" in tools_to_use or "Structured Output" in tools_to_use))
    if is_structured:
        system_prompt += (
            "\nFormat JSON impératif : Réponds sous la forme d'un objet JSON structuré avec des clés courtes et explicites "
            "(ex: {\"response\": \"...\"} ou {\"message\": \"...\", \"data\": [...]}). "
            "Ne mets jamais de phrase entière en guise de clé."
        )

    history.append({"role": "system", "content": system_prompt})

    # Charger les 15 derniers messages pour le contexte
    past_messages = db.query(Message).filter(Message.conversation_id == conv.id).order_by(Message.created_at).limit(15).all()
    for pm in past_messages:
        history.append({"role": pm.role, "content": pm.content})

    async def event_generator():
        accumulated_text = ""
        prompt_tokens_eval = user_tokens
        completion_tokens_eval = 0

        use_mcp = "mcp_runner" in tools_to_use
        # Événement initial notifiant l'identifiant réel en base du message utilisateur
        yield json.dumps({"type": "start", "user_message_id": user_msg_id}) + "\n"

        ollama_payload = {
            "model": model_to_use,
            "messages": history,
            "stream": True,
        }
        if is_structured:
            ollama_payload["format"] = "json"
        if use_mcp:
            ollama_payload["tools"] = get_ollama_tools()

        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                tool_calls_to_process = []
                async with client.stream(
                    "POST",
                    f"{OLLAMA_BASE_URL}/api/chat",
                    json=ollama_payload
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

                            tc_list = data.get("message", {}).get("tool_calls")
                            if tc_list:
                                tool_calls_to_process.extend(tc_list)

                            if data.get("done"):
                                prompt_tokens_eval = data.get("prompt_eval_count") or user_tokens
                                completion_tokens_eval = data.get("eval_count") or estimate_tokens(accumulated_text)
                        except Exception:
                            continue
                if tool_calls_to_process:
                    history.append({
                        "role": "assistant",
                        "content": accumulated_text,
                        "tool_calls": tool_calls_to_process,
                    })

                    for tc in tool_calls_to_process:
                        fn = tc.get("function", {})
                        t_name = fn.get("name", "")
                        t_args = fn.get("arguments", {})
                        if isinstance(t_args, str):
                            try:
                                t_args = json.loads(t_args)
                            except Exception:
                                t_args = {}

                        tool_output = run_tool(t_name, t_args)
                        info_text = f"\n\n*[Outil exécuté : {t_name}]*\n```json\n{tool_output}\n```\n\n"
                        accumulated_text += info_text
                        yield json.dumps({"type": "chunk", "content": info_text}) + "\n"

                        history.append({"role": "tool", "content": tool_output})
                    second_payload = {
                        "model": model_to_use,
                        "messages": history,
                        "stream": True,
                    }
                    async with client.stream(
                        "POST",
                        f"{OLLAMA_BASE_URL}/api/chat",
                        json=second_payload,
                    ) as final_resp:
                        async for raw_line in final_resp.aiter_lines():
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
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    err_msg = f"\n[Connexion à l'IA indisponible : {str(e)}]"
                    accumulated_text += err_msg
                    yield json.dumps({"type": "chunk", "content": err_msg}) + "\n"
                    completion_tokens_eval = estimate_tokens(accumulated_text)
        except asyncio.CancelledError:
            if accumulated_text.strip():
                try:
                    assistant_msg_id = str(uuid.uuid4())
                    assistant_msg = Message(
                        id=assistant_msg_id,
                        conversation_id=conv.id,
                        sender_id=None,
                        sender_name="SensAI",
                        content=accumulated_text.strip() + " *(Génération interrompue)*",
                        prompt_tokens=prompt_tokens_eval,
                        completion_tokens=estimate_tokens(accumulated_text),
                        total_tokens=prompt_tokens_eval + estimate_tokens(accumulated_text),
                    )
                    db.add(assistant_msg)
                    conv.updated_at = datetime.utcnow()
                    db.commit()
                except Exception:
                    pass
            raise

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
            "user_message_id": user_msg_id,
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


import asyncio
import json
import os
from pathlib import Path
import re
import threading
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
from src.core import memory_management, sementic_cache
from src.core.ollama_client import ChatMessage, OllamaClient
from src.features.sec.security import mask_pii, validate_input_with_llm
from tools_registry import (
    ALL_TOOLS_ID,
    DESTRUCTIVE_TOOLS,
    FORM_TOOL_NAME,
    build_confirm_block,
    build_form_block,
    create_pending_action,
    get_ollama_tools,
    list_tools,
    run_tool,
    run_tool_confirmed,
    selected_tool_names,
    take_pending_action,
)

MAX_TOOL_ROUNDS = 4  # nombre maximal d'allers-retours modèle <-> outils par message

router = APIRouter(prefix="/api/conversations", tags=["conversations"])
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ia:11434")


class CreateConversationRequest(BaseModel):
    title: Optional[str] = "Nouvelle conversation"
    mode: Optional[str] = "solo"
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
    owned = db.query(Conversation).filter(Conversation.created_by_id == user.id).all()

    memberships = db.query(ConversationMember).filter(ConversationMember.user_id == user.id).all()
    shared_ids = [m.conversation_id for m in memberships]
    shared = db.query(Conversation).filter(Conversation.id.in_(shared_ids)).all() if shared_ids else []

    all_convs = {c.id: c for c in (owned + shared)}.values()
    sorted_convs = sorted(all_convs, key=lambda x: x.updated_at or x.created_at, reverse=True)

    result = []
    for c in sorted_convs:
        total_tokens = sum(m.total_tokens for m in c.messages)
        tools = json.loads(c.tools_enabled) if c.tools_enabled else []
        valid_tool_ids = [t["id"] for t in list_tools()] + ["Structured Output", ALL_TOOLS_ID]
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


@router.post("/{conversation_id}")
@router.put("/{conversation_id}")
def save_conversation(
    conversation_id: str,
    payload: dict,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Enregistre ou met à jour une conversation et ses messages."""
    meta = payload.get("metadata", payload)
    title = meta.get("title") or payload.get("title")
    model_name = meta.get("model") or meta.get("model_name") or payload.get("model_name") or "qwen2.5:3b"
    raw_messages = payload.get("messages", [])

    conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conv:
        conv = Conversation(
            id=conversation_id,
            title=title or f"Session {conversation_id[:8]}",
            created_by_id=user.id,
            mode="solo",
            model_name=model_name,
        )
        db.add(conv)
        db.commit()
        db.refresh(conv)
    else:
        if title:
            conv.title = title
        if model_name:
            conv.model_name = model_name

    existing_count = len(conv.messages)
    if len(raw_messages) > existing_count:
        for new_msg in raw_messages[existing_count:]:
            m_role = new_msg.get("role", "user")
            m_content = new_msg.get("content", "")
            if m_role == "user" and m_content:
                masked_m, has_pii_m = mask_pii(m_content)
                if has_pii_m:
                    m_content = masked_m
            m = Message(
                id=str(uuid.uuid4()),
                conversation_id=conv.id,
                sender_id=user.id if m_role == "user" else None,
                sender_name=user.username if m_role == "user" else "SensAI",
                role=m_role,
                content=m_content,
                prompt_tokens=estimate_tokens(m_content),
                completion_tokens=0,
                total_tokens=estimate_tokens(m_content),
                created_at=datetime.utcnow(),
            )
            db.add(m)
        conv.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(conv)

    return {"success": True, "id": conv.id}


@router.get("/sync/list")
def list_conversations_sync(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return list_conversations(user, db)


@router.get("/sync/{conversation_id}")
def get_conversation_sync(conversation_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return get_conversation(conversation_id, user, db)


@router.post("/sync/{conversation_id}")
def save_conversation_sync(conversation_id: str, payload: dict, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return save_conversation(conversation_id, payload, user, db)


@router.delete("/sync/{conversation_id}")
def delete_conversation_sync(conversation_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return delete_conversation(conversation_id, user, db)


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

    target_msg = None
    target_idx = -1
    ordered_messages = sorted(conv.messages, key=lambda m: m.created_at or datetime.min)

    for i, m in enumerate(ordered_messages):
        if m.id == req.message_id:
            target_msg = m
            target_idx = i
            break

    if target_msg is None and req.content:
        for i, m in enumerate(ordered_messages):
            if m.content.strip() == req.content.strip():
                target_msg = m
                target_idx = i
                break

    if target_msg is None and ordered_messages:
        user_msgs = [(i, m) for i, m in enumerate(ordered_messages) if m.role == "user"]
        if user_msgs:
            target_idx, target_msg = user_msgs[-1]
        else:
            target_idx = len(ordered_messages) - 1
            target_msg = ordered_messages[-1]

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


@router.post("/{conversation_id}/clearcache")
def clear_semantic_cache(
    conversation_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation introuvable")

    if not check_user_access(conv, user, db):
        raise HTTPException(status_code=403, detail="Accès non autorisé à cette conversation")

    try:
        sementic_cache.clean_cache()
        return {"success": True, "message": "Cache sémantique vidé avec succès"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erreur lors du vidage du cache : {str(exc)}")


HISTORY_TOKEN_BUDGET = 2000
# memory_management lit un compteur global (singleton_token) : une requête à la fois entre consume et enforce
_history_budget_lock = threading.Lock()
# Le message d'approbation du frontend commence par ce marqueur suivi du token de l'action
APPROVAL_PATTERN = re.compile(r'^\[Confirmation : approuvée\] \[action_id:([A-Za-z0-9_\-]+)\]')


def _describe_destructive_call(tool_name: str, args: dict) -> str:
    if tool_name == "write_manuscript_file":
        return f"Écriture dans le fichier {args.get('filename')}"
    if tool_name == "update_kingdom_database":
        return f"Mise à jour SQL : {args.get('sql_statement')}"
    return f"Exécution de l'action {tool_name}"


async def _save_and_announce(
    db: Session,
    conv: Conversation,
    user_msg_id: str,
    content: str,
    prompt_tokens: int,
    completion_tokens: int,
    from_cache: bool = False,
) -> str:
    """Enregistre la réponse de l'assistant, la diffuse aux membres et renvoie la ligne NDJSON `done`."""
    total_tokens = prompt_tokens + completion_tokens
    assistant_msg_id = str(uuid.uuid4())
    assistant_msg = Message(
        id=assistant_msg_id,
        conversation_id=conv.id,
        sender_id=None,
        sender_name="SensAI",
        role="assistant",
        content=content,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
    )
    db.add(assistant_msg)
    conv.updated_at = datetime.utcnow()
    db.commit()
    conv_total_tokens = sum(m.total_tokens for m in conv.messages)
    cache_flags = {"from_cache": True, "source": "cache"} if from_cache else {}

    await manager.broadcast(conv.id, {
        "type": "new_message",
        "message": {
            "id": assistant_msg_id,
            "role": "assistant",
            "sender_name": "SensAI",
            "content": content,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "created_at": assistant_msg.created_at.isoformat(),
            "conversation_total_tokens": conv_total_tokens,
            **cache_flags,
        }
    })
    return json.dumps({
        "type": "done",
        "message_id": assistant_msg_id,
        "user_message_id": user_msg_id,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "conversation_total_tokens": conv_total_tokens,
        **cache_flags,
    }) + "\n"


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

    # Masquage des données sensibles (email, téléphone)
    masked_content, has_pii = mask_pii(req.content)
    effective_content = masked_content if has_pii else req.content
    approval_match = APPROVAL_PATTERN.match(req.content)
    approval_token = approval_match.group(1) if approval_match else None

    user_tokens = estimate_tokens(effective_content)
    user_msg_id = str(uuid.uuid4())
    user_msg = Message(
        id=user_msg_id,
        conversation_id=conv.id,
        sender_id=user.id,
        sender_name=user.username,
        role="user",
        content=effective_content,
        prompt_tokens=user_tokens,
        completion_tokens=0,
        total_tokens=user_tokens,
    )
    db.add(user_msg)
    conv.updated_at = datetime.utcnow()
    if conv.title == "Nouvelle conversation":
        clean_prompt = re.sub(
            r'\[Fichier joint\s*:\s*[^\]\(\)]+?(?: \([^)]+\))?\](?:\s*--- Début du contenu de [^\n\r]+ ---\s*[\s\S]*?\s*--- Fin du contenu de [^\n\r]+ ---)?',
            '',
            effective_content
        ).strip()
        if clean_prompt:
            conv.title = clean_prompt[:35] + ("..." if len(clean_prompt) > 35 else "")
        else:
            file_match = re.search(r'\[Fichier joint\s*:\s*([^\]\(\)]+?)', effective_content)
            if file_match:
                conv.title = file_match.group(1).strip()[:35]
            else:
                conv.title = effective_content[:35] + ("..." if len(effective_content) > 35 else "")

    db.commit()

    await manager.broadcast(conv.id, {
        "type": "new_message",
        "message": {
            "id": user_msg_id,
            "role": "user",
            "sender_name": user.username,
            "content": effective_content,
            "prompt_tokens": user_tokens,
            "completion_tokens": 0,
            "total_tokens": user_tokens,
            "created_at": user_msg.created_at.isoformat()
        }
    })

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

    active_tool_names = selected_tool_names(tools_to_use)
    if "search_historical_archives" in active_tool_names:
        system_prompt += (
            "\nPriorité documentaire : Les archives historiques locales (outil 'search_historical_archives') "
            "sont ta source première d'information. N'appelle l'outil 'web_search' que pour confirmer des faits "
            "ou si les archives locales ne contiennent pas les informations recherchées."
        )

    if FORM_TOOL_NAME in active_tool_names:
        system_prompt += (
            f"\nSi des informations indispensables manquent pour répondre, utilise l'outil {FORM_TOOL_NAME} "
            "pour les demander à l'utilisateur au lieu de les deviner, puis attends ses réponses."
        )

    # Récupération de l'historique et gestion du budget de tokens via memory_management ([M2])
    past_messages = db.query(Message).filter(Message.conversation_id == conv.id).order_by(Message.created_at).all()
    raw_chat_messages = [ChatMessage(role="system", content=system_prompt)]
    total_tokens_calc = estimate_tokens(system_prompt)
    for pm in past_messages:
        raw_chat_messages.append(ChatMessage(role=pm.role, content=pm.content))
        total_tokens_calc += (pm.total_tokens or estimate_tokens(pm.content))

    def compress_history() -> list:
        mem_client = OllamaClient(base_url=OLLAMA_BASE_URL)
        try:
            with _history_budget_lock:
                memory_management.consume_tokens(total_tokens_calc)
                return memory_management.enforce_token_budget(
                    model=model_to_use,
                    client=mem_client,
                    messages=raw_chat_messages,
                    max_history_tokens=HISTORY_TOKEN_BUDGET,
                )
        finally:
            mem_client.close()

    # Appel Ollama synchrone possible (résumé) : hors de la boucle d'événements
    try:
        managed_messages = await asyncio.to_thread(compress_history)
    except Exception:
        managed_messages = raw_chat_messages

    for msg in managed_messages:
        history.append({
            "role": getattr(msg, "role", "user"),
            "content": getattr(msg, "content", ""),
        })

    async def event_generator():
        accumulated_text = ""
        prompt_tokens_eval = user_tokens
        completion_tokens_eval = 0

        ollama_tools = get_ollama_tools(tools_to_use)
        yield json.dumps({"type": "start", "user_message_id": user_msg_id}) + "\n"

        # Validation de sécurité par guardrail LLM
        sec_client = OllamaClient(base_url=OLLAMA_BASE_URL)
        try:
            is_valid, refusal_message = await asyncio.to_thread(
                validate_input_with_llm,
                effective_content,
                sec_client,
                model_to_use
            )
        finally:
            sec_client.close()

        if not is_valid:
            refusal_text = refusal_message or "The imperial advisor refuses to discuss this topic with you."
            accumulated_text = refusal_text
            completion_tokens_eval = estimate_tokens(accumulated_text)

            yield json.dumps({"type": "chunk", "content": refusal_text}) + "\n"
            yield await _save_and_announce(
                db, conv, user_msg_id, refusal_text, prompt_tokens_eval, completion_tokens_eval,
            )
            return

        # Interrogation du cache sémantique vectoriel ([A6])
        cached_response = None
        try:
            cached_response = await asyncio.to_thread(
                sementic_cache.get_info_cache,
                prompt=effective_content,
                ollama_url=OLLAMA_BASE_URL,
                model=model_to_use,
            )
        except Exception:
            cached_response = None

        if cached_response and cached_response.strip():
            completion_tokens_eval = estimate_tokens(cached_response)

            yield json.dumps({
                "type": "chunk",
                "content": cached_response,
                "from_cache": True,
                "source": "cache",
            }) + "\n"
            yield await _save_and_announce(
                db, conv, user_msg_id, cached_response, prompt_tokens_eval, completion_tokens_eval,
                from_cache=True,
            )
            return

        ollama_payload = {
            "model": model_to_use,
            "messages": history,
            "stream": True,
            # Les modèles à réflexion (qwen3...) rangent leur sortie dans message.thinking, que l'on
            # n'affiche pas : avec format=json le contenu restait vide. On désactive la réflexion.
            "think": False,
        }
        if is_structured:
            ollama_payload["format"] = "json"
        if ollama_tools:
            ollama_payload["tools"] = ollama_tools

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                try:
                    form_sent = False
                    for round_idx in range(MAX_TOOL_ROUNDS + 1):
                        round_payload = {**ollama_payload, "messages": history}
                        if round_idx == MAX_TOOL_ROUNDS:
                            round_payload.pop("tools", None)
                        tool_calls_to_process = []
                        round_text = ""
                        async with client.stream(
                            "POST",
                            f"{OLLAMA_BASE_URL}/api/chat",
                            json=round_payload
                        ) as response:
                            async for raw_line in response.aiter_lines():
                                if not raw_line:
                                    continue
                                try:
                                    data = json.loads(raw_line)
                                    if data.get("error"):
                                        err_msg = f"\n[Erreur du modèle {model_to_use} : {data['error']}]"
                                        accumulated_text += err_msg
                                        yield json.dumps({"type": "chunk", "content": err_msg}) + "\n"
                                        continue
                                    msg_chunk = data.get("message", {}).get("content", "")
                                    if msg_chunk:
                                        round_text += msg_chunk
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

                        if not tool_calls_to_process:
                            break

                        history.append({
                            "role": "assistant",
                            "content": round_text,
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

                            if t_name == FORM_TOOL_NAME:
                                # Formulaire : on l'envoie au frontend et on termine le tour,
                                # les réponses reviendront comme prochain message de l'utilisateur
                                try:
                                    form_block = build_form_block(t_args)
                                except ValueError as form_exc:
                                    history.append({"role": "tool", "tool_name": t_name, "content": json.dumps({"status": "error", "message": str(form_exc)}, ensure_ascii=False)})
                                    continue
                                accumulated_text += form_block
                                yield json.dumps({"type": "chunk", "content": form_block}) + "\n"
                                form_sent = True
                                break

                            # Les outils sont synchrones (réseau, SQL, fichiers) : hors de la boucle d'événements
                            if t_name in DESTRUCTIVE_TOOLS:
                                # Seul un token émis par le serveur pour cet utilisateur, cette conversation et cet outil
                                # débloque l'action ; elle s'exécute avec les arguments que l'utilisateur a vus.
                                approved_args = (
                                    take_pending_action(approval_token, user.id, conv.id, t_name)
                                    if approval_token else None
                                )
                                if approved_args is None:
                                    confirm_block = build_confirm_block(
                                        summary=_describe_destructive_call(t_name, t_args),
                                        tool_name=t_name,
                                        action_id=create_pending_action(user.id, conv.id, t_name, t_args),
                                        details=t_args,
                                    )
                                    accumulated_text += confirm_block
                                    yield json.dumps({"type": "chunk", "content": confirm_block}) + "\n"
                                    form_sent = True
                                    break
                                tool_output = await asyncio.to_thread(run_tool_confirmed, t_name, approved_args)
                            else:
                                tool_output = await asyncio.to_thread(run_tool, t_name, t_args)

                            history.append({"role": "tool", "tool_name": t_name, "content": tool_output})

                        if form_sent:
                            break
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

        if not accumulated_text.strip():
            # Aucune erreur mais aucun contenu : on le dit plutôt que d'afficher une bulle vide
            empty_msg = f"[Le modèle {model_to_use} n'a renvoyé aucune réponse. Réessayez ou changez de modèle.]"
            accumulated_text = empty_msg
            yield json.dumps({"type": "chunk", "content": empty_msg}) + "\n"

        # Enregistrement dans le cache sémantique après génération réussie ([A6]).
        # Les réponses à usage unique (confirmation, formulaire, sortie d'outil) ne doivent jamais être rejouées.
        if (
            accumulated_text.strip()
            and "```sensai-" not in accumulated_text
            and not accumulated_text.startswith("[Erreur")
            and not accumulated_text.startswith("[Connexion")
            and not accumulated_text.startswith("[Le modèle")
        ):
            try:
                await asyncio.to_thread(
                    sementic_cache.add_to_cache,
                    prompt=effective_content,
                    llm_response=accumulated_text,
                    ollama_url=OLLAMA_BASE_URL,
                )
            except Exception:
                pass

        yield await _save_and_announce(
            db, conv, user_msg_id, accumulated_text, prompt_tokens_eval, completion_tokens_eval,
        )

    return StreamingResponse(event_generator(), media_type="application/x-ndjson")


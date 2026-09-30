#!/usr/bin/env python3
"""Active l'option d'export native en Markdown (.md)"""

from pathlib import Path

build_dir = Path("/app/build/_app/immutable")
if build_dir.exists():
    for file in build_dir.rglob("*.js"):
        content = file.read_text(encoding="utf-8", errors="ignore")
        if "chat-${J.chat.title}.txt" in content or "Plain text (.txt)" in content or "Texte brut (.txt)" in content:
            content = content.replace("chat-${J.chat.title}.txt", "chat-${J.chat.title}.md")
            content = content.replace("playground-chat-${Date.now()}.txt", "playground-chat-${Date.now()}.md")
            content = content.replace('"Plain text (.txt)"', '"Markdown (.md)"')
            content = content.replace("Texte brut (.txt)", "Markdown (.md)")
            content = content.replace('"Texte (.txt)"', '"Markdown (.md)"')
            file.write_text(content, encoding="utf-8")
    print("[SensAI] Interface Open WebUI configurée avec l'export Markdown (.md).")

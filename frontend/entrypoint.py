#!/usr/bin/env python3
"""Script de démarrage pour SensAI WebUI.

1. Active l'export Markdown (.md) natif dans l'interface.
2. Vérifie et télécharge automatiquement le modèle Ollama configuré si absent.
"""

import json
import os
import time
import urllib.request
from pathlib import Path

OLLAMA_API_URL = os.getenv("OLLAMA_API_URL", "http://ia:11434")
DEFAULT_MODEL = os.getenv("DEFAULT_MODELS", "qwen3:0.6b").split(",")[0].strip()


def patch_markdown_export() -> None:
    """Remplace l'export texte brut (.txt) par Markdown (.md) dans le frontend."""
    build_dir = Path("/app/build/_app/immutable")
    if not build_dir.exists():
        return

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


def ensure_ollama_model(model: str = DEFAULT_MODEL) -> None:
    """Vérifie et télécharge le modèle Ollama au démarrage si nécessaire."""
    print(f"[SensAI] Vérification de la disponibilité du modèle '{model}' sur Ollama...")

    # Attente qu'Ollama soit prêt à répondre (jusqu'à 15 secondes)
    for _ in range(15):
        try:
            with urllib.request.urlopen(f"{OLLAMA_API_URL}/api/tags", timeout=3) as res:
                data = json.loads(res.read())
                models = [m.get("name") for m in data.get("models", [])]
                if model in models or f"{model}:latest" in models:
                    print(f"[SensAI] Modèle '{model}' prêt et disponible.")
                    return
                break
        except Exception:
            time.sleep(1)
    else:
        print("[SensAI] Avertissement : Ollama n'a pas répondu à temps.")
        return

    print(f"[SensAI] Modèle '{model}' absent. Téléchargement en cours depuis Ollama...")
    try:
        req = urllib.request.Request(
            f"{OLLAMA_API_URL}/api/pull",
            data=json.dumps({"model": model, "stream": False}).encode(),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=600):
            print(f"[SensAI] Modèle '{model}' téléchargé avec succès !")
    except Exception as exc:
        print(f"[SensAI] Erreur lors du téléchargement du modèle : {exc}")


def main() -> None:
    patch_markdown_export()
    ensure_ollama_model()


if __name__ == "__main__":
    main()

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field


class PDFDocumentInfo(BaseModel):
    file_name: str
    file_path: str
    total_pages: int
    extracted_pages: int
    content: str
    is_truncated: bool = False


def extract_text_from_pdf(
    file_path: str | Path,
    max_pages: int = 50,
    max_chars: int = 100_000,
) -> PDFDocumentInfo:
    """Extrait le texte page par page d'un fichier PDF de manière sécurisée.
    PARAMS: - file_path - STR | PATH: chemin vers le fichier PDF cible
            - max_pages - INT: nombre maximal de pages à extraire
            - max_chars - INT: plafond de caractères pour éviter la saturation mémoire
    RETURN: objet PDFDocumentInfo contenant les métadonnées et le texte assemblé"""
    try:
        from pypdf import PdfReader
        from pypdf.errors import FileNotDecryptedError, PdfStreamError
    except ImportError as err:
        raise RuntimeError("La bibliothèque 'pypdf' est requise pour lire les fichiers PDF. Installez-la via 'pip install pypdf'.") from err

    path = Path(file_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Le fichier PDF '{file_path}' n'existe pas ou est inaccessible.")

    if path.suffix.lower() != ".pdf":
        raise ValueError(f"Le fichier '{path.name}' n'est pas un document PDF (.pdf attendu).")

    if path.stat().st_size == 0:
        raise ValueError(f"Le document PDF '{path.name}' est vide (0 octet).")

    try:
        reader = PdfReader(str(path))
    except (PdfStreamError, Exception) as exc:
        raise ValueError(f"Le document PDF '{path.name}' est corrompu ou illisible : {exc}") from exc

    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except (FileNotDecryptedError, Exception) as exc:
            raise PermissionError(f"Le document PDF '{path.name}' est protégé par mot de passe.") from exc

    total_pages = len(reader.pages)
    if total_pages == 0:
        raise ValueError(f"Le document PDF '{path.name}' ne contient aucune page.")

    extracted_pages = min(total_pages, max_pages)
    pages_text: list[str] = []
    current_char_count = 0
    is_truncated = False

    # Concaténation séquentielle avec marquage explicite des numéros de pages
    for idx in range(extracted_pages):
        try:
            page_content = (reader.pages[idx].extract_text() or "").strip()
        except Exception:
            page_content = ""

        if page_content:
            header = f"--- [Page {idx + 1}/{total_pages}] ---"
            block = f"{header}\n{page_content}"
            if current_char_count + len(block) > max_chars:
                remaining = max_chars - current_char_count
                if remaining > len(header) + 10:
                    pages_text.append(block[:remaining] + "\n[... Contenu tronqué pour respecter la limite ...]")
                is_truncated = True
                break
            pages_text.append(block)
            current_char_count += len(block)

    full_text = "\n\n".join(pages_text).strip()
    if not full_text:
        raise ValueError(
            f"Aucun texte extractible trouvé dans '{path.name}'. "
            "Le document est peut-être constitué uniquement d'images scannées sans couche OCR."
        )

    if total_pages > max_pages:
        is_truncated = True

    return PDFDocumentInfo(
        file_name=path.name,
        file_path=str(path),
        total_pages=total_pages,
        extracted_pages=extracted_pages if not is_truncated else len(pages_text),
        content=full_text,
        is_truncated=is_truncated,
    )


def find_pdf_path_in_text(text: str) -> Path | None:
    """Recherche un chemin valide vers un document PDF existant dans le texte saisi.
    PARAMS: - text - STR: texte ou invite utilisateur à inspecter
    RETURN: chemin résolu vers le fichier PDF existant ou None"""
    if not text or ".pdf" not in text.lower():
        return None

    candidates: list[str] = []

    # Extraction des chemins entourés de guillemets
    quoted = re.findall(r'["\']([^"\']+\.[pP][dD][fF])["\']', text)
    candidates.extend(quoted)

    # Extraction des chemins absolus ou relatifs sans guillemets
    unquoted = re.findall(
        r'(?:^|[\s:;=<\(\[])([A-Za-z]:[\\/][^\s\r\n"\':;><\)]+\.[pP][dD][fF]|(?:\.{1,2}[\\/])?[^\s\r\n"\':;><\)]+\.[pP][dD][fF])',
        text,
    )
    candidates.extend(unquoted)

    search_dirs = [
        Path.cwd(),
        Path("manuscrit_royaumes"),
        Path("exports"),
        Path("storage"),
        Path("tests"),
    ]

    for cand in candidates:
        cleaned = cand.strip().strip("'\"")
        if not cleaned:
            continue
        direct_path = Path(cleaned)
        if direct_path.is_file():
            return direct_path.resolve()

        for s_dir in search_dirs:
            joined = s_dir / direct_path
            if joined.is_file():
                return joined.resolve()
            by_name = s_dir / direct_path.name
            if by_name.is_file():
                return by_name.resolve()

    return None


def build_pdf_correction_prompt(
    pdf_info: PDFDocumentInfo,
    custom_instruction: str | None = None,
) -> str:
    """Construit une invite de relecture et correction structurée à soumettre au LLM.
    PARAMS: - pdf_info - PDFDOCUMENTINFO: métadonnées et texte extrait du document
            - custom_instruction - STR | NONE: consigne particulière de l'utilisateur
    RETURN: invite complète formatée prête pour le modèle"""
    instructions = custom_instruction.strip() if custom_instruction and custom_instruction.strip() else (
        "Effectue une relecture complète et rigoureuse de ce document. "
        "Relève l'ensemble des fautes d'orthographe, de grammaire, de ponctuation et de syntaxe. "
        "Propose des améliorations de style et de clarté, et fournis une version corrigée des passages concernés."
    )

    truncated_warning = (
        "\n> NOTE : Le document a été partiellement extrait en raison des limites de contexte.\n"
        if pdf_info.is_truncated
        else ""
    )

    return (
        f"Tu es un relecteur et correcteur professionnel de haut niveau.{truncated_warning}\n\n"
        f"Voici le contenu extrait du document PDF '{pdf_info.file_name}' "
        f"({pdf_info.extracted_pages} page(s) extraite(s) sur un total de {pdf_info.total_pages}) :\n\n"
        f"```text\n{pdf_info.content}\n```\n\n"
        f"CONSIGNES DE TRAVAIL :\n"
        f"{instructions}\n\n"
        "FORMAT DE RÉPONSE ATTENDU :\n"
        "1. **Résumé du document** : Présentation synthétique du sujet abordé (2 à 3 phrases).\n"
        "2. **Corrections détaillées** : Tableau ou liste des erreurs détectées avec le texte original, "
        "l'explication de la faute et la correction proposée.\n"
        "3. **Remarques de style & clarté** : Conseils pour fluidifier la lecture et renforcer l'impact du texte.\n"
        "4. **Texte corrigé** : Restitution des passages améliorés ou du document corrigé."
    )


def build_pdf_historical_veracity_prompt(
    pdf_info: PDFDocumentInfo,
    user_instruction: str = "",
) -> str:
    """Construit une invite dédiée à l'audit et à la correction de la véracité historique d'un document PDF.
    PARAMS: - pdf_info - PDFDOCUMENTINFO: informations extraites du fichier
            - user_instruction - STR: question ou consigne formulée par l'utilisateur
    RETURN: invite complète avec directives d'audit historique des 7 Royaumes Combattants"""
    instruction = user_instruction.strip() if user_instruction and user_instruction.strip() else (
        "Vérifie et audite la véracité historique de ce document au regard des chroniques authentiques "
        "de la Chine ancienne (période des 7 Royaumes Combattants et unification Qin). "
        "Relève toute erreur historique (dates, noms des généraux, alliances, royaumes), "
        "corrige les effectifs militaires selon la convention Wan (x10), "
        "et propose une version corrigée et authentifiée des passages erronés."
    )
    truncated_warning = (
        "\n> [Avertissement] Le document a été extrait partiellement pour respecter le budget de contexte.\n"
        if pdf_info.is_truncated
        else ""
    )
    return (
        f"Tu es l'expert historien et conseiller stratégique des 7 Grands Royaumes Combattants (Qin, Zhao, Chu, Yan, Han, Wei, Qi).{truncated_warning}\n\n"
        f"Un document historique issu du fichier PDF '{pdf_info.file_name}' ({pdf_info.extracted_pages}/{pdf_info.total_pages} page(s) extraite(s)) t'est soumis :\n\n"
        f"=== CONTENU DU DOCUMENT PDF ===\n{pdf_info.content}\n=== FIN DU DOCUMENT PDF ===\n\n"
        f"DEMANDE DE L'UTILISATEUR :\n{instruction}\n\n"
        "CONSIGNES D'AUDIT DE VÉRACITÉ HISTORIQUE :\n"
        "1. **Confrontation aux sources antiques** : Vérifie chaque fait par rapport aux annales historiques (Shiji de Sima Qian, Zhan Guo Ce).\n"
        "2. **Relevé des inexactitudes historiques** : Liste explicitement les erreurs de dates, de noms (confusion de généraux tels que Bai Qi, Wang Jian, Li Xin, Lian Po, Li Mu), de royaumes ou d'anachronismes.\n"
        "3. **Correction des effectifs militaires** : Rectifie systématiquement par un facteur 10 les effectifs traduits littéralement de l'unité 'Wan' (10 000) (ex. 20 000 -> 200 000 soldats).\n"
        "4. **Restitution du texte corrigé** : Propose la version historiquement authentifiée et corrigée des passages erronés.\n"
        "5. **Document vivant (Artifact)** : Si un livrable d'état est actif, intègre ces faits historiques vérifiés dans l'artefact de la session."
    )


def detect_and_prepare_pdf_audit(user_input: str) -> tuple[Path, str, PDFDocumentInfo] | None:
    """Détecte la présence d'un document PDF dans la phrase utilisateur et prépare l'audit de véracité.
    PARAMS: - user_input - STR: invite ou message naturel saisi par l'utilisateur
    RETURN: tuple (chemin_pdf, consigne_extraite, infos_pdf) ou None si aucun PDF valide n'est détecté"""
    path = find_pdf_path_in_text(user_input)
    if not path:
        return None

    try:
        pdf_info = extract_text_from_pdf(path)
    except Exception:
        return None

    cleaned_prompt = user_input
    for pattern in (f'"{path}"', f"'{path}'", str(path), path.name):
        cleaned_prompt = cleaned_prompt.replace(pattern, "")

    cleaned_prompt = re.sub(r'["\']\s*["\']', "", cleaned_prompt).strip(" :;,\n\t")

    return path, cleaned_prompt, pdf_info


def read_pdf_file(file_path: str, max_pages: int = 30) -> dict[str, Any]:
    """Extrait le texte d'un PDF sous forme de dictionnaire prêt pour les outils du modèle.
    PARAMS: - file_path - STR: chemin d'accès au document PDF
            - max_pages - INT: nombre maximal de pages à parcourir
    RETURN: dictionnaire contenant le statut, les métadonnées et le texte extrait"""
    try:
        info = extract_text_from_pdf(file_path, max_pages=max_pages)
        return {
            "status": "success",
            "file_name": info.file_name,
            "file_path": info.file_path,
            "total_pages": info.total_pages,
            "extracted_pages": info.extracted_pages,
            "is_truncated": info.is_truncated,
            "content": info.content,
        }
    except Exception as exc:
        return {
            "status": "error",
            "error": str(exc),
        }

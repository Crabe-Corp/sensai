import json
from typing import Any

from src.core.db.database import (execute_db_update, get_active_diplomacy, get_kingdom_stats, query_db,)
from src.core.fs_tools import agent_read_file, agent_write_file
from src.features.tools.registry import tool


@tool
def get_kingdom_info(kingdom_name: str) -> dict[str, Any]:
    """Récupère les informations complètes d'un royaume incluant ses statistiques et ses relations diplomatiques.
            PARAMS: - kingdom_name - STR: le nom du royaume à consulter
            RETURN: dictionnaire contenant les statistiques et relations du royaume, ou une erreur"""

    stats = get_kingdom_stats(kingdom_name)
    if "error" in stats:
        return stats

    diplomacy = get_active_diplomacy(kingdom_name)
    if "error" not in diplomacy:
        stats["relations"] = diplomacy.get("relations", [])
    return stats


@tool
def read_manuscript_file(filename: str) -> dict[str, Any]:
    """Lit un fichier texte ou markdown sécurisé dans le répertoire restreint /manuscrit_royaumes.
            PARAMS: - filename - STR: nom du fichier relatif au dossier des manuscrits
            RETURN: dictionnaire contenant le statut et le contenu du fichier ou une erreur"""

    raw = agent_read_file(filename)
    try:
        return json.loads(raw)
    except Exception:
        return {"content": raw}


@tool
def write_manuscript_file(filename: str, content: str) -> dict[str, Any]:
    """Crée ou modifie un fichier dans /manuscrit_royaumes avec confirmation humaine préalable.
            PARAMS: - filename - STR: nom du fichier cible
                    - content - STR: contenu textuel à écrire
            RETURN: dictionnaire contenant le résultat de l'opération ou le motif d'annulation"""

    raw = agent_write_file(filename, content)
    try:
        return json.loads(raw)
    except Exception:
        return {"result": raw}


@tool
def query_kingdom_database(sql_query: str) -> dict[str, Any]:
    """Exécute une requête SQL de consultation en lecture seule (SELECT) sur la base de données SQLite.
            PARAMS: - sql_query - STR: requête SQL SELECT
            RETURN: dictionnaire contenant les lignes retournées ou le message d'erreur"""

    raw = query_db(sql_query)
    try:
        return json.loads(raw)
    except Exception:
        return {"data": raw}


@tool
def update_kingdom_database(sql_statement: str) -> dict[str, Any]:
    """Exécute une requête SQL d'écriture (INSERT, UPDATE, DELETE) avec confirmation humaine obligatoire.
            PARAMS: - sql_statement - STR: instruction SQL de mise à jour
            RETURN: dictionnaire contenant le statut de l'exécution"""

    raw = execute_db_update(sql_statement)
    try:
        return json.loads(raw)
    except Exception:
        return {"status": raw}


@tool
def search_historical_archives(query: str) -> dict[str, Any]:
    """Recherche des chroniques et extraits historiques pertinents dans les archives (RAG vectoriel).
            PARAMS: - query - STR: question ou mots-clés historiques à rechercher
            RETURN: dictionnaire contenant les extraits des sources d'époque trouvées"""

    try:
        from src.RAG.retriever import retrieve_rag_context

        context = retrieve_rag_context(query)
        if context:
            return {"status": "success", "context": context}
        return {"status": "empty", "message": "Aucun document historique trouvé pour cette requête."}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@tool
def read_pdf_document(file_path: str) -> dict[str, Any]:
    """Extrait et lit le contenu textuel d'un document PDF pour le relire, l'analyser ou le corriger.
            PARAMS: - file_path - STR: chemin d'accès au document PDF sur le disque
            RETURN: dictionnaire contenant les métadonnées et le contenu extrait du document ou une erreur"""

    from src.features.pdf.pdf_reader import read_pdf_file

    return read_pdf_file(file_path)


@tool
def verify_pdf_historical_veracity(file_path: str, focus_topic: str = "") -> dict[str, Any]:
    """Lit un document PDF pour vérifier et corriger sa véracité historique (Chine ancienne, 7 Royaumes Combattants).
            PARAMS: - file_path - STR: chemin d'accès au fichier PDF
                    - focus_topic - STR: point ou événement historique précis à vérifier
            RETURN: dictionnaire contenant les métadonnées, le texte extrait et les directives d'audit"""

    from src.features.pdf.pdf_reader import read_pdf_file

    res = read_pdf_file(file_path)
    if res.get("status") == "success":
        res["instructions"] = (
            "Vérifie la conformité avec les chroniques des Royaumes Combattants (Shiji, Zhan Guo Ce), "
            "corrige les effectifs de troupes (Wan x10), les dates et les attributions de batailles."
        )
        if focus_topic:
            res["focus_topic"] = focus_topic
    return res


@tool
def generate_pdf_document(filename: str, title: str, content: str, author: str = "SENSAI Historical Advisor",) -> dict[str, Any]:
    """Génère et exporte un document PDF complet mis en page (biographie, chronique, rapport de bataille).
            PARAMS: - filename - STR: nom du fichier PDF à créer (ex: 'qin_shi_huang_biography.pdf', enregistré dans exports/)
                    - title - STR: titre principal du document PDF
                    - content - STR: texte complet structuré en paragraphes ou markdown à intégrer dans le PDF
                    - author - STR: nom de l'auteur ou conseiller émetteur
            RETURN: dictionnaire contenant le statut, le chemin d'accès, la taille et le nombre de pages du document généré"""

    from src.features.pdf.pdf_generator import generate_pdf

    try:
        result = generate_pdf(file_path=filename, title=title, content=content, author=author)
        return result.model_dump()
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


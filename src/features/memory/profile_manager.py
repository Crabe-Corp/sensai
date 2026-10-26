import json
import os
import re
from pathlib import Path
from pydantic import BaseModel, Field


class UserProfile(BaseModel):
    username: str = "default"
    tone: str = "scribe antique"
    conciseness: str = "équilibré"
    language: str = "français"
    custom_instructions: str = "Tu t'adresses à un apprenti historien passionné par la dynastie Qin et les Royaumes combattants."
    facts: list[str] = Field(default_factory=list)

    def format_system_prompt(self) -> str:
        """Génère le bloc de consignes système injecté au démarrage de la session.
        PARAMS: Aucun
        RETURN: chaîne de caractères formatée pour le rôle système"""
        lines = [
            f"[Profil Utilisateur : {self.username}]",
            f"- Style et ton : {self.tone}",
            f"- Niveau de concision : {self.conciseness}",
            f"- Langue d'échange : {self.language}",
        ]
        if self.custom_instructions:
            lines.append(f"- Instructions personnalisées : {self.custom_instructions}")
        if self.facts:
            facts_rendered = "\n".join(f"  * {fact}" for fact in self.facts)
            lines.append(f"- Faits permanents connus :\n{facts_rendered}")
        return "\n".join(lines)


class ProfileManager:
    def __init__(self, storage_dir: Path | str = "storage/profiles") -> None:
        """Initialise le gestionnaire de profils et crée le répertoire de stockage si nécessaire.
        PARAMS: - storage_dir - PATH | STR: répertoire de persistance des profils JSON
        RETURN: None"""
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _sanitize_username(self, username: str) -> str:
        """Nettoie le nom d'utilisateur pour sécuriser le nom de fichier sur le disque.
                PARAMS: - username - STR: nom d'utilisateur brut
                RETURN: nom d'utilisateur nettoyé et sécurisé"""
        sanitized = re.sub(r"[^\w\-.]", "_", username.strip())
        return sanitized or "default"

    def _get_profile_path(self, username: str) -> Path:
        """Construit le chemin d'accès au fichier JSON associé au profil utilisateur.
                PARAMS: - username - STR: nom d'utilisateur recherché
                RETURN: chemin Path vers le fichier JSON du profil"""
        clean_name = self._sanitize_username(username)
        return self.storage_dir / f"{clean_name}.json"

    def save_profile(self, profile: UserProfile) -> Path:
        """Sauvegarde atomique d'un profil utilisateur au format JSON.
        PARAMS: - profile - USERPROFILE: profil à sérialiser
        RETURN: chemin vers le fichier sauvegardé"""
        target_path = self._get_profile_path(profile.username)
        temp_path = self.storage_dir / f"{target_path.name}.tmp.{os.getpid()}"

        payload = profile.model_dump_json(indent=2)
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(payload)
        os.replace(temp_path, target_path)
        return target_path

    def load_profile(self, username: str) -> UserProfile:
        """Charge un profil existant depuis le stockage disque.
        PARAMS: - username - STR: identifiant du profil recherché
        RETURN: instance UserProfile désérialisée"""
        path = self._get_profile_path(username)
        if not path.is_file():
            raise FileNotFoundError(f"Profil utilisateur '{username}' introuvable dans {self.storage_dir}")
        with open(path, "r", encoding="utf-8") as f:
            return UserProfile.model_validate_json(f.read())

    def get_or_create_profile(self, username: str = "default") -> UserProfile:
        """Récupère un profil ou l'initialise avec des valeurs par défaut s'il n'existe pas.
        PARAMS: - username - STR: identifiant du profil demandé
        RETURN: instance UserProfile existante ou nouvellement créée"""
        clean_name = self._sanitize_username(username)
        path = self._get_profile_path(clean_name)
        if path.is_file():
            try:
                return self.load_profile(clean_name)
            except Exception:
                pass
        profile = UserProfile(username=clean_name)
        self.save_profile(profile)
        return profile

    def list_profiles(self) -> list[str]:
        """Retourne les identifiants de tous les profils JSON disponibles.
        PARAMS: Aucun
        RETURN: liste des noms d'utilisateurs triée"""
        profiles = [p.stem for p in self.storage_dir.glob("*.json")]
        return sorted(profiles)

    def delete_profile(self, username: str) -> bool:
        """Supprime le fichier de profil persistant associé à l'utilisateur.
        PARAMS: - username - STR: identifiant du profil à supprimer
        RETURN: True si supprimé avec succès, False si inexistant"""
        path = self._get_profile_path(username)
        if path.is_file():
            path.unlink()
            return True
        return False

from typing import Any, Literal
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

RoleType = Literal["stratège", "général", "légiste", "souverain"]


class KingdomInfo(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    nom: str = Field(
        ...,
        validation_alias=AliasChoices("nom", "name"),
        description="Nom officiel du royaume (ex: Qin, Zhao, Chu, Han, Wei, Qi, Yan)",
    )
    capitale: str = Field(
        ...,
        validation_alias=AliasChoices("capitale", "capital"),
        description="Capitale historique et centre administratif du royaume",
    )
    souverain: str = Field(
        ...,
        validation_alias=AliasChoices("souverain", "ruler"),
        description="Nom du souverain régnant ou dirigeant marquant du royaume",
    )
    puissance_militaire: int = Field(
        ...,
        validation_alias=AliasChoices("puissance_militaire", "military_power"),
        ge=1,
        le=100,
        description="Puissance militaire globale estimée sur une échelle de 1 à 100",
    )
    specialite_strategique: str = Field(
        ...,
        validation_alias=AliasChoices("specialite_strategique", "strategic_specialty"),
        description="Spécialité stratégique ou tactique de l'armée du royaume",
    )
    description: str = Field(
        ...,
        description="Description synthétique du royaume et de sa position géopolitique",
    )

    @property
    def name(self) -> str:
        return self.nom

    @property
    def capital(self) -> str:
        return self.capitale

    @property
    def ruler(self) -> str:
        return self.souverain

    @property
    def military_power(self) -> int:
        return self.puissance_militaire

    @property
    def strategic_specialty(self) -> str:
        return self.specialite_strategique


class HistoricalFigure(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    nom: str = Field(
        ...,
        validation_alias=AliasChoices("nom", "name"),
        description="Nom du personnage historique de la période des Royaumes combattants",
    )
    royaume_origine: str = Field(
        ...,
        validation_alias=AliasChoices("royaume_origine", "royaume_d_origine", "origin_kingdom"),
        description="Royaume d'origine ou d'allégeance du personnage historique",
    )
    role: RoleType = Field(
        ...,
        description="Rôle dominant : stratège, général, légiste ou souverain",
    )
    faits_marquants: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("faits_marquants", "facts", "notable_facts", "notable_actions"),
        description="Liste des faits marquants et accomplissements majeurs",
    )

    @field_validator("role", mode="before")
    @classmethod
    def _normalize_role(cls, value: Any) -> Any:
        """Normalise le rôle d'un personnage historique vers l'une des valeurs admises.
                PARAMS: - value - ANY: valeur brute du rôle reçue
                RETURN: chaîne normalisée ou valeur d'origine inchangée"""
        if isinstance(value, str):
            mapping = {
                "general": "général",
                "général": "général",
                "stratege": "stratège",
                "stratège": "stratège",
                "strategist": "stratège",
                "legiste": "légiste",
                "légiste": "légiste",
                "legalist": "légiste",
                "souverain": "souverain",
                "ruler": "souverain",
                "king": "souverain",
                "empereur": "souverain",
            }
            return mapping.get(value.strip().lower(), value)
        return value

    @property
    def name(self) -> str:
        return self.nom

    @property
    def origin_kingdom(self) -> str:
        return self.royaume_origine

    @property
    def facts(self) -> list[str]:
        return self.faits_marquants

    @property
    def notable_facts(self) -> list[str]:
        return self.faits_marquants

class StructuredResponse(BaseModel):
    response: str = Field(
        ...,
        description="Réponse textuelle de l'assistant",
    )

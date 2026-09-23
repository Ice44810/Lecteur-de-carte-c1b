"""Configuration des seuils du moteur de regles.

Trois exigences du cahier des charges sont satisfaites ici :

* **les regles sont configurables** : les seuils vivent dans un fichier JSON
  modifiable, pas dans le code ;
* **aucun seuil sans source** : le champ ``source`` est obligatoire et non vide ;
* **aucun seuil non verifie n'est applique** : un parametre dont l'etat de
  confirmation n'est pas ``CONFIRMED`` ne peut pas etre utilise par une evaluation
  (:meth:`RuleSet.require` leve une erreur explicite).

Consequence assumee pour cette version : le jeu de regles livre par defaut est
**vide**. L'application ne signalera donc aucun depassement tant que les seuils
n'auront pas ete saisis et confirmes a partir des textes officiels. C'est un choix
delibere : afficher des depassements calcules sur des seuils devines serait plus
dangereux que de n'en afficher aucun.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config.logging_config import get_logger
from app.core.exceptions import RuleConfigurationError
from app.parser.specification import ConfirmationStatus

__all__ = ["RuleParameter", "RuleSet", "load_ruleset", "save_ruleset", "empty_ruleset"]

logger = get_logger(__name__)

RULESET_FILENAME = "rules.json"
"""Nom du fichier de configuration des regles, dans le repertoire de donnees."""


class RuleParameter(BaseModel):
    """Seuil configurable d'une regle.

    Attributes:
        code: Identifiant du parametre, reference par les regles.
        label: Libelle affichable dans les parametres de l'application.
        value: Valeur du seuil.
        unit: Unite de la valeur (``seconds``, ``count``, ``km`` ...).
        source: Reference du texte fixant ce seuil. Obligatoire.
        status: Etat de verification de la valeur face a sa source.
        notes: Precisions ou reserves sur l'interpretation du seuil.
    """

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    code: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=200)
    value: float
    unit: str = Field(default="seconds", min_length=1, max_length=16)
    source: str = Field(min_length=10, max_length=500)
    status: ConfirmationStatus = ConfirmationStatus.OPEN
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("code")
    @classmethod
    def _normalize_code(cls, value: str) -> str:
        """Normalise le code en majuscules."""
        return value.upper()

    @property
    def is_usable(self) -> bool:
        """Indique que le parametre peut etre applique a une evaluation."""
        return self.status is ConfirmationStatus.CONFIRMED


class RuleSet(BaseModel):
    """Jeu de parametres applique par le moteur de regles.

    Attributes:
        version: Version du jeu de regles, enregistree avec chaque analyse pour
            permettre de retracer quels seuils ont ete appliques.
        parameters: Parametres indexes par code.
    """

    model_config = ConfigDict(frozen=True)

    version: str = Field(default="0.0.0-empty", min_length=1, max_length=32)
    parameters: dict[str, RuleParameter] = Field(default_factory=dict)

    @field_validator("parameters")
    @classmethod
    def _check_keys(cls, value: dict[str, RuleParameter]) -> dict[str, RuleParameter]:
        """Verifie la coherence entre les cles et les codes de parametres."""
        for key, parameter in value.items():
            if key.upper() != parameter.code:
                raise ValueError(
                    f"la cle '{key}' ne correspond pas au code du parametre "
                    f"'{parameter.code}'"
                )
        return {key.upper(): parameter for key, parameter in value.items()}

    def get(self, code: str) -> RuleParameter | None:
        """Retourne un parametre, ou ``None`` s'il n'est pas defini."""
        return self.parameters.get(code.upper())

    def require(self, code: str) -> RuleParameter:
        """Retourne un parametre utilisable, ou echoue avec un message explicite.

        Args:
            code: Code du parametre recherche.

        Returns:
            Le parametre demande.

        Raises:
            RuleConfigurationError: Le parametre est absent, ou sa valeur n'a pas
                encore ete confirmee face a sa source.
        """
        parameter = self.get(code)
        if parameter is None:
            raise RuleConfigurationError(
                "Un seuil necessaire a l'analyse n'est pas configure.",
                cause=f"Le parametre « {code} » n'existe pas dans le jeu de regles.",
                action=(
                    "Renseignez ce seuil dans Parametres > Regles, en indiquant le texte "
                    "de reference qui le fixe."
                ),
            )
        if not parameter.is_usable:
            raise RuleConfigurationError(
                "Un seuil necessaire a l'analyse n'est pas encore verifie.",
                cause=(
                    f"Le parametre « {parameter.label} » est a l'etat "
                    f"« {parameter.status.label} » : sa valeur n'a pas ete confirmee "
                    "face a sa source."
                ),
                action=(
                    "Verifiez la valeur avec le texte cite, puis marquez le parametre "
                    "comme confirme dans Parametres > Regles."
                ),
                technical_detail=f"{parameter.code} source='{parameter.source}'",
            )
        return parameter

    def seconds(self, code: str) -> int:
        """Retourne un seuil exprime en secondes.

        Args:
            code: Code du parametre.

        Returns:
            La valeur entiere en secondes.

        Raises:
            RuleConfigurationError: Le parametre est inutilisable ou n'est pas
                exprime en secondes.
        """
        parameter = self.require(code)
        if parameter.unit != "seconds":
            raise RuleConfigurationError(
                "Un seuil de duree est mal configure.",
                cause=(
                    f"Le parametre « {parameter.label} » est exprime en "
                    f"« {parameter.unit} » alors qu'une duree est attendue."
                ),
                action="Corrigez l'unite de ce parametre dans Parametres > Regles.",
            )
        return int(parameter.value)

    @property
    def usable_parameters(self) -> dict[str, RuleParameter]:
        """Parametres confirmes, donc applicables."""
        return {
            code: parameter for code, parameter in self.parameters.items() if parameter.is_usable
        }

    @property
    def is_empty(self) -> bool:
        """Indique qu'aucun parametre applicable n'est configure."""
        return not self.usable_parameters


def empty_ruleset() -> RuleSet:
    """Retourne le jeu de regles livre par defaut : vide.

    Aucun seuil reglementaire n'est distribue avec le logiciel tant qu'il n'a pas ete
    verifie contre son texte de reference. L'application fonctionne, archive et
    analyse les temps ; elle ne signale simplement aucun depassement.

    Returns:
        Un jeu de regles sans parametre.
    """
    return RuleSet(version="0.0.0-empty", parameters={})


def load_ruleset(path: Path) -> RuleSet:
    """Charge un jeu de regles depuis un fichier JSON.

    Args:
        path: Chemin du fichier de configuration.

    Returns:
        Le jeu de regles charge, ou :func:`empty_ruleset` si le fichier est absent.

    Raises:
        RuleConfigurationError: Le fichier est illisible ou invalide.
    """
    if not path.is_file():
        logger.info("Aucun fichier de regles a %s : jeu de regles vide applique", path)
        return empty_ruleset()
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuleConfigurationError(
            "Le fichier de configuration des regles n'a pas pu etre lu.",
            cause="Le fichier est inaccessible ou son contenu n'est pas un JSON valide.",
            action=f"Corrigez ou supprimez le fichier {path.name} puis relancez l'analyse.",
            technical_detail=str(exc),
        ) from exc
    try:
        ruleset = RuleSet.model_validate(payload)
    except ValueError as exc:
        raise RuleConfigurationError(
            "Le fichier de configuration des regles est invalide.",
            cause="Un parametre est incomplet : chaque seuil doit citer sa source.",
            action=f"Corrigez le fichier {path.name} puis relancez l'analyse.",
            technical_detail=str(exc),
        ) from exc
    logger.info(
        "Jeu de regles %s charge : %d parametre(s), dont %d applicable(s)",
        ruleset.version,
        len(ruleset.parameters),
        len(ruleset.usable_parameters),
    )
    return ruleset


def save_ruleset(ruleset: RuleSet, path: Path) -> None:
    """Enregistre un jeu de regles au format JSON.

    Args:
        ruleset: Jeu de regles a enregistrer.
        path: Chemin de destination.

    Raises:
        RuleConfigurationError: Le fichier n'a pas pu etre ecrit.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(ruleset.model_dump(mode="json"), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError as exc:
        raise RuleConfigurationError(
            "La configuration des regles n'a pas pu etre enregistree.",
            cause="Le fichier de configuration n'est pas accessible en ecriture.",
            action="Verifiez les droits sur le repertoire de donnees.",
            technical_detail=str(exc),
        ) from exc
    logger.info("Jeu de regles %s enregistre dans %s", ruleset.version, path)

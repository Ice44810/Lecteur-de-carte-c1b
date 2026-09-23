"""Modeles de DONNEE DECODEE produits par les parsers.

Ces modeles constituent le contrat entre la couche de decodage et la couche
metier. Ils sont volontairement independants de SQLAlchemy : un parser ne connait
pas la base de donnees, et le service d'import est seul responsable de la
transformation ``donnee decodee -> donnee metier``.

Deux principes structurent ces modeles :

* **aucun champ n'est devine** : tout champ non decode vaut ``None``, jamais une
  valeur par defaut plausible ;
* **tout doute est trace** : chaque resultat de decodage transporte la liste de ses
  diagnostics (:class:`ParseDiagnostic`) ainsi que les blocs non reconnus, afin que
  l'utilisateur sache exactement ce qui a ete lu et ce qui a ete ignore.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.enums import ActivityType, FileType

__all__ = [
    "DiagnosticLevel",
    "ParseDiagnostic",
    "RawBlock",
    "DecodedDriverIdentification",
    "DecodedVehicleIdentification",
    "DecodedActivityPeriod",
    "DecodedEvent",
    "DecodedTechnicalData",
    "ParseResult",
]


class DiagnosticLevel(StrEnum):
    """Gravite d'un diagnostic de decodage.

    Attributes:
        INFO: Information sur le deroulement du decodage.
        WARNING: Donnee ignoree ou structure inconnue rencontree.
        ERROR: Decodage interrompu pour la structure concernee.
    """

    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"

    @property
    def label(self) -> str:
        """Libelle affichable."""
        return {
            DiagnosticLevel.INFO: "Information",
            DiagnosticLevel.WARNING: "Avertissement",
            DiagnosticLevel.ERROR: "Erreur",
        }[self]


class ParseDiagnostic(BaseModel):
    """Observation faite pendant le decodage d'un fichier.

    Attributes:
        level: Gravite de l'observation.
        code: Code stable, exploitable par les tests et l'interface.
        message: Message lisible par un exploitant.
        offset: Position dans le fichier, si pertinent.
        detail: Complement technique destine au journal.
    """

    model_config = ConfigDict(frozen=True)

    level: DiagnosticLevel
    code: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1)
    offset: int | None = Field(default=None, ge=0)
    detail: str | None = None


class RawBlock(BaseModel):
    """Bloc de donnee brute isole mais non interprete.

    Conserver ces blocs est essentiel : lorsqu'une structure n'est pas encore
    confirmee par une specification officielle, l'application doit pouvoir montrer
    ce qu'elle a vu sans en inventer le sens.

    Attributes:
        tag: Identifiant du bloc tel que lu dans le fichier (en hexadecimal).
        offset: Position de debut du bloc dans le fichier.
        length: Longueur du bloc en octets.
        interpreted: Indique si le contenu du bloc a ete decode.
    """

    model_config = ConfigDict(frozen=True)

    tag: str = Field(min_length=1, max_length=32)
    offset: int = Field(ge=0)
    length: int = Field(ge=0)
    interpreted: bool = False


class DecodedDriverIdentification(BaseModel):
    """Identification du titulaire d'une carte conducteur.

    Seul ``card_number`` est obligatoire : c'est l'identifiant metier du
    conducteur. Tous les autres champs restent ``None`` tant qu'ils n'ont pas ete
    effectivement lus dans le fichier.
    """

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    card_number: str = Field(min_length=1, max_length=32)
    first_name: str | None = Field(default=None, max_length=64)
    last_name: str | None = Field(default=None, max_length=64)
    birth_date: date | None = None
    card_issuing_country: str | None = Field(default=None, max_length=3)
    card_issue_date: date | None = None
    card_expiry_date: date | None = None

    @model_validator(mode="after")
    def _check_card_dates(self) -> DecodedDriverIdentification:
        """Verifie la coherence des dates de la carte."""
        if (
            self.card_issue_date is not None
            and self.card_expiry_date is not None
            and self.card_expiry_date < self.card_issue_date
        ):
            raise ValueError(
                "la date d'expiration de la carte precede sa date de delivrance"
            )
        return self


class DecodedVehicleIdentification(BaseModel):
    """Identification d'un vehicule lue dans un fichier tachygraphique."""

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    registration: str = Field(min_length=1, max_length=24)
    registration_country: str | None = Field(default=None, max_length=3)
    vin: str | None = Field(default=None, max_length=24)
    tachograph_identifier: str | None = Field(default=None, max_length=64)


class DecodedActivityPeriod(BaseModel):
    """Periode d'activite decodee, avant enregistrement en base.

    Attributes:
        activity_type: Nature de l'activite.
        start: Debut de la periode (UTC).
        end: Fin de la periode (UTC).
        vehicle_registration: Immatriculation associee, si connue.
        card_slot: Emplacement de carte (1 conducteur, 2 convoyeur), si connu.
    """

    model_config = ConfigDict(frozen=True)

    activity_type: ActivityType
    start: datetime
    end: datetime
    vehicle_registration: str | None = Field(default=None, max_length=24)
    card_slot: int | None = Field(default=None, ge=1, le=2)

    @model_validator(mode="after")
    def _check_bounds(self) -> DecodedActivityPeriod:
        """Refuse une periode dont la fin precede le debut."""
        if self.end < self.start:
            raise ValueError("la fin d'une periode d'activite ne peut pas preceder son debut")
        return self

    @property
    def duration_seconds(self) -> int:
        """Duree de la periode en secondes."""
        from app.core.timeutils import seconds_between

        return seconds_between(self.start, self.end)


class DecodedEvent(BaseModel):
    """Evenement ou anomalie technique enregistre par l'equipement.

    Le ``event_type_code`` est conserve tel quel : la table de correspondance des
    types d'evenements devra etre reprise de la specification officielle avant
    toute traduction en libelle (voir ``docs/SPECIFICATION_C1B.md``).
    """

    model_config = ConfigDict(frozen=True)

    event_type_code: str = Field(min_length=1, max_length=32)
    begin: datetime
    end: datetime | None = None
    vehicle_registration: str | None = Field(default=None, max_length=24)
    description: str | None = None


class DecodedTechnicalData(BaseModel):
    """Donnees techniques (etalonnages, controles) lues dans le fichier."""

    model_config = ConfigDict(frozen=True)

    card_number: str | None = Field(default=None, max_length=32)
    download_datetime: datetime | None = None
    generation: str | None = Field(
        default=None,
        max_length=16,
        description="Generation de l'equipement, si identifiable de maniere fiable.",
    )
    raw_blocks: tuple[RawBlock, ...] = ()


class ParseResult(BaseModel):
    """Resultat complet du decodage d'un fichier tachygraphique.

    Un resultat est toujours retourne, meme partiel : un decodage incomplet reste
    exploitable et doit rester visible par l'utilisateur, plutot que d'etre
    transforme en echec silencieux.
    """

    model_config = ConfigDict(frozen=True)

    file_type: FileType
    driver: DecodedDriverIdentification | None = None
    vehicle: DecodedVehicleIdentification | None = None
    activities: tuple[DecodedActivityPeriod, ...] = ()
    events: tuple[DecodedEvent, ...] = ()
    technical_data: DecodedTechnicalData | None = None
    diagnostics: tuple[ParseDiagnostic, ...] = ()
    raw_blocks: tuple[RawBlock, ...] = ()
    is_complete: bool = Field(
        default=False,
        description=(
            "Vrai uniquement si toutes les structures du fichier ont ete "
            "reconnues et decodees."
        ),
    )

    @field_validator("activities")
    @classmethod
    def _sort_activities(
        cls, value: tuple[DecodedActivityPeriod, ...]
    ) -> tuple[DecodedActivityPeriod, ...]:
        """Trie les activites par date de debut."""
        return tuple(sorted(value, key=lambda period: period.start))

    @property
    def has_errors(self) -> bool:
        """Indique la presence d'au moins un diagnostic de niveau ERROR."""
        return any(item.level is DiagnosticLevel.ERROR for item in self.diagnostics)

    @property
    def has_warnings(self) -> bool:
        """Indique la presence d'au moins un diagnostic de niveau WARNING."""
        return any(item.level is DiagnosticLevel.WARNING for item in self.diagnostics)

    @property
    def uninterpreted_blocks(self) -> tuple[RawBlock, ...]:
        """Blocs isoles dont le contenu n'a pas ete decode."""
        return tuple(block for block in self.raw_blocks if not block.interpreted)

    def summary(self) -> str:
        """Retourne un resume lisible du decodage, affichable dans l'interface."""
        parts = [f"{len(self.activities)} periode(s) d'activite"]
        if self.driver is not None:
            parts.append("conducteur identifie")
        if self.vehicle is not None:
            parts.append("vehicule identifie")
        if self.events:
            parts.append(f"{len(self.events)} evenement(s)")
        uninterpreted = len(self.uninterpreted_blocks)
        if uninterpreted:
            parts.append(f"{uninterpreted} bloc(s) non interprete(s)")
        return ", ".join(parts)

"""Contrat commun des parsers de fichiers tachygraphiques.

Chaine de traitement, une couche par etage :

.. code-block:: text

    BinaryReader  ->  structures binaires  ->  decodage des champs
                  ->  modeles decodes (app.parser.models)  ->  base de donnees

Le parser s'arrete au modele decode : il n'ecrit jamais en base. Cette separation
permet de tester le decodage sans base de donnees, et de rejouer un decodage sur un
fichier archive sans risque d'effet de bord.

Les methodes d'extraction sont autorisees a lever
:class:`~app.core.exceptions.UnconfirmedStructureError` lorsque la structure
concernee n'est pas encore confirmee par une source officielle. La methode
:meth:`TachographFileParser.parse` les rattrape et produit un resultat **partiel
mais honnete**, accompagne des diagnostics correspondants.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from app.config.logging_config import get_logger
from app.core.enums import FileType
from app.core.exceptions import ParsingError, StorageError, UnconfirmedStructureError
from app.parser.binary_reader import BinaryReader
from app.parser.models import (
    DecodedActivityPeriod,
    DecodedDriverIdentification,
    DecodedEvent,
    DecodedTechnicalData,
    DecodedVehicleIdentification,
    DiagnosticLevel,
    ParseDiagnostic,
    ParseResult,
)
from app.parser.specification import OpenQuestion, questions_for

__all__ = ["TachographFileParser", "MINIMUM_PLAUSIBLE_SIZE"]

logger = get_logger(__name__)

MINIMUM_PLAUSIBLE_SIZE = 16
"""Taille minimale en octets en dessous de laquelle un fichier ne peut rien contenir.

Ce seuil ne pretend pas valider le format : il ne sert qu'a rejeter immediatement un
fichier vide ou tronque a quelques octets, sans faire d'hypothese sur la structure.
"""


class TachographFileParser(ABC):
    """Classe de base des parsers.

    Args:
        data: Contenu binaire complet du fichier.
        filename: Nom d'origine du fichier, utilise dans les messages.
    """

    file_type: FileType
    """Type de fichier pris en charge par le parser."""

    specification_topic: str
    """Domaine du registre d'incertitudes associe (voir ``app.parser.specification``)."""

    def __init__(self, data: bytes, *, filename: str | None = None) -> None:
        self._data = bytes(data)
        self._filename = filename or "(flux en memoire)"

    # ------------------------------------------------------------------ #
    # Construction
    # ------------------------------------------------------------------ #
    @classmethod
    def from_path(cls, path: Path | str) -> TachographFileParser:
        """Construit un parser a partir d'un fichier sur disque.

        Le fichier est ouvert en lecture seule et n'est jamais modifie.

        Args:
            path: Chemin du fichier a decoder.

        Returns:
            Une instance de parser.

        Raises:
            StorageError: Le fichier est introuvable ou illisible.
        """
        file_path = Path(path)
        try:
            payload = file_path.read_bytes()
        except FileNotFoundError as exc:
            raise StorageError(
                f"Le fichier {file_path.name} est introuvable.",
                cause="Le fichier a ete deplace ou supprime.",
                action="Verifiez l'emplacement du fichier archive.",
                technical_detail=str(exc),
            ) from exc
        except OSError as exc:
            raise StorageError(
                f"Le fichier {file_path.name} n'a pas pu etre lu.",
                cause="Les droits d'acces sont insuffisants ou le support est indisponible.",
                action="Verifiez les permissions du fichier.",
                technical_detail=str(exc),
            ) from exc
        return cls(payload, filename=file_path.name)

    # ------------------------------------------------------------------ #
    # Proprietes
    # ------------------------------------------------------------------ #
    @property
    def filename(self) -> str:
        """Nom du fichier en cours de decodage."""
        return self._filename

    @property
    def size(self) -> int:
        """Taille du contenu, en octets."""
        return len(self._data)

    @property
    def decoding_available(self) -> bool:
        """Indique si le decodage complet est disponible dans cette version.

        Retourne ``False`` tant qu'une question bloquante du registre
        d'incertitudes n'est pas confirmee. L'interface s'appuie sur cette
        propriete pour expliquer clairement a l'utilisateur pourquoi un fichier est
        archive sans etre decode.
        """
        from app.parser.specification import is_confirmed

        return is_confirmed(self.specification_topic)

    @property
    def blocking_questions(self) -> tuple[OpenQuestion, ...]:
        """Questions de specification bloquant le decodage de ce format."""
        return questions_for(self.specification_topic, blocking_only=True)

    def reader(self, *, offset: int = 0) -> BinaryReader:
        """Cree un lecteur binaire positionne sur le contenu du fichier."""
        return BinaryReader(self._data, offset=offset)

    # ------------------------------------------------------------------ #
    # Validation
    # ------------------------------------------------------------------ #
    def validate(self) -> list[ParseDiagnostic]:
        """Verifie les proprietes du fichier independantes du format.

        Ne valide **pas** la structure interne : cette methode se limite aux
        controles que l'on peut faire sans hypothese sur le format (fichier non
        vide, taille plausible). Les parsers concrets peuvent l'enrichir via
        :meth:`_validate_format`.

        Returns:
            La liste des diagnostics non bloquants constates.

        Raises:
            ParsingError: Le fichier est vide ou manifestement tronque.
        """
        if self.size == 0:
            raise ParsingError(
                f"Le fichier {self._filename} est vide.",
                cause="Le fichier ne contient aucune donnee (0 octet).",
                action=(
                    "Recommencez le telechargement depuis la carte ou l'unite embarquee, "
                    "puis importez le nouveau fichier."
                ),
            )
        if self.size < MINIMUM_PLAUSIBLE_SIZE:
            raise ParsingError(
                f"Le fichier {self._filename} est trop petit pour etre exploitable.",
                cause=f"Le fichier ne contient que {self.size} octets.",
                action="Verifiez que le telechargement s'est termine normalement.",
                technical_detail=f"taille {self.size} < minimum {MINIMUM_PLAUSIBLE_SIZE}",
            )
        return list(self._validate_format())

    def _validate_format(self) -> list[ParseDiagnostic]:
        """Controles specifiques au format, a surcharger si necessaire.

        Returns:
            Des diagnostics non bloquants. Par defaut, aucun.
        """
        return []

    # ------------------------------------------------------------------ #
    # Extraction (implementee par les parsers concrets)
    # ------------------------------------------------------------------ #
    @abstractmethod
    def extract_driver(self) -> DecodedDriverIdentification | None:
        """Extrait l'identification du conducteur.

        Returns:
            L'identification decodee, ou ``None`` si le fichier n'en contient pas.

        Raises:
            UnconfirmedStructureError: La structure n'est pas encore confirmee.
        """

    @abstractmethod
    def extract_vehicle(self) -> DecodedVehicleIdentification | None:
        """Extrait l'identification du vehicule.

        Raises:
            UnconfirmedStructureError: La structure n'est pas encore confirmee.
        """

    @abstractmethod
    def extract_activities(self) -> tuple[DecodedActivityPeriod, ...]:
        """Extrait les periodes d'activite.

        Raises:
            UnconfirmedStructureError: La structure n'est pas encore confirmee.
        """

    @abstractmethod
    def extract_events(self) -> tuple[DecodedEvent, ...]:
        """Extrait les evenements et anomalies techniques.

        Raises:
            UnconfirmedStructureError: La structure n'est pas encore confirmee.
        """

    @abstractmethod
    def extract_technical_data(self) -> DecodedTechnicalData | None:
        """Extrait les donnees techniques (etalonnages, telechargement).

        Raises:
            UnconfirmedStructureError: La structure n'est pas encore confirmee.
        """

    # ------------------------------------------------------------------ #
    # Orchestration
    # ------------------------------------------------------------------ #
    def parse(self) -> ParseResult:
        """Decode le fichier et retourne un resultat, meme partiel.

        Chaque extraction est tentee independamment : une structure non confirmee ou
        en echec produit un diagnostic, sans empecher les autres extractions. Le
        fichier original n'est jamais modifie.

        Returns:
            Le resultat du decodage. ``is_complete`` ne vaut ``True`` que si toutes
            les extractions ont abouti sans avertissement.

        Raises:
            ParsingError: Le fichier est vide ou trop petit (echec de validation).
        """
        diagnostics = self.validate()

        driver, diagnostics_driver = self._attempt("driver", self.extract_driver)
        vehicle, diagnostics_vehicle = self._attempt("vehicle", self.extract_vehicle)
        activities, diagnostics_activities = self._attempt("activities", self.extract_activities)
        events, diagnostics_events = self._attempt("events", self.extract_events)
        technical, diagnostics_technical = self._attempt(
            "technical_data", self.extract_technical_data
        )

        diagnostics.extend(
            diagnostics_driver
            + diagnostics_vehicle
            + diagnostics_activities
            + diagnostics_events
            + diagnostics_technical
        )

        result = ParseResult(
            file_type=self.file_type,
            driver=driver,
            vehicle=vehicle,
            activities=tuple(activities or ()),
            events=tuple(events or ()),
            technical_data=technical,
            diagnostics=tuple(diagnostics),
            is_complete=not any(
                item.level in (DiagnosticLevel.WARNING, DiagnosticLevel.ERROR)
                for item in diagnostics
            ),
        )
        logger.info(
            "Decodage de %s termine : %s (complet: %s)",
            self._filename,
            result.summary(),
            result.is_complete,
        )
        return result

    def _attempt(self, section: str, extractor: object) -> tuple[object, list[ParseDiagnostic]]:
        """Execute une extraction en capturant les incertitudes et les erreurs.

        Args:
            section: Nom de la section decodee, utilise dans les diagnostics.
            extractor: Methode d'extraction a appeler.

        Returns:
            Un couple ``(valeur, diagnostics)``. La valeur vaut ``None`` en cas
            d'echec de la section.
        """
        assert callable(extractor)
        try:
            return extractor(), []
        except UnconfirmedStructureError as exc:
            logger.warning(
                "Section '%s' de %s non decodee : structure a confirmer",
                section,
                self._filename,
            )
            return None, [
                ParseDiagnostic(
                    level=DiagnosticLevel.WARNING,
                    code="STRUCTURE_NOT_CONFIRMED",
                    message=(
                        f"La section '{section}' n'a pas ete decodee : "
                        "sa structure doit d'abord etre confirmee par la specification "
                        "officielle."
                    ),
                    detail=exc.technical_detail,
                )
            ]
        except ParsingError as exc:
            logger.error("Section '%s' de %s en echec : %s", section, self._filename, exc)
            return None, [
                ParseDiagnostic(
                    level=DiagnosticLevel.ERROR,
                    code="SECTION_DECODE_FAILED",
                    message=f"La section '{section}' n'a pas pu etre decodee : {exc.message}",
                    detail=exc.technical_detail,
                )
            ]

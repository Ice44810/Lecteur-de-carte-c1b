"""Parser de fichiers V1B (telechargement d'unite embarquee / vehicule).

Meme etat d'avancement que le parser C1B : l'architecture est en place, le
decodage attend la confirmation des structures binaires (phase 10 de la feuille de
route).

TODO : "Structure a confirmer avec specification officielle / fichier V1B de test."

Chaine cible, identique au C1B a l'exception de l'entite pivot :

.. code-block:: text

    V1B -> parser -> vehicule -> activites -> evenements -> analyse

L'interface et la base sont deja pretes a accueillir ce format : ``FileType.V1B``
existe, ``Activity.vehicle_id`` est renseignable, et la page d'import propose deja
le type V1B.
"""

from __future__ import annotations

from app.core.enums import FileType
from app.core.exceptions import UnconfirmedStructureError
from app.parser.base import TachographFileParser
from app.parser.models import (
    DecodedActivityPeriod,
    DecodedDriverIdentification,
    DecodedEvent,
    DecodedTechnicalData,
    DecodedVehicleIdentification,
)
from app.parser.specification import OpenQuestion, questions_for

__all__ = ["V1BParser"]


def _unconfirmed(code: str) -> UnconfirmedStructureError:
    """Construit l'erreur d'incertitude associee a une question de specification V1B."""
    question: OpenQuestion | None = next(
        (item for item in questions_for("v1b") if item.code == code), None
    )
    reference = question.reference if question else "specification non identifiee"
    detail = question.question if question else code
    return UnconfirmedStructureError(
        "Cette partie du fichier V1B n'est pas encore decodee.",
        cause=(
            "La structure binaire correspondante n'a pas encore ete confirmee a partir "
            "d'une specification officielle et d'un fichier de test reel."
        ),
        action=(
            "Le fichier est archive et son empreinte enregistree. Fournissez un fichier "
            "V1B de test pour permettre la validation du decodage."
        ),
        technical_detail=f"{code} - a confirmer via : {reference} ({detail})",
    )


class V1BParser(TachographFileParser):
    """Parser de fichier de telechargement d'unite embarquee."""

    file_type = FileType.V1B
    specification_topic = "v1b"

    def extract_driver(self) -> DecodedDriverIdentification | None:
        """Un telechargement vehicule peut concerner plusieurs conducteurs.

        L'identification conducteur n'est donc pas un champ unique : elle sera
        reconstituee depuis les activites par emplacement de carte.

        Returns:
            Toujours ``None``.
        """
        return None

    def extract_vehicle(self) -> DecodedVehicleIdentification | None:
        """Extrait l'identification du vehicule.

        Raises:
            UnconfirmedStructureError: Structure a confirmer
                (``V1B_VEHICLE_IDENTIFICATION_FIELDS``).
        """
        raise _unconfirmed("V1B_VEHICLE_IDENTIFICATION_FIELDS")

    def extract_activities(self) -> tuple[DecodedActivityPeriod, ...]:
        """Extrait les activites par emplacement de carte.

        Raises:
            UnconfirmedStructureError: Structure a confirmer
                (``V1B_DRIVER_SLOT_ACTIVITIES``).
        """
        raise _unconfirmed("V1B_DRIVER_SLOT_ACTIVITIES")

    def extract_events(self) -> tuple[DecodedEvent, ...]:
        """Extrait les evenements enregistres par l'unite embarquee.

        Raises:
            UnconfirmedStructureError: Structure a confirmer (``V1B_CONTAINER_LAYOUT``).
        """
        raise _unconfirmed("V1B_CONTAINER_LAYOUT")

    def extract_technical_data(self) -> DecodedTechnicalData | None:
        """Extrait les donnees techniques du telechargement.

        Raises:
            UnconfirmedStructureError: Structure a confirmer (``V1B_CONTAINER_LAYOUT``).
        """
        raise _unconfirmed("V1B_CONTAINER_LAYOUT")

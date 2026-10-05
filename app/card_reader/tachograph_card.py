"""Lecture d'une carte conducteur tachygraphique.

ETAT : NON IMPLEMENTE (phase 12 de la feuille de route).

Ce module est le seul endroit ou la connaissance specifique de la carte
tachygraphique doit apparaitre : identifiant d'application, identifiants de fichiers
elementaires, ordre de lecture, assemblage du fichier de telechargement. Or aucun de
ces elements n'a ete confirme a partir d'une source officielle. Ils sont recenses dans
:mod:`app.parser.specification`, domaine ``card`` :

* ``CARD_APPLICATION_SELECTION`` ;
* ``CARD_FILE_IDENTIFIERS`` ;
* ``CARD_READ_BINARY_SEQUENCE`` ;
* ``CARD_DOWNLOAD_FILE_ASSEMBLY``.

Tant que ces points ne sont pas leves, :meth:`TachographCard.download` leve
:class:`~app.core.exceptions.UnconfirmedStructureError`. L'architecture est en place
et testee : la couche transport (``PCSCReader``), la detection (``CardDetector``), la
forme des commandes (``apdu``) et le simulateur fonctionnent. Il ne manque que la
connaissance de la carte, qui ne peut pas etre devinee.

Chaine cible :

.. code-block:: text

    PCSCReader -> CardDetector -> TachographCard -> APDU
               -> CardDataExtractor -> C1BGenerator / RawDataStorage
               -> Parser -> Database
"""

from __future__ import annotations

from dataclasses import dataclass

from app.card_reader.apdu import APDUCommand, APDUResponse
from app.card_reader.interface import CardPresence, CardReaderInterface
from app.config.logging_config import get_logger
from app.core.exceptions import CardCommunicationError, UnconfirmedStructureError
from app.parser.specification import questions_for

__all__ = ["TachographCard", "CardDownload"]

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class CardDownload:
    """Resultat brut d'un telechargement de carte.

    Attributes:
        payload: Octets telecharges, tels que lus, sans transformation.
        atr: ATR de la carte, pour tracabilite.
        reader_name: Lecteur utilise.
    """

    payload: bytes
    atr: str | None = None
    reader_name: str | None = None

    @property
    def size(self) -> int:
        """Taille des donnees telechargees, en octets."""
        return len(self.payload)


def _unconfirmed(code: str) -> UnconfirmedStructureError:
    """Construit l'erreur d'incertitude associee a une question du domaine ``card``."""
    question = next((item for item in questions_for("card") if item.code == code), None)
    reference = question.reference if question else "specification non identifiee"
    detail = question.question if question else code
    return UnconfirmedStructureError(
        "La lecture directe de la carte n'est pas encore disponible.",
        cause=(
            "La sequence de commandes propre aux cartes tachygraphiques n'a pas encore "
            "ete confirmee a partir d'une specification officielle."
        ),
        action=(
            "Utilisez pour l'instant l'import d'un fichier C1B produit par un outil de "
            "telechargement existant. Le lecteur est detecte et diagnostique "
            "correctement dans la page « Lecteur de carte »."
        ),
        technical_detail=f"{code} - a confirmer via : {reference} ({detail})",
    )


class TachographCard:
    """Represente une carte tachygraphique accessible via un lecteur.

    Args:
        reader: Lecteur deja connecte, ou a connecter.
    """

    def __init__(self, reader: CardReaderInterface) -> None:
        self._reader = reader

    @property
    def reader(self) -> CardReaderInterface:
        """Lecteur utilise."""
        return self._reader

    def presence(self) -> CardPresence:
        """Retourne l'etat courant du lecteur et de la carte."""
        return self._reader.poll()

    def transmit(self, command: APDUCommand) -> APDUResponse:
        """Transmet une commande APDU brute a la carte.

        Cette methode est volontairement exposee : elle permet de valider
        experimentalement une sequence de commandes documentee, sans que le reste de
        l'application ne depende d'hypotheses non confirmees.

        Args:
            command: Commande a transmettre.

        Returns:
            La reponse de la carte, non interpretee.

        Raises:
            CardCommunicationError: Aucune connexion active ou echange interrompu.
        """
        if not self._reader.is_connected:
            raise CardCommunicationError(
                "Aucune carte connectee.",
                cause="La connexion avec la carte n'a pas ete etablie.",
                action="Connectez la carte avant d'envoyer une commande.",
            )
        return self._reader.transmit(command)

    def select_application(self) -> None:
        """Selectionne l'application tachygraphique de la carte.

        Raises:
            UnconfirmedStructureError: L'identifiant d'application n'est pas confirme
                (``CARD_APPLICATION_SELECTION``).
        """
        raise _unconfirmed("CARD_APPLICATION_SELECTION")

    def read_elementary_file(self, file_identifier: bytes) -> bytes:
        """Lit un fichier elementaire de la carte.

        Args:
            file_identifier: Identifiant du fichier a lire, sur 2 octets.

        Raises:
            UnconfirmedStructureError: La sequence de lecture n'est pas confirmee
                (``CARD_READ_BINARY_SEQUENCE``).
        """
        raise _unconfirmed("CARD_READ_BINARY_SEQUENCE")

    def download(self) -> CardDownload:
        """Telecharge l'integralite des donnees de la carte.

        Raises:
            UnconfirmedStructureError: Les fichiers a lire et l'assemblage du fichier
                de telechargement ne sont pas confirmes (``CARD_FILE_IDENTIFIERS``).
        """
        raise _unconfirmed("CARD_FILE_IDENTIFIERS")

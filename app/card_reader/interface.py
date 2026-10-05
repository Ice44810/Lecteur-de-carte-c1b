"""Abstraction du lecteur de carte.

Le reste de l'application ne connait que :class:`CardReaderInterface`. Deux
implementations existent :

* :class:`~app.card_reader.pcsc_reader.PCSCReader` : materiel reel via PC/SC ;
* :class:`~app.card_reader.mock_reader.MockCardReader` : simulateur pour les tests.

Aucune implementation n'est importee par defaut : ``pyscard`` est une dependance
optionnelle, et l'application doit fonctionner sur un poste sans lecteur.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from types import TracebackType

from app.card_reader.apdu import APDUCommand, APDUResponse

__all__ = ["CardReaderInterface", "ReaderInfo", "CardStatus", "CardPresence"]


class CardStatus(StrEnum):
    """Etat du couple lecteur / carte, tel qu'affiche a l'utilisateur.

    Attributes:
        PCSC_UNAVAILABLE: Pile PC/SC absente ou service arrete.
        NO_READER: Aucun lecteur detecte.
        NO_CARD: Lecteur present, aucune carte inseree.
        CARD_PRESENT: Carte inseree, non encore identifiee.
        CARD_CONNECTED: Connexion etablie avec la carte.
        CARD_UNKNOWN: Carte inseree mais non reconnue comme carte tachygraphique.
        ERROR: Erreur de communication.
    """

    PCSC_UNAVAILABLE = "PCSC_UNAVAILABLE"
    NO_READER = "NO_READER"
    NO_CARD = "NO_CARD"
    CARD_PRESENT = "CARD_PRESENT"
    CARD_CONNECTED = "CARD_CONNECTED"
    CARD_UNKNOWN = "CARD_UNKNOWN"
    ERROR = "ERROR"

    @property
    def label(self) -> str:
        """Libelle affichable dans la barre d'etat."""
        return {
            CardStatus.PCSC_UNAVAILABLE: "Service PC/SC indisponible",
            CardStatus.NO_READER: "Aucun lecteur detecte",
            CardStatus.NO_CARD: "Lecteur detecte, aucune carte",
            CardStatus.CARD_PRESENT: "Carte detectee",
            CardStatus.CARD_CONNECTED: "Carte connectee",
            CardStatus.CARD_UNKNOWN: "Carte non reconnue",
            CardStatus.ERROR: "Erreur de communication",
        }[self]

    @property
    def is_ready_to_read(self) -> bool:
        """Indique qu'une lecture peut etre tentee."""
        return self in {CardStatus.CARD_PRESENT, CardStatus.CARD_CONNECTED}


@dataclass(frozen=True, slots=True)
class ReaderInfo:
    """Description d'un lecteur detecte.

    Attributes:
        name: Nom du lecteur tel que rapporte par la pile PC/SC.
        index: Position du lecteur dans la liste.
    """

    name: str
    index: int = 0

    @property
    def display_name(self) -> str:
        """Nom affichable du lecteur."""
        return self.name


@dataclass(frozen=True, slots=True)
class CardPresence:
    """Etat instantane d'un lecteur.

    Attributes:
        status: Etat courant.
        reader: Lecteur concerne, si un lecteur est disponible.
        atr: Reponse ATR de la carte en hexadecimal, si une carte est presente.
        detail: Complement technique destine aux journaux.
    """

    status: CardStatus
    reader: ReaderInfo | None = None
    atr: str | None = None
    detail: str | None = None

    @property
    def card_present(self) -> bool:
        """Indique qu'une carte est physiquement presente."""
        return self.status in {
            CardStatus.CARD_PRESENT,
            CardStatus.CARD_CONNECTED,
            CardStatus.CARD_UNKNOWN,
        }


class CardReaderInterface(ABC):
    """Contrat d'un lecteur de carte.

    Cycle de vie attendu :

    .. code-block:: text

        list_readers() -> poll() -> connect() -> transmit()* -> disconnect()

    Toute implementation doit lever les exceptions de
    :mod:`app.core.exceptions` (``PCSCUnavailableError``, ``NoReaderFoundError``,
    ``NoCardPresentError``, ``CardCommunicationError``), afin que l'interface
    graphique puisse afficher un message, une cause et une action sans connaitre la
    technologie sous-jacente.
    """

    @abstractmethod
    def is_available(self) -> bool:
        """Indique si la pile logicielle du lecteur est utilisable.

        Returns:
            ``False`` si la bibliotheque ou le service necessaire est absent, sans
            lever d'exception : cette methode sert precisement a le tester.
        """

    @abstractmethod
    def list_readers(self) -> tuple[ReaderInfo, ...]:
        """Liste les lecteurs disponibles.

        Returns:
            Les lecteurs detectes, dans l'ordre rapporte par le systeme.

        Raises:
            PCSCUnavailableError: La pile PC/SC n'est pas disponible.
        """

    @abstractmethod
    def poll(self) -> CardPresence:
        """Retourne l'etat courant du lecteur et de la carte.

        Cette methode ne leve pas d'exception pour les situations normales (absence
        de lecteur ou de carte) : elle les traduit en :class:`CardStatus`, de maniere
        a pouvoir etre appelee periodiquement par l'interface.
        """

    @abstractmethod
    def connect(self, reader: ReaderInfo | None = None) -> CardPresence:
        """Etablit une connexion avec la carte inseree.

        Args:
            reader: Lecteur a utiliser ; par defaut le premier disponible.

        Returns:
            L'etat de la connexion etablie.

        Raises:
            PCSCUnavailableError: La pile PC/SC n'est pas disponible.
            NoReaderFoundError: Aucun lecteur n'est detecte.
            NoCardPresentError: Aucune carte n'est inseree.
            CardCommunicationError: La connexion a echoue.
        """

    @abstractmethod
    def transmit(self, command: APDUCommand) -> APDUResponse:
        """Transmet une commande APDU a la carte connectee.

        Args:
            command: Commande a transmettre.

        Returns:
            La reponse de la carte, mot d'etat inclus (non interprete).

        Raises:
            CardCommunicationError: Aucune connexion active, ou echange interrompu.
        """

    @abstractmethod
    def disconnect(self) -> None:
        """Ferme proprement la connexion.

        Doit pouvoir etre appelee sans effet si aucune connexion n'est active.
        """

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Indique qu'une connexion est active."""

    # ------------------------------------------------------------------ #
    # Gestion de contexte
    # ------------------------------------------------------------------ #
    def __enter__(self) -> CardReaderInterface:
        """Etablit la connexion a l'entree du bloc ``with``."""
        self.connect()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Ferme la connexion a la sortie du bloc, y compris en cas d'erreur."""
        self.disconnect()

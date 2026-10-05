"""Surveillance de l'etat du lecteur et detection des changements.

Le detecteur transforme une suite d'etats instantanes (:meth:`CardReaderInterface.poll`)
en **evenements** : lecteur detecte, lecteur retire, carte inseree, carte retiree. C'est
ce dont l'interface a besoin pour afficher les messages attendus en section 19 du cahier
des charges (« Lecteur detecte », « Carte detectee », ...).

Le detecteur est volontairement synchrone et sans fil d'execution : c'est l'appelant
(un minuteur Qt, un test) qui decide du rythme des appels a :meth:`CardDetector.refresh`.
Cela le rend entierement testable avec :class:`~app.card_reader.mock_reader.MockCardReader`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.card_reader.interface import CardPresence, CardReaderInterface, CardStatus
from app.config.logging_config import get_logger

__all__ = ["CardEvent", "CardEventType", "CardDetector"]

logger = get_logger(__name__)


class CardEventType(StrEnum):
    """Nature d'un changement d'etat detecte.

    Attributes:
        READER_CONNECTED: Un lecteur est devenu disponible.
        READER_DISCONNECTED: Le lecteur n'est plus disponible.
        CARD_INSERTED: Une carte a ete inseree.
        CARD_REMOVED: La carte a ete retiree.
        CARD_UNRECOGNIZED: Une carte est presente mais n'a pas ete reconnue.
        PCSC_UNAVAILABLE: Le service PC/SC est devenu indisponible.
        STATUS_CHANGED: Autre changement d'etat.
    """

    READER_CONNECTED = "READER_CONNECTED"
    READER_DISCONNECTED = "READER_DISCONNECTED"
    CARD_INSERTED = "CARD_INSERTED"
    CARD_REMOVED = "CARD_REMOVED"
    CARD_UNRECOGNIZED = "CARD_UNRECOGNIZED"
    PCSC_UNAVAILABLE = "PCSC_UNAVAILABLE"
    STATUS_CHANGED = "STATUS_CHANGED"

    @property
    def message(self) -> str:
        """Message destine a la barre d'etat de l'application."""
        return {
            CardEventType.READER_CONNECTED: "Lecteur detecte",
            CardEventType.READER_DISCONNECTED: "Lecteur deconnecte",
            CardEventType.CARD_INSERTED: "Carte detectee",
            CardEventType.CARD_REMOVED: "Carte retiree",
            CardEventType.CARD_UNRECOGNIZED: "Carte non reconnue",
            CardEventType.PCSC_UNAVAILABLE: "Service PC/SC indisponible",
            CardEventType.STATUS_CHANGED: "Etat du lecteur modifie",
        }[self]


@dataclass(frozen=True, slots=True)
class CardEvent:
    """Changement d'etat observe.

    Attributes:
        event_type: Nature du changement.
        presence: Etat du lecteur apres le changement.
    """

    event_type: CardEventType
    presence: CardPresence

    @property
    def message(self) -> str:
        """Message affichable correspondant a l'evenement."""
        return self.event_type.message


class CardDetector:
    """Compare les etats successifs d'un lecteur pour en deduire des evenements.

    Args:
        reader: Lecteur a surveiller.
    """

    def __init__(self, reader: CardReaderInterface) -> None:
        self._reader = reader
        self._previous: CardPresence | None = None

    @property
    def reader(self) -> CardReaderInterface:
        """Lecteur surveille."""
        return self._reader

    @property
    def current(self) -> CardPresence | None:
        """Dernier etat observe, ou ``None`` avant le premier rafraichissement."""
        return self._previous

    def reset(self) -> None:
        """Oublie l'etat precedent : le prochain rafraichissement repart de zero."""
        self._previous = None

    def refresh(self) -> tuple[CardEvent, ...]:
        """Interroge le lecteur et retourne les evenements survenus.

        Returns:
            Les evenements deduits de la comparaison avec l'etat precedent. Le premier
            appel retourne les evenements decrivant l'etat initial.
        """
        current = self._reader.poll()
        events = tuple(self._diff(self._previous, current))
        self._previous = current
        for event in events:
            logger.info("Lecteur de carte : %s", event.message)
        return events

    @staticmethod
    def _diff(previous: CardPresence | None, current: CardPresence) -> list[CardEvent]:
        """Deduit les evenements entre deux etats.

        Args:
            previous: Etat precedent, ou ``None`` au premier appel.
            current: Etat courant.

        Returns:
            Les evenements correspondants, du plus structurant au plus fin.
        """
        if previous is not None and previous.status is current.status:
            return []

        events: list[CardEvent] = []

        if current.status is CardStatus.PCSC_UNAVAILABLE:
            return [CardEvent(CardEventType.PCSC_UNAVAILABLE, current)]

        had_reader = previous is not None and previous.reader is not None
        has_reader = current.reader is not None
        if has_reader and not had_reader:
            events.append(CardEvent(CardEventType.READER_CONNECTED, current))
        elif had_reader and not has_reader:
            events.append(CardEvent(CardEventType.READER_DISCONNECTED, current))

        had_card = previous is not None and previous.card_present
        if current.status is CardStatus.CARD_UNKNOWN:
            events.append(CardEvent(CardEventType.CARD_UNRECOGNIZED, current))
        elif current.card_present and not had_card:
            events.append(CardEvent(CardEventType.CARD_INSERTED, current))
        elif had_card and not current.card_present:
            events.append(CardEvent(CardEventType.CARD_REMOVED, current))

        if not events:
            events.append(CardEvent(CardEventType.STATUS_CHANGED, current))
        return events

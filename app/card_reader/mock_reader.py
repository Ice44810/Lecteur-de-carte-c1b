"""Lecteur simule, utilise par les tests et les demonstrations.

Ce lecteur permet de tester tout le chemin applicatif (detection, connexion,
echanges, erreurs, messages affiches) sans materiel. Il reproduit fidelement les
etats et les exceptions de l'interface.

Limite assumee et importante : ce simulateur **ne simule pas de donnees
tachygraphiques**. Il retourne uniquement les reponses que le test lui a explicitement
fournies. Fabriquer de fausses reponses de carte tachygraphique donnerait l'illusion
d'un decodage fonctionnel ; la consigne est de ne jamais inventer de telles donnees.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from app.card_reader.apdu import APDUCommand, APDUResponse, StatusWord
from app.card_reader.interface import CardPresence, CardReaderInterface, CardStatus, ReaderInfo
from app.config.logging_config import get_logger
from app.core.exceptions import (
    CardCommunicationError,
    NoCardPresentError,
    NoReaderFoundError,
    PCSCUnavailableError,
)

__all__ = ["MockCardReader"]

logger = get_logger(__name__)

ResponseFactory = Callable[[APDUCommand], APDUResponse]


class MockCardReader(CardReaderInterface):
    """Lecteur de carte simule.

    Args:
        readers: Noms des lecteurs simules. Une liste vide simule l'absence de lecteur.
        card_present: Indique si une carte est inseree.
        available: Indique si la pile logicielle est disponible (``False`` simule
            l'absence de service PC/SC).
        atr: ATR simule de la carte, en hexadecimal.
        responses: Reponses a retourner, indexees par ``(CLA, INS)``. Toute commande
            non prevue recoit le mot d'etat « commande non prise en charge », comme le
            ferait une carte reelle.
        response_factory: Fonction appelee a la place de ``responses`` pour construire
            dynamiquement une reponse.
        card_recognized: Indique si la carte doit etre presentee comme reconnue.
    """

    def __init__(
        self,
        *,
        readers: tuple[str, ...] = ("Lecteur simule 0",),
        card_present: bool = True,
        available: bool = True,
        atr: str | None = None,
        responses: Mapping[tuple[int, int], APDUResponse] | None = None,
        response_factory: ResponseFactory | None = None,
        card_recognized: bool = True,
    ) -> None:
        self._reader_names = tuple(readers)
        self._card_present = card_present
        self._available = available
        self._atr = atr
        self._responses = dict(responses or {})
        self._response_factory = response_factory
        self._card_recognized = card_recognized
        self._connected = False
        self.transmitted: list[APDUCommand] = []
        """Historique des commandes transmises, pour les assertions de test."""

    # ------------------------------------------------------------------ #
    # Pilotage du simulateur
    # ------------------------------------------------------------------ #
    def insert_card(self, *, atr: str | None = None, recognized: bool = True) -> None:
        """Simule l'insertion d'une carte.

        Args:
            atr: ATR a rapporter, en hexadecimal.
            recognized: Simule une carte reconnue ou non reconnue.
        """
        self._card_present = True
        self._card_recognized = recognized
        if atr is not None:
            self._atr = atr

    def remove_card(self) -> None:
        """Simule le retrait de la carte et ferme toute connexion active."""
        self._card_present = False
        self._connected = False

    def set_readers(self, *names: str) -> None:
        """Remplace la liste des lecteurs simules (aucun argument : plus de lecteur)."""
        self._reader_names = tuple(names)
        if not names:
            self._connected = False

    def set_available(self, available: bool) -> None:
        """Simule la disponibilite ou l'arret du service PC/SC."""
        self._available = available
        if not available:
            self._connected = False

    def set_response(self, cla: int, ins: int, response: APDUResponse) -> None:
        """Enregistre la reponse a retourner pour un couple ``(CLA, INS)``."""
        self._responses[(cla, ins)] = response

    # ------------------------------------------------------------------ #
    # Interface
    # ------------------------------------------------------------------ #
    def is_available(self) -> bool:
        """Indique si la pile simulee est disponible."""
        return self._available

    def list_readers(self) -> tuple[ReaderInfo, ...]:
        """Liste les lecteurs simules.

        Raises:
            PCSCUnavailableError: Le simulateur est configure comme indisponible.
        """
        if not self._available:
            raise PCSCUnavailableError()
        return tuple(
            ReaderInfo(name=name, index=index) for index, name in enumerate(self._reader_names)
        )

    def poll(self) -> CardPresence:
        """Retourne l'etat simule du lecteur."""
        if not self._available:
            return CardPresence(status=CardStatus.PCSC_UNAVAILABLE)
        readers = self.list_readers()
        if not readers:
            return CardPresence(status=CardStatus.NO_READER)
        reader = readers[0]
        if not self._card_present:
            return CardPresence(status=CardStatus.NO_CARD, reader=reader)
        if not self._card_recognized:
            return CardPresence(status=CardStatus.CARD_UNKNOWN, reader=reader, atr=self._atr)
        status = CardStatus.CARD_CONNECTED if self._connected else CardStatus.CARD_PRESENT
        return CardPresence(status=status, reader=reader, atr=self._atr)

    def connect(self, reader: ReaderInfo | None = None) -> CardPresence:
        """Etablit une connexion simulee.

        Raises:
            PCSCUnavailableError: Pile simulee indisponible.
            NoReaderFoundError: Aucun lecteur simule.
            NoCardPresentError: Aucune carte simulee.
        """
        if not self._available:
            raise PCSCUnavailableError()
        readers = self.list_readers()
        if not readers:
            raise NoReaderFoundError()
        if not self._card_present:
            raise NoCardPresentError()
        self._connected = True
        selected = reader or readers[0]
        logger.info("Connexion simulee etablie avec %s", selected.display_name)
        return CardPresence(status=CardStatus.CARD_CONNECTED, reader=selected, atr=self._atr)

    def transmit(self, command: APDUCommand) -> APDUResponse:
        """Retourne la reponse simulee associee a une commande.

        Raises:
            CardCommunicationError: Aucune connexion active.
        """
        if not self._connected:
            raise CardCommunicationError(
                "Aucune carte connectee.",
                cause="Une commande a ete envoyee avant l'etablissement de la connexion.",
                action="Connectez la carte avant de lancer la lecture.",
            )
        self.transmitted.append(command)
        if self._response_factory is not None:
            return self._response_factory(command)
        key = (command.cla, command.ins)
        if key in self._responses:
            return self._responses[key]
        return APDUResponse(
            data=b"",
            sw1=StatusWord.INSTRUCTION_NOT_SUPPORTED >> 8,
            sw2=StatusWord.INSTRUCTION_NOT_SUPPORTED & 0xFF,
        )

    def disconnect(self) -> None:
        """Ferme la connexion simulee (sans effet si aucune n'est active)."""
        self._connected = False

    @property
    def is_connected(self) -> bool:
        """Indique qu'une connexion simulee est active."""
        return self._connected

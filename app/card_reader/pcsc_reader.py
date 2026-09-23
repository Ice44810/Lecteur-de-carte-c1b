"""Lecteur PC/SC reel, adosse a ``pyscard``.

``pyscard`` et le service ``pcscd`` sont des dependances **optionnelles** : leur
absence ne doit jamais empecher l'application de demarrer. L'import de ``pyscard``
est donc differe et toute indisponibilite est traduite en message explicite comportant
une cause et une action (section 16 du cahier des charges).

Perimetre : ce module gere le transport (detection, connexion, transmission, fermeture).
Il ne connait aucune particularite de la carte tachygraphique.
"""

from __future__ import annotations

from typing import Any

from app.card_reader.apdu import APDUCommand, APDUResponse
from app.card_reader.interface import CardPresence, CardReaderInterface, CardStatus, ReaderInfo
from app.config.logging_config import get_logger
from app.core.exceptions import (
    CardCommunicationError,
    NoCardPresentError,
    NoReaderFoundError,
    PCSCUnavailableError,
)

__all__ = ["PCSCReader", "pyscard_available", "diagnose_pcsc"]

logger = get_logger(__name__)


def pyscard_available() -> bool:
    """Indique si la bibliotheque ``pyscard`` est installee.

    Returns:
        ``True`` si le module peut etre importe.
    """
    try:
        import smartcard  # noqa: F401
    except ImportError:
        return False
    return True


def diagnose_pcsc() -> tuple[bool, str, str]:
    """Diagnostique l'etat de la pile PC/SC.

    Fournit a l'interface un diagnostic exploitable sans qu'elle ait a connaitre
    ``pyscard`` : la page « Lecteur de carte » affiche directement ces trois
    elements.

    Returns:
        Un triplet ``(disponible, cause, action)``. Lorsque ``disponible`` vaut
        ``True``, ``cause`` decrit l'etat constate et ``action`` est vide.
    """
    if not pyscard_available():
        return (
            False,
            "La bibliotheque Python pyscard n'est pas installee.",
            "Installez les dependances systeme puis pyscard : "
            "sudo apt install pcscd libpcsclite-dev python3-dev build-essential swig "
            "&& pip install pyscard",
        )
    try:
        from smartcard.System import readers as list_system_readers
    except ImportError as exc:  # pragma: no cover - installation incomplete
        return (False, "L'installation de pyscard est incomplete.", f"Reinstallez pyscard ({exc})")

    try:
        found = list_system_readers()
    except Exception as exc:  # noqa: BLE001 - pyscard leve des exceptions variees
        return (
            False,
            "Le service PC/SC n'a pas repondu.",
            "Verifiez que le service pcscd est actif : sudo systemctl status pcscd "
            "(puis sudo systemctl start pcscd). "
            f"Detail technique : {exc}",
        )

    if not found:
        return (
            True,
            "Service PC/SC disponible, mais aucun lecteur n'est connecte.",
            "Branchez le lecteur USB, puis verifiez sa detection avec la commande pcsc_scan.",
        )
    return (True, f"{len(found)} lecteur(s) detecte(s).", "")


class PCSCReader(CardReaderInterface):
    """Lecteur de carte PC/SC.

    Args:
        reader_name: Nom exact du lecteur a utiliser. Par defaut, le premier lecteur
            detecte est employe.
        protocol: Protocole de connexion ``pyscard``. ``None`` laisse la bibliotheque
            negocier (T=0 ou T=1).
    """

    def __init__(self, *, reader_name: str | None = None, protocol: int | None = None) -> None:
        self._reader_name = reader_name
        self._protocol = protocol
        self._connection: Any | None = None
        self._connected_reader: ReaderInfo | None = None

    # ------------------------------------------------------------------ #
    # Disponibilite
    # ------------------------------------------------------------------ #
    def is_available(self) -> bool:
        """Indique si ``pyscard`` est installe et si le service PC/SC repond."""
        available, _, _ = diagnose_pcsc()
        return available

    def list_readers(self) -> tuple[ReaderInfo, ...]:
        """Liste les lecteurs PC/SC detectes.

        Returns:
            Les lecteurs detectes.

        Raises:
            PCSCUnavailableError: ``pyscard`` est absent ou le service ne repond pas.
        """
        for reader in self._system_readers():
            logger.debug("Lecteur detecte : %s", reader)
        return tuple(
            ReaderInfo(name=str(reader), index=index)
            for index, reader in enumerate(self._system_readers())
        )

    def poll(self) -> CardPresence:
        """Retourne l'etat courant du lecteur, sans lever d'exception.

        Convient a un appel periodique depuis l'interface graphique.
        """
        available, cause, _ = diagnose_pcsc()
        if not available:
            return CardPresence(status=CardStatus.PCSC_UNAVAILABLE, detail=cause)

        try:
            readers = self.list_readers()
        except PCSCUnavailableError as exc:
            return CardPresence(status=CardStatus.PCSC_UNAVAILABLE, detail=exc.technical_detail)

        target = self._select_reader(readers)
        if target is None:
            return CardPresence(status=CardStatus.NO_READER, detail=cause)

        atr = self._read_atr(target)
        if atr is None:
            return CardPresence(status=CardStatus.NO_CARD, reader=target)
        status = CardStatus.CARD_CONNECTED if self.is_connected else CardStatus.CARD_PRESENT
        return CardPresence(status=status, reader=target, atr=atr)

    # ------------------------------------------------------------------ #
    # Connexion
    # ------------------------------------------------------------------ #
    def connect(self, reader: ReaderInfo | None = None) -> CardPresence:
        """Etablit une connexion avec la carte inseree.

        Args:
            reader: Lecteur a utiliser ; par defaut, celui configure ou le premier
                detecte.

        Returns:
            L'etat de la connexion.

        Raises:
            PCSCUnavailableError: Pile PC/SC indisponible.
            NoReaderFoundError: Aucun lecteur detecte.
            NoCardPresentError: Aucune carte inseree.
            CardCommunicationError: La connexion a echoue.
        """
        readers = self._system_readers()
        if not readers:
            raise NoReaderFoundError()

        target_name = reader.name if reader is not None else self._reader_name
        selected = self._find_system_reader(readers, target_name)

        try:
            connection = selected.createConnection()
            if self._protocol is None:
                connection.connect()
            else:
                connection.connect(protocol=self._protocol)
        except Exception as exc:  # noqa: BLE001 - pyscard leve des exceptions variees
            message = str(exc).lower()
            if "no smart card" in message or "not present" in message or "removed" in message:
                raise NoCardPresentError(technical_detail=str(exc)) from exc
            raise CardCommunicationError(
                "La connexion avec la carte n'a pas pu etre etablie.",
                cause="Le lecteur a refuse la connexion ou la carte est mal inseree.",
                action="Retirez puis reinserez la carte, puce vers le haut, et reessayez.",
                technical_detail=str(exc),
            ) from exc

        self._connection = connection
        self._connected_reader = ReaderInfo(
            name=str(selected), index=readers.index(selected) if selected in readers else 0
        )
        atr = self._format_atr(getattr(connection, "getATR", lambda: [])())
        logger.info("Connexion etablie avec le lecteur %s", self._connected_reader.name)
        return CardPresence(
            status=CardStatus.CARD_CONNECTED, reader=self._connected_reader, atr=atr
        )

    def transmit(self, command: APDUCommand) -> APDUResponse:
        """Transmet une commande APDU a la carte.

        Args:
            command: Commande a transmettre.

        Returns:
            La reponse de la carte, mot d'etat inclus.

        Raises:
            CardCommunicationError: Aucune connexion active, ou echange interrompu.
        """
        if self._connection is None:
            raise CardCommunicationError(
                "Aucune carte connectee.",
                cause="Une commande a ete envoyee avant l'etablissement de la connexion.",
                action="Connectez la carte avant de lancer la lecture.",
            )
        logger.debug("Transmission APDU : %s", command.describe())
        try:
            data, sw1, sw2 = self._connection.transmit(command.to_list())
        except Exception as exc:  # noqa: BLE001 - pyscard leve des exceptions variees
            raise CardCommunicationError(
                "L'echange avec la carte a ete interrompu.",
                cause="La carte a peut-etre ete retiree pendant la lecture.",
                action="Laissez la carte en place pendant toute la duree de la lecture.",
                technical_detail=f"{command.describe()} : {exc}",
            ) from exc
        return APDUResponse.from_pyscard(data, sw1, sw2)

    def disconnect(self) -> None:
        """Ferme la connexion, sans effet si aucune n'est active."""
        if self._connection is None:
            return
        try:
            self._connection.disconnect()
        except Exception as exc:  # noqa: BLE001 - la fermeture ne doit jamais echouer
            logger.warning("Fermeture de la connexion imparfaite : %s", exc)
        finally:
            self._connection = None
            self._connected_reader = None
            logger.info("Connexion au lecteur fermee")

    @property
    def is_connected(self) -> bool:
        """Indique qu'une connexion est active."""
        return self._connection is not None

    # ------------------------------------------------------------------ #
    # Interne
    # ------------------------------------------------------------------ #
    def _system_readers(self) -> list[Any]:
        """Retourne les objets lecteurs de ``pyscard``.

        Raises:
            PCSCUnavailableError: ``pyscard`` est absent ou le service ne repond pas.
        """
        try:
            from smartcard.System import readers as list_system_readers
        except ImportError as exc:
            raise PCSCUnavailableError(
                "Le support des lecteurs de carte n'est pas installe.",
                cause="La bibliotheque Python pyscard est absente.",
                action=(
                    "Installez les dependances : sudo apt install pcscd libpcsclite-dev "
                    "python3-dev build-essential swig && pip install pyscard"
                ),
                technical_detail=str(exc),
            ) from exc
        try:
            return list(list_system_readers())
        except Exception as exc:  # noqa: BLE001 - pyscard leve des exceptions variees
            raise PCSCUnavailableError(technical_detail=str(exc)) from exc

    def _select_reader(self, readers: tuple[ReaderInfo, ...]) -> ReaderInfo | None:
        """Choisit le lecteur a utiliser parmi ceux detectes."""
        if not readers:
            return None
        if self._reader_name is None:
            return readers[0]
        return next((item for item in readers if item.name == self._reader_name), None)

    def _find_system_reader(self, readers: list[Any], name: str | None) -> Any:
        """Retrouve l'objet lecteur ``pyscard`` correspondant a un nom.

        Raises:
            NoReaderFoundError: Le lecteur demande n'est pas present.
        """
        if name is None:
            return readers[0]
        for reader in readers:
            if str(reader) == name:
                return reader
        raise NoReaderFoundError(
            f"Le lecteur « {name} » n'est pas disponible.",
            cause="Le lecteur configure n'est pas connecte ou porte un autre nom.",
            action="Selectionnez un lecteur dans la liste des lecteurs detectes.",
            technical_detail=f"lecteurs presents : {[str(item) for item in readers]}",
        )

    def _read_atr(self, reader: ReaderInfo) -> str | None:
        """Tente de lire l'ATR de la carte presente dans un lecteur.

        Returns:
            L'ATR en hexadecimal, ou ``None`` si aucune carte n'est presente.
        """
        try:
            system_readers = self._system_readers()
            target = self._find_system_reader(system_readers, reader.name)
            connection = target.createConnection()
            connection.connect()
            try:
                return self._format_atr(connection.getATR())
            finally:
                connection.disconnect()
        except (PCSCUnavailableError, NoReaderFoundError):
            raise
        except Exception:  # noqa: BLE001 - absence de carte : cas normal
            return None

    @staticmethod
    def _format_atr(atr: list[int] | None) -> str | None:
        """Formate un ATR en hexadecimal majuscule espace, ou ``None`` s'il est vide."""
        if not atr:
            return None
        return " ".join(f"{byte:02X}" for byte in atr)

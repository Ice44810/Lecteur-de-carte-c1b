"""Acces au lecteur de carte a puce.

L'application ne depend que de :class:`~app.card_reader.interface.CardReaderInterface`.
La fabrique :func:`create_reader` choisit l'implementation : le lecteur PC/SC reel, ou
le simulateur lorsque ``pyscard`` est absent ou que le mode simule est demande.

``pyscard`` n'est importe qu'a l'interieur de
:mod:`app.card_reader.pcsc_reader` : importer ce paquet ne necessite donc aucune
dependance systeme.
"""

from app.card_reader.apdu import APDUCommand, APDUResponse, StatusWord
from app.card_reader.card_detector import CardDetector, CardEvent, CardEventType
from app.card_reader.interface import (
    CardPresence,
    CardReaderInterface,
    CardStatus,
    ReaderInfo,
)
from app.card_reader.mock_reader import MockCardReader
from app.card_reader.tachograph_card import CardDownload, TachographCard

__all__ = [
    "APDUCommand",
    "APDUResponse",
    "CardDetector",
    "CardDownload",
    "CardEvent",
    "CardEventType",
    "CardPresence",
    "CardReaderInterface",
    "CardStatus",
    "MockCardReader",
    "ReaderInfo",
    "StatusWord",
    "TachographCard",
    "create_reader",
    "pcsc_diagnostics",
]


def create_reader(*, use_mock: bool = False, reader_name: str | None = None) -> CardReaderInterface:
    """Retourne une implementation de lecteur.

    Args:
        use_mock: Force l'utilisation du simulateur.
        reader_name: Nom du lecteur PC/SC a utiliser, le cas echeant.

    Returns:
        Le lecteur PC/SC si ``pyscard`` est installe, sinon le simulateur configure
        pour refleter l'absence de pile PC/SC (aucun lecteur, service indisponible).
    """
    if use_mock:
        return MockCardReader()

    from app.card_reader.pcsc_reader import PCSCReader, pyscard_available

    if not pyscard_available():
        return MockCardReader(readers=(), card_present=False, available=False)
    return PCSCReader(reader_name=reader_name)


def pcsc_diagnostics() -> tuple[bool, str, str]:
    """Retourne le diagnostic de la pile PC/SC sous la forme (disponible, cause, action)."""
    from app.card_reader.pcsc_reader import diagnose_pcsc

    return diagnose_pcsc()

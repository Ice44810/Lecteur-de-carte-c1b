"""Tests de la couche transport PC/SC.

Aucun lecteur n'etant disponible en integration continue, la bibliotheque ``pyscard``
est remplacee par un double minimal. Ce double ne simule **pas** une carte
tachygraphique : il ne reproduit que l'interface documentee de ``pyscard``
(``readers()``, ``createConnection()``, ``connect()``, ``transmit()``, ``getATR()``,
``disconnect()``), ce qui permet de tester nos propres chemins d'erreur.

Ce qui est verifie : la traduction de chaque defaillance en message comportant une
cause et une action, l'absence de plantage lorsque la pile est absente, et la fermeture
systematique de la connexion.
"""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest

from app.card_reader.apdu import APDUCommand
from app.card_reader.interface import CardStatus, ReaderInfo
from app.card_reader.pcsc_reader import PCSCReader, diagnose_pcsc, pyscard_available
from app.core.exceptions import (
    CardCommunicationError,
    NoCardPresentError,
    NoReaderFoundError,
    PCSCUnavailableError,
)


class FausseConnexion:
    """Double d'une connexion ``pyscard``."""

    def __init__(
        self,
        *,
        atr: list[int] | None = None,
        connect_error: Exception | None = None,
        transmit_error: Exception | None = None,
        response: tuple[list[int], int, int] = ([0x01], 0x90, 0x00),
        disconnect_error: Exception | None = None,
    ) -> None:
        self._atr = atr if atr is not None else [0x3B, 0x7F]
        self._connect_error = connect_error
        self._transmit_error = transmit_error
        self._response = response
        self._disconnect_error = disconnect_error
        self.connected = False
        self.transmitted: list[list[int]] = []

    def connect(self, protocol: int | None = None) -> None:
        """Simule l'ouverture de la connexion."""
        if self._connect_error is not None:
            raise self._connect_error
        self.connected = True

    def transmit(self, command: list[int]) -> tuple[list[int], int, int]:
        """Simule un echange APDU."""
        if self._transmit_error is not None:
            raise self._transmit_error
        self.transmitted.append(command)
        return self._response

    def getATR(self) -> list[int]:  # noqa: N802 - nom impose par pyscard
        """Retourne l'ATR simule."""
        return self._atr

    def disconnect(self) -> None:
        """Simule la fermeture de la connexion."""
        if self._disconnect_error is not None:
            raise self._disconnect_error
        self.connected = False


class FauxLecteur:
    """Double d'un objet lecteur ``pyscard``."""

    def __init__(self, name: str, connection: FausseConnexion | None = None) -> None:
        self._name = name
        self.connection = connection if connection is not None else FausseConnexion()

    def createConnection(self) -> FausseConnexion:  # noqa: N802 - nom impose par pyscard
        """Retourne la connexion simulee."""
        return self.connection

    def __str__(self) -> str:
        """Nom du lecteur, tel que pyscard le presente."""
        return self._name


def installer_pyscard(
    monkeypatch: pytest.MonkeyPatch,
    lecteurs: list[Any] | Exception,
) -> None:
    """Remplace ``smartcard.System`` par un double.

    Args:
        monkeypatch: Utilitaire de remplacement, qui restaure l'etat initial.
        lecteurs: Lecteurs a retourner, ou exception a lever a l'appel.
    """

    def readers() -> list[Any]:
        if isinstance(lecteurs, Exception):
            raise lecteurs
        return lecteurs

    module_system = types.ModuleType("smartcard.System")
    module_system.readers = readers  # type: ignore[attr-defined]
    module_racine = types.ModuleType("smartcard")
    module_racine.System = module_system  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "smartcard", module_racine)
    monkeypatch.setitem(sys.modules, "smartcard.System", module_system)


def masquer_pyscard(monkeypatch: pytest.MonkeyPatch) -> None:
    """Simule l'absence complete de ``pyscard``."""
    monkeypatch.setitem(sys.modules, "smartcard", None)
    monkeypatch.setitem(sys.modules, "smartcard.System", None)


# --------------------------------------------------------------------------- #
# Absence de la bibliotheque
# --------------------------------------------------------------------------- #
def test_l_absence_de_pyscard_n_est_pas_une_erreur(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un poste sans lecteur doit pouvoir utiliser l'application normalement."""
    masquer_pyscard(monkeypatch)

    assert pyscard_available() is False


def test_l_absence_de_pyscard_propose_la_commande_d_installation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    masquer_pyscard(monkeypatch)

    disponible, cause, action = diagnose_pcsc()

    assert disponible is False
    assert "pyscard" in cause
    assert "apt install pcscd" in action


def test_l_absence_de_pyscard_est_traduite_en_etat_et_non_en_plantage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    masquer_pyscard(monkeypatch)

    etat = PCSCReader().poll()

    assert etat.status is CardStatus.PCSC_UNAVAILABLE
    assert etat.detail


def test_l_absence_de_pyscard_leve_une_erreur_explicite_a_l_enumeration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    masquer_pyscard(monkeypatch)

    with pytest.raises(PCSCUnavailableError) as erreur:
        PCSCReader().list_readers()

    message, cause, action = erreur.value.user_report()
    assert message and cause
    assert "pip install pyscard" in action


# --------------------------------------------------------------------------- #
# Service injoignable
# --------------------------------------------------------------------------- #
def test_un_service_injoignable_propose_de_verifier_pcscd(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    installer_pyscard(monkeypatch, RuntimeError("service not available"))

    disponible, cause, action = diagnose_pcsc()

    assert disponible is False
    assert "PC/SC" in cause
    assert "systemctl" in action


def test_un_service_injoignable_est_rapporte_comme_indisponible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    installer_pyscard(monkeypatch, RuntimeError("service not available"))

    assert PCSCReader().poll().status is CardStatus.PCSC_UNAVAILABLE
    assert PCSCReader().is_available() is False


# --------------------------------------------------------------------------- #
# Aucun lecteur
# --------------------------------------------------------------------------- #
def test_aucun_lecteur_est_signale_sans_erreur(monkeypatch: pytest.MonkeyPatch) -> None:
    installer_pyscard(monkeypatch, [])

    disponible, cause, action = diagnose_pcsc()

    assert disponible is True
    assert "aucun lecteur" in cause.lower()
    assert "pcsc_scan" in action


def test_aucun_lecteur_empeche_la_connexion(monkeypatch: pytest.MonkeyPatch) -> None:
    installer_pyscard(monkeypatch, [])

    with pytest.raises(NoReaderFoundError):
        PCSCReader().connect()


def test_aucun_lecteur_est_traduit_en_etat(monkeypatch: pytest.MonkeyPatch) -> None:
    installer_pyscard(monkeypatch, [])

    assert PCSCReader().poll().status is CardStatus.NO_READER


# --------------------------------------------------------------------------- #
# Lecteur present
# --------------------------------------------------------------------------- #
def test_les_lecteurs_detectes_sont_enumeres(monkeypatch: pytest.MonkeyPatch) -> None:
    installer_pyscard(monkeypatch, [FauxLecteur("Lecteur A"), FauxLecteur("Lecteur B")])

    lecteurs = PCSCReader().list_readers()

    assert [item.name for item in lecteurs] == ["Lecteur A", "Lecteur B"]
    assert [item.index for item in lecteurs] == [0, 1]


def test_un_diagnostic_positif_compte_les_lecteurs(monkeypatch: pytest.MonkeyPatch) -> None:
    installer_pyscard(monkeypatch, [FauxLecteur("Lecteur A")])

    disponible, cause, action = diagnose_pcsc()

    assert disponible is True
    assert "1 lecteur(s)" in cause
    assert action == ""


def test_un_lecteur_nomme_inexistant_est_refuse(monkeypatch: pytest.MonkeyPatch) -> None:
    installer_pyscard(monkeypatch, [FauxLecteur("Lecteur A")])

    with pytest.raises(NoReaderFoundError) as erreur:
        PCSCReader(reader_name="Lecteur Z").connect()

    message, _, action = erreur.value.user_report()
    assert "Lecteur Z" in message
    assert "liste" in action


def test_un_lecteur_configure_absent_est_signale_dans_l_etat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    installer_pyscard(monkeypatch, [FauxLecteur("Lecteur A")])

    assert PCSCReader(reader_name="Lecteur Z").poll().status is CardStatus.NO_READER


# --------------------------------------------------------------------------- #
# Carte absente
# --------------------------------------------------------------------------- #
def test_une_carte_absente_est_traduite_en_etat(monkeypatch: pytest.MonkeyPatch) -> None:
    """L'absence de carte est un cas normal, detecte sans exception."""
    connexion = FausseConnexion(connect_error=RuntimeError("No smart card inserted"))
    installer_pyscard(monkeypatch, [FauxLecteur("Lecteur A", connexion)])

    etat = PCSCReader().poll()

    assert etat.status is CardStatus.NO_CARD
    assert etat.reader is not None


def test_une_carte_absente_leve_une_erreur_explicite_a_la_connexion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connexion = FausseConnexion(connect_error=RuntimeError("No smart card inserted"))
    installer_pyscard(monkeypatch, [FauxLecteur("Lecteur A", connexion)])

    with pytest.raises(NoCardPresentError) as erreur:
        PCSCReader().connect()

    _, _, action = erreur.value.user_report()
    assert "Inserez la carte" in action


def test_un_refus_de_connexion_est_distingue_d_une_carte_absente(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connexion = FausseConnexion(connect_error=RuntimeError("protocol mismatch"))
    installer_pyscard(monkeypatch, [FauxLecteur("Lecteur A", connexion)])

    with pytest.raises(CardCommunicationError) as erreur:
        PCSCReader().connect()

    message, cause, action = erreur.value.user_report()
    assert "connexion" in message.lower()
    assert cause and action
    assert "Traceback" not in message


# --------------------------------------------------------------------------- #
# Carte presente
# --------------------------------------------------------------------------- #
def test_une_carte_presente_est_detectee_avec_son_atr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    installer_pyscard(
        monkeypatch, [FauxLecteur("Lecteur A", FausseConnexion(atr=[0x3B, 0x0F, 0xFF]))]
    )

    etat = PCSCReader().poll()

    assert etat.status is CardStatus.CARD_PRESENT
    assert etat.atr == "3B 0F FF"


def test_la_connexion_retourne_l_etat_connecte(monkeypatch: pytest.MonkeyPatch) -> None:
    installer_pyscard(monkeypatch, [FauxLecteur("Lecteur A")])
    lecteur = PCSCReader()

    etat = lecteur.connect()

    assert etat.status is CardStatus.CARD_CONNECTED
    assert lecteur.is_connected is True
    assert etat.reader is not None
    assert etat.reader.name == "Lecteur A"


def test_la_connexion_peut_viser_un_lecteur_precis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    installer_pyscard(monkeypatch, [FauxLecteur("Lecteur A"), FauxLecteur("Lecteur B")])

    etat = PCSCReader().connect(ReaderInfo(name="Lecteur B", index=1))

    assert etat.reader is not None
    assert etat.reader.name == "Lecteur B"


def test_un_protocole_impose_est_transmis_a_la_bibliotheque(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    installer_pyscard(monkeypatch, [FauxLecteur("Lecteur A")])

    assert PCSCReader(protocol=1).connect().status is CardStatus.CARD_CONNECTED


# --------------------------------------------------------------------------- #
# Echanges
# --------------------------------------------------------------------------- #
def test_une_commande_est_transmise_octet_par_octet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connexion = FausseConnexion(response=([0x11, 0x22], 0x90, 0x00))
    installer_pyscard(monkeypatch, [FauxLecteur("Lecteur A", connexion)])
    lecteur = PCSCReader()
    lecteur.connect()

    reponse = lecteur.transmit(APDUCommand(cla=0x00, ins=0xB0, expected_length=2))

    assert connexion.transmitted == [[0x00, 0xB0, 0x00, 0x00, 0x02]]
    assert reponse.data == b"\x11\x22"
    assert reponse.is_success


def test_aucune_commande_sans_connexion(monkeypatch: pytest.MonkeyPatch) -> None:
    installer_pyscard(monkeypatch, [FauxLecteur("Lecteur A")])

    with pytest.raises(CardCommunicationError) as erreur:
        PCSCReader().transmit(APDUCommand(cla=0x00, ins=0xA4))

    _, _, action = erreur.value.user_report()
    assert "Connectez la carte" in action


def test_un_retrait_pendant_la_lecture_est_explique(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connexion = FausseConnexion(transmit_error=RuntimeError("card removed"))
    installer_pyscard(monkeypatch, [FauxLecteur("Lecteur A", connexion)])
    lecteur = PCSCReader()
    lecteur.connect()

    with pytest.raises(CardCommunicationError) as erreur:
        lecteur.transmit(APDUCommand(cla=0x00, ins=0xB0, expected_length=4))

    message, cause, action = erreur.value.user_report()
    assert "interrompu" in message
    assert "retiree" in cause
    assert "en place" in action


def test_le_detail_technique_ne_journalise_pas_les_donnees_envoyees(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connexion = FausseConnexion(transmit_error=RuntimeError("card removed"))
    installer_pyscard(monkeypatch, [FauxLecteur("Lecteur A", connexion)])
    lecteur = PCSCReader()
    lecteur.connect()

    with pytest.raises(CardCommunicationError) as erreur:
        lecteur.transmit(APDUCommand(cla=0x00, ins=0xA4, data=b"\xde\xad"))

    detail = erreur.value.technical_detail or ""
    assert "CLA=00" in detail
    assert "dead" not in detail.lower()


# --------------------------------------------------------------------------- #
# Fermeture
# --------------------------------------------------------------------------- #
def test_la_fermeture_libere_la_connexion(monkeypatch: pytest.MonkeyPatch) -> None:
    connexion = FausseConnexion()
    installer_pyscard(monkeypatch, [FauxLecteur("Lecteur A", connexion)])
    lecteur = PCSCReader()
    lecteur.connect()

    lecteur.disconnect()

    assert lecteur.is_connected is False
    assert connexion.connected is False


def test_la_fermeture_sans_connexion_est_sans_effet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    installer_pyscard(monkeypatch, [FauxLecteur("Lecteur A")])

    PCSCReader().disconnect()


def test_une_fermeture_imparfaite_ne_bloque_pas_l_application(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Une erreur a la fermeture est journalisee, jamais propagee a l'utilisateur."""
    connexion = FausseConnexion(disconnect_error=RuntimeError("reader busy"))
    installer_pyscard(monkeypatch, [FauxLecteur("Lecteur A", connexion)])
    lecteur = PCSCReader()
    lecteur.connect()

    lecteur.disconnect()

    assert lecteur.is_connected is False


def test_le_gestionnaire_de_contexte_ferme_la_connexion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    installer_pyscard(monkeypatch, [FauxLecteur("Lecteur A")])
    lecteur = PCSCReader()

    with lecteur:
        assert lecteur.is_connected is True

    assert lecteur.is_connected is False


def test_l_etat_reflete_la_connexion_active(monkeypatch: pytest.MonkeyPatch) -> None:
    installer_pyscard(monkeypatch, [FauxLecteur("Lecteur A")])
    lecteur = PCSCReader()
    lecteur.connect()

    assert lecteur.poll().status is CardStatus.CARD_CONNECTED

"""Tests du lecteur simule.

Le cahier des charges impose de tester quatre situations qui, sur un poste reel, ne
peuvent pas etre provoquees a volonte : lecteur absent, lecteur present, carte absente
et carte presente. Le simulateur existe pour cela, et ces tests couvrent les quatre cas
explicitement.

Le simulateur ne retourne **aucune donnee tachygraphique** : il ne repond que ce que le
test lui a fourni. Un simulateur qui fabriquerait de fausses reponses de carte
donnerait l'illusion d'un decodage fonctionnel.
"""

from __future__ import annotations

import pytest

from app.card_reader import create_reader
from app.card_reader.apdu import APDUCommand, APDUResponse, StatusWord
from app.card_reader.interface import CardReaderInterface, CardStatus, ReaderInfo
from app.card_reader.mock_reader import MockCardReader
from app.core.exceptions import (
    CardCommunicationError,
    NoCardPresentError,
    NoReaderFoundError,
    PCSCUnavailableError,
)


# --------------------------------------------------------------------------- #
# Cas exige : pile PC/SC indisponible
# --------------------------------------------------------------------------- #
def test_pile_pcsc_indisponible() -> None:
    lecteur = MockCardReader(available=False)

    assert lecteur.is_available() is False
    assert lecteur.poll().status is CardStatus.PCSC_UNAVAILABLE


def test_pile_pcsc_indisponible_leve_une_erreur_explicite() -> None:
    lecteur = MockCardReader(available=False)

    with pytest.raises(PCSCUnavailableError) as erreur:
        lecteur.list_readers()

    message, cause, action = erreur.value.user_report()
    assert message and cause
    assert "pcscd" in action


# --------------------------------------------------------------------------- #
# Cas exige : lecteur absent
# --------------------------------------------------------------------------- #
def test_lecteur_absent() -> None:
    lecteur = MockCardReader(readers=())

    assert lecteur.list_readers() == ()
    assert lecteur.poll().status is CardStatus.NO_READER


def test_lecteur_absent_refuse_la_connexion() -> None:
    lecteur = MockCardReader(readers=())

    with pytest.raises(NoReaderFoundError) as erreur:
        lecteur.connect()

    _, _, action = erreur.value.user_report()
    assert "pcsc_scan" in action


def test_le_retrait_du_lecteur_est_pris_en_compte_a_chaud() -> None:
    lecteur = MockCardReader()
    assert lecteur.poll().status is CardStatus.CARD_PRESENT

    lecteur.set_readers()

    assert lecteur.poll().status is CardStatus.NO_READER


# --------------------------------------------------------------------------- #
# Cas exige : lecteur present
# --------------------------------------------------------------------------- #
def test_lecteur_present() -> None:
    lecteur = MockCardReader(readers=("Lecteur A", "Lecteur B"), card_present=False)

    lecteurs = lecteur.list_readers()

    assert [item.name for item in lecteurs] == ["Lecteur A", "Lecteur B"]
    assert [item.index for item in lecteurs] == [0, 1]
    assert lecteurs[0].display_name == "Lecteur A"


def test_lecteur_present_est_rapporte_dans_l_etat() -> None:
    lecteur = MockCardReader(readers=("Lecteur A",), card_present=False)

    etat = lecteur.poll()

    assert etat.reader is not None
    assert etat.reader.name == "Lecteur A"
    assert etat.status.label == "Lecteur detecte, aucune carte"


# --------------------------------------------------------------------------- #
# Cas exige : carte absente
# --------------------------------------------------------------------------- #
def test_carte_absente() -> None:
    lecteur = MockCardReader(card_present=False)

    etat = lecteur.poll()

    assert etat.status is CardStatus.NO_CARD
    assert etat.card_present is False
    assert etat.status.is_ready_to_read is False


def test_carte_absente_refuse_la_connexion() -> None:
    lecteur = MockCardReader(card_present=False)

    with pytest.raises(NoCardPresentError) as erreur:
        lecteur.connect()

    _, _, action = erreur.value.user_report()
    assert "Inserez la carte" in action


def test_le_retrait_de_la_carte_ferme_la_connexion() -> None:
    lecteur = MockCardReader()
    lecteur.connect()

    lecteur.remove_card()

    assert lecteur.is_connected is False
    assert lecteur.poll().status is CardStatus.NO_CARD


# --------------------------------------------------------------------------- #
# Cas exige : carte presente
# --------------------------------------------------------------------------- #
def test_carte_presente() -> None:
    lecteur = MockCardReader(atr="3B 7F")

    etat = lecteur.poll()

    assert etat.status is CardStatus.CARD_PRESENT
    assert etat.card_present is True
    assert etat.status.is_ready_to_read is True
    assert etat.atr == "3B 7F"


def test_carte_presente_permet_la_connexion() -> None:
    lecteur = MockCardReader(atr="3B 7F")

    etat = lecteur.connect()

    assert etat.status is CardStatus.CARD_CONNECTED
    assert lecteur.is_connected is True
    assert lecteur.poll().status is CardStatus.CARD_CONNECTED


def test_l_insertion_d_une_carte_est_prise_en_compte_a_chaud() -> None:
    lecteur = MockCardReader(card_present=False)

    lecteur.insert_card(atr="3B 01")

    assert lecteur.poll().status is CardStatus.CARD_PRESENT
    assert lecteur.poll().atr == "3B 01"


def test_une_carte_non_reconnue_est_distinguee_d_une_carte_valide() -> None:
    lecteur = MockCardReader()
    lecteur.insert_card(recognized=False)

    etat = lecteur.poll()

    assert etat.status is CardStatus.CARD_UNKNOWN
    assert etat.card_present is True
    assert etat.status.is_ready_to_read is False


def test_la_connexion_peut_viser_un_lecteur_precis() -> None:
    lecteur = MockCardReader(readers=("Lecteur A", "Lecteur B"))

    etat = lecteur.connect(ReaderInfo(name="Lecteur B", index=1))

    assert etat.reader is not None
    assert etat.reader.name == "Lecteur B"


# --------------------------------------------------------------------------- #
# Echanges APDU
# --------------------------------------------------------------------------- #
def test_aucune_commande_n_est_acceptee_sans_connexion() -> None:
    lecteur = MockCardReader()

    with pytest.raises(CardCommunicationError) as erreur:
        lecteur.transmit(APDUCommand(cla=0x00, ins=0xA4))

    _, _, action = erreur.value.user_report()
    assert "Connectez la carte" in action


def test_une_commande_non_prevue_recoit_un_refus_et_non_une_donnee_inventee() -> None:
    """Le simulateur ne fabrique jamais de contenu : il refuse la commande."""
    lecteur = MockCardReader()
    lecteur.connect()

    reponse = lecteur.transmit(APDUCommand(cla=0x00, ins=0xB0, expected_length=16))

    assert reponse.data == b""
    assert reponse.status_word == StatusWord.INSTRUCTION_NOT_SUPPORTED


def test_une_reponse_programmee_est_retournee_telle_quelle() -> None:
    attendue = APDUResponse(data=b"\x01\x02", sw1=0x90, sw2=0x00)
    lecteur = MockCardReader(responses={(0x00, 0xB0): attendue})
    lecteur.connect()

    assert lecteur.transmit(APDUCommand(cla=0x00, ins=0xB0)) is attendue


def test_une_reponse_peut_etre_programmee_apres_construction() -> None:
    lecteur = MockCardReader()
    lecteur.connect()
    lecteur.set_response(0x00, 0xA4, APDUResponse(data=b"", sw1=0x90, sw2=0x00))

    assert lecteur.transmit(APDUCommand(cla=0x00, ins=0xA4)).is_success


def test_une_fabrique_de_reponses_recoit_la_commande() -> None:
    vues: list[APDUCommand] = []

    def fabrique(commande: APDUCommand) -> APDUResponse:
        vues.append(commande)
        return APDUResponse(data=b"\xff", sw1=0x90, sw2=0x00)

    lecteur = MockCardReader(response_factory=fabrique)
    lecteur.connect()
    lecteur.transmit(APDUCommand(cla=0x00, ins=0xB0, expected_length=1))

    assert len(vues) == 1
    assert vues[0].ins == 0xB0


def test_les_commandes_transmises_sont_tracees() -> None:
    lecteur = MockCardReader()
    lecteur.connect()
    lecteur.transmit(APDUCommand(cla=0x00, ins=0xA4))
    lecteur.transmit(APDUCommand(cla=0x00, ins=0xB0))

    assert [commande.ins for commande in lecteur.transmitted] == [0xA4, 0xB0]


# --------------------------------------------------------------------------- #
# Cycle de vie
# --------------------------------------------------------------------------- #
def test_la_deconnexion_est_idempotente() -> None:
    lecteur = MockCardReader()

    lecteur.disconnect()
    lecteur.connect()
    lecteur.disconnect()
    lecteur.disconnect()

    assert lecteur.is_connected is False


def test_le_gestionnaire_de_contexte_ferme_la_connexion() -> None:
    lecteur = MockCardReader()

    with lecteur as ouvert:
        assert ouvert.is_connected is True

    assert lecteur.is_connected is False


def test_le_gestionnaire_de_contexte_ferme_meme_en_cas_d_erreur() -> None:
    lecteur = MockCardReader()

    with pytest.raises(RuntimeError), lecteur:
        raise RuntimeError("echec simule pendant la lecture")

    assert lecteur.is_connected is False


def test_l_arret_du_service_ferme_la_connexion() -> None:
    lecteur = MockCardReader()
    lecteur.connect()

    lecteur.set_available(False)

    assert lecteur.is_connected is False
    assert lecteur.poll().status is CardStatus.PCSC_UNAVAILABLE


# --------------------------------------------------------------------------- #
# Fabrique
# --------------------------------------------------------------------------- #
def test_la_fabrique_peut_forcer_le_simulateur() -> None:
    assert isinstance(create_reader(use_mock=True), MockCardReader)


def test_la_fabrique_retourne_toujours_un_lecteur_utilisable() -> None:
    """Sur un poste sans pyscard, l'application doit quand meme obtenir un lecteur."""
    lecteur = create_reader()

    assert isinstance(lecteur, CardReaderInterface)
    assert lecteur.poll().status in set(CardStatus)

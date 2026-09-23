"""Tests de la lecture directe d'une carte tachygraphique.

Ces tests verifient une propriete **negative**, et c'est leur raison d'etre : tant que
la sequence de commandes propre aux cartes tachygraphiques n'a pas ete confirmee a
partir d'une specification officielle, la couche concernee doit refuser d'agir et le
dire clairement, plutot que d'essayer une sequence devinee.

Ils verifient aussi que tout ce qui **peut** l'etre fonctionne bien : detection,
connexion, transmission d'une commande brute, diagnostic. C'est ce decoupage qui permet
de livrer une architecture complete sans inventer de format.
"""

from __future__ import annotations

import pytest

from app.card_reader import pcsc_diagnostics
from app.card_reader.apdu import APDUCommand, APDUResponse
from app.card_reader.mock_reader import MockCardReader
from app.card_reader.pcsc_reader import diagnose_pcsc, pyscard_available
from app.card_reader.tachograph_card import CardDownload, TachographCard
from app.core.exceptions import CardCommunicationError, UnconfirmedStructureError
from app.parser.specification import is_confirmed, questions_for


# --------------------------------------------------------------------------- #
# Refus documente d'inventer une sequence
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("operation", "arguments"),
    [
        ("select_application", ()),
        ("read_elementary_file", (b"\x00\x02",)),
        ("download", ()),
    ],
)
def test_aucune_operation_specifique_n_est_devinee(
    operation: str, arguments: tuple[object, ...]
) -> None:
    carte = TachographCard(MockCardReader())
    carte.reader.connect()

    with pytest.raises(UnconfirmedStructureError):
        getattr(carte, operation)(*arguments)


def test_le_refus_explique_la_situation_a_l_utilisateur() -> None:
    carte = TachographCard(MockCardReader())

    with pytest.raises(UnconfirmedStructureError) as erreur:
        carte.download()

    message, cause, action = erreur.value.user_report()
    assert "n'est pas encore disponible" in message
    assert "confirm" in cause
    assert "C1B" in action
    assert "Traceback" not in message


def test_le_refus_cite_la_question_a_lever() -> None:
    """Le detail technique doit pointer la specification a consulter."""
    carte = TachographCard(MockCardReader())

    with pytest.raises(UnconfirmedStructureError) as erreur:
        carte.select_application()

    detail = erreur.value.technical_detail or ""
    assert "CARD_APPLICATION_SELECTION" in detail
    assert "confirmer" in detail


def test_le_domaine_carte_est_toujours_declare_non_confirme() -> None:
    assert is_confirmed("card") is False
    assert questions_for("card")


def test_aucune_commande_n_est_transmise_lors_d_un_refus() -> None:
    """Le refus est structurel : la carte n'est meme pas sollicitee."""
    lecteur = MockCardReader()
    lecteur.connect()
    carte = TachographCard(lecteur)

    with pytest.raises(UnconfirmedStructureError):
        carte.download()

    assert lecteur.transmitted == []


# --------------------------------------------------------------------------- #
# Ce qui fonctionne des maintenant
# --------------------------------------------------------------------------- #
def test_l_etat_du_lecteur_reste_consultable() -> None:
    lecteur = MockCardReader(atr="3B 7F")
    carte = TachographCard(lecteur)

    etat = carte.presence()

    assert etat.card_present is True
    assert etat.atr == "3B 7F"


def test_une_commande_brute_peut_etre_transmise_pour_experimentation() -> None:
    """Valider une sequence documentee doit rester possible, sans l'inscrire en dur."""
    attendue = APDUResponse(data=b"\x01", sw1=0x90, sw2=0x00)
    lecteur = MockCardReader(responses={(0x00, 0xA4): attendue})
    lecteur.connect()
    carte = TachographCard(lecteur)

    reponse = carte.transmit(APDUCommand(cla=0x00, ins=0xA4, data=b"\x3f\x00"))

    assert reponse is attendue
    assert len(lecteur.transmitted) == 1


def test_une_commande_brute_exige_une_connexion() -> None:
    carte = TachographCard(MockCardReader())

    with pytest.raises(CardCommunicationError) as erreur:
        carte.transmit(APDUCommand(cla=0x00, ins=0xA4))

    _, _, action = erreur.value.user_report()
    assert "Connectez la carte" in action


def test_la_carte_expose_son_lecteur() -> None:
    lecteur = MockCardReader()

    assert TachographCard(lecteur).reader is lecteur


def test_le_resultat_de_telechargement_mesure_les_octets_recus() -> None:
    telechargement = CardDownload(payload=b"\x00" * 128, atr="3B 7F", reader_name="Lecteur A")

    assert telechargement.size == 128
    assert telechargement.reader_name == "Lecteur A"


# --------------------------------------------------------------------------- #
# Diagnostic de la pile PC/SC
# --------------------------------------------------------------------------- #
def test_le_diagnostic_retourne_toujours_un_triplet_exploitable() -> None:
    disponible, cause, action = diagnose_pcsc()

    assert isinstance(disponible, bool)
    assert cause.strip()
    assert isinstance(action, str)


def test_un_diagnostic_negatif_propose_une_action() -> None:
    disponible, _, action = diagnose_pcsc()

    if not disponible:
        assert action.strip()


def test_le_diagnostic_est_expose_par_le_paquet() -> None:
    assert pcsc_diagnostics() == diagnose_pcsc()


def test_la_disponibilite_de_pyscard_est_un_booleen() -> None:
    """L'absence de pyscard est un cas normal, pas une erreur."""
    assert isinstance(pyscard_available(), bool)

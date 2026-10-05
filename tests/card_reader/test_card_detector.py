"""Tests du detecteur d'evenements du lecteur de carte.

Le detecteur doit produire exactement les messages attendus par l'interface
(« Lecteur detecte », « Carte detectee », ...) a partir d'une suite d'etats. Comme il
est synchrone et sans fil d'execution, il se teste entierement avec le simulateur, sans
materiel et sans attente.
"""

from __future__ import annotations

from app.card_reader.card_detector import CardDetector, CardEventType
from app.card_reader.interface import CardStatus
from app.card_reader.mock_reader import MockCardReader


def types(evenements: tuple[object, ...]) -> list[CardEventType]:
    """Retourne la liste des natures d'evenements, pour des assertions lisibles."""
    return [evenement.event_type for evenement in evenements]  # type: ignore[attr-defined]


# --------------------------------------------------------------------------- #
# Premier rafraichissement
# --------------------------------------------------------------------------- #
def test_avant_le_premier_rafraichissement_aucun_etat_n_est_connu() -> None:
    detecteur = CardDetector(MockCardReader())

    assert detecteur.current is None


def test_le_premier_rafraichissement_decrit_l_etat_initial() -> None:
    detecteur = CardDetector(MockCardReader())

    evenements = detecteur.refresh()

    assert CardEventType.READER_CONNECTED in types(evenements)
    assert CardEventType.CARD_INSERTED in types(evenements)


def test_le_premier_rafraichissement_sans_lecteur_le_signale() -> None:
    detecteur = CardDetector(MockCardReader(readers=()))

    evenements = detecteur.refresh()

    assert types(evenements) == [CardEventType.STATUS_CHANGED]
    assert detecteur.current is not None
    assert detecteur.current.status is CardStatus.NO_READER


def test_le_service_indisponible_est_signale_seul() -> None:
    detecteur = CardDetector(MockCardReader(available=False))

    evenements = detecteur.refresh()

    assert types(evenements) == [CardEventType.PCSC_UNAVAILABLE]


# --------------------------------------------------------------------------- #
# Stabilite
# --------------------------------------------------------------------------- #
def test_un_etat_inchange_ne_produit_aucun_evenement() -> None:
    detecteur = CardDetector(MockCardReader())
    detecteur.refresh()

    assert detecteur.refresh() == ()
    assert detecteur.refresh() == ()


def test_la_reinitialisation_fait_reproduire_l_etat_initial() -> None:
    detecteur = CardDetector(MockCardReader())
    detecteur.refresh()

    detecteur.reset()

    assert detecteur.current is None
    assert detecteur.refresh() != ()


# --------------------------------------------------------------------------- #
# Insertion et retrait de la carte
# --------------------------------------------------------------------------- #
def test_l_insertion_d_une_carte_est_detectee() -> None:
    lecteur = MockCardReader(card_present=False)
    detecteur = CardDetector(lecteur)
    detecteur.refresh()

    lecteur.insert_card()

    assert types(detecteur.refresh()) == [CardEventType.CARD_INSERTED]


def test_le_retrait_d_une_carte_est_detecte() -> None:
    lecteur = MockCardReader()
    detecteur = CardDetector(lecteur)
    detecteur.refresh()

    lecteur.remove_card()

    assert types(detecteur.refresh()) == [CardEventType.CARD_REMOVED]


def test_une_carte_non_reconnue_est_signalee_comme_telle() -> None:
    lecteur = MockCardReader(card_present=False)
    detecteur = CardDetector(lecteur)
    detecteur.refresh()

    lecteur.insert_card(recognized=False)

    assert types(detecteur.refresh()) == [CardEventType.CARD_UNRECOGNIZED]


def test_une_serie_d_insertions_et_de_retraits_est_suivie() -> None:
    lecteur = MockCardReader(card_present=False)
    detecteur = CardDetector(lecteur)
    detecteur.refresh()

    observes: list[CardEventType] = []
    for action in ("inserer", "retirer", "inserer"):
        if action == "inserer":
            lecteur.insert_card()
        else:
            lecteur.remove_card()
        observes.extend(types(detecteur.refresh()))

    assert observes == [
        CardEventType.CARD_INSERTED,
        CardEventType.CARD_REMOVED,
        CardEventType.CARD_INSERTED,
    ]


# --------------------------------------------------------------------------- #
# Branchement et debranchement du lecteur
# --------------------------------------------------------------------------- #
def test_le_branchement_d_un_lecteur_est_detecte() -> None:
    lecteur = MockCardReader(readers=(), card_present=False)
    detecteur = CardDetector(lecteur)
    detecteur.refresh()

    lecteur.set_readers("Lecteur A")

    assert types(detecteur.refresh()) == [CardEventType.READER_CONNECTED]


def test_le_debranchement_du_lecteur_est_detecte() -> None:
    lecteur = MockCardReader(card_present=False)
    detecteur = CardDetector(lecteur)
    detecteur.refresh()

    lecteur.set_readers()

    assert types(detecteur.refresh()) == [CardEventType.READER_DISCONNECTED]


def test_le_debranchement_avec_carte_signale_les_deux_changements() -> None:
    lecteur = MockCardReader()
    detecteur = CardDetector(lecteur)
    detecteur.refresh()

    lecteur.set_readers()

    observes = types(detecteur.refresh())
    assert CardEventType.READER_DISCONNECTED in observes
    assert CardEventType.CARD_REMOVED in observes


def test_l_arret_du_service_est_signale_apres_un_etat_normal() -> None:
    lecteur = MockCardReader()
    detecteur = CardDetector(lecteur)
    detecteur.refresh()

    lecteur.set_available(False)

    assert types(detecteur.refresh()) == [CardEventType.PCSC_UNAVAILABLE]


# --------------------------------------------------------------------------- #
# Messages destines a l'interface
# --------------------------------------------------------------------------- #
def test_chaque_evenement_porte_un_message_affichable() -> None:
    lecteur = MockCardReader(card_present=False)
    detecteur = CardDetector(lecteur)
    detecteur.refresh()
    lecteur.insert_card()

    evenement = detecteur.refresh()[0]

    assert evenement.message == "Carte detectee"
    assert evenement.message == evenement.event_type.message


def test_tous_les_types_d_evenements_ont_un_message() -> None:
    for type_evenement in CardEventType:
        assert type_evenement.message.strip()


def test_l_evenement_transporte_l_etat_complet() -> None:
    lecteur = MockCardReader(atr="3B 7F")
    detecteur = CardDetector(lecteur)

    evenement = next(
        item for item in detecteur.refresh() if item.event_type is CardEventType.CARD_INSERTED
    )

    assert evenement.presence.atr == "3B 7F"
    assert evenement.presence.reader is not None


def test_le_detecteur_expose_le_lecteur_surveille() -> None:
    lecteur = MockCardReader()

    assert CardDetector(lecteur).reader is lecteur

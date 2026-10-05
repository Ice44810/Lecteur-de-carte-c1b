"""Tests du decodage d'un fichier de carte conducteur (C1B).

Fichiers synthetiques codes selon le reglement (UE) 2016/799, annexe I C (voir
``c1b_synthetique.py``). Chaque test fixe une regle de l'appendice 1.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from app.core.enums import ActivityType
from app.core.exceptions import ParsingError
from app.parser import C1BParser
from app.parser.c1b_parser import content_digest, decode_container
from tests.parser.c1b_synthetique import CarteSynthetique, mot_activite, tlv

JOUR = date(2025, 10, 1)
MINUIT = datetime(2025, 10, 1, tzinfo=UTC)


def heure(h: float, jour: datetime = MINUIT) -> datetime:
    return jour + timedelta(minutes=round(h * 60))


def journee_type() -> list[int]:
    """Repos manuel, travail puis conduite carte inseree, repos, retrait de la carte."""
    return [
        mot_activite(0, "REPOS", retiree=True, connue=True),
        mot_activite(6 * 60, "TRAVAIL"),
        mot_activite(6 * 60 + 15, "CONDUITE"),
        mot_activite(10 * 60, "REPOS"),
        mot_activite(10 * 60 + 45, "CONDUITE", equipage=True),
        mot_activite(14 * 60, "REPOS", retiree=True),
    ]


def carte(**options: object) -> CarteSynthetique:
    valeurs: dict[str, object] = {
        "jours": [(JOUR, journee_type())],
        "vehicules": [
            (heure(6, MINUIT) + timedelta(seconds=40), heure(14), "AB-123-CD", 1000, 1250)
        ],
    }
    valeurs.update(options)
    return CarteSynthetique(**valeurs)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# Identification (2.24, 2.62, 2.18)
# --------------------------------------------------------------------------- #
def test_l_identification_du_titulaire_est_decodee() -> None:
    conducteur = C1BParser(carte().fichier()).extract_driver()

    assert conducteur is not None
    assert conducteur.card_number == "F123456789012301"
    assert (conducteur.last_name, conducteur.first_name) == ("DUPONT", "MARIE")
    assert conducteur.birth_date == date(1985, 3, 14)
    assert conducteur.card_issuing_country == "F"
    assert conducteur.card_issuing_authority == "AUTORITE DE TEST"
    assert conducteur.card_issue_date == date(2022, 1, 10)
    assert conducteur.card_validity_begin == date(2022, 2, 1)
    assert conducteur.card_expiry_date == date(2027, 1, 31)
    assert conducteur.preferred_language == "fr"


def test_le_permis_de_conduire_est_decode() -> None:
    conducteur = C1BParser(carte().fichier()).extract_driver()

    assert conducteur is not None
    assert conducteur.licence_number == "PERMIS0001"
    assert conducteur.licence_issuing_authority == "PREFECTURE DE TEST"
    assert conducteur.licence_issuing_country == "F"


def test_le_jeu_de_caracteres_du_nom_est_respecte() -> None:
    """Code page 1 : ISO 8859-1 (appendice 1, chapitre 4)."""
    conducteur = C1BParser(carte(nom="LEFEVRE", prenom="HELENE").fichier()).extract_driver()

    assert conducteur is not None
    assert conducteur.first_name == "HELENE"


def test_une_date_de_naissance_absente_reste_absente() -> None:
    conducteur = C1BParser(carte(naissance=None).fichier()).extract_driver()

    assert conducteur is not None
    assert conducteur.birth_date is None


# --------------------------------------------------------------------------- #
# Activites (2.1, 2.9, 2.17)
# --------------------------------------------------------------------------- #
def test_les_changements_d_activite_deviennent_des_periodes() -> None:
    activites = C1BParser(carte().fichier()).extract_activities()

    resume = [(item.activity_type, item.start, item.end) for item in activites]
    assert resume == [
        (ActivityType.REST, heure(0), heure(6)),
        (ActivityType.WORK, heure(6), heure(6.25)),
        (ActivityType.DRIVING, heure(6.25), heure(10)),
        (ActivityType.REST, heure(10), heure(10.75)),
        (ActivityType.DRIVING, heure(10.75), heure(14)),
        (ActivityType.UNKNOWN, heure(14), heure(24)),
    ]


def test_le_statut_de_la_carte_est_conserve() -> None:
    activites = C1BParser(carte().fichier()).extract_activities()

    manuel, travail, *_, equipage, inconnu = activites
    assert (manuel.card_inserted, manuel.manual_entry) == (False, True)
    assert (travail.card_inserted, travail.crew, travail.card_slot) == (True, False, 1)
    assert equipage.crew is True
    assert (inconnu.card_inserted, inconnu.manual_entry) == (False, False)


def test_le_vehicule_est_rattache_aux_activites_carte_inseree() -> None:
    """Le vehicule est enregistre a la seconde, l'activite a la minute."""
    activites = C1BParser(carte().fichier()).extract_activities()

    assert [item.vehicle_registration for item in activites] == [
        None,
        "AB-123-CD",
        "AB-123-CD",
        "AB-123-CD",
        "AB-123-CD",
        None,
    ]


def test_une_journee_absente_de_la_carte_n_est_pas_comblee() -> None:
    jours = [
        (JOUR, [mot_activite(0, "REPOS")]),
        (JOUR + timedelta(days=2), [mot_activite(0, "REPOS")]),
    ]

    activites = C1BParser(carte(jours=jours).fichier()).extract_activities()

    assert len(activites) == 2
    assert activites[0].end == heure(24)
    assert activites[1].start == heure(48)


def test_la_memoire_circulaire_est_relue_apres_rebouclage() -> None:
    """Les enregistrements continuent au debut du tampon une fois la fin atteinte."""
    jours = [(JOUR + timedelta(days=index), journee_type()) for index in range(3)]
    fichier = carte(jours=jours, taille_activites=100, debut_activites=60).fichier()

    activites = C1BParser(fichier).extract_activities()

    debuts = {item.start.date() for item in activites}
    assert debuts == {JOUR + timedelta(days=index) for index in range(3)}


def test_la_journee_en_cours_s_arrete_a_l_instant_present() -> None:
    aujourd_hui = datetime.now(UTC).date()
    activites = C1BParser(
        carte(jours=[(aujourd_hui, [mot_activite(0, "REPOS")])]).fichier()
    ).extract_activities()

    assert activites[0].end <= datetime.now(UTC)


# --------------------------------------------------------------------------- #
# Vehicules, lieux, evenements, conditions
# --------------------------------------------------------------------------- #
def test_les_vehicules_utilises_sont_decodes() -> None:
    (vehicule,) = C1BParser(carte().fichier()).extract_vehicles_used()

    assert vehicule.registration == "AB-123-CD"
    assert vehicule.registration_country == "F"
    assert (vehicule.odometer_begin, vehicule.odometer_end, vehicule.distance) == (1000, 1250, 250)


def test_les_lieux_sont_decodes_avec_leur_pays() -> None:
    lieux = [(heure(6), 0, 0x11, 1000), (heure(14), 1, 0x0D, 1250)]

    debut, fin = C1BParser(carte(lieux=lieux).fichier()).extract_places()

    assert (debut.entry_type, debut.country, debut.country_name, debut.odometer) == (
        0,
        "F",
        "France",
        1000,
    )
    assert (fin.entry_type, fin.country) == (1, "D")


def test_les_evenements_sont_decodes_avec_leur_libelle() -> None:
    evenements = [(0x05, heure(7), heure(7), "AB-123-CD")]

    (evenement,) = C1BParser(carte(evenements=evenements).fichier()).extract_events()

    assert evenement.event_type_code == "05"
    assert evenement.description == "Insertion de la carte en cours de conduite"
    assert evenement.vehicle_registration == "AB-123-CD"
    assert evenement.is_fault is False


def test_les_conditions_particulieres_sont_decodees() -> None:
    (condition,) = C1BParser(
        carte(conditions=[(heure(9), 3)]).fichier()
    ).extract_specific_conditions()

    assert (condition.entry_time, condition.condition_type) == (heure(9), 3)


def test_le_resultat_complet_est_coherent() -> None:
    resultat = C1BParser(carte().fichier()).parse()

    assert resultat.is_complete is True
    assert resultat.driver is not None
    assert len(resultat.activities) == 6
    assert resultat.technical_data is not None
    assert resultat.technical_data.generation == "G2"


# --------------------------------------------------------------------------- #
# Conteneur (appendice 7)
# --------------------------------------------------------------------------- #
def test_un_conteneur_tronque_est_refuse() -> None:
    with pytest.raises(ParsingError):
        decode_container(carte().fichier()[:-10])


def test_une_etiquette_invalide_est_refusee() -> None:
    with pytest.raises(ParsingError):
        decode_container(tlv(0x0520, 0x07, b"\x00" * 4))


def test_l_empreinte_du_contenu_ignore_les_signatures() -> None:
    """Les signatures ECDSA de 2e generation changent a chaque telechargement."""
    premier = carte().fichier(signature=b"\xaa" * 128)
    second = carte().fichier(signature=b"\xbb" * 128)

    assert premier != second
    assert content_digest(premier) == content_digest(second)
    assert content_digest(carte(nom="AUTRE").fichier()) != content_digest(premier)


def test_l_empreinte_d_un_fichier_invalide_est_absente() -> None:
    assert content_digest(b"\x00\x01\x02") is None

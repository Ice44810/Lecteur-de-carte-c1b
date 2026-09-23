"""Tests du service des conducteurs."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from app.core.enums import ActivityType
from app.database.database import Database
from app.services.driver_service import DriverNotFoundError, DriverService, DriverSummary


@pytest.fixture
def service(migrated_database: Database) -> DriverService:
    """Service des conducteurs branche sur la base temporaire du test."""
    return DriverService(migrated_database)


# --------------------------------------------------------------------------- #
# Lecture
# --------------------------------------------------------------------------- #
def test_une_base_neuve_ne_contient_aucun_conducteur(service: DriverService) -> None:
    assert service.count() == 0
    assert service.list_drivers() == ()


def test_un_conducteur_enregistre_est_liste(service: DriverService, driver) -> None:
    fiches = service.list_drivers()

    assert len(fiches) == 1
    assert fiches[0].display_name == "DURAND Camille"
    assert fiches[0].card_number == "TESTCARD0000001"


def test_les_conducteurs_sont_tries_par_nom(service: DriverService) -> None:
    service.create(card_number="C2", last_name="Zola")
    service.create(card_number="C1", last_name="Bernard")

    assert [fiche.last_name for fiche in service.list_drivers()] == ["Bernard", "Zola"]


def test_la_liste_peut_etre_limitee(service: DriverService) -> None:
    for index in range(3):
        service.create(card_number=f"CARTE{index}", last_name=f"Nom{index}")

    assert len(service.list_drivers(limit=2)) == 2


def test_un_conducteur_se_retrouve_par_identifiant(service: DriverService, driver) -> None:
    assert service.get(driver.id).id == driver.id


def test_un_identifiant_inconnu_produit_un_message_exploitable(
    service: DriverService,
) -> None:
    with pytest.raises(DriverNotFoundError) as erreur:
        service.get(9999)

    message, cause, action = erreur.value.user_report()
    assert message and cause and action
    assert "Traceback" not in message


def test_un_conducteur_se_retrouve_par_numero_de_carte(service: DriverService, driver) -> None:
    fiche = service.get_by_card_number("TESTCARD0000001")

    assert fiche is not None
    assert fiche.id == driver.id


def test_un_numero_de_carte_inconnu_retourne_rien(service: DriverService) -> None:
    assert service.get_by_card_number("CARTE-INEXISTANTE") is None


# --------------------------------------------------------------------------- #
# Recherche
# --------------------------------------------------------------------------- #
def test_la_recherche_porte_sur_le_nom(service: DriverService, driver) -> None:
    assert len(service.search("durand")) == 1


def test_la_recherche_porte_sur_le_numero_de_carte(service: DriverService, driver) -> None:
    assert len(service.search("TESTCARD")) == 1


def test_une_recherche_vide_retourne_la_liste_complete(service: DriverService, driver) -> None:
    assert len(service.search("   ")) == 1


def test_une_recherche_sans_resultat_retourne_un_tuple_vide(service: DriverService, driver) -> None:
    assert service.search("inconnu") == ()


# --------------------------------------------------------------------------- #
# Creation manuelle
# --------------------------------------------------------------------------- #
def test_une_fiche_peut_etre_saisie_manuellement(service: DriverService) -> None:
    """La saisie manuelle est necessaire tant que le decodage n'est pas disponible."""
    fiche = service.create(
        card_number="F1234567890123",
        first_name="Alex",
        last_name="Martin",
        card_issuing_country="F",
        card_expiry_date=date(2030, 6, 30),
    )

    assert fiche.id > 0
    assert fiche.display_name == "MARTIN Alex"
    assert service.count() == 1


def test_un_numero_de_carte_vide_est_refuse(service: DriverService) -> None:
    with pytest.raises(ValueError, match="numero de carte"):
        service.create(card_number="   ")


def test_une_seconde_creation_ne_duplique_pas_la_fiche(service: DriverService) -> None:
    premiere = service.create(card_number="F1234567890123", last_name="MARTIN")
    seconde = service.create(card_number="F1234567890123", last_name="MARTIN")

    assert premiere.id == seconde.id
    assert service.count() == 1


def test_le_numero_de_carte_est_nettoye_des_espaces(service: DriverService) -> None:
    fiche = service.create(card_number="  F1234567890123  ")

    assert fiche.card_number == "F1234567890123"


def test_les_champs_vides_ne_sont_pas_enregistres_comme_chaines(
    service: DriverService,
) -> None:
    fiche = service.create(card_number="F1234567890123", first_name="", last_name="")

    assert fiche.first_name is None
    assert fiche.last_name is None


def test_une_fiche_sans_nom_reste_identifiable(service: DriverService) -> None:
    fiche = service.create(card_number="F1234567890123")

    assert "F1234567890123" in fiche.display_name


# --------------------------------------------------------------------------- #
# Donnees derivees
# --------------------------------------------------------------------------- #
def test_le_nombre_d_activites_est_rapporte(
    service: DriverService, driver, add_activity, reference_day: datetime
) -> None:
    add_activity(ActivityType.DRIVING, reference_day, reference_day.replace(hour=4))
    add_activity(ActivityType.REST, reference_day.replace(hour=4), reference_day.replace(hour=8))

    fiche = service.get(driver.id)

    assert fiche.activities_count == 2
    assert fiche.last_activity_end == reference_day.date()


def test_le_nombre_de_fichiers_rattaches_est_rapporte(
    service: DriverService, driver, add_file
) -> None:
    add_file(sha256="a" * 64, driver_id=driver.id)

    assert service.get(driver.id).files_count == 1


def test_un_conducteur_sans_activite_ne_declare_aucune_date(service: DriverService, driver) -> None:
    fiche = service.get(driver.id)

    assert fiche.activities_count == 0
    assert fiche.last_activity_end is None


# --------------------------------------------------------------------------- #
# Etat de la carte
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("expiration", "reference", "attendu"),
    [
        (None, date(2026, 9, 23), "Inconnue"),
        (date(2026, 1, 1), date(2026, 9, 23), "Expiree"),
        (date(2030, 1, 1), date(2026, 9, 23), "Valide"),
    ],
)
def test_l_etat_de_la_carte_est_qualifie(
    expiration: date | None, reference: date, attendu: str
) -> None:
    fiche = DriverSummary(
        id=1,
        card_number="F1234567890123",
        display_name="MARTIN Alex",
        card_expiry_date=expiration,
    )

    assert fiche.card_expiry_status(reference) == attendu


def test_le_service_ne_retourne_jamais_d_objet_orm(service: DriverService, driver) -> None:
    """Frontiere de couche : l'interface ne doit pas pouvoir declencher de requete."""
    fiche = service.get(driver.id)

    assert isinstance(fiche, DriverSummary)
    assert not hasattr(fiche, "_sa_instance_state")

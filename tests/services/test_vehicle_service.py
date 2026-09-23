"""Tests du service des vehicules."""

from __future__ import annotations

from datetime import datetime

import pytest

from app.core.enums import ActivityType
from app.database.database import Database
from app.services.vehicle_service import VehicleNotFoundError, VehicleService, VehicleSummary


@pytest.fixture
def service(migrated_database: Database) -> VehicleService:
    """Service des vehicules branche sur la base temporaire du test."""
    return VehicleService(migrated_database)


def test_une_base_neuve_ne_contient_aucun_vehicule(service: VehicleService) -> None:
    assert service.count() == 0
    assert service.list_vehicles() == ()


def test_un_vehicule_enregistre_est_liste(service: VehicleService, vehicle) -> None:
    fiches = service.list_vehicles()

    assert len(fiches) == 1
    assert fiches[0].registration == "AA-123-BB"
    assert fiches[0].display_name == "AA-123-BB"


def test_les_vehicules_sont_tries_par_immatriculation(service: VehicleService) -> None:
    service.create(registration="ZZ-999-ZZ")
    service.create(registration="AA-111-AA")

    assert [fiche.registration for fiche in service.list_vehicles()] == [
        "AA-111-AA",
        "ZZ-999-ZZ",
    ]


def test_la_liste_peut_etre_limitee(service: VehicleService) -> None:
    for index in range(3):
        service.create(registration=f"AA-00{index}-AA")

    assert len(service.list_vehicles(limit=2)) == 2


def test_un_vehicule_se_retrouve_par_identifiant(service: VehicleService, vehicle) -> None:
    assert service.get(vehicle.id).registration == "AA-123-BB"


def test_un_identifiant_inconnu_produit_un_message_exploitable(
    service: VehicleService,
) -> None:
    with pytest.raises(VehicleNotFoundError) as erreur:
        service.get(9999)

    message, cause, action = erreur.value.user_report()
    assert message and cause and action
    assert "Traceback" not in message


def test_une_fiche_peut_etre_creee(service: VehicleService) -> None:
    fiche = service.create(
        registration="BB-456-CC",
        registration_country="F",
        vin="VF1234567890ABCDE",
        tachograph_identifier="UE-0001",
    )

    assert fiche.registration == "BB-456-CC"
    assert fiche.vin == "VF1234567890ABCDE"
    assert fiche.tachograph_identifier == "UE-0001"


def test_l_immatriculation_est_normalisee(service: VehicleService) -> None:
    assert service.create(registration="  bb-456-cc ").registration == "BB-456-CC"


def test_une_immatriculation_vide_est_refusee(service: VehicleService) -> None:
    with pytest.raises(ValueError, match="immatriculation"):
        service.create(registration="  ")


def test_une_seconde_creation_ne_duplique_pas_la_fiche(service: VehicleService) -> None:
    premiere = service.create(registration="BB-456-CC")
    seconde = service.create(registration="bb-456-cc")

    assert premiere.id == seconde.id
    assert service.count() == 1


def test_le_nombre_d_activites_rattachees_est_rapporte(
    service: VehicleService,
    vehicle,
    add_activity,
    reference_day: datetime,
) -> None:
    add_activity(
        ActivityType.DRIVING,
        reference_day,
        reference_day.replace(hour=3),
        vehicle_id=vehicle.id,
    )

    assert service.get(vehicle.id).activities_count == 1


def test_le_service_ne_retourne_jamais_d_objet_orm(service: VehicleService, vehicle) -> None:
    fiche = service.get(vehicle.id)

    assert isinstance(fiche, VehicleSummary)
    assert not hasattr(fiche, "_sa_instance_state")

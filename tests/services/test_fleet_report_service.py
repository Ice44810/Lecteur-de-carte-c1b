"""Tests des statistiques et controles de flotte (cartes fictives)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from app.bootstrap import ApplicationContext
from app.services.driver_service import DriverService
from app.services.fleet_report_service import FleetReportService
from app.services.import_service import ImportService
from app.services.vehicle_service import VehicleService
from tests.parser.c1b_synthetique import mot_activite
from tests.services.test_import_service import carte_synthetique

JOUR = date(2025, 10, 1)


def utc(jour: int, heure: float) -> datetime:
    return datetime(2025, 10, jour, tzinfo=UTC) + timedelta(minutes=round(heure * 60))


def journee(debut: float, fin: float) -> list[int]:
    return [
        mot_activite(0, "REPOS"),
        mot_activite(round(debut * 60), "CONDUITE"),
        mot_activite(round(fin * 60), "REPOS"),
    ]


@pytest.fixture
def flotte(context: ApplicationContext, tmp_path) -> FleetReportService:
    """Deux conducteurs fictifs partagent le vehicule AB-123-CD.

    Marie : 1er et 3 octobre (rien le 2), compteur 1000 -> 1300 puis 1310 -> 1500.
    Paul : 2 octobre, AB-123-CD de 1300 a 1310 (continuite assuree) et EF-456-GH.
    Entre le 3 (1500) et un retour de Marie le 3 a 1520 : 20 km sans carte.
    """
    imports = ImportService(context.database, settings=context.settings)
    imports.import_file(
        carte_synthetique(
            tmp_path,
            "marie.C1B",
            jours=[(JOUR, journee(6, 10)), (JOUR + timedelta(days=2), journee(6, 12))],
            vehicules=[
                (utc(1, 6), utc(1, 10), "AB-123-CD", 1000, 1300),
                (utc(3, 6), utc(3, 9), "AB-123-CD", 1310, 1500),
                (utc(3, 9.5), utc(3, 12), "AB-123-CD", 1520, 1600),
            ],
            evenements=[(0x07, utc(3, 7), utc(3, 7.1), "AB-123-CD")],
        )
    )
    imports.import_file(
        carte_synthetique(
            tmp_path,
            "paul.C1B",
            numero="F999999999999901",
            nom="MARTIN",
            prenom="PAUL",
            jours=[(JOUR + timedelta(days=1), journee(8, 9))],
            vehicules=[
                (utc(2, 8), utc(2, 8.5), "AB-123-CD", 1300, 1310),
                (utc(2, 8.5), utc(2, 9), "EF-456-GH", 50, 80),
            ],
        )
    )
    return FleetReportService(context.database, settings=context.settings)


def periode(service: FleetReportService) -> tuple[datetime, datetime]:
    return service.local_day_bounds(JOUR, date(2025, 10, 3))


def test_l_activite_cumulee_totalise_par_conducteur(flotte: FleetReportService) -> None:
    tableau = flotte.cumulative_activity(*periode(flotte), daily=False)

    totaux = {ligne[0]: ligne[2] for ligne in tableau.rows}
    assert totaux == {"DUPONT MARIE": "10h00", "MARTIN PAUL": "01h00"}


def test_le_detail_journalier_suit_les_journees_locales(flotte: FleetReportService) -> None:
    tableau = flotte.cumulative_activity(*periode(flotte), daily=True)

    marie = [ligne for ligne in tableau.rows if ligne[0] == "DUPONT MARIE"]
    assert [ligne[1] for ligne in marie] == ["01/10/2025", "02/10/2025", "03/10/2025", "Total"]
    assert marie[0][2] == "04h00"


def test_les_heures_peuvent_etre_exprimees_en_centiemes(flotte: FleetReportService) -> None:
    tableau = flotte.cumulative_activity(*periode(flotte), daily=False, centesimal=True)

    assert {ligne[0]: ligne[2] for ligne in tableau.rows}["MARTIN PAUL"] == "1,00"


def test_les_distances_sont_cumulees_par_conducteur_et_par_vehicule(
    flotte: FleetReportService,
) -> None:
    conducteurs = flotte.driver_distance(*periode(flotte), daily=False)
    vehicules = flotte.vehicle_distance(*periode(flotte), daily=False)

    assert {ligne[0]: ligne[2] for ligne in conducteurs.rows} == {
        "DUPONT MARIE": "570",
        "MARTIN PAUL": "40",
    }
    assert {ligne[0]: ligne[2] for ligne in vehicules.rows} == {
        "AB-123-CD": "580",
        "EF-456-GH": "30",
    }


def test_les_exces_de_vitesse_des_cartes_sont_listes(flotte: FleetReportService) -> None:
    (ligne,) = flotte.speeding(*periode(flotte)).rows

    assert ligne[0] == "DUPONT MARIE"
    assert ligne[6] == "Exces de vitesse"


def test_un_trajet_sans_carte_est_detecte_par_le_compteur(flotte: FleetReportService) -> None:
    (ecart,) = flotte.driving_without_card(*periode(flotte), minimum_km=2).rows

    assert ecart[0] == "AB-123-CD"
    assert (ecart[3], ecart[6], ecart[7]) == ("1500", "1520", "20")
    assert flotte.driving_without_card(*periode(flotte), minimum_km=50).rows == ()


def test_la_continuite_vehicule_tient_compte_de_tous_les_conducteurs(
    flotte: FleetReportService,
) -> None:
    """Le trajet de Paul comble l'ecart entre les deux utilisations de Marie."""
    ecarts = flotte.vehicle_continuity(*periode(flotte)).rows

    assert [ligne[7] for ligne in ecarts] == ["20"]


def test_la_continuite_conducteur_signale_les_jours_sans_enregistrement(
    flotte: FleetReportService,
) -> None:
    lignes = [
        ligne
        for ligne in flotte.driver_continuity(*periode(flotte)).rows
        if ligne[0] == "DUPONT MARIE"
    ]

    # Le 2 octobre manque entierement (de 02h00 a 02h00, heure de Paris) ; les deux
    # premieres heures du 1er precedent la journee UTC enregistree sur la carte.
    assert [(ligne[2], ligne[4]) for ligne in lignes] == [
        ("01/10/2025 00:00", "02h00"),
        ("02/10/2025 02:00", "24h00"),
    ]


def test_le_delai_de_telechargement_des_cartes_est_mesure(flotte: FleetReportService) -> None:
    dans_30_jours = datetime.now(UTC) + timedelta(days=30)

    tableau = flotte.driver_download_delays(reference=dans_30_jours)

    assert {ligne[4] for ligne in tableau.rows} == {"Delai depasse"}
    assert "581/2010" in tableau.note


def test_le_delai_vehicule_porte_sur_les_vehicules_de_la_flotte(
    flotte: FleetReportService, context: ApplicationContext
) -> None:
    VehicleService(context.database).create(registration="AB-123-CD")

    (ligne,) = flotte.vehicle_download_delays().rows

    assert ligne[0] == "AB-123-CD"
    assert ligne[2] == "Jamais"


def test_les_conducteurs_et_vehicules_non_confirmes_sont_inconnus(
    flotte: FleetReportService, context: ApplicationContext
) -> None:
    marie = DriverService(context.database).get_by_card_number("F123456789012301")
    assert marie is not None
    DriverService(context.database).set_in_fleet(marie.id, True)
    VehicleService(context.database).create(registration="AB-123-CD")

    assert [ligne[0] for ligne in flotte.unknown_drivers().rows] == ["MARTIN PAUL"]
    assert [ligne[0] for ligne in flotte.unknown_vehicles(*periode(flotte)).rows] == ["EF-456-GH"]


def test_une_saisie_manuelle_confirme_la_flotte(context: ApplicationContext) -> None:
    fiche = DriverService(context.database).create(card_number="F000000000000001")
    vehicule = VehicleService(context.database).create(registration="ZZ-000-ZZ")

    assert fiche.in_fleet is True
    assert vehicule.in_fleet is True
    assert VehicleService(context.database).set_in_fleet(vehicule.id, False).in_fleet is False


def test_les_exports_regroupent_les_tableaux(flotte: FleetReportService) -> None:
    detaille = flotte.detailed_tables(*periode(flotte))
    anomalies = flotte.anomaly_tables(*periode(flotte), minimum_km=2)

    assert [tableau.title for tableau in detaille][0] == "Synthese"
    assert len(detaille) == 6
    assert [tableau.title for tableau in anomalies] == [
        "Evenements et anomalies",
        "Conduites sans carte",
        "Delai archivage conducteurs",
        "Situations a verifier",
    ]
    assert flotte.summary(*periode(flotte)).rows[0][-1] == "570"

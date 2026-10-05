"""Tests du service du tableau de bord.

Exigence testee en priorite : **aucune valeur affichee n'est ecrite en dur**. Chaque
indicateur doit provenir de la base, et une base vide doit produire des indicateurs
neutres plutot que des chiffres trompeurs. Le tableau de bord doit egalement avertir
l'utilisateur lorsqu'aucune regle n'est active, afin qu'il ne prenne pas l'absence
d'alerte pour une conformite constatee.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.core.enums import ActivityType, FileType, ParsingStatus
from app.database.database import Database
from app.services.dashboard_service import DashboardData, DashboardService

SEMAINE = datetime(2026, 9, 16, 12, tzinfo=UTC)  # mercredi
LUNDI = datetime(2026, 9, 14, tzinfo=UTC)


@pytest.fixture
def service(migrated_database: Database) -> DashboardService:
    """Service du tableau de bord branche sur la base temporaire du test."""
    return DashboardService(migrated_database)


# --------------------------------------------------------------------------- #
# Base vide
# --------------------------------------------------------------------------- #
def test_une_base_vide_produit_des_indicateurs_neutres(service: DashboardService) -> None:
    donnees = service.load(reference=SEMAINE)

    assert donnees.drivers_count == 0
    assert donnees.files_count == 0
    assert donnees.last_import_at is None
    assert donnees.recent_activity == ()
    assert donnees.alerts == ()
    assert donnees.is_empty is True


def test_l_absence_de_telechargement_est_dite_et_non_chiffree(
    service: DashboardService,
) -> None:
    assert service.load(reference=SEMAINE).last_import_label == "Aucun"


# --------------------------------------------------------------------------- #
# Comptages issus de la base
# --------------------------------------------------------------------------- #
def test_les_comptages_proviennent_de_la_base(
    service: DashboardService, driver, vehicle, add_file
) -> None:
    add_file(filename="a.C1B", sha256="a" * 64)
    add_file(filename="b.V1B", file_type=FileType.V1B, sha256="b" * 64)

    donnees = service.load(reference=SEMAINE)

    assert donnees.drivers_count == 1
    assert donnees.vehicles_count == 1
    assert donnees.files_count == 2
    assert donnees.c1b_count == 1
    assert donnees.v1b_count == 1
    assert donnees.is_empty is False


def test_les_fichiers_non_decodes_sont_comptes(service: DashboardService, add_file) -> None:
    add_file(filename="a.C1B", sha256="a" * 64, parsing_status=ParsingStatus.PENDING)
    add_file(filename="b.C1B", sha256="b" * 64, parsing_status=ParsingStatus.UNSUPPORTED)
    add_file(filename="c.C1B", sha256="c" * 64, parsing_status=ParsingStatus.SUCCESS)

    assert service.load(reference=SEMAINE).pending_parsing_count == 2


def test_la_date_du_dernier_import_est_formatee(service: DashboardService, add_file) -> None:
    add_file(sha256="a" * 64, imported_at=datetime(2026, 9, 20, 8, 30, tzinfo=UTC))

    assert service.load(reference=SEMAINE).last_import_label == "20/09/2026 08:30"


# --------------------------------------------------------------------------- #
# Cumuls de la semaine
# --------------------------------------------------------------------------- #
def test_les_cumuls_portent_sur_la_semaine_du_lundi(
    service: DashboardService, driver, add_activity
) -> None:
    add_activity(ActivityType.DRIVING, LUNDI + timedelta(hours=7), LUNDI + timedelta(hours=11))
    add_activity(ActivityType.REST, LUNDI + timedelta(hours=11), LUNDI + timedelta(hours=20))

    donnees = service.load(reference=SEMAINE)

    assert donnees.week_driving_seconds == 4 * 3600
    assert donnees.week_rest_seconds == 9 * 3600
    assert donnees.week_driving_label == "04h00"
    assert donnees.week_rest_label == "09h00"


def test_une_activite_de_la_semaine_precedente_est_exclue(
    service: DashboardService, driver, add_activity
) -> None:
    precedente = LUNDI - timedelta(days=2)
    add_activity(
        ActivityType.DRIVING, precedente + timedelta(hours=7), precedente + timedelta(hours=11)
    )

    assert service.load(reference=SEMAINE).week_driving_seconds == 0


def test_les_conducteurs_actifs_de_la_semaine_sont_comptes(
    service: DashboardService, driver, add_activity
) -> None:
    add_activity(ActivityType.DRIVING, LUNDI + timedelta(hours=7), LUNDI + timedelta(hours=9))

    assert service.load(reference=SEMAINE).active_drivers_this_week == 1


# --------------------------------------------------------------------------- #
# Activite recente
# --------------------------------------------------------------------------- #
def test_l_activite_recente_resume_la_journee_de_service(
    service: DashboardService, driver, add_activity
) -> None:
    jour = datetime(2026, 9, 15, tzinfo=UTC)
    add_activity(ActivityType.WORK, jour + timedelta(hours=6), jour + timedelta(hours=7))
    add_activity(ActivityType.DRIVING, jour + timedelta(hours=7), jour + timedelta(hours=11))
    add_activity(ActivityType.WORK, jour + timedelta(hours=11), jour + timedelta(hours=12))

    lignes = service.load(reference=SEMAINE).recent_activity

    assert len(lignes) == 1
    assert lignes[0].day_label == "15/09/2026"
    assert lignes[0].time_range == "06:00 - 12:00"
    assert lignes[0].driving_label == "04h00"


def test_une_journee_de_repos_seul_n_apparait_pas_comme_service(
    service: DashboardService, driver, add_activity
) -> None:
    jour = datetime(2026, 9, 15, tzinfo=UTC)
    add_activity(ActivityType.REST, jour, jour + timedelta(hours=20))

    assert service.load(reference=SEMAINE).recent_activity == ()


def test_le_nombre_de_lignes_recentes_est_limitable(
    service: DashboardService, driver, add_activity
) -> None:
    jour = datetime(2026, 9, 15, tzinfo=UTC)
    add_activity(ActivityType.DRIVING, jour + timedelta(hours=7), jour + timedelta(hours=9))

    assert len(service.load(reference=SEMAINE, recent_limit=0).recent_activity) == 0


# --------------------------------------------------------------------------- #
# Regles actives
# --------------------------------------------------------------------------- #
def test_l_absence_de_regle_active_est_signalee(service: DashboardService) -> None:
    """L'utilisateur ne doit pas interpreter l'absence d'alerte comme une conformite."""
    donnees = service.load(reference=SEMAINE)

    assert donnees.rules_active_count == 0
    avertissement = donnees.rules_notice
    assert avertissement is not None
    assert "aucun depassement n'est recherche" in avertissement


def test_la_version_du_jeu_de_seuils_est_rapportee(service: DashboardService) -> None:
    assert service.load(reference=SEMAINE).ruleset_version == "0.0.0-empty"


def test_aucun_avertissement_lorsque_des_regles_sont_actives() -> None:
    donnees = DashboardData(rules_active_count=3)

    assert donnees.rules_notice is None


# --------------------------------------------------------------------------- #
# Alertes
# --------------------------------------------------------------------------- #
def test_aucune_alerte_n_est_produite_sans_regle(service: DashboardService, driver) -> None:
    donnees = service.load(reference=SEMAINE)

    assert donnees.open_alerts_count == 0
    assert donnees.alerts == ()


def test_l_instant_de_reference_est_conserve(service: DashboardService) -> None:
    assert service.load(reference=SEMAINE).generated_at == SEMAINE

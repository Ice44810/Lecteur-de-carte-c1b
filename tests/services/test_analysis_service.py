"""Tests du service d'analyse.

Le service fait la jonction entre la base et le moteur de calcul. Les tests verifient
qu'il lit bien les activites, delegue les calculs, et surtout qu'il **rend visible
l'absence de donnee** : une periode sans enregistrement apparait explicitement dans la
frise, et n'est jamais presentee comme du repos.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.core.enums import ActivityType
from app.database.database import Database
from app.services.analysis_service import AnalysisService, PeriodAnalysis, TimelineEntry

JOUR = datetime(2026, 9, 15, tzinfo=UTC)  # mardi
LENDEMAIN = JOUR + timedelta(days=1)


@pytest.fixture
def service(migrated_database: Database) -> AnalysisService:
    """Service d'analyse branche sur la base temporaire du test."""
    return AnalysisService(migrated_database)


@pytest.fixture
def journee_enregistree(add_activity, driver) -> None:
    """Journee de service complete enregistree en base.

    06h00-07h00 travail, 07h00-10h45 conduite, 10h45-11h30 repos, 11h30-15h30
    conduite, 15h30-16h00 disponibilite, 16h00-17h00 travail. Conduite : 7h45.
    """
    for type_activite, debut, fin in (
        (ActivityType.WORK, 6, 7),
        (ActivityType.DRIVING, 7, 10.75),
        (ActivityType.REST, 10.75, 11.5),
        (ActivityType.DRIVING, 11.5, 15.5),
        (ActivityType.AVAILABILITY, 15.5, 16),
        (ActivityType.WORK, 16, 17),
    ):
        add_activity(type_activite, JOUR + timedelta(hours=debut), JOUR + timedelta(hours=fin))


@pytest.fixture
def journee_avec_trou(add_activity, driver) -> None:
    """Journee comportant une heure sans aucun enregistrement (09h00-10h00)."""
    add_activity(ActivityType.DRIVING, JOUR + timedelta(hours=7), JOUR + timedelta(hours=9))
    add_activity(ActivityType.WORK, JOUR + timedelta(hours=10), JOUR + timedelta(hours=11))


# --------------------------------------------------------------------------- #
# Lecture des activites
# --------------------------------------------------------------------------- #
def test_une_periode_sans_activite_retourne_un_tuple_vide(service: AnalysisService, driver) -> None:
    assert service.load_intervals(driver.id, period_start=JOUR, period_end=LENDEMAIN) == ()


def test_les_activites_sont_converties_en_intervalles(
    service: AnalysisService, driver, journee_enregistree
) -> None:
    intervalles = service.load_intervals(driver.id, period_start=JOUR, period_end=LENDEMAIN)

    assert len(intervalles) == 6
    assert intervalles[0].activity_type is ActivityType.WORK
    assert intervalles[0].start == JOUR + timedelta(hours=6)


def test_les_intervalles_sont_bornes_a_la_periode(
    service: AnalysisService, driver, journee_enregistree
) -> None:
    intervalles = service.load_intervals(
        driver.id,
        period_start=JOUR + timedelta(hours=8),
        period_end=JOUR + timedelta(hours=9),
    )

    assert all(interval.start >= JOUR + timedelta(hours=8) for interval in intervalles)
    assert all(interval.end <= JOUR + timedelta(hours=9) for interval in intervalles)


# --------------------------------------------------------------------------- #
# Frise journaliere
# --------------------------------------------------------------------------- #
def test_la_frise_est_chronologique(service: AnalysisService, driver, journee_enregistree) -> None:
    frise = service.daily_timeline(driver.id, JOUR.date())

    debuts = [ligne.start for ligne in frise]
    assert debuts == sorted(debuts)


def test_la_frise_affiche_les_plages_et_les_durees(
    service: AnalysisService, driver, journee_enregistree
) -> None:
    frise = service.daily_timeline(driver.id, JOUR.date())

    premiere = frise[0]
    assert premiere.time_range == "06:00 - 07:00"
    assert premiere.duration_label == "01h00"
    assert premiere.label == ActivityType.WORK.label


def test_les_periodes_sans_enregistrement_sont_explicites(
    service: AnalysisService, driver, journee_avec_trou
) -> None:
    """Un trou de donnees doit se voir, et ne jamais etre comble par du repos."""
    frise = service.daily_timeline(driver.id, JOUR.date())

    trous = [ligne for ligne in frise if ligne.is_gap]
    assert len(trous) == 1
    assert trous[0].time_range == "09:00 - 10:00"
    assert trous[0].label == "Aucun enregistrement"
    assert trous[0].activity_type is not ActivityType.REST


def test_les_trous_peuvent_etre_masques(
    service: AnalysisService, driver, journee_avec_trou
) -> None:
    frise = service.daily_timeline(driver.id, JOUR.date(), include_gaps=False)

    assert all(not ligne.is_gap for ligne in frise)


def test_une_journee_continue_ne_signale_aucun_trou(
    service: AnalysisService, driver, journee_enregistree
) -> None:
    frise = service.daily_timeline(driver.id, JOUR.date())

    assert all(not ligne.is_gap for ligne in frise)


def test_la_frise_se_filtre_par_type(service: AnalysisService, driver, journee_enregistree) -> None:
    frise = service.daily_timeline(
        driver.id,
        JOUR.date(),
        activity_types=(ActivityType.DRIVING,),
        include_gaps=False,
    )

    assert {ligne.activity_type for ligne in frise} == {ActivityType.DRIVING}


def test_les_enregistrements_contigus_de_meme_type_sont_fusionnes(
    service: AnalysisService, driver, add_activity
) -> None:
    add_activity(ActivityType.DRIVING, JOUR + timedelta(hours=7), JOUR + timedelta(hours=8))
    add_activity(ActivityType.DRIVING, JOUR + timedelta(hours=8), JOUR + timedelta(hours=9))

    frise = service.daily_timeline(driver.id, JOUR.date(), include_gaps=False)

    assert len(frise) == 1
    assert frise[0].duration_seconds == 2 * 3600


def test_la_fusion_peut_etre_desactivee(service: AnalysisService, driver, add_activity) -> None:
    add_activity(ActivityType.DRIVING, JOUR + timedelta(hours=7), JOUR + timedelta(hours=8))
    add_activity(ActivityType.DRIVING, JOUR + timedelta(hours=8), JOUR + timedelta(hours=9))

    frise = service.daily_timeline(
        driver.id, JOUR.date(), include_gaps=False, merge_contiguous=False
    )

    assert len(frise) == 2


def test_une_journee_sans_donnee_produit_une_frise_vide(service: AnalysisService, driver) -> None:
    assert service.daily_timeline(driver.id, JOUR.date()) == ()


# --------------------------------------------------------------------------- #
# Analyse d'une periode
# --------------------------------------------------------------------------- #
def test_l_analyse_journaliere_totalise_les_temps(
    service: AnalysisService, driver, journee_enregistree
) -> None:
    analyse = service.analyze_day(driver.id, JOUR.date())

    assert analyse.driving_seconds == int(7.75 * 3600)
    assert analyse.rest_seconds == int(0.75 * 3600)
    assert analyse.working_seconds == int(9.75 * 3600)
    assert analyse.availability_seconds == int(0.5 * 3600)
    assert analyse.activities_count == 6
    assert analyse.has_data is True


def test_l_analyse_hebdomadaire_couvre_la_semaine_du_lundi(
    service: AnalysisService, driver, journee_enregistree
) -> None:
    analyse = service.analyze_week(driver.id, JOUR)

    assert analyse.period_start == datetime(2026, 9, 14, tzinfo=UTC)
    assert analyse.period_end == datetime(2026, 9, 21, tzinfo=UTC)
    assert analyse.driving_seconds == int(7.75 * 3600)


def test_l_analyse_signale_les_periodes_sans_enregistrement(
    service: AnalysisService, driver, journee_avec_trou
) -> None:
    analyse = service.analyze_day(driver.id, JOUR.date())

    assert analyse.gaps == ((JOUR + timedelta(hours=9), JOUR + timedelta(hours=10)),)


def test_une_periode_vide_est_annoncee_comme_telle(service: AnalysisService, driver) -> None:
    analyse = service.analyze_day(driver.id, JOUR.date())

    assert analyse.has_data is False
    assert analyse.activities_count == 0
    assert analyse.summary_message() == "Aucune activite enregistree sur la periode selectionnee."


def test_les_cumuls_par_type_sont_disponibles(
    service: AnalysisService, driver, journee_enregistree
) -> None:
    analyse = service.analyze_day(driver.id, JOUR.date())

    assert analyse.totals.driving == int(7.75 * 3600)
    assert analyse.totals.work == 2 * 3600
    assert analyse.totals.as_dict()[ActivityType.AVAILABILITY] == int(0.5 * 3600)


# --------------------------------------------------------------------------- #
# Aucune regle active
# --------------------------------------------------------------------------- #
def test_aucune_alerte_n_est_produite_sans_regle_active(
    service: AnalysisService, driver, journee_enregistree
) -> None:
    analyse = service.analyze_day(driver.id, JOUR.date())

    assert analyse.alerts_count == 0
    assert analyse.evaluation is not None
    assert analyse.evaluation.rules_evaluated == 0


def test_le_message_de_synthese_indique_l_absence_de_controle(
    service: AnalysisService, driver, journee_enregistree
) -> None:
    """Sans regle active, l'utilisateur doit savoir qu'aucun controle n'a eu lieu."""
    message = service.analyze_day(driver.id, JOUR.date()).summary_message()

    assert "aucune regle" in message.lower()
    assert "infraction" not in message.lower()


def test_le_registre_et_le_jeu_de_seuils_sont_exposes(service: AnalysisService) -> None:
    assert service.registry.is_empty is True
    assert service.ruleset.is_empty is True


# --------------------------------------------------------------------------- #
# Ecriture differee en phase 6
# --------------------------------------------------------------------------- #
def test_l_enregistrement_d_une_analyse_echoue_explicitement(
    service: AnalysisService, driver, journee_enregistree
) -> None:
    analyse = service.analyze_day(driver.id, JOUR.date())

    with pytest.raises(NotImplementedError, match="phase 6"):
        service.store_analysis(analyse)


# --------------------------------------------------------------------------- #
# Objets de transfert
# --------------------------------------------------------------------------- #
def test_une_ligne_de_frise_distingue_l_absence_de_donnee() -> None:
    ligne = TimelineEntry(
        activity_type=ActivityType.UNKNOWN,
        start=JOUR,
        end=JOUR + timedelta(hours=1),
        duration_seconds=3600,
        is_gap=True,
    )

    assert ligne.label == "Aucun enregistrement"
    assert ligne.duration_label == "01h00"


def test_une_analyse_sans_evaluation_reste_exploitable() -> None:
    from app.analysis.models import PeriodTotals

    analyse = PeriodAnalysis(
        driver_id=1,
        period_start=JOUR,
        period_end=LENDEMAIN,
        totals=PeriodTotals.from_intervals(()),
        driving_seconds=0,
        rest_seconds=0,
        working_seconds=0,
        availability_seconds=0,
        activities_count=1,
    )

    assert analyse.alerts_count == 0
    assert analyse.summary_message() == "Analyse des temps terminee."

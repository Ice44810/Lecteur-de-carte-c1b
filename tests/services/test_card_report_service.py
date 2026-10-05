"""Tests du rapport de carte : periodes de travail, interruptions, rubriques."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from app.bootstrap import ApplicationContext
from app.core.enums import ActivityType
from app.reports.tables import card_report_tables
from app.services.card_report_service import CardReportError, CardReportService
from app.services.import_service import ImportService
from tests.parser.c1b_synthetique import mot_activite
from tests.services.test_import_service import carte_synthetique

JOUR = date(2025, 10, 1)


def minute(heures: float) -> int:
    return round(heures * 60)


@pytest.fixture
def service(context: ApplicationContext) -> CardReportService:
    return CardReportService(context.database, settings=context.settings)


def importer(context: ApplicationContext, tmp_path, jours) -> int:
    ImportService(context.database, settings=context.settings).import_file(
        carte_synthetique(tmp_path, jours=jours)
    )
    return 1


def journee(debut: float, fin: float) -> list[int]:
    """Repos, conduite de ``debut`` a ``fin`` (heures UTC), puis repos."""
    return [
        mot_activite(0, "REPOS"),
        mot_activite(minute(debut), "CONDUITE"),
        mot_activite(minute(fin), "REPOS"),
    ]


def rapport(service: CardReportService, premier: date, dernier: date):
    debut, fin = service.local_day_bounds(premier, dernier)
    return service.build(1, period_start=debut, period_end=fin)


def test_les_periodes_sont_separees_par_une_longue_interruption(
    service: CardReportService, context: ApplicationContext, tmp_path
) -> None:
    importer(
        context, tmp_path, [(JOUR, journee(6, 14)), (JOUR + timedelta(days=1), journee(5, 12))]
    )

    resultat = rapport(service, JOUR, JOUR + timedelta(days=1))

    premiere, seconde = resultat.work_periods
    assert premiere.totals.driving == 8 * 3600
    assert premiere.rest_after_seconds == 15 * 3600
    # 6h00 + 24 h = 6h00 le lendemain : 16 h de repos dans la fenetre de 24 h.
    assert premiere.rest_within_24h_seconds is None
    assert premiere.rest_label == "15h00"
    assert seconde.rest_after_seconds is None


def test_la_part_de_repos_dans_les_24_heures_est_indiquee(
    service: CardReportService, context: ApplicationContext, tmp_path
) -> None:
    importer(
        context, tmp_path, [(JOUR, journee(6, 14)), (JOUR + timedelta(days=1), journee(8, 12))]
    )

    premiere, _ = rapport(service, JOUR, JOUR + timedelta(days=1)).work_periods

    assert premiere.rest_after_seconds == 18 * 3600
    assert premiere.rest_within_24h_seconds == 16 * 3600
    assert premiere.rest_label == "18h00 (16h00)"


def test_une_courte_pause_ne_coupe_pas_la_periode(
    service: CardReportService, context: ApplicationContext, tmp_path
) -> None:
    mots = [
        mot_activite(0, "REPOS"),
        mot_activite(minute(6), "CONDUITE"),
        mot_activite(minute(10), "REPOS"),
        mot_activite(minute(11), "TRAVAIL"),
        mot_activite(minute(13), "REPOS"),
    ]
    importer(context, tmp_path, [(JOUR, mots)])

    (periode,) = rapport(service, JOUR, JOUR).work_periods

    assert periode.span_seconds == 7 * 3600
    assert (periode.totals.driving, periode.totals.work, periode.totals.rest) == (
        4 * 3600,
        2 * 3600,
        3600,
    )


def test_un_repos_d_au_moins_24_heures_est_qualifie_d_hebdomadaire(
    service: CardReportService, context: ApplicationContext, tmp_path
) -> None:
    importer(context, tmp_path, [(JOUR, journee(6, 14)), (JOUR + timedelta(days=3), journee(6, 8))])

    premiere, _ = rapport(service, JOUR, JOUR + timedelta(days=3)).work_periods

    assert premiere.weekly_rest is True
    assert premiere.rest_within_24h_seconds is None


def test_les_rubriques_sont_mises_en_tableaux(
    service: CardReportService, context: ApplicationContext, tmp_path
) -> None:
    importer(context, tmp_path, [(JOUR, journee(6, 14))])

    tableaux = card_report_tables(rapport(service, JOUR, JOUR))

    titres = [tableau.title for tableau in tableaux]
    assert titres == [
        "Info carte de conducteur",
        "Evenements",
        "Periodes de travail journalieres",
        "Activites",
        "Vehicules",
        "Pays",
    ]
    activites = tableaux[3]
    assert [ligne[4] for ligne in activites.rows] == [
        ActivityType.REST.label,
        ActivityType.DRIVING.label,
        ActivityType.REST.label,
    ]
    # Heure locale (Europe/Paris, ete) : 6h00 UTC = 8h00.
    assert activites.rows[1][2].startswith("08:00")


def test_un_conducteur_inconnu_est_signale(service: CardReportService) -> None:
    debut = datetime(2025, 10, 1, tzinfo=UTC)

    with pytest.raises(CardReportError):
        service.build(999, period_start=debut, period_end=debut + timedelta(days=1))

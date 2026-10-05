"""Tests du calcul des temps de repos.

Point de vigilance : une periode **sans enregistrement** n'est jamais assimilee a du
repos. Ce serait une hypothese favorable non verifiable.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta

import pytest

from app.analysis.models import ActivityInterval
from app.analysis.rest_time import (
    calculate_daily_rest,
    calculate_rest_periods,
    calculate_total_rest,
    day_bounds_for,
    longest_rest_period,
    rest_periods_by_day,
)
from app.core.enums import ActivityType

Factory = Callable[..., ActivityInterval]


def test_repos_cumule(journee_type: tuple[ActivityInterval, ...]) -> None:
    assert calculate_total_rest(journee_type) == 45 * 60


def test_les_periodes_de_repos_contigues_sont_fusionnees(interval_factory: Factory) -> None:
    intervals = (
        interval_factory(ActivityType.REST, 20, 22),
        interval_factory(ActivityType.REST, 22, 24),
    )

    periodes = calculate_rest_periods(intervals)

    assert len(periodes) == 1
    assert periodes[0].duration_seconds == 4 * 3600


def test_filtrage_par_duree_minimale(interval_factory: Factory) -> None:
    intervals = (
        interval_factory(ActivityType.REST, 10, 10.25),
        interval_factory(ActivityType.WORK, 10.25, 12),
        interval_factory(ActivityType.REST, 12, 21),
    )

    assert len(calculate_rest_periods(intervals)) == 2
    assert len(calculate_rest_periods(intervals, minimum_seconds=9 * 3600)) == 1


def test_duree_minimale_negative_refusee(interval_factory: Factory) -> None:
    with pytest.raises(ValueError):
        calculate_rest_periods((interval_factory(ActivityType.REST, 0, 1),), minimum_seconds=-1)


def test_un_trou_n_est_pas_du_repos(interval_factory: Factory) -> None:
    """Exigence de prudence : l'absence de donnee ne devient pas une periode de repos."""
    intervals = (
        interval_factory(ActivityType.DRIVING, 8, 10),
        interval_factory(ActivityType.DRIVING, 18, 20),
    )

    assert calculate_total_rest(intervals) == 0
    assert calculate_rest_periods(intervals) == ()


def test_repos_journalier(journee_type: tuple[ActivityInterval, ...], jour) -> None:
    assert calculate_daily_rest(journee_type, jour.date()) == 45 * 60


def test_un_repos_a_cheval_sur_minuit_est_reparti(interval_factory: Factory, jour) -> None:
    intervals = (interval_factory(ActivityType.REST, 21, 30),)

    assert calculate_daily_rest(intervals, jour.date()) == 3 * 3600
    assert calculate_daily_rest(intervals, (jour + timedelta(days=1)).date()) == 6 * 3600


def test_plus_longue_periode_de_repos(interval_factory: Factory) -> None:
    intervals = (
        interval_factory(ActivityType.REST, 0, 2),
        interval_factory(ActivityType.DRIVING, 2, 4),
        interval_factory(ActivityType.REST, 4, 15),
    )

    plus_long = longest_rest_period(intervals)

    assert plus_long is not None
    assert plus_long.duration_seconds == 11 * 3600


def test_plus_longue_periode_absente(interval_factory: Factory) -> None:
    assert longest_rest_period((interval_factory(ActivityType.DRIVING, 8, 10),)) is None


def test_repos_par_journee(interval_factory: Factory, jour) -> None:
    intervals = (
        interval_factory(ActivityType.REST, 0, 6),
        interval_factory(ActivityType.DRIVING, 6, 10),
        interval_factory(ActivityType.REST, 10, 12, day=jour + timedelta(days=1)),
    )

    par_jour = rest_periods_by_day(intervals)

    assert set(par_jour) == {jour.date(), (jour + timedelta(days=1)).date()}


def test_bornes_de_journee_pour_une_date(jour) -> None:
    debut, fin = day_bounds_for(jour.date())

    assert debut == jour
    assert fin == jour + timedelta(days=1)


def test_repos_borne_a_une_periode(journee_type: tuple[ActivityInterval, ...], jour) -> None:
    total = calculate_total_rest(
        journee_type,
        period_start=jour + timedelta(hours=11),
        period_end=jour + timedelta(hours=12),
    )

    assert total == 30 * 60

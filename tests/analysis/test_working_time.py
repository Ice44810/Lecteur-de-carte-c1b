"""Tests des temps de travail, de disponibilite et de l'amplitude.

La composition du temps de travail est une **incertitude documentee** (directive
2002/15/CE, article 3, a confirmer) : elle doit donc rester un parametre explicite et
non une regle figee dans le code. Ces tests verifient precisement cette propriete.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta

import pytest

from app.analysis.availability import (
    availability_periods,
    calculate_availability_by_day,
    calculate_availability_time,
)
from app.analysis.models import ActivityInterval
from app.analysis.working_time import (
    DEFAULT_WORKING_TIME_TYPES,
    WORKING_TIME_SOURCE,
    calculate_amplitude_by_day,
    calculate_daily_amplitude,
    calculate_daily_working_time,
    calculate_working_time,
)
from app.core.enums import ActivityType

Factory = Callable[..., ActivityInterval]


def test_composition_par_defaut_du_temps_de_travail() -> None:
    assert DEFAULT_WORKING_TIME_TYPES == (ActivityType.DRIVING, ActivityType.WORK)


def test_la_source_du_temps_de_travail_est_citee_et_marquee_a_confirmer() -> None:
    assert "2002/15/CE" in WORKING_TIME_SOURCE
    assert "confirmer" in WORKING_TIME_SOURCE


def test_temps_de_travail_par_defaut(journee_type: tuple[ActivityInterval, ...]) -> None:
    assert calculate_working_time(journee_type) == int(9.75 * 3600)


def test_la_composition_du_temps_de_travail_est_parametrable(
    journee_type: tuple[ActivityInterval, ...],
) -> None:
    avec_disponibilite = calculate_working_time(
        journee_type,
        included_types=(ActivityType.DRIVING, ActivityType.WORK, ActivityType.AVAILABILITY),
    )

    assert avec_disponibilite == int(10.25 * 3600)


def test_composition_vide_refusee(journee_type: tuple[ActivityInterval, ...]) -> None:
    with pytest.raises(ValueError):
        calculate_working_time(journee_type, included_types=())


def test_temps_de_travail_par_journee(interval_factory: Factory, jour) -> None:
    intervals = (
        interval_factory(ActivityType.DRIVING, 8, 12),
        interval_factory(ActivityType.WORK, 8, 9, day=jour + timedelta(days=1)),
        interval_factory(ActivityType.REST, 20, 22, day=jour + timedelta(days=2)),
    )

    par_jour = calculate_daily_working_time(intervals)

    assert par_jour == {jour.date(): 4 * 3600, (jour + timedelta(days=1)).date(): 3600}


def test_amplitude_de_service(journee_type: tuple[ActivityInterval, ...], jour) -> None:
    """De 06h00 (premiere activite) a 17h00 (derniere activite) : 11 heures."""
    assert calculate_daily_amplitude(journee_type, jour.date()) == 11 * 3600


def test_amplitude_absente_sans_service(interval_factory: Factory, jour) -> None:
    intervals = (interval_factory(ActivityType.REST, 0, 24),)

    assert calculate_daily_amplitude(intervals, jour.date()) is None


def test_amplitude_par_journee(journee_type: tuple[ActivityInterval, ...], jour) -> None:
    assert calculate_amplitude_by_day(journee_type) == {jour.date(): 11 * 3600}


def test_temps_de_disponibilite(journee_type: tuple[ActivityInterval, ...]) -> None:
    assert calculate_availability_time(journee_type) == 30 * 60


def test_disponibilite_par_journee(journee_type: tuple[ActivityInterval, ...], jour) -> None:
    assert calculate_availability_by_day(journee_type) == {jour.date(): 30 * 60}


def test_periodes_de_disponibilite(journee_type: tuple[ActivityInterval, ...]) -> None:
    periodes = availability_periods(journee_type)

    assert len(periodes) == 1
    assert periodes[0].activity_type is ActivityType.AVAILABILITY

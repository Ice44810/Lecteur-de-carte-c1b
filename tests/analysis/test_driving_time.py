"""Tests du calcul des temps de conduite.

Ces fonctions **mesurent** sans juger : aucun seuil reglementaire n'y figure. Le
parametre ``break_minimum_seconds`` est obligatoire, ce que ces tests verifient
explicitement : la duree qui constitue une coupure valable est une question
reglementaire, tranchee par le moteur de regles.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest

from app.analysis.driving_time import (
    calculate_daily_driving_time,
    calculate_driving_time,
    calculate_driving_time_by_day,
    calculate_weekly_driving_time,
    continuous_driving_blocks,
)
from app.analysis.models import ActivityInterval
from app.core.enums import ActivityType

Factory = Callable[..., ActivityInterval]


def test_temps_de_conduite_cumule(journee_type: tuple[ActivityInterval, ...]) -> None:
    assert calculate_driving_time(journee_type) == int(7.75 * 3600)


def test_seule_la_conduite_est_comptee(interval_factory: Factory) -> None:
    intervals = (
        interval_factory(ActivityType.WORK, 8, 10),
        interval_factory(ActivityType.AVAILABILITY, 10, 12),
        interval_factory(ActivityType.REST, 12, 14),
        interval_factory(ActivityType.UNKNOWN, 14, 16),
    )

    assert calculate_driving_time(intervals) == 0


def test_temps_de_conduite_borne_a_une_periode(
    journee_type: tuple[ActivityInterval, ...], jour: datetime
) -> None:
    total = calculate_driving_time(
        journee_type,
        period_start=jour + timedelta(hours=7),
        period_end=jour + timedelta(hours=9),
    )

    assert total == 2 * 3600


def test_temps_de_conduite_journalier(
    journee_type: tuple[ActivityInterval, ...], jour: datetime
) -> None:
    assert calculate_daily_driving_time(journee_type, jour) == int(7.75 * 3600)
    assert calculate_daily_driving_time(journee_type, jour.date()) == int(7.75 * 3600)
    assert calculate_daily_driving_time(journee_type, jour.date() + timedelta(days=1)) == 0


def test_conduite_a_cheval_sur_minuit_repartie_sur_deux_jours(
    interval_factory: Factory, jour: datetime
) -> None:
    intervals = (interval_factory(ActivityType.DRIVING, 23, 25),)

    assert calculate_daily_driving_time(intervals, jour) == 3600
    assert calculate_daily_driving_time(intervals, jour + timedelta(days=1)) == 3600


def test_temps_de_conduite_hebdomadaire(interval_factory: Factory, jour: datetime) -> None:
    """La semaine va du lundi au dimanche (reglement (CE) no 561/2006, art. 4 i)."""
    lundi = jour - timedelta(days=1)
    intervals = (
        interval_factory(ActivityType.DRIVING, 8, 12, day=lundi),
        interval_factory(ActivityType.DRIVING, 8, 13, day=jour),
        interval_factory(ActivityType.DRIVING, 8, 10, day=lundi + timedelta(days=7)),
    )

    assert calculate_weekly_driving_time(intervals, jour) == 9 * 3600


def test_conduite_par_journee(interval_factory: Factory, jour: datetime) -> None:
    intervals = (
        interval_factory(ActivityType.DRIVING, 8, 10),
        interval_factory(ActivityType.DRIVING, 8, 11, day=jour + timedelta(days=1)),
        interval_factory(ActivityType.REST, 20, 22, day=jour + timedelta(days=2)),
    )

    par_jour = calculate_driving_time_by_day(intervals)

    assert par_jour == {jour.date(): 2 * 3600, (jour + timedelta(days=1)).date(): 3 * 3600}


# --------------------------------------------------------------------------- #
# Blocs de conduite continue
# --------------------------------------------------------------------------- #
def test_le_seuil_de_coupure_est_obligatoire(
    journee_type: tuple[ActivityInterval, ...],
) -> None:
    """Aucune valeur par defaut : le seuil est une decision reglementaire."""
    with pytest.raises(TypeError):
        continuous_driving_blocks(journee_type)  # type: ignore[call-arg]


def test_une_coupure_suffisante_ouvre_un_nouveau_bloc(
    journee_type: tuple[ActivityInterval, ...],
) -> None:
    blocs = continuous_driving_blocks(journee_type, break_minimum_seconds=45 * 60)

    assert [bloc.driving_seconds for bloc in blocs] == [int(3.75 * 3600), 4 * 3600]


def test_une_coupure_insuffisante_ne_coupe_pas_le_bloc(interval_factory: Factory) -> None:
    intervals = (
        interval_factory(ActivityType.DRIVING, 8, 10),
        interval_factory(ActivityType.REST, 10, 10.25),
        interval_factory(ActivityType.DRIVING, 10.25, 12),
    )

    blocs = continuous_driving_blocks(intervals, break_minimum_seconds=45 * 60)

    assert len(blocs) == 1
    assert blocs[0].driving_seconds == int(3.75 * 3600)
    assert blocs[0].span_seconds == 4 * 3600


def test_le_meme_jeu_donne_des_blocs_differents_selon_le_seuil(
    interval_factory: Factory,
) -> None:
    intervals = (
        interval_factory(ActivityType.DRIVING, 8, 10),
        interval_factory(ActivityType.REST, 10, 10.5),
        interval_factory(ActivityType.DRIVING, 10.5, 12),
    )

    assert len(continuous_driving_blocks(intervals, break_minimum_seconds=15 * 60)) == 2
    assert len(continuous_driving_blocks(intervals, break_minimum_seconds=60 * 60)) == 1


def test_un_trou_sans_enregistrement_compte_comme_interruption(
    interval_factory: Factory,
) -> None:
    intervals = (
        interval_factory(ActivityType.DRIVING, 8, 10),
        interval_factory(ActivityType.DRIVING, 12, 14),
    )

    blocs = continuous_driving_blocks(intervals, break_minimum_seconds=45 * 60)

    assert len(blocs) == 2


def test_seuil_negatif_refuse(journee_type: tuple[ActivityInterval, ...]) -> None:
    with pytest.raises(ValueError):
        continuous_driving_blocks(journee_type, break_minimum_seconds=-1)


def test_aucune_conduite_aucun_bloc(interval_factory: Factory) -> None:
    intervals = (interval_factory(ActivityType.REST, 0, 24),)

    assert continuous_driving_blocks(intervals, break_minimum_seconds=45 * 60) == ()


def test_les_blocs_conservent_leurs_bornes(journee_type: tuple[ActivityInterval, ...]) -> None:
    blocs = continuous_driving_blocks(journee_type, break_minimum_seconds=45 * 60)

    assert blocs[0].start == datetime(2026, 9, 15, 7, 0, tzinfo=UTC)
    assert blocs[0].end == datetime(2026, 9, 15, 10, 45, tzinfo=UTC)
    assert blocs[0].intervals

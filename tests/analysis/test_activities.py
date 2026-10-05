"""Tests de la normalisation des suites d'activites."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest

from app.analysis.activities import (
    clip_to_period,
    filter_by_type,
    find_gaps,
    find_overlaps,
    merge_adjacent,
    normalize_intervals,
    split_by_day,
    summarize_days,
    to_intervals,
)
from app.analysis.models import ActivityInterval, PeriodTotals
from app.core.enums import ActivityType
from app.core.exceptions import AnalysisError

Factory = Callable[..., ActivityInterval]


# --------------------------------------------------------------------------- #
# Intervalles
# --------------------------------------------------------------------------- #
def test_un_intervalle_est_normalise_en_utc() -> None:
    interval = ActivityInterval(
        activity_type=ActivityType.DRIVING,
        start=datetime(2026, 9, 15, 8, 0),
        end=datetime(2026, 9, 15, 9, 30),
    )

    assert interval.start.tzinfo is not None
    assert interval.duration_seconds == 5400


def test_un_intervalle_inverse_est_refuse() -> None:
    with pytest.raises(ValueError):
        ActivityInterval(
            activity_type=ActivityType.DRIVING,
            start=datetime(2026, 9, 15, 10, 0, tzinfo=UTC),
            end=datetime(2026, 9, 15, 9, 0, tzinfo=UTC),
        )


def test_clip_retourne_none_hors_periode(interval_factory: Factory, jour: datetime) -> None:
    interval = interval_factory(ActivityType.DRIVING, 8, 10)

    assert interval.clip(jour + timedelta(hours=12), jour + timedelta(hours=14)) is None


# --------------------------------------------------------------------------- #
# Conversion depuis la couche de persistance
# --------------------------------------------------------------------------- #
def test_to_intervals_convertit_les_activites_orm() -> None:
    from app.database.models import Activity

    activity = Activity.from_bounds(
        driver_id=1,
        activity_type=ActivityType.DRIVING,
        start_datetime=datetime(2026, 9, 15, 8, 0, tzinfo=UTC),
        end_datetime=datetime(2026, 9, 15, 9, 0, tzinfo=UTC),
    )

    intervals = to_intervals([activity])

    assert len(intervals) == 1
    assert intervals[0].activity_type is ActivityType.DRIVING
    assert intervals[0].duration_seconds == 3600


def test_to_intervals_signale_un_enregistrement_incomplet() -> None:
    class Incomplet:
        activity_type = ActivityType.DRIVING

    with pytest.raises(AnalysisError) as exc_info:
        to_intervals([Incomplet()])

    message, cause, action = exc_info.value.user_report()
    assert message and cause and action


# --------------------------------------------------------------------------- #
# Chevauchements
# --------------------------------------------------------------------------- #
def test_les_chevauchements_sont_detectes(interval_factory: Factory) -> None:
    conflits = find_overlaps(
        (
            interval_factory(ActivityType.DRIVING, 8, 10),
            interval_factory(ActivityType.WORK, 9, 11),
        )
    )

    assert len(conflits) == 1


def test_un_chevauchement_est_signale_et_non_corrige_en_silence(
    interval_factory: Factory,
) -> None:
    intervals = (
        interval_factory(ActivityType.DRIVING, 8, 10),
        interval_factory(ActivityType.WORK, 9, 11),
    )

    with pytest.raises(AnalysisError) as exc_info:
        normalize_intervals(intervals)

    message, cause, action = exc_info.value.user_report()
    assert "chevauchent" in message.lower()
    assert "fichiers importes" in action
    assert cause


def test_le_mode_troncature_conserve_l_ordre(interval_factory: Factory) -> None:
    intervals = (
        interval_factory(ActivityType.DRIVING, 8, 10),
        interval_factory(ActivityType.WORK, 9, 11),
    )

    normalises = normalize_intervals(intervals, on_overlap="truncate")

    assert [item.duration_seconds for item in normalises] == [3600, 7200]
    assert find_overlaps(normalises) == ()


def test_le_mode_conservation_ne_touche_a_rien(interval_factory: Factory) -> None:
    intervals = (
        interval_factory(ActivityType.DRIVING, 8, 10),
        interval_factory(ActivityType.WORK, 9, 11),
    )

    assert len(normalize_intervals(intervals, on_overlap="keep")) == 2


def test_mode_de_chevauchement_inconnu_refuse(interval_factory: Factory) -> None:
    with pytest.raises(AnalysisError):
        normalize_intervals((interval_factory(ActivityType.DRIVING, 8, 10),), on_overlap="devine")


def test_normalisation_trie_et_supprime_les_intervalles_vides(
    interval_factory: Factory,
) -> None:
    intervals = (
        interval_factory(ActivityType.WORK, 12, 13),
        interval_factory(ActivityType.DRIVING, 8, 8),
        interval_factory(ActivityType.DRIVING, 9, 10),
    )

    normalises = normalize_intervals(intervals)

    assert [item.start.hour for item in normalises] == [9, 12]


# --------------------------------------------------------------------------- #
# Fusion
# --------------------------------------------------------------------------- #
def test_fusion_des_enregistrements_contigus_de_meme_type(interval_factory: Factory) -> None:
    """Un tachygraphe decoupe une conduite continue en plusieurs enregistrements."""
    intervals = (
        interval_factory(ActivityType.DRIVING, 8, 9),
        interval_factory(ActivityType.DRIVING, 9, 10),
        interval_factory(ActivityType.REST, 10, 11),
    )

    fusionnes = merge_adjacent(intervals)

    assert len(fusionnes) == 2
    assert fusionnes[0].duration_seconds == 7200


def test_la_fusion_respecte_le_type(interval_factory: Factory) -> None:
    intervals = (
        interval_factory(ActivityType.DRIVING, 8, 9),
        interval_factory(ActivityType.WORK, 9, 10),
    )

    assert len(merge_adjacent(intervals)) == 2


def test_la_fusion_accepte_une_tolerance(interval_factory: Factory) -> None:
    intervals = (
        interval_factory(ActivityType.DRIVING, 8, 9),
        interval_factory(ActivityType.DRIVING, 9.01, 10),
    )

    assert len(merge_adjacent(intervals, tolerance_seconds=60)) == 1
    assert len(merge_adjacent(intervals, tolerance_seconds=0)) == 2


def test_tolerance_negative_refusee(interval_factory: Factory) -> None:
    with pytest.raises(ValueError):
        merge_adjacent((interval_factory(ActivityType.DRIVING, 8, 9),), tolerance_seconds=-1)


# --------------------------------------------------------------------------- #
# Bornage
# --------------------------------------------------------------------------- #
def test_une_activite_a_cheval_est_decoupee(interval_factory: Factory, jour: datetime) -> None:
    interval = interval_factory(ActivityType.REST, 22, 30)  # 22h00 -> 06h00 le lendemain

    bornes = clip_to_period((interval,), jour + timedelta(hours=24), jour + timedelta(hours=48))

    assert len(bornes) == 1
    assert bornes[0].duration_seconds == 6 * 3600


def test_periode_invalide_refusee(interval_factory: Factory, jour: datetime) -> None:
    with pytest.raises(AnalysisError) as exc_info:
        clip_to_period((), jour + timedelta(hours=10), jour)

    assert "periode" in exc_info.value.message.lower()


# --------------------------------------------------------------------------- #
# Trous
# --------------------------------------------------------------------------- #
def test_un_trou_est_signale_et_jamais_comble(interval_factory: Factory) -> None:
    """Regle de prudence : une absence d'enregistrement n'est pas du repos."""
    intervals = (
        interval_factory(ActivityType.DRIVING, 8, 10),
        interval_factory(ActivityType.DRIVING, 13, 15),
    )

    trous = find_gaps(intervals)

    assert len(trous) == 1
    debut, fin = trous[0]
    assert (fin - debut).total_seconds() == 3 * 3600
    assert PeriodTotals.from_intervals(intervals).rest == 0


def test_les_trous_de_bordure_sont_detectes(interval_factory: Factory, jour: datetime) -> None:
    intervals = (interval_factory(ActivityType.DRIVING, 8, 10),)

    trous = find_gaps(intervals, period_start=jour, period_end=jour + timedelta(hours=24))

    assert len(trous) == 2


def test_une_journee_sans_activite_est_un_trou_complet(jour: datetime) -> None:
    trous = find_gaps((), period_start=jour, period_end=jour + timedelta(hours=24))

    assert len(trous) == 1


def test_les_micro_trous_sont_ignores(interval_factory: Factory) -> None:
    intervals = (
        interval_factory(ActivityType.DRIVING, 8, 10),
        interval_factory(ActivityType.DRIVING, 10.005, 12),
    )

    assert find_gaps(intervals, minimum_seconds=60) == ()


# --------------------------------------------------------------------------- #
# Decoupage journalier
# --------------------------------------------------------------------------- #
def test_une_activite_traversant_minuit_est_repartie(interval_factory: Factory) -> None:
    interval = interval_factory(ActivityType.REST, 22, 30)

    par_jour = split_by_day((interval,))

    assert len(par_jour) == 2
    durees = [sum(item.duration_seconds for item in intervals) for intervals in par_jour.values()]
    assert durees == [2 * 3600, 6 * 3600]


def test_synthese_journaliere(journee_type: tuple[ActivityInterval, ...]) -> None:
    syntheses = summarize_days(journee_type)

    assert len(syntheses) == 1
    synthese = syntheses[0]
    assert synthese.totals.driving == int(7.75 * 3600)
    assert synthese.has_data is True
    assert synthese.first_activity_start is not None
    assert synthese.last_activity_end is not None


def test_filtre_par_type(journee_type: tuple[ActivityInterval, ...]) -> None:
    conduite = filter_by_type(journee_type, ActivityType.DRIVING)

    assert len(conduite) == 2
    assert all(item.activity_type is ActivityType.DRIVING for item in conduite)


# --------------------------------------------------------------------------- #
# Totaux
# --------------------------------------------------------------------------- #
def test_totaux_par_type(journee_type: tuple[ActivityInterval, ...]) -> None:
    totaux = PeriodTotals.from_intervals(journee_type)

    assert totaux.driving == int(7.75 * 3600)
    assert totaux.work == 2 * 3600
    assert totaux.rest == 45 * 60
    assert totaux.availability == 30 * 60
    assert totaux.unknown == 0
    assert totaux.total == sum(item.duration_seconds for item in journee_type)


def test_totaux_formates(journee_type: tuple[ActivityInterval, ...]) -> None:
    formats = PeriodTotals.from_intervals(journee_type).formatted()

    assert formats[ActivityType.DRIVING] == "07h45"


def test_addition_de_totaux() -> None:
    somme = PeriodTotals(driving=3600) + PeriodTotals(driving=1800, rest=600)

    assert somme.driving == 5400
    assert somme.rest == 600


def test_duree_negative_refusee() -> None:
    with pytest.raises(ValueError):
        PeriodTotals(driving=-1)

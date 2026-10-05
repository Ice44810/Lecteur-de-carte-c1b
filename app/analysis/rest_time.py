"""Calcul des periodes de repos et de pause.

Comme pour les temps de conduite, ce module mesure sans juger : il identifie les
periodes de repos et leur duree. Determiner quelle duree constitue un repos
journalier valable, une pause reglementaire ou un repos hebdomadaire releve du
moteur de regles, ou le seuil est configurable et source.

Point d'attention : une periode **sans enregistrement** n'est pas assimilee a du
repos. Ce serait une hypothese favorable non verifiable. Les trous sont signales
par :func:`app.analysis.activities.find_gaps` et laisses a l'appreciation de
l'exploitant.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date, datetime

from app.analysis.activities import clip_to_period, merge_adjacent, split_by_day
from app.analysis.models import ActivityInterval
from app.core.enums import ActivityType
from app.core.timeutils import day_bounds

__all__ = [
    "calculate_rest_periods",
    "calculate_total_rest",
    "calculate_daily_rest",
    "longest_rest_period",
    "rest_periods_by_day",
]


def calculate_rest_periods(
    intervals: Sequence[ActivityInterval],
    *,
    minimum_seconds: int = 0,
    merge_contiguous: bool = True,
) -> tuple[ActivityInterval, ...]:
    """Retourne les periodes de repos, eventuellement fusionnees et filtrees.

    Args:
        intervals: Intervalles d'activite normalises et tries.
        minimum_seconds: Duree minimale retenue. ``0`` retourne toutes les periodes.
        merge_contiguous: Fusionne les periodes de repos contigues avant filtrage,
            un repos pouvant etre enregistre en plusieurs segments successifs.

    Returns:
        Les periodes de repos retenues, dans l'ordre chronologique.

    Raises:
        ValueError: ``minimum_seconds`` est negatif.
    """
    if minimum_seconds < 0:
        raise ValueError("minimum_seconds ne peut pas etre negatif")

    ordered = sorted(intervals, key=lambda item: (item.start, item.end))
    if merge_contiguous:
        ordered = list(merge_adjacent(tuple(ordered)))
    return tuple(
        interval
        for interval in ordered
        if interval.activity_type is ActivityType.REST
        and interval.duration_seconds >= minimum_seconds
    )


def calculate_total_rest(
    intervals: Iterable[ActivityInterval],
    *,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
) -> int:
    """Retourne le temps de repos cumule sur une periode, en secondes."""
    selected: Sequence[ActivityInterval] = tuple(intervals)
    if period_start is not None and period_end is not None:
        selected = clip_to_period(selected, period_start, period_end)
    return sum(
        interval.duration_seconds
        for interval in selected
        if interval.activity_type is ActivityType.REST
    )


def calculate_daily_rest(intervals: Iterable[ActivityInterval], day: date) -> int:
    """Retourne le temps de repos enregistre sur une journee calendaire UTC.

    Args:
        intervals: Intervalles d'activite normalises.
        day: Jour analyse.

    Returns:
        Le temps de repos du jour, en secondes.
    """
    return sum(
        interval.duration_seconds
        for interval in split_by_day(intervals).get(day, ())
        if interval.activity_type is ActivityType.REST
    )


def longest_rest_period(
    intervals: Sequence[ActivityInterval],
    *,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
) -> ActivityInterval | None:
    """Retourne la plus longue periode de repos continue d'une periode.

    Les periodes de repos contigues sont fusionnees avant comparaison, afin de ne
    pas sous-evaluer un repos enregistre en plusieurs segments.

    Args:
        intervals: Intervalles d'activite normalises et tries.
        period_start: Borne inferieure optionnelle (inclus).
        period_end: Borne superieure optionnelle (exclu).

    Returns:
        La periode de repos la plus longue, ou ``None`` si aucun repos n'est
        enregistre.
    """
    selected: Sequence[ActivityInterval] = tuple(intervals)
    if period_start is not None and period_end is not None:
        selected = clip_to_period(selected, period_start, period_end)
    rests = calculate_rest_periods(selected)
    if not rests:
        return None
    return max(rests, key=lambda interval: interval.duration_seconds)


def rest_periods_by_day(
    intervals: Iterable[ActivityInterval], *, minimum_seconds: int = 0
) -> dict[date, tuple[ActivityInterval, ...]]:
    """Retourne les periodes de repos regroupees par journee calendaire.

    Une periode de repos a cheval sur minuit apparait dans les deux journees, bornee
    a chacune d'elles.

    Args:
        intervals: Intervalles d'activite normalises.
        minimum_seconds: Duree minimale retenue apres decoupage journalier.

    Returns:
        Un dictionnaire ``jour -> periodes de repos``.
    """
    result: dict[date, tuple[ActivityInterval, ...]] = {}
    for day, day_intervals in split_by_day(intervals).items():
        rests = tuple(
            interval
            for interval in day_intervals
            if interval.activity_type is ActivityType.REST
            and interval.duration_seconds >= minimum_seconds
        )
        if rests:
            result[day] = rests
    return result


def day_bounds_for(day: date) -> tuple[datetime, datetime]:
    """Retourne les bornes UTC d'une journee calendaire.

    Fonction de commodite pour les appelants qui disposent d'une ``date`` et non
    d'un ``datetime``.
    """
    from datetime import UTC

    return day_bounds(datetime(day.year, day.month, day.day, tzinfo=UTC))

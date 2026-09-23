"""Calcul des temps de disponibilite.

Le temps de disponibilite est enregistre par le tachygraphe comme un mode
d'activite distinct. Son traitement (compte-t-il dans le temps de travail ? peut-il
valoir coupure ?) est une question reglementaire, laissee au moteur de regles :
ce module se contente de le mesurer.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date, datetime

from app.analysis.activities import clip_to_period, merge_adjacent, split_by_day
from app.analysis.models import ActivityInterval
from app.core.enums import ActivityType

__all__ = [
    "calculate_availability_time",
    "calculate_availability_by_day",
    "availability_periods",
]


def calculate_availability_time(
    intervals: Iterable[ActivityInterval],
    *,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
) -> int:
    """Retourne le temps de disponibilite cumule, en secondes.

    Args:
        intervals: Intervalles d'activite normalises.
        period_start: Borne inferieure optionnelle (inclus).
        period_end: Borne superieure optionnelle (exclu).

    Returns:
        Le cumul des durees de disponibilite, en secondes.
    """
    selected: Sequence[ActivityInterval] = tuple(intervals)
    if period_start is not None and period_end is not None:
        selected = clip_to_period(selected, period_start, period_end)
    return sum(
        interval.duration_seconds
        for interval in selected
        if interval.activity_type is ActivityType.AVAILABILITY
    )


def calculate_availability_by_day(
    intervals: Iterable[ActivityInterval],
) -> dict[date, int]:
    """Retourne le temps de disponibilite par journee calendaire UTC."""
    result: dict[date, int] = {}
    for day, day_intervals in split_by_day(intervals).items():
        total = sum(
            interval.duration_seconds
            for interval in day_intervals
            if interval.activity_type is ActivityType.AVAILABILITY
        )
        if total:
            result[day] = total
    return result


def availability_periods(
    intervals: Sequence[ActivityInterval], *, minimum_seconds: int = 0
) -> tuple[ActivityInterval, ...]:
    """Retourne les periodes de disponibilite, fusionnees et filtrees.

    Args:
        intervals: Intervalles d'activite normalises et tries.
        minimum_seconds: Duree minimale retenue.

    Returns:
        Les periodes de disponibilite retenues, dans l'ordre chronologique.

    Raises:
        ValueError: ``minimum_seconds`` est negatif.
    """
    if minimum_seconds < 0:
        raise ValueError("minimum_seconds ne peut pas etre negatif")
    merged = merge_adjacent(tuple(sorted(intervals, key=lambda item: (item.start, item.end))))
    return tuple(
        interval
        for interval in merged
        if interval.activity_type is ActivityType.AVAILABILITY
        and interval.duration_seconds >= minimum_seconds
    )

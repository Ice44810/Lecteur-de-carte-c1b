"""Calcul des temps de conduite.

Ce module ne contient **aucun seuil reglementaire** : il ne fait que mesurer. Les
seuils appartiennent au moteur de regles (``app.analysis.rules``), ou ils sont
configurables et accompagnes de leur source. Les parametres de ce module
(``break_minimum_seconds`` par exemple) sont donc obligatoires et sans valeur par
defaut : l'appelant doit indiquer explicitement quel seuil il applique.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime

from app.analysis.activities import clip_to_period, split_by_day
from app.analysis.models import ActivityInterval
from app.core.enums import ActivityType
from app.core.timeutils import day_bounds, ensure_utc, week_bounds

__all__ = [
    "DrivingBlock",
    "calculate_driving_time",
    "calculate_daily_driving_time",
    "calculate_weekly_driving_time",
    "calculate_driving_time_by_day",
    "continuous_driving_blocks",
]


@dataclass(frozen=True, slots=True)
class DrivingBlock:
    """Bloc de conduite continue, au sens d'une coupure minimale donnee.

    Attributes:
        start: Debut du premier intervalle de conduite du bloc.
        end: Fin du dernier intervalle de conduite du bloc.
        driving_seconds: Temps de conduite effectif du bloc (hors interruptions
            inferieures a la coupure minimale retenue).
        intervals: Intervalles de conduite composant le bloc.
    """

    start: datetime
    end: datetime
    driving_seconds: int
    intervals: tuple[ActivityInterval, ...]

    @property
    def span_seconds(self) -> int:
        """Duree totale entre le debut et la fin du bloc, interruptions incluses."""
        return int((self.end - self.start).total_seconds())


def calculate_driving_time(
    intervals: Iterable[ActivityInterval],
    *,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
) -> int:
    """Retourne le temps de conduite cumule, en secondes.

    Args:
        intervals: Intervalles d'activite normalises.
        period_start: Si fourni avec ``period_end``, borne inferieure (inclus).
        period_end: Si fourni avec ``period_start``, borne superieure (exclu).

    Returns:
        Le cumul des durees de conduite, en secondes.
    """
    selected: Sequence[ActivityInterval] = tuple(intervals)
    if period_start is not None and period_end is not None:
        selected = clip_to_period(selected, period_start, period_end)
    return sum(
        interval.duration_seconds
        for interval in selected
        if interval.activity_type is ActivityType.DRIVING
    )


def calculate_daily_driving_time(
    intervals: Iterable[ActivityInterval], day: date | datetime
) -> int:
    """Retourne le temps de conduite d'une journee calendaire UTC.

    Args:
        intervals: Intervalles d'activite normalises.
        day: Jour analyse : une ``date``, ou un ``datetime`` appartenant a ce jour.

    Returns:
        Le temps de conduite du jour, en secondes.
    """
    reference = _as_datetime(day)
    start, end = day_bounds(reference)
    return calculate_driving_time(intervals, period_start=start, period_end=end)


def calculate_weekly_driving_time(intervals: Iterable[ActivityInterval], moment: datetime) -> int:
    """Retourne le temps de conduite de la semaine contenant ``moment``.

    La semaine commence le lundi a 00:00 UTC (definition de la "semaine" donnee par
    le reglement (CE) no 561/2006, article 4, point i).

    Args:
        intervals: Intervalles d'activite normalises.
        moment: Instant appartenant a la semaine analysee.

    Returns:
        Le temps de conduite de la semaine, en secondes.
    """
    start, end = week_bounds(moment)
    return calculate_driving_time(intervals, period_start=start, period_end=end)


def calculate_driving_time_by_day(intervals: Iterable[ActivityInterval]) -> dict[date, int]:
    """Retourne le temps de conduite par journee calendaire.

    Args:
        intervals: Intervalles d'activite normalises.

    Returns:
        Un dictionnaire ``jour -> secondes de conduite``, limite aux jours comportant
        de la conduite, tri par jour croissant.
    """
    result: dict[date, int] = {}
    for day, day_intervals in split_by_day(intervals).items():
        total = sum(
            interval.duration_seconds
            for interval in day_intervals
            if interval.activity_type is ActivityType.DRIVING
        )
        if total:
            result[day] = total
    return result


def continuous_driving_blocks(
    intervals: Sequence[ActivityInterval],
    *,
    break_minimum_seconds: int,
) -> tuple[DrivingBlock, ...]:
    """Regroupe la conduite en blocs separes par une interruption suffisante.

    Deux periodes de conduite appartiennent au meme bloc tant qu'elles ne sont pas
    separees par une interruption (repos, travail, disponibilite, ou absence
    d'enregistrement) d'au moins ``break_minimum_seconds``.

    ``break_minimum_seconds`` est un parametre obligatoire : la duree qui constitue
    une coupure valable est une question reglementaire, tranchee par le moteur de
    regles et non par ce module de mesure.

    Args:
        intervals: Intervalles d'activite normalises et tries.
        break_minimum_seconds: Duree minimale d'interruption ouvrant un nouveau bloc.

    Returns:
        Les blocs de conduite, dans l'ordre chronologique.

    Raises:
        ValueError: ``break_minimum_seconds`` est negatif.
    """
    if break_minimum_seconds < 0:
        raise ValueError("break_minimum_seconds ne peut pas etre negatif")

    ordered = sorted(intervals, key=lambda item: (item.start, item.end))
    blocks: list[list[ActivityInterval]] = []
    interruption = 0
    for interval in ordered:
        if interval.activity_type is not ActivityType.DRIVING:
            interruption += interval.duration_seconds
            continue
        if blocks:
            gap = int((interval.start - blocks[-1][-1].end).total_seconds())
            # Un trou sans enregistrement compte aussi comme interruption.
            interruption = max(interruption, gap)
        if not blocks or interruption >= break_minimum_seconds:
            blocks.append([interval])
        else:
            blocks[-1].append(interval)
        interruption = 0

    return tuple(
        DrivingBlock(
            start=block[0].start,
            end=block[-1].end,
            driving_seconds=sum(item.duration_seconds for item in block),
            intervals=tuple(block),
        )
        for block in blocks
    )


def _as_datetime(value: date | datetime) -> datetime:
    """Convertit une date en instant UTC a minuit, ou normalise un instant."""
    if isinstance(value, datetime):
        return ensure_utc(value)
    return datetime(value.year, value.month, value.day, tzinfo=UTC)

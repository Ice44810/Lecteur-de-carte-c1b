"""Calcul des temps de travail et de l'amplitude de service.

INCERTITUDE DOCUMENTEE : la composition exacte du "temps de travail" d'un
conducteur routier n'est pas une simple somme d'activites tachygraphiques. Selon le
texte applique, les temps de disponibilite peuvent etre exclus du temps de travail
tout en etant pris en compte autrement.

La reference a consulter est la directive 2002/15/CE du Parlement europeen et du
Conseil du 11 mars 2002 (amenagement du temps de travail des personnes executant
des activites mobiles de transport routier), article 3, ainsi que sa transposition
nationale.

En consequence, la composition du temps de travail est un **parametre explicite**
(``included_types``) et non une regle figee dans le code. La valeur par defaut,
conduite + autres taches, correspond a la lecture la plus restrictive et donc la
moins susceptible de surestimer un temps de travail ; elle doit etre confirmee avant
toute exploitation reglementaire.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date, datetime

from app.analysis.activities import clip_to_period, split_by_day
from app.analysis.models import ActivityInterval
from app.core.enums import ActivityType

__all__ = [
    "DEFAULT_WORKING_TIME_TYPES",
    "WORKING_TIME_SOURCE",
    "calculate_working_time",
    "calculate_daily_working_time",
    "calculate_daily_amplitude",
    "calculate_amplitude_by_day",
]

DEFAULT_WORKING_TIME_TYPES: tuple[ActivityType, ...] = (
    ActivityType.DRIVING,
    ActivityType.WORK,
)
"""Composition par defaut du temps de travail : conduite et autres taches.

A confirmer au regard de la directive 2002/15/CE, article 3, avant toute
exploitation reglementaire (voir docstring du module).
"""

WORKING_TIME_SOURCE = (
    "Directive 2002/15/CE du 11 mars 2002, article 3 - definition a confirmer "
    "(y compris sa transposition nationale)"
)
"""Reference a citer dans les rapports lorsqu'un temps de travail est presente."""


def calculate_working_time(
    intervals: Iterable[ActivityInterval],
    *,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
    included_types: Sequence[ActivityType] = DEFAULT_WORKING_TIME_TYPES,
) -> int:
    """Retourne le temps de travail cumule, en secondes.

    Args:
        intervals: Intervalles d'activite normalises.
        period_start: Borne inferieure optionnelle (inclus).
        period_end: Borne superieure optionnelle (exclu).
        included_types: Types d'activite comptes comme temps de travail.

    Returns:
        Le cumul des durees des types retenus, en secondes.

    Raises:
        ValueError: ``included_types`` est vide.
    """
    if not included_types:
        raise ValueError("included_types ne peut pas etre vide")

    wanted = set(included_types)
    selected: Sequence[ActivityInterval] = tuple(intervals)
    if period_start is not None and period_end is not None:
        selected = clip_to_period(selected, period_start, period_end)
    return sum(
        interval.duration_seconds
        for interval in selected
        if interval.activity_type in wanted
    )


def calculate_daily_working_time(
    intervals: Iterable[ActivityInterval],
    *,
    included_types: Sequence[ActivityType] = DEFAULT_WORKING_TIME_TYPES,
) -> dict[date, int]:
    """Retourne le temps de travail par journee calendaire UTC.

    Args:
        intervals: Intervalles d'activite normalises.
        included_types: Types d'activite comptes comme temps de travail.

    Returns:
        Un dictionnaire ``jour -> secondes``, limite aux jours travailles.
    """
    wanted = set(included_types)
    result: dict[date, int] = {}
    for day, day_intervals in split_by_day(intervals).items():
        total = sum(
            interval.duration_seconds
            for interval in day_intervals
            if interval.activity_type in wanted
        )
        if total:
            result[day] = total
    return result


def calculate_daily_amplitude(
    intervals: Sequence[ActivityInterval], day: date
) -> int | None:
    """Retourne l'amplitude de service d'une journee, en secondes.

    L'amplitude est mesuree entre le debut de la premiere activite de service et la
    fin de la derniere activite de service de la journee. Les periodes de repos ne
    sont pas considerees comme du service, mais celles situees entre deux activites
    sont incluses dans l'amplitude puisqu'elles se trouvent dans l'intervalle.

    Args:
        intervals: Intervalles d'activite normalises.
        day: Jour analyse.

    Returns:
        L'amplitude en secondes, ou ``None`` si la journee ne comporte aucune
        activite de service.
    """
    day_intervals = [
        interval
        for interval in split_by_day(intervals).get(day, ())
        if interval.activity_type is not ActivityType.REST
    ]
    if not day_intervals:
        return None
    start = min(interval.start for interval in day_intervals)
    end = max(interval.end for interval in day_intervals)
    return int((end - start).total_seconds())


def calculate_amplitude_by_day(
    intervals: Sequence[ActivityInterval],
) -> dict[date, int]:
    """Retourne l'amplitude de service pour chaque journee comportant du service."""
    result: dict[date, int] = {}
    for day in split_by_day(intervals):
        amplitude = calculate_daily_amplitude(intervals, day)
        if amplitude is not None:
            result[day] = amplitude
    return result

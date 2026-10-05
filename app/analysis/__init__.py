"""Moteur d'analyse (DONNEE METIER -> ANALYSE -> ALERTE).

Deux responsabilites, strictement separees :

* **mesurer** : ``activities``, ``driving_time``, ``rest_time``, ``working_time`` et
  ``availability`` calculent des durees. Ces modules ne connaissent aucun seuil
  reglementaire et n'emettent aucun jugement ;
* **juger** : ``rules`` et ``infringements`` comparent une mesure a un seuil
  **configure et source**, et produisent des resultats structures.

Cette separation rend les calculs verifiables independamment des regles, et permet de
faire evoluer la reglementation sans toucher aux calculs.

Aucune couche de ce paquet n'importe SQLAlchemy ni PySide6 : le moteur s'execute sur
de simples :class:`~app.analysis.models.ActivityInterval`.
"""

from app.analysis.activities import (
    clip_to_period,
    find_gaps,
    find_overlaps,
    merge_adjacent,
    normalize_intervals,
    split_by_day,
    summarize_days,
    to_intervals,
)
from app.analysis.availability import calculate_availability_time
from app.analysis.driving_time import (
    calculate_daily_driving_time,
    calculate_driving_time,
    calculate_weekly_driving_time,
    continuous_driving_blocks,
)
from app.analysis.infringements import RuleEvaluation, evaluate_rules
from app.analysis.models import ActivityInterval, DaySummary, PeriodTotals
from app.analysis.rest_time import calculate_rest_periods, calculate_total_rest
from app.analysis.working_time import calculate_daily_amplitude, calculate_working_time

__all__ = [
    "ActivityInterval",
    "DaySummary",
    "PeriodTotals",
    "RuleEvaluation",
    "calculate_availability_time",
    "calculate_daily_amplitude",
    "calculate_daily_driving_time",
    "calculate_driving_time",
    "calculate_rest_periods",
    "calculate_total_rest",
    "calculate_weekly_driving_time",
    "calculate_working_time",
    "clip_to_period",
    "continuous_driving_blocks",
    "evaluate_rules",
    "find_gaps",
    "find_overlaps",
    "merge_adjacent",
    "normalize_intervals",
    "split_by_day",
    "summarize_days",
    "to_intervals",
]

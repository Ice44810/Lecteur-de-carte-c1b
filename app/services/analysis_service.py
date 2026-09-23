"""Service d'analyse : passerelle entre la base et le moteur de calcul.

Le service lit les activites, les convertit en intervalles, delegue les calculs a
``app.analysis``, puis retourne des objets de transfert. Il ne contient lui-meme aucun
calcul ni aucune regle.

ETAT D'AVANCEMENT

* **Implemente** : les calculs en lecture seule (frise journaliere, totaux sur une
  periode, evaluation des regles actives).
* **Non implemente (phase 6)** : l'enregistrement d'une analyse et de ses alertes en
  base (:meth:`AnalysisService.store_analysis`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from app.analysis.activities import (
    clip_to_period,
    find_gaps,
    merge_adjacent,
    normalize_intervals,
    to_intervals,
)
from app.analysis.availability import calculate_availability_time
from app.analysis.driving_time import calculate_driving_time
from app.analysis.infringements import RuleEvaluation, evaluate_rules
from app.analysis.models import ActivityInterval, PeriodTotals
from app.analysis.rest_time import calculate_total_rest
from app.analysis.rules import RuleContext, RuleRegistry, RuleSet, default_registry, empty_ruleset
from app.analysis.working_time import calculate_working_time
from app.config.logging_config import get_logger
from app.core.enums import ActivityType
from app.core.timeutils import day_bounds, format_duration, week_bounds
from app.database.repositories import ActivityRepository
from app.services.base import BaseService

__all__ = ["AnalysisService", "TimelineEntry", "PeriodAnalysis"]

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class TimelineEntry:
    """Ligne de la frise d'activites, prete a etre affichee.

    Attributes:
        activity_type: Nature de l'activite.
        start: Debut de la periode (UTC).
        end: Fin de la periode (UTC).
        duration_seconds: Duree en secondes.
        vehicle_id: Vehicule associe, si connu.
        is_gap: Indique une periode **sans enregistrement**, et non une activite.
    """

    activity_type: ActivityType
    start: datetime
    end: datetime
    duration_seconds: int
    vehicle_id: int | None = None
    is_gap: bool = False

    @property
    def label(self) -> str:
        """Libelle de la ligne, distinguant explicitement l'absence de donnee."""
        return "Aucun enregistrement" if self.is_gap else self.activity_type.label

    @property
    def time_range(self) -> str:
        """Plage horaire formatee, par exemple ``"08:00 - 10:15"``."""
        return f"{self.start.strftime('%H:%M')} - {self.end.strftime('%H:%M')}"

    @property
    def duration_label(self) -> str:
        """Duree formatee en ``HHhMM``."""
        return format_duration(self.duration_seconds)


@dataclass(frozen=True, slots=True)
class PeriodAnalysis:
    """Synthese calculee pour un conducteur sur une periode.

    Attributes:
        driver_id: Conducteur analyse.
        period_start: Debut de la periode (UTC, inclus).
        period_end: Fin de la periode (UTC, exclu).
        totals: Cumuls par type d'activite.
        driving_seconds: Temps de conduite.
        rest_seconds: Temps de repos.
        working_seconds: Temps de travail, selon la composition configuree.
        availability_seconds: Temps de disponibilite.
        gaps: Periodes sans enregistrement.
        evaluation: Resultat de l'evaluation des regles actives.
        activities_count: Nombre d'activites prises en compte.
    """

    driver_id: int
    period_start: datetime
    period_end: datetime
    totals: PeriodTotals
    driving_seconds: int
    rest_seconds: int
    working_seconds: int
    availability_seconds: int
    gaps: tuple[tuple[datetime, datetime], ...] = ()
    evaluation: RuleEvaluation | None = None
    activities_count: int = 0
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def has_data(self) -> bool:
        """Indique que la periode comporte au moins une activite."""
        return self.activities_count > 0

    @property
    def alerts_count(self) -> int:
        """Nombre de situations a verifier detectees sur la periode."""
        return len(self.evaluation.reportable) if self.evaluation is not None else 0

    def summary_message(self) -> str:
        """Message de synthese prudent, destine a la barre d'etat."""
        if not self.has_data:
            return "Aucune activite enregistree sur la periode selectionnee."
        if self.evaluation is None:
            return "Analyse des temps terminee."
        return self.evaluation.user_message()


class AnalysisService(BaseService):
    """Calculs d'analyse pour un conducteur."""

    def __init__(
        self,
        database: object | None = None,
        *,
        registry: RuleRegistry | None = None,
        ruleset: RuleSet | None = None,
    ) -> None:
        """Initialise le service.

        Args:
            database: Base a utiliser.
            registry: Regles actives. Par defaut, le registre livre (vide).
            ruleset: Jeu de seuils. Par defaut, le jeu livre (vide).
        """
        super().__init__(database)  # type: ignore[arg-type]
        self._registry = registry if registry is not None else default_registry()
        self._ruleset = ruleset if ruleset is not None else empty_ruleset()

    @property
    def registry(self) -> RuleRegistry:
        """Regles actives utilisees par ce service."""
        return self._registry

    @property
    def ruleset(self) -> RuleSet:
        """Jeu de seuils utilise par ce service."""
        return self._ruleset

    # ------------------------------------------------------------------ #
    # Lecture des activites
    # ------------------------------------------------------------------ #
    def load_intervals(
        self, driver_id: int, *, period_start: datetime, period_end: datetime
    ) -> tuple[ActivityInterval, ...]:
        """Charge les activites d'un conducteur et les convertit en intervalles.

        Args:
            driver_id: Conducteur concerne.
            period_start: Debut de la periode (inclus).
            period_end: Fin de la periode (exclu).

        Returns:
            Les intervalles normalises, bornes a la periode.
        """
        with self._session() as session:
            activities = ActivityRepository(session).list_for_driver(
                driver_id, period_start=period_start, period_end=period_end
            )
            intervals = to_intervals(activities)
        normalized = normalize_intervals(intervals, on_overlap="truncate")
        return clip_to_period(normalized, period_start, period_end)

    # ------------------------------------------------------------------ #
    # Frise journaliere
    # ------------------------------------------------------------------ #
    def daily_timeline(
        self,
        driver_id: int,
        day: date,
        *,
        activity_types: tuple[ActivityType, ...] | None = None,
        include_gaps: bool = True,
        merge_contiguous: bool = True,
    ) -> tuple[TimelineEntry, ...]:
        """Retourne la frise d'activites d'une journee.

        Args:
            driver_id: Conducteur concerne.
            day: Journee analysee.
            activity_types: Filtre optionnel sur les types d'activite.
            include_gaps: Insere une ligne explicite pour chaque periode sans
                enregistrement, afin que l'absence de donnee soit visible.
            merge_contiguous: Fusionne les enregistrements contigus de meme type.

        Returns:
            Les lignes de la frise, dans l'ordre chronologique.
        """
        start, end = day_bounds(datetime(day.year, day.month, day.day, tzinfo=UTC))
        intervals = self.load_intervals(driver_id, period_start=start, period_end=end)
        if merge_contiguous:
            intervals = merge_adjacent(intervals)

        entries: list[TimelineEntry] = [
            TimelineEntry(
                activity_type=interval.activity_type,
                start=interval.start,
                end=interval.end,
                duration_seconds=interval.duration_seconds,
                vehicle_id=interval.vehicle_id,
            )
            for interval in intervals
            if activity_types is None or interval.activity_type in activity_types
        ]

        if include_gaps and intervals:
            for gap_start, gap_end in find_gaps(intervals):
                entries.append(
                    TimelineEntry(
                        activity_type=ActivityType.UNKNOWN,
                        start=gap_start,
                        end=gap_end,
                        duration_seconds=int((gap_end - gap_start).total_seconds()),
                        is_gap=True,
                    )
                )

        return tuple(sorted(entries, key=lambda entry: (entry.start, entry.end)))

    # ------------------------------------------------------------------ #
    # Analyse d'une periode
    # ------------------------------------------------------------------ #
    def analyze_period(
        self,
        driver_id: int,
        *,
        period_start: datetime,
        period_end: datetime,
        source_file_id: int | None = None,
    ) -> PeriodAnalysis:
        """Calcule la synthese d'une periode et evalue les regles actives.

        Args:
            driver_id: Conducteur analyse.
            period_start: Debut de la periode (inclus).
            period_end: Fin de la periode (exclu).
            source_file_id: Fichier a l'origine des donnees, pour tracabilite.

        Returns:
            La synthese de la periode.
        """
        intervals = self.load_intervals(driver_id, period_start=period_start, period_end=period_end)
        totals = PeriodTotals.from_intervals(intervals)
        evaluation = evaluate_rules(
            RuleContext(
                driver_id=driver_id,
                intervals=intervals,
                period_start=period_start,
                period_end=period_end,
                ruleset=self._ruleset,
                metadata={"source_file_id": source_file_id} if source_file_id else {},
            ),
            registry=self._registry,
            ruleset=self._ruleset,
        )
        gaps = find_gaps(intervals) if intervals else ()

        analysis = PeriodAnalysis(
            driver_id=driver_id,
            period_start=period_start,
            period_end=period_end,
            totals=totals,
            driving_seconds=calculate_driving_time(intervals),
            rest_seconds=calculate_total_rest(intervals),
            working_seconds=calculate_working_time(intervals),
            availability_seconds=calculate_availability_time(intervals),
            gaps=gaps,
            evaluation=evaluation,
            activities_count=len(intervals),
            warnings=tuple(reason for _, reason in evaluation.skipped),
        )
        logger.info(
            "Analyse du conducteur %s du %s au %s : %d activite(s), conduite %s",
            driver_id,
            period_start.date(),
            period_end.date(),
            analysis.activities_count,
            format_duration(analysis.driving_seconds),
        )
        return analysis

    def analyze_day(self, driver_id: int, day: date) -> PeriodAnalysis:
        """Analyse une journee calendaire UTC."""
        start, end = day_bounds(datetime(day.year, day.month, day.day, tzinfo=UTC))
        return self.analyze_period(driver_id, period_start=start, period_end=end)

    def analyze_week(self, driver_id: int, moment: datetime) -> PeriodAnalysis:
        """Analyse la semaine (du lundi) contenant ``moment``."""
        start, end = week_bounds(moment)
        return self.analyze_period(driver_id, period_start=start, period_end=end)

    # ------------------------------------------------------------------ #
    # Ecriture (phase 6)
    # ------------------------------------------------------------------ #
    def store_analysis(self, analysis: PeriodAnalysis) -> int:
        """Enregistre une analyse et ses alertes en base.

        Args:
            analysis: Synthese a enregistrer.

        Returns:
            L'identifiant de l'analyse creee.

        Raises:
            NotImplementedError: Fonctionnalite prevue en phase 6. Les calculs en
                lecture seule sont deja disponibles.
        """
        raise NotImplementedError(
            "L'enregistrement des analyses et des alertes est prevu en phase 6. "
            "Les calculs sont d'ores et deja disponibles via analyze_period()."
        )

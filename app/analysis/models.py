"""Modeles du moteur d'analyse.

Le moteur d'analyse ne manipule **pas** d'objets SQLAlchemy : il travaille sur des
:class:`ActivityInterval`, structures immuables et sans dependance. Cela rend les
calculs testables sans base de donnees, et garantit qu'une analyse ne peut pas
modifier les donnees metier par effet de bord.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime

from app.core.enums import ActivityType
from app.core.timeutils import ensure_utc, format_duration, seconds_between

__all__ = ["ActivityInterval", "PeriodTotals", "DaySummary"]


@dataclass(frozen=True, slots=True)
class ActivityInterval:
    """Periode d'activite elementaire utilisee par les calculs.

    Attributes:
        activity_type: Nature de l'activite.
        start: Debut de la periode (UTC).
        end: Fin de la periode (UTC).
        activity_id: Identifiant de l'activite en base, si elle en provient.
        vehicle_id: Identifiant du vehicule, si connu.
        source_file_id: Identifiant du fichier d'origine (tracabilite).
    """

    activity_type: ActivityType
    start: datetime
    end: datetime
    activity_id: int | None = None
    vehicle_id: int | None = None
    source_file_id: int | None = None

    def __post_init__(self) -> None:
        """Normalise les bornes en UTC et refuse un intervalle inverse."""
        object.__setattr__(self, "start", ensure_utc(self.start))
        object.__setattr__(self, "end", ensure_utc(self.end))
        if self.end < self.start:
            raise ValueError(
                "la fin d'un intervalle d'activite ne peut pas preceder son debut"
            )

    @property
    def duration_seconds(self) -> int:
        """Duree de l'intervalle, en secondes."""
        return seconds_between(self.start, self.end)

    @property
    def is_empty(self) -> bool:
        """Indique un intervalle de duree nulle."""
        return self.start == self.end

    def overlaps(self, other: ActivityInterval) -> bool:
        """Indique si deux intervalles se chevauchent sur une duree non nulle."""
        return self.start < other.end and other.start < self.end

    def clip(self, period_start: datetime, period_end: datetime) -> ActivityInterval | None:
        """Restreint l'intervalle a une periode donnee.

        Args:
            period_start: Debut de la periode (inclus).
            period_end: Fin de la periode (exclu).

        Returns:
            Un nouvel intervalle borne a la periode, ou ``None`` s'il n'a aucune
            intersection de duree non nulle avec elle.
        """
        start = max(self.start, ensure_utc(period_start))
        end = min(self.end, ensure_utc(period_end))
        if end <= start:
            return None
        return ActivityInterval(
            activity_type=self.activity_type,
            start=start,
            end=end,
            activity_id=self.activity_id,
            vehicle_id=self.vehicle_id,
            source_file_id=self.source_file_id,
        )

    def with_bounds(self, start: datetime, end: datetime) -> ActivityInterval:
        """Retourne une copie de l'intervalle avec de nouvelles bornes."""
        return ActivityInterval(
            activity_type=self.activity_type,
            start=start,
            end=end,
            activity_id=self.activity_id,
            vehicle_id=self.vehicle_id,
            source_file_id=self.source_file_id,
        )


@dataclass(frozen=True, slots=True)
class PeriodTotals:
    """Cumul des durees par type d'activite sur une periode.

    Attributes:
        driving: Temps de conduite, en secondes.
        work: Temps de travail hors conduite, en secondes.
        availability: Temps de disponibilite, en secondes.
        rest: Temps de repos et de pause, en secondes.
        unknown: Temps dont le mode n'a pas pu etre determine, en secondes.
    """

    driving: int = 0
    work: int = 0
    availability: int = 0
    rest: int = 0
    unknown: int = 0

    def __post_init__(self) -> None:
        """Refuse une duree negative."""
        for field_name in ("driving", "work", "availability", "rest", "unknown"):
            if getattr(self, field_name) < 0:
                raise ValueError(f"{field_name} ne peut pas etre negatif")

    @classmethod
    def from_intervals(cls, intervals: Iterable[ActivityInterval]) -> PeriodTotals:
        """Cumule les durees d'une suite d'intervalles.

        Args:
            intervals: Intervalles a cumuler. Les chevauchements ne sont pas
                traites ici : utiliser d'abord
                :func:`app.analysis.activities.normalize_intervals`.

        Returns:
            Les totaux par type d'activite.
        """
        totals: dict[ActivityType, int] = dict.fromkeys(ActivityType, 0)
        for interval in intervals:
            totals[interval.activity_type] += interval.duration_seconds
        return cls.from_mapping(totals)

    @classmethod
    def from_mapping(cls, mapping: Mapping[ActivityType, int]) -> PeriodTotals:
        """Construit les totaux depuis un dictionnaire ``type -> secondes``."""
        return cls(
            driving=mapping.get(ActivityType.DRIVING, 0),
            work=mapping.get(ActivityType.WORK, 0),
            availability=mapping.get(ActivityType.AVAILABILITY, 0),
            rest=mapping.get(ActivityType.REST, 0),
            unknown=mapping.get(ActivityType.UNKNOWN, 0),
        )

    @property
    def total(self) -> int:
        """Somme de toutes les durees, en secondes."""
        return self.driving + self.work + self.availability + self.rest + self.unknown

    def as_dict(self) -> dict[ActivityType, int]:
        """Retourne les totaux sous forme de dictionnaire ``type -> secondes``."""
        return {
            ActivityType.DRIVING: self.driving,
            ActivityType.WORK: self.work,
            ActivityType.AVAILABILITY: self.availability,
            ActivityType.REST: self.rest,
            ActivityType.UNKNOWN: self.unknown,
        }

    def formatted(self) -> dict[ActivityType, str]:
        """Retourne les totaux formates en ``HHhMM``, pour affichage."""
        return {key: format_duration(value) for key, value in self.as_dict().items()}

    def __add__(self, other: PeriodTotals) -> PeriodTotals:
        """Additionne deux cumuls."""
        if not isinstance(other, PeriodTotals):  # pragma: no cover - garde-fou
            return NotImplemented
        return PeriodTotals(
            driving=self.driving + other.driving,
            work=self.work + other.work,
            availability=self.availability + other.availability,
            rest=self.rest + other.rest,
            unknown=self.unknown + other.unknown,
        )


@dataclass(frozen=True, slots=True)
class DaySummary:
    """Synthese d'une journee de service.

    Attributes:
        day: Jour calendaire concerne (UTC).
        totals: Cumuls par type d'activite.
        intervals: Intervalles bornes a la journee, tries chronologiquement.
    """

    day: date
    totals: PeriodTotals
    intervals: tuple[ActivityInterval, ...] = ()

    @property
    def first_activity_start(self) -> datetime | None:
        """Debut de la premiere activite de la journee."""
        return self.intervals[0].start if self.intervals else None

    @property
    def last_activity_end(self) -> datetime | None:
        """Fin de la derniere activite de la journee."""
        return self.intervals[-1].end if self.intervals else None

    @property
    def has_data(self) -> bool:
        """Indique que la journee comporte au moins une activite."""
        return bool(self.intervals)

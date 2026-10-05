"""Rapport de carte conducteur : contenu calcule, pret a etre affiche ou exporte.

Le rapport reprend les rubriques d'usage des logiciels de lecture de carte :

1. informations de la carte et du titulaire ;
2. evenements et anomalies ;
3. periodes de travail journalieres et interruptions qui les separent ;
4. activites ;
5. vehicules utilises ;
6. lieux de debut et de fin de periode de travail (pays).

Les activites proviennent de la base ; les evenements, vehicules et lieux sont relus
dans les fichiers archives du conducteur, qui en sont la source (aucune copie
intermediaire n'est conservee). Les horaires sont exprimes dans le fuseau d'affichage
(``TACHOLIBRE_TIMEZONE_DISPLAY``).

Decoupage en periodes de travail : deux periodes sont separees par une interruption
(repos, activite inconnue ou absence d'enregistrement) d'au moins
:data:`DAILY_REST_SPLIT_SECONDS`. Pour chaque interruption sont donnees sa duree totale
et, lorsqu'elle est plus courte, sa partie comprise dans les 24 heures qui suivent le
debut de la periode precedente (notion de repos journalier du reglement (CE)
no 561/2006, article 8, paragraphe 2). Ces valeurs sont des mesures, pas des
constats : aucune conformite n'est evaluee ici.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from app.analysis.activities import clip_to_period, normalize_intervals
from app.analysis.models import ActivityInterval, PeriodTotals
from app.config.logging_config import get_logger
from app.config.settings import Settings, get_settings
from app.core.enums import ActivityType, FileType
from app.core.exceptions import ParsingError, TachyError
from app.core.timeutils import ensure_utc, format_duration
from app.database.database import Database
from app.database.models import Activity
from app.database.repositories import ActivityRepository, DriverRepository, ImportRepository
from app.parser.c1b_parser import C1BParser
from app.parser.models import DecodedEvent, DecodedPlace, DecodedVehicleUse
from app.parser.reference_tables import ENTRY_TYPES
from app.services.base import BaseService

__all__ = [
    "DAILY_REST_SPLIT_SECONDS",
    "WEEKLY_REST_SECONDS",
    "ActivityLine",
    "CardReport",
    "CardReportService",
    "DriverCardInfo",
    "EventLine",
    "PlaceLine",
    "VehicleLine",
    "WorkPeriod",
]

logger = get_logger(__name__)

DAILY_REST_SPLIT_SECONDS = 9 * 3600
"""Interruption separant deux periodes de travail : 9 heures, duree minimale d'un repos
journalier reduit (reglement (CE) no 561/2006, article 4, point g)."""

WEEKLY_REST_SECONDS = 24 * 3600
"""Interruption qualifiee de repos hebdomadaire : 24 heures, duree minimale d'un repos
hebdomadaire reduit (reglement (CE) no 561/2006, article 4, point h)."""

DAILY_REST_WINDOW = timedelta(hours=24)
"""Fenetre de 24 heures du repos journalier (reglement (CE) no 561/2006, article 8 §2)."""

_WORK_TYPES = frozenset({ActivityType.DRIVING, ActivityType.WORK, ActivityType.AVAILABILITY})


class CardReportError(TachyError):
    """Le rapport demande ne peut pas etre etabli."""

    default_message = "Le rapport n'a pas pu etre etabli."
    default_cause = "Le conducteur demande est introuvable."
    default_action = "Actualisez la liste des conducteurs puis recommencez."


# --------------------------------------------------------------------------- #
# Objets de transfert
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class DriverCardInfo:
    """Rubrique « Info carte de conducteur »."""

    last_name: str | None
    first_name: str | None
    birth_date: date | None
    preferred_language: str | None
    card_number: str
    card_issuing_authority: str | None
    card_issuing_country: str | None
    card_issue_date: date | None
    card_validity_begin: date | None
    card_expiry_date: date | None
    licence_number: str | None
    licence_issuing_authority: str | None
    licence_issuing_country: str | None

    @property
    def display_name(self) -> str:
        """Nom affichable du titulaire."""
        parts = [part for part in ((self.last_name or "").upper(), self.first_name or "") if part]
        return " ".join(parts) or f"Carte {self.card_number}"


@dataclass(frozen=True, slots=True)
class EventLine:
    """Ligne de la rubrique « Evenements » (evenement ou anomalie)."""

    begin: datetime
    end: datetime | None
    kind: str
    code: str
    description: str
    vehicle: str | None

    @property
    def duration_seconds(self) -> int | None:
        """Duree de l'evenement, si sa fin est connue."""
        if self.end is None or self.end < self.begin:
            return None
        return int((self.end - self.begin).total_seconds())


@dataclass(frozen=True, slots=True)
class ActivityLine:
    """Ligne de la rubrique « Activites »."""

    start: datetime
    end: datetime
    activity_type: ActivityType
    vehicle: str | None
    crew: bool | None
    card_inserted: bool | None
    manual_entry: bool | None

    @property
    def duration_seconds(self) -> int:
        """Duree de l'activite, en secondes."""
        return int((self.end - self.start).total_seconds())

    @property
    def activity_label(self) -> str:
        """Libelle de l'activite."""
        return self.activity_type.label

    @property
    def driving_status_label(self) -> str:
        """Conducteur seul ou equipage, lorsque la carte est inseree."""
        if self.card_inserted is not True:
            return "Inconnu"
        return "Equipage" if self.crew else "Conducteur seul"

    @property
    def card_status_label(self) -> str:
        """Carte inseree, saisie manuelle ou inconnu."""
        if self.card_inserted:
            return "Carte inseree"
        if self.manual_entry:
            return "Saisie manuelle"
        return "Inconnu"


@dataclass(frozen=True, slots=True)
class VehicleLine:
    """Ligne de la rubrique « Vehicules »."""

    first_use: datetime
    last_use: datetime | None
    registration: str
    country: str | None
    odometer_begin: int | None
    odometer_end: int | None
    distance: int | None

    @property
    def duration_seconds(self) -> int | None:
        """Duree d'utilisation, si la fin est connue."""
        if self.last_use is None:
            return None
        return int((self.last_use - self.first_use).total_seconds())


@dataclass(frozen=True, slots=True)
class PlaceLine:
    """Ligne de la rubrique « Pays »."""

    entry_time: datetime
    country: str
    region: int | None
    odometer: int | None
    entry_label: str


@dataclass(frozen=True, slots=True)
class WorkPeriod:
    """Periode de travail journaliere et interruption qui la suit.

    Attributes:
        start: Debut de la premiere activite de travail.
        end: Fin de la derniere activite de travail.
        totals: Cumul par type d'activite entre ``start`` et ``end``.
        vehicles: Immatriculations utilisees, dans l'ordre d'apparition.
        activities_count: Nombre d'enregistrements d'activite de la periode.
        rest_after_seconds: Duree de l'interruption suivante, si une periode suit.
        rest_within_24h_seconds: Partie de cette interruption comprise dans les 24 h
            suivant ``start``, lorsqu'elle est plus courte que l'interruption.
        weekly_rest: L'interruption atteint :data:`WEEKLY_REST_SECONDS`.
    """

    start: datetime
    end: datetime
    totals: PeriodTotals
    vehicles: tuple[str, ...] = ()
    activities_count: int = 0
    rest_after_seconds: int | None = None
    rest_within_24h_seconds: int | None = None
    weekly_rest: bool = False

    @property
    def span_seconds(self) -> int:
        """Amplitude de la periode, en secondes."""
        return int((self.end - self.start).total_seconds())

    @property
    def rest_label(self) -> str | None:
        """Libelle de l'interruption suivante, par exemple ``"14h27 (14h07)"``."""
        if self.rest_after_seconds is None:
            return None
        label = format_duration(self.rest_after_seconds)
        if self.rest_within_24h_seconds is not None:
            label += f" ({format_duration(self.rest_within_24h_seconds)})"
        return label


@dataclass(frozen=True, slots=True)
class CardReport:
    """Rapport complet d'un conducteur sur une periode."""

    driver: DriverCardInfo
    period_start: datetime
    period_end: datetime
    timezone: str
    events: tuple[EventLine, ...] = ()
    work_periods: tuple[WorkPeriod, ...] = ()
    activities: tuple[ActivityLine, ...] = ()
    vehicles: tuple[VehicleLine, ...] = ()
    places: tuple[PlaceLine, ...] = ()
    files_count: int = 0
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def totals(self) -> PeriodTotals:
        """Cumul de toutes les periodes de travail."""
        total = PeriodTotals()
        for period in self.work_periods:
            total += period.totals
        return total

    def local(self, moment: datetime) -> datetime:
        """Convertit un instant dans le fuseau d'affichage du rapport."""
        return ensure_utc(moment).astimezone(ZoneInfo(self.timezone))

    @property
    def title(self) -> str:
        """En-tete du rapport : numero de carte, titulaire et periode."""
        last_day = self.local(self.period_end - timedelta(seconds=1))
        return (
            f"{self.driver.card_number}, {self.driver.display_name}, "
            f"{self.local(self.period_start):%d/%m/%Y} - {last_day:%d/%m/%Y}"
        )


# --------------------------------------------------------------------------- #
# Service
# --------------------------------------------------------------------------- #
class CardReportService(BaseService):
    """Etablit le rapport de carte d'un conducteur.

    Args:
        database: Base a utiliser.
        settings: Configuration (fuseau d'affichage).
    """

    def __init__(
        self, database: Database | None = None, *, settings: Settings | None = None
    ) -> None:
        super().__init__(database)
        self._settings = settings or get_settings()

    @property
    def timezone(self) -> str:
        """Fuseau d'affichage des rapports."""
        return self._settings.timezone_display

    def local_day_bounds(self, first_day: date, last_day: date) -> tuple[datetime, datetime]:
        """Bornes UTC d'une suite de journees locales ``[premier jour, dernier jour]``."""
        zone = ZoneInfo(self.timezone)
        start = datetime(first_day.year, first_day.month, first_day.day, tzinfo=zone)
        end_day = last_day + timedelta(days=1)
        end = datetime(end_day.year, end_day.month, end_day.day, tzinfo=zone)
        return ensure_utc(start), ensure_utc(end)

    def build(self, driver_id: int, *, period_start: datetime, period_end: datetime) -> CardReport:
        """Etablit le rapport d'un conducteur sur une periode.

        Args:
            driver_id: Conducteur concerne.
            period_start: Debut de la periode (UTC, inclus).
            period_end: Fin de la periode (UTC, exclu).

        Returns:
            Le rapport.

        Raises:
            CardReportError: Le conducteur n'existe pas.
        """
        start, end = ensure_utc(period_start), ensure_utc(period_end)
        # Contexte elargi : une periode de travail peut commencer avant la periode
        # demandee, et l'interruption qui suit la derniere se poursuivre apres.
        context_start, context_end = start - timedelta(days=3), end + timedelta(days=3)
        with self._session() as session:
            driver = DriverRepository(session).get(driver_id)
            if driver is None:
                raise CardReportError(technical_detail=f"driver_id={driver_id}")
            info = DriverCardInfo(
                last_name=driver.last_name,
                first_name=driver.first_name,
                birth_date=driver.birth_date,
                preferred_language=driver.preferred_language,
                card_number=driver.card_number,
                card_issuing_authority=driver.card_issuing_authority,
                card_issuing_country=driver.card_issuing_country,
                card_issue_date=driver.card_issue_date,
                card_validity_begin=driver.card_validity_begin,
                card_expiry_date=driver.card_expiry_date,
                licence_number=driver.licence_number,
                licence_issuing_authority=driver.licence_issuing_authority,
                licence_issuing_country=driver.licence_issuing_country,
            )
            activities = ActivityRepository(session).list_for_driver(
                driver_id, period_start=context_start, period_end=context_end
            )
            registrations = {
                item.id: item.vehicle.registration
                for item in activities
                if item.vehicle is not None
            }
            lines = self._activity_lines(activities, registrations)
            files = [
                Path(item.original_path)
                for item in ImportRepository(session).list_filtered(
                    driver_id=driver_id, file_type=FileType.C1B
                )
            ]

        events, vehicles, places, warnings = self._file_sections(files)
        intervals = normalize_intervals(
            (
                ActivityInterval(
                    activity_type=line.activity_type,
                    start=line.start,
                    end=line.end,
                )
                for line in lines
            ),
            on_overlap="truncate",
        )
        periods = _work_periods(intervals, lines)

        def within(moment: datetime) -> bool:
            return start <= moment < end

        return CardReport(
            driver=info,
            period_start=start,
            period_end=end,
            timezone=self.timezone,
            events=tuple(item for item in events if within(item.begin)),
            work_periods=tuple(item for item in periods if within(item.start)),
            activities=tuple(line for line in lines if line.end > start and line.start < end),
            vehicles=tuple(item for item in vehicles if within(item.first_use)),
            places=tuple(item for item in places if within(item.entry_time)),
            files_count=len(files),
            warnings=tuple(warnings),
        )

    # ------------------------------------------------------------------ #
    # Interne
    # ------------------------------------------------------------------ #
    @staticmethod
    def _activity_lines(
        activities: Iterable[Activity], registrations: dict[int, str]
    ) -> list[ActivityLine]:
        """Convertit les activites en lignes de rapport."""
        return [
            ActivityLine(
                start=item.start_datetime,
                end=item.end_datetime,
                activity_type=item.activity_type,
                vehicle=registrations.get(item.id),
                crew=item.crew,
                card_inserted=item.card_inserted,
                manual_entry=item.manual_entry,
            )
            for item in activities
        ]

    @staticmethod
    def _file_sections(
        files: list[Path],
    ) -> tuple[list[EventLine], list[VehicleLine], list[PlaceLine], list[str]]:
        """Relit evenements, vehicules et lieux dans les fichiers archives.

        Un meme enregistrement figure dans plusieurs telechargements successifs : les
        doublons sont elimines.
        """
        events: dict[tuple[object, ...], EventLine] = {}
        vehicles: dict[tuple[object, ...], VehicleLine] = {}
        places: dict[tuple[object, ...], PlaceLine] = {}
        warnings: list[str] = []
        for path in files:
            try:
                parser = C1BParser.from_path(path)
                decoded_events = parser.extract_events()
                decoded_vehicles = parser.extract_vehicles_used()
                decoded_places = parser.extract_places()
            except (ParsingError, TachyError) as exc:
                logger.warning("Fichier archive %s illisible : %s", path.name, exc)
                warnings.append(f"Le fichier archive {path.name} n'a pas pu etre relu.")
                continue
            for event in decoded_events:
                line = _event_line(event)
                events.setdefault((line.begin, line.code, line.kind), line)
            for use in decoded_vehicles:
                vehicle = _vehicle_line(use)
                vehicles.setdefault((vehicle.first_use, vehicle.registration), vehicle)
            for place in decoded_places:
                place_line = _place_line(place)
                places.setdefault((place_line.entry_time, place_line.entry_label), place_line)
        return (
            sorted(events.values(), key=lambda item: item.begin),
            sorted(vehicles.values(), key=lambda item: item.first_use),
            sorted(places.values(), key=lambda item: item.entry_time),
            warnings,
        )


def _event_line(event: DecodedEvent) -> EventLine:
    """Convertit un evenement decode en ligne de rapport."""
    return EventLine(
        begin=event.begin,
        end=event.end,
        kind="Anomalie" if event.is_fault else "Evenement",
        code=event.event_type_code,
        description=event.description or event.event_type_code,
        vehicle=event.vehicle_registration,
    )


def _vehicle_line(use: DecodedVehicleUse) -> VehicleLine:
    """Convertit une utilisation de vehicule decodee en ligne de rapport."""
    return VehicleLine(
        first_use=use.first_use,
        last_use=use.last_use,
        registration=use.registration,
        country=use.registration_country,
        odometer_begin=use.odometer_begin,
        odometer_end=use.odometer_end,
        distance=use.distance,
    )


def _place_line(place: DecodedPlace) -> PlaceLine:
    """Convertit un lieu decode en ligne de rapport."""
    return PlaceLine(
        entry_time=place.entry_time,
        country=place.country_name or place.country or "-",
        region=place.region or None,
        odometer=place.odometer,
        entry_label=ENTRY_TYPES.get(place.entry_type, f"Type {place.entry_type}"),
    )


def _work_periods(
    intervals: tuple[ActivityInterval, ...], lines: list[ActivityLine]
) -> list[WorkPeriod]:
    """Decoupe les activites en periodes de travail separees par de longues interruptions."""
    work = [item for item in intervals if item.activity_type in _WORK_TYPES]
    if not work:
        return []

    groups: list[list[ActivityInterval]] = [[work[0]]]
    for item in work[1:]:
        interruption = (item.start - groups[-1][-1].end).total_seconds()
        if interruption >= DAILY_REST_SPLIT_SECONDS:
            groups.append([item])
        else:
            groups[-1].append(item)

    periods: list[WorkPeriod] = []
    for index, group in enumerate(groups):
        start, end = group[0].start, group[-1].end
        totals = PeriodTotals.from_intervals(clip_to_period(intervals, start, end))
        in_period = [line for line in lines if line.start < end and line.end > start]
        vehicles: list[str] = []
        for line in in_period:
            if line.vehicle and line.vehicle not in vehicles:
                vehicles.append(line.vehicle)
        rest_after = rest_24h = None
        weekly = False
        if index + 1 < len(groups):
            next_start = groups[index + 1][0].start
            rest_after = int((next_start - end).total_seconds())
            weekly = rest_after >= WEEKLY_REST_SECONDS
            window_end = start + DAILY_REST_WINDOW
            # La fenetre de 24 heures ne concerne que le repos journalier.
            if not weekly and window_end < next_start:
                rest_24h = max(0, int((window_end - end).total_seconds()))
        periods.append(
            WorkPeriod(
                start=start,
                end=end,
                totals=totals,
                vehicles=tuple(vehicles),
                activities_count=len(in_period),
                rest_after_seconds=rest_after,
                rest_within_24h_seconds=rest_24h,
                weekly_rest=weekly,
            )
        )
    return periods

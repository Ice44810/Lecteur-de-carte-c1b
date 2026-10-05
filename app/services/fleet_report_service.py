"""Statistiques et controles de flotte, sur une periode.

Chaque methode retourne un :class:`~app.reports.model.ReportTable`, affiche tel quel
dans l'interface et exportable en Excel :

* activite cumulee par conducteur (detail journalier facultatif, heures-minutes ou
  heures-centiemes) ;
* distance cumulee par conducteur et par vehicule ;
* exces de vitesse enregistres sur les cartes ;
* conduites sans carte et continuite des vehicules, deduites des releves
  kilometriques : un vehicule dont le compteur a avance entre deux utilisations
  connues a roule sans qu'aucune carte importee ne l'enregistre ;
* continuite des conducteurs : periodes sans aucun enregistrement ;
* delais de telechargement des cartes et des unites embarquees ;
* conducteurs et vehicules inconnus : presents dans les donnees, non confirmes
  dans la flotte.

Sources : les activites viennent de la base ; vehicules utilises, kilometrages et
evenements sont relus dans les fichiers de carte archives, qui en sont la source.
Les journees sont celles du fuseau d'affichage (``TACHOLIBRE_TIMEZONE_DISPLAY``).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from app.analysis.activities import normalize_intervals, to_intervals
from app.analysis.models import ActivityInterval, PeriodTotals
from app.config.logging_config import get_logger
from app.config.settings import Settings, get_settings
from app.core.enums import FileType
from app.core.exceptions import ParsingError, TachyError
from app.core.timeutils import ensure_utc, format_duration, utcnow
from app.database.database import Database
from app.database.repositories import (
    ActivityRepository,
    DriverRepository,
    ImportRepository,
    InfringementRepository,
    VehicleRepository,
)
from app.parser.c1b_parser import C1BParser
from app.reports.model import ReportTable
from app.services.base import BaseService

__all__ = [
    "DRIVER_CARD_DOWNLOAD_DAYS",
    "VEHICLE_UNIT_DOWNLOAD_DAYS",
    "FleetReportService",
    "VehicleUse",
]

logger = get_logger(__name__)

DRIVER_CARD_DOWNLOAD_DAYS = 28
"""Frequence maximale de telechargement d'une carte conducteur : 28 jours
(reglement (UE) no 581/2010, article 1er, paragraphe 3, point b)."""

VEHICLE_UNIT_DOWNLOAD_DAYS = 90
"""Frequence maximale de telechargement d'une unite embarquee : 90 jours
(reglement (UE) no 581/2010, article 1er, paragraphe 3, point a)."""

DOWNLOAD_SOURCE = "Reglement (UE) no 581/2010, article 1er, paragraphe 3"

SPEEDING_EVENT = "07"
"""Code ``EventFaultType`` de l'exces de vitesse (reglement (UE) 2016/799, annexe I C,
appendice 1, 2.70)."""


@dataclass(frozen=True, slots=True)
class VehicleUse:
    """Utilisation d'un vehicule par un conducteur, relue dans une carte."""

    driver_id: int
    driver_name: str
    registration: str
    first_use: datetime
    last_use: datetime | None
    odometer_begin: int | None
    odometer_end: int | None

    @property
    def distance(self) -> int:
        """Distance parcourue (0 si les releves sont absents ou incoherents)."""
        if self.odometer_begin is None or self.odometer_end is None:
            return 0
        return max(self.odometer_end - self.odometer_begin, 0)


class FleetReportService(BaseService):
    """Statistiques et controles de flotte.

    Args:
        database: Base a utiliser.
        settings: Configuration (fuseau d'affichage).
    """

    def __init__(
        self, database: Database | None = None, *, settings: Settings | None = None
    ) -> None:
        super().__init__(database)
        self._settings = settings or get_settings()
        self._zone = ZoneInfo(self._settings.timezone_display)

    # ------------------------------------------------------------------ #
    # Outils
    # ------------------------------------------------------------------ #
    def local_day_bounds(self, first_day: date, last_day: date) -> tuple[datetime, datetime]:
        """Bornes UTC d'une suite de journees locales ``[premier jour, dernier jour]``."""
        start = datetime(first_day.year, first_day.month, first_day.day, tzinfo=self._zone)
        after = last_day + timedelta(days=1)
        end = datetime(after.year, after.month, after.day, tzinfo=self._zone)
        return ensure_utc(start), ensure_utc(end)

    def _local(self, moment: datetime) -> datetime:
        return ensure_utc(moment).astimezone(self._zone)

    def _stamp(self, moment: datetime | None) -> str:
        return self._local(moment).strftime("%d/%m/%Y %H:%M") if moment else "-"

    def _local_days(
        self, start: datetime, end: datetime
    ) -> Iterator[tuple[date, datetime, datetime]]:
        """Decoupe ``[start, end[`` en journees locales ``(jour, debut, fin)``."""
        cursor = start
        while cursor < end:
            day = self._local(cursor).date()
            _, next_midnight = self.local_day_bounds(day, day)
            yield day, cursor, min(next_midnight, end)
            cursor = next_midnight

    @staticmethod
    def _duration(seconds: int, *, centesimal: bool = False) -> str:
        """Duree en ``HHhMM`` ou en heures-centiemes (``12,75``)."""
        if centesimal:
            return f"{seconds / 3600:.2f}".replace(".", ",")
        return format_duration(seconds)

    # ------------------------------------------------------------------ #
    # Chargement
    # ------------------------------------------------------------------ #
    def _drivers(self) -> dict[int, tuple[str, str, bool]]:
        """Conducteurs : identifiant -> (nom, numero de carte, dans la flotte)."""
        with self._session() as session:
            return {
                driver.id: (driver.display_name, driver.card_number, bool(driver.in_fleet))
                for driver in DriverRepository(session).list_ordered()
            }

    def _intervals(self, start: datetime, end: datetime) -> dict[int, tuple[ActivityInterval, ...]]:
        """Activites normalisees par conducteur, chevauchant la periode."""
        result: dict[int, tuple[ActivityInterval, ...]] = {}
        with self._session() as session:
            by_driver: dict[int, list[object]] = defaultdict(list)
            for activity in ActivityRepository(session).list_overlapping(
                period_start=start, period_end=end
            ):
                by_driver[activity.driver_id].append(activity)
            for driver_id, activities in by_driver.items():
                result[driver_id] = normalize_intervals(
                    to_intervals(activities), on_overlap="truncate"
                )
        return result

    def _card_files(self) -> list[tuple[int, Path]]:
        """Fichiers de carte archives rattaches a un conducteur."""
        with self._session() as session:
            return [
                (item.driver_id, Path(item.original_path))
                for item in ImportRepository(session).list_filtered(file_type=FileType.C1B)
                if item.driver_id is not None
            ]

    def _vehicle_uses(self) -> list[VehicleUse]:
        """Utilisations de vehicules de toutes les cartes archivees, sans doublon."""
        names = self._drivers()
        uses: dict[tuple[int, datetime, str], VehicleUse] = {}
        for driver_id, path in self._card_files():
            for item in self._parse(path, "vehicles"):
                key = (driver_id, item.first_use, item.registration)
                uses.setdefault(
                    key,
                    VehicleUse(
                        driver_id=driver_id,
                        driver_name=names.get(driver_id, ("-", "", False))[0],
                        registration=item.registration.strip().upper(),
                        first_use=item.first_use,
                        last_use=item.last_use,
                        odometer_begin=item.odometer_begin,
                        odometer_end=item.odometer_end,
                    ),
                )
        return sorted(uses.values(), key=lambda use: use.first_use)

    @staticmethod
    def _parse(path: Path, section: str) -> tuple:  # type: ignore[type-arg]
        """Relit une section d'un fichier de carte archive (vide s'il est illisible)."""
        try:
            parser = C1BParser.from_path(path)
            if section == "vehicles":
                return parser.extract_vehicles_used()
            return parser.extract_events()
        except (ParsingError, TachyError) as exc:
            logger.warning("Fichier archive %s illisible : %s", path.name, exc)
            return ()

    # ------------------------------------------------------------------ #
    # Activite et distances cumulees
    # ------------------------------------------------------------------ #
    def cumulative_activity(
        self, start: datetime, end: datetime, *, daily: bool = True, centesimal: bool = False
    ) -> ReportTable:
        """Activite cumulee par conducteur sur la periode."""
        names = self._drivers()
        rows: list[tuple[str, ...]] = []
        emphasized: set[int] = set()
        for driver_id, intervals in sorted(
            self._intervals(start, end).items(), key=lambda item: names.get(item[0], ("",))[0]
        ):
            name = names.get(driver_id, ("-", "", False))[0]
            total = PeriodTotals()
            for day, day_start, day_end in self._local_days(start, end):
                totals = PeriodTotals.from_intervals(
                    portion
                    for item in intervals
                    if (portion := item.clip(day_start, day_end)) is not None
                )
                total += totals
                if daily and totals.total:
                    rows.append(
                        self._activity_row(name, day.strftime("%d/%m/%Y"), totals, centesimal)
                    )
            emphasized.add(len(rows))
            rows.append(self._activity_row(name, "Total", total, centesimal))
        return ReportTable(
            title="Activite cumulee",
            headers=(
                "Conducteur",
                "Jour",
                "Conduite",
                "Travail",
                "Disponibilite",
                "Repos",
                "Inconnu",
                "Conduite + travail",
                "Conduite + travail + dispo.",
            ),
            rows=tuple(rows),
            emphasized=frozenset(emphasized),
            note=(
                "Durees en heures et centiemes d'heure."
                if centesimal
                else "Durees en heures et minutes."
            )
            + " Journees du fuseau "
            + self._settings.timezone_display
            + ".",
        )

    def _activity_row(
        self, name: str, label: str, totals: PeriodTotals, centesimal: bool
    ) -> tuple[str, ...]:
        def fmt(seconds: int) -> str:
            return self._duration(seconds, centesimal=centesimal)

        return (
            name,
            label,
            fmt(totals.driving),
            fmt(totals.work),
            fmt(totals.availability),
            fmt(totals.rest),
            fmt(totals.unknown),
            fmt(totals.driving + totals.work),
            fmt(totals.driving + totals.work + totals.availability),
        )

    def driver_distance(self, start: datetime, end: datetime, *, daily: bool = True) -> ReportTable:
        """Distance cumulee par conducteur (somme des utilisations de vehicules)."""
        return self._distance(start, end, daily=daily, by_driver=True)

    def vehicle_distance(
        self, start: datetime, end: datetime, *, daily: bool = True
    ) -> ReportTable:
        """Distance cumulee par vehicule, tous conducteurs confondus."""
        return self._distance(start, end, daily=daily, by_driver=False)

    def _distance(
        self, start: datetime, end: datetime, *, daily: bool, by_driver: bool
    ) -> ReportTable:
        """Cumule les distances, rattachees au jour local du debut d'utilisation."""
        groups: dict[str, dict[date, list[VehicleUse]]] = defaultdict(lambda: defaultdict(list))
        for use in self._vehicle_uses():
            if start <= use.first_use < end:
                key = use.driver_name if by_driver else use.registration
                groups[key][self._local(use.first_use).date()].append(use)

        rows: list[tuple[str, ...]] = []
        emphasized: set[int] = set()
        for key in sorted(groups):
            total = 0
            others: set[str] = set()
            for day in sorted(groups[key]):
                uses = groups[key][day]
                distance = sum(use.distance for use in uses)
                related = sorted(
                    {use.registration if by_driver else use.driver_name for use in uses}
                )
                others.update(related)
                total += distance
                if daily:
                    rows.append((key, day.strftime("%d/%m/%Y"), str(distance), ", ".join(related)))
            emphasized.add(len(rows))
            rows.append((key, "Total", str(total), ", ".join(sorted(others))))
        return ReportTable(
            title="Distance cumulee conducteur" if by_driver else "Distance cumulee vehicule",
            headers=(
                "Conducteur" if by_driver else "Vehicule",
                "Jour",
                "Distance (km)",
                "Vehicules" if by_driver else "Conducteurs",
            ),
            rows=tuple(rows),
            emphasized=frozenset(emphasized),
            note=(
                "Distances relevees sur les cartes conducteur (compteur en debut et fin "
                "d'utilisation), rattachees au jour du debut d'utilisation."
                + (
                    ""
                    if by_driver
                    else " Seuls les trajets enregistres par une carte importee sont comptes."
                )
            ),
        )

    # ------------------------------------------------------------------ #
    # Evenements
    # ------------------------------------------------------------------ #
    def card_events(
        self, start: datetime, end: datetime, *, codes: frozenset[str] | None = None
    ) -> ReportTable:
        """Evenements et anomalies enregistres sur les cartes, sur la periode."""
        names = self._drivers()
        seen: set[tuple[object, ...]] = set()
        rows: list[tuple[str, ...]] = []
        lines = []
        for driver_id, path in self._card_files():
            for event in self._parse(path, "events"):
                if codes is not None and event.event_type_code not in codes:
                    continue
                if not start <= event.begin < end:
                    continue
                key = (driver_id, event.begin, event.event_type_code, event.is_fault)
                if key in seen:
                    continue
                seen.add(key)
                lines.append((event.begin, driver_id, event))
        for begin, driver_id, event in sorted(lines, key=lambda item: item[0]):
            duration = (
                format_duration(int((event.end - event.begin).total_seconds()))
                if event.end and event.end >= event.begin
                else "-"
            )
            rows.append(
                (
                    names.get(driver_id, ("-", "", False))[0],
                    self._stamp(begin),
                    self._stamp(event.end),
                    duration,
                    event.vehicle_registration or "-",
                    "Anomalie" if event.is_fault else "Evenement",
                    event.description or event.event_type_code,
                )
            )
        speeding_only = codes == frozenset({SPEEDING_EVENT})
        return ReportTable(
            title="Exces de vitesse" if speeding_only else "Evenements et anomalies",
            headers=("Conducteur", "Debut", "Fin", "Duree", "Vehicule", "Type", "Description"),
            rows=tuple(rows),
            note=(
                "Exces de vitesse enregistres sur les cartes conducteur. L'enregistrement "
                "detaille des vitesses est conserve par l'unite embarquee (fichiers V1B, "
                "dont le decodage n'est pas encore disponible)."
                if speeding_only
                else "Evenements et anomalies enregistres sur les cartes conducteur."
            )
            + ("" if rows else " Aucun enregistrement sur la periode."),
        )

    def speeding(self, start: datetime, end: datetime) -> ReportTable:
        """Exces de vitesse enregistres sur les cartes (code 07)."""
        return self.card_events(start, end, codes=frozenset({SPEEDING_EVENT}))

    # ------------------------------------------------------------------ #
    # Continuite
    # ------------------------------------------------------------------ #
    def _odometer_gaps(
        self, start: datetime, end: datetime
    ) -> list[tuple[VehicleUse, VehicleUse, int]]:
        """Ecarts de compteur entre utilisations successives d'un meme vehicule."""
        by_vehicle: dict[str, list[VehicleUse]] = defaultdict(list)
        for use in self._vehicle_uses():
            if use.odometer_begin is not None and use.odometer_end is not None:
                by_vehicle[use.registration].append(use)
        gaps: list[tuple[VehicleUse, VehicleUse, int]] = []
        for uses in by_vehicle.values():
            ordered = sorted(uses, key=lambda use: use.first_use)
            for previous, current in zip(ordered, ordered[1:], strict=False):
                if not start <= current.first_use < end:
                    continue
                assert previous.odometer_end is not None and current.odometer_begin is not None
                difference = current.odometer_begin - previous.odometer_end
                if difference:
                    gaps.append((previous, current, difference))
        return sorted(gaps, key=lambda item: item[1].first_use)

    def driving_without_card(
        self, start: datetime, end: datetime, *, minimum_km: int
    ) -> ReportTable:
        """Deplacements d'au moins ``minimum_km`` sans carte importee."""
        rows = tuple(
            self._gap_row(previous, current, difference)
            for previous, current, difference in self._odometer_gaps(start, end)
            if difference >= minimum_km
        )
        return ReportTable(
            title="Conduites sans carte",
            headers=self._gap_headers(),
            rows=rows,
            note=(
                f"Ecarts d'au moins {minimum_km} km entre la fin d'une utilisation et le "
                "debut de la suivante, d'apres les cartes importees : le vehicule a roule "
                "sans qu'une carte importee ne l'enregistre (carte d'un conducteur dont les "
                "donnees n'ont pas ete importees, ou conduite sans carte). Situation a "
                "verifier, non une constatation."
            ),
        )

    def vehicle_continuity(self, start: datetime, end: datetime) -> ReportTable:
        """Toutes les ruptures de continuite kilometrique des vehicules."""
        rows = tuple(
            self._gap_row(previous, current, difference)
            for previous, current, difference in self._odometer_gaps(start, end)
        )
        return ReportTable(
            title="Continuite vehicules",
            headers=self._gap_headers(),
            rows=rows,
            note=(
                "Un ecart positif est un trajet non couvert par les cartes importees ; un "
                "ecart negatif signale des releves incoherents (compteur remplace ou erreur)."
            ),
        )

    @staticmethod
    def _gap_headers() -> tuple[str, ...]:
        return (
            "Vehicule",
            "Fin d'utilisation precedente",
            "Conducteur precedent",
            "Compteur fin",
            "Debut d'utilisation suivante",
            "Conducteur suivant",
            "Compteur debut",
            "Ecart (km)",
        )

    def _gap_row(
        self, previous: VehicleUse, current: VehicleUse, difference: int
    ) -> tuple[str, ...]:
        return (
            current.registration,
            self._stamp(previous.last_use),
            previous.driver_name,
            str(previous.odometer_end),
            self._stamp(current.first_use),
            current.driver_name,
            str(current.odometer_begin),
            str(difference),
        )

    def driver_continuity(self, start: datetime, end: datetime) -> ReportTable:
        """Periodes sans aucun enregistrement, par conducteur de la flotte ou suivi."""
        names = self._drivers()
        intervals = self._intervals(start, end)
        rows: list[tuple[str, ...]] = []
        for driver_id, (name, card, in_fleet) in names.items():
            items = [
                portion
                for item in intervals.get(driver_id, ())
                if (portion := item.clip(start, end)) is not None
            ]
            if not items and not in_fleet:
                continue
            cursor = start
            for item in [*items, None]:
                gap_end = item.start if item is not None else end
                if gap_end - cursor >= timedelta(minutes=1):
                    rows.append(
                        (
                            name,
                            card,
                            self._stamp(cursor),
                            self._stamp(gap_end),
                            format_duration(int((gap_end - cursor).total_seconds())),
                        )
                    )
                if item is not None:
                    cursor = max(cursor, item.end)
        return ReportTable(
            title="Continuite conducteurs",
            headers=("Conducteur", "Carte", "Debut", "Fin", "Duree sans enregistrement"),
            rows=tuple(rows),
            note=(
                "Periodes pour lesquelles aucune activite n'est enregistree : jours sans "
                "carte inseree ni saisie manuelle, ou donnees non encore importees. Elles "
                "ne sont jamais assimilees a du repos."
            ),
        )

    # ------------------------------------------------------------------ #
    # Delais de telechargement
    # ------------------------------------------------------------------ #
    def driver_download_delays(self, *, reference: datetime | None = None) -> ReportTable:
        """Delai ecoule depuis le dernier telechargement de chaque carte conducteur."""
        now = reference or utcnow()
        names = self._drivers()
        last: dict[int, datetime] = {}
        with self._session() as session:
            for item in ImportRepository(session).list_filtered(file_type=FileType.C1B):
                if item.driver_id is not None and (
                    item.driver_id not in last or item.imported_at > last[item.driver_id]
                ):
                    last[item.driver_id] = item.imported_at
        rows = []
        for driver_id, (name, card, in_fleet) in names.items():
            if not in_fleet and driver_id not in last:
                continue
            rows.append(
                self._delay_row(name, card, last.get(driver_id), now, DRIVER_CARD_DOWNLOAD_DAYS)
            )
        return ReportTable(
            title="Delai archivage conducteurs",
            headers=("Conducteur", "Carte", "Dernier telechargement", "Jours ecoules", "Etat"),
            rows=tuple(rows),
            note=(
                f"Delai maximal entre deux telechargements de la carte : "
                f"{DRIVER_CARD_DOWNLOAD_DAYS} jours ({DOWNLOAD_SOURCE}, b)."
            ),
        )

    def vehicle_download_delays(self, *, reference: datetime | None = None) -> ReportTable:
        """Delai ecoule depuis le dernier telechargement de chaque unite embarquee."""
        now = reference or utcnow()
        rows = []
        with self._session() as session:
            last: dict[int, datetime] = {}
            for item in ImportRepository(session).list_filtered(file_type=FileType.V1B):
                if item.vehicle_id is not None and (
                    item.vehicle_id not in last or item.imported_at > last[item.vehicle_id]
                ):
                    last[item.vehicle_id] = item.imported_at
            for vehicle in VehicleRepository(session).list_ordered():
                if not vehicle.in_fleet:
                    continue
                rows.append(
                    self._delay_row(
                        vehicle.registration,
                        vehicle.registration_country or "-",
                        last.get(vehicle.id),
                        now,
                        VEHICLE_UNIT_DOWNLOAD_DAYS,
                    )
                )
        return ReportTable(
            title="Delai archivage vehicules",
            headers=("Vehicule", "Pays", "Dernier telechargement", "Jours ecoules", "Etat"),
            rows=tuple(rows),
            note=(
                f"Delai maximal entre deux telechargements de l'unite embarquee : "
                f"{VEHICLE_UNIT_DOWNLOAD_DAYS} jours ({DOWNLOAD_SOURCE}, a). Un fichier V1B "
                "n'est rattache a son vehicule qu'une fois decode : ce decodage n'etant pas "
                "encore disponible, les telechargements V1B importes n'apparaissent pas ici. "
                "Seuls les vehicules confirmes dans la flotte sont listes."
            ),
        )

    def _delay_row(
        self, name: str, detail: str, last: datetime | None, now: datetime, limit: int
    ) -> tuple[str, ...]:
        if last is None:
            return (name, detail, "Jamais", "-", "Aucun telechargement importe")
        days = (ensure_utc(now) - ensure_utc(last)).days
        state = "Delai depasse" if days > limit else f"A telecharger sous {limit - days} jour(s)"
        return (name, detail, self._stamp(last), str(days), state)

    # ------------------------------------------------------------------ #
    # Conducteurs et vehicules inconnus
    # ------------------------------------------------------------------ #
    def unknown_drivers(self) -> ReportTable:
        """Conducteurs crees par un import, non confirmes dans la flotte."""
        rows = []
        with self._session() as session:
            activities = ActivityRepository(session)
            imports = ImportRepository(session)
            for driver in DriverRepository(session).list_ordered():
                if driver.in_fleet:
                    continue
                last = activities.latest_activity_datetime(driver.id)
                rows.append(
                    (
                        driver.display_name,
                        driver.card_number,
                        str(imports.count_for_driver(driver.id)),
                        str(activities.count_for_driver(driver.id)),
                        self._stamp(last),
                    )
                )
        return ReportTable(
            title="Conducteurs inconnus",
            headers=("Conducteur", "Carte", "Telechargements", "Activites", "Derniere activite"),
            rows=tuple(rows),
            note=(
                "Conducteurs apparus a l'import d'une carte et non confirmes dans la flotte. "
                "Confirmez-les depuis la page Conducteurs s'ils font partie de l'entreprise."
            ),
        )

    def unknown_vehicles(self, start: datetime, end: datetime) -> ReportTable:
        """Vehicules utilises sur la periode, non confirmes dans la flotte."""
        with self._session() as session:
            fleet = {
                vehicle.registration
                for vehicle in VehicleRepository(session).list_ordered()
                if vehicle.in_fleet
            }
        groups: dict[str, list[VehicleUse]] = defaultdict(list)
        for use in self._vehicle_uses():
            if start <= use.first_use < end and use.registration not in fleet:
                groups[use.registration].append(use)
        rows = tuple(
            (
                registration,
                ", ".join(sorted({use.driver_name for use in uses})),
                self._stamp(min(use.first_use for use in uses)),
                self._stamp(max((use.last_use or use.first_use) for use in uses)),
                str(len(uses)),
                str(sum(use.distance for use in uses)),
            )
            for registration, uses in sorted(groups.items())
        )
        return ReportTable(
            title="Vehicules inconnus",
            headers=(
                "Vehicule",
                "Conducteurs",
                "Premiere utilisation",
                "Derniere utilisation",
                "Utilisations",
                "Distance (km)",
            ),
            rows=rows,
            note=(
                "Vehicules utilises par vos conducteurs et non confirmes dans la flotte "
                "(location, pret, autre entreprise...). Confirmez-les depuis la page "
                "Vehicules s'ils font partie de l'entreprise."
            ),
        )

    # ------------------------------------------------------------------ #
    # Exports
    # ------------------------------------------------------------------ #
    def summary(self, start: datetime, end: datetime) -> ReportTable:
        """Synthese par conducteur : temps et distance de la periode."""
        activity = self.cumulative_activity(start, end, daily=False)
        distance = {row[0]: row[2] for row in self.driver_distance(start, end, daily=False).rows}
        rows = tuple((row[0], *row[2:], distance.get(row[0], "0")) for row in activity.rows)
        return ReportTable(
            title="Synthese",
            headers=(
                "Conducteur",
                "Conduite",
                "Travail",
                "Disponibilite",
                "Repos",
                "Inconnu",
                "Conduite + travail",
                "Conduite + travail + dispo.",
                "Distance (km)",
            ),
            rows=rows,
            note=activity.note,
        )

    def detailed_tables(self, start: datetime, end: datetime) -> tuple[ReportTable, ...]:
        """Tableaux de l'export detaille."""
        return (
            self.summary(start, end),
            self.cumulative_activity(start, end, daily=True),
            self.driver_distance(start, end, daily=True),
            self.vehicle_distance(start, end, daily=True),
            self.driver_continuity(start, end),
            self.vehicle_continuity(start, end),
        )

    def anomaly_tables(
        self, start: datetime, end: datetime, *, minimum_km: int
    ) -> tuple[ReportTable, ...]:
        """Tableaux de l'export des anomalies."""
        with self._session() as session:
            recorded = tuple(
                (
                    item.occurred_on.strftime("%d/%m/%Y"),
                    item.driver.display_name,
                    item.rule_code,
                    item.status.label,
                    item.description,
                    item.regulation_reference or "-",
                )
                for item in InfringementRepository(session).list_recent(limit=10_000)
                if start
                <= ensure_utc(datetime.combine(item.occurred_on, datetime.min.time()))
                < end
            )
        return (
            self.card_events(start, end),
            self.driving_without_card(start, end, minimum_km=minimum_km),
            self.driver_download_delays(),
            ReportTable(
                title="Situations a verifier",
                headers=("Jour", "Conducteur", "Regle", "Statut", "Description", "Source"),
                rows=recorded,
                note=(
                    "Situations detectees par le moteur de regles. Aucune regle n'etant "
                    "active tant que ses seuils ne sont pas verifies, cette liste peut "
                    "etre vide."
                ),
            ),
        )

"""Service du tableau de bord.

Toutes les valeurs affichees par le tableau de bord proviennent de ce service, donc
de la base : aucune valeur n'est ecrite en dur dans l'interface (exigence de la
section 10 du cahier des charges). Lorsqu'une donnee n'est pas disponible, le service
retourne ``None`` et l'interface affiche un tiret, jamais un zero trompeur.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.analysis.rules import RuleRegistry, RuleSet, default_registry, empty_ruleset
from app.config.logging_config import get_logger
from app.core.enums import ActivityType, FileType, ParsingStatus
from app.core.timeutils import format_duration, utcnow, week_bounds
from app.database.repositories import (
    ActivityRepository,
    DriverRepository,
    ImportRepository,
    InfringementRepository,
    VehicleRepository,
)
from app.services.base import BaseService

__all__ = ["DashboardService", "DashboardData", "RecentActivityLine", "AlertLine"]

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RecentActivityLine:
    """Ligne du bloc « activite recente » du tableau de bord.

    Attributes:
        driver_display_name: Conducteur concerne.
        day_label: Journee concernee, au format ``JJ/MM/AAAA``.
        first_start: Debut de la premiere activite de la journee.
        last_end: Fin de la derniere activite de la journee.
        driving_seconds: Temps de conduite de la journee.
    """

    driver_display_name: str
    day_label: str
    first_start: datetime
    last_end: datetime
    driving_seconds: int

    @property
    def time_range(self) -> str:
        """Plage horaire de service, par exemple ``"08:00 - 17:30"``."""
        return f"{self.first_start.strftime('%H:%M')} - {self.last_end.strftime('%H:%M')}"

    @property
    def driving_label(self) -> str:
        """Temps de conduite formate."""
        return format_duration(self.driving_seconds)


@dataclass(frozen=True, slots=True)
class AlertLine:
    """Ligne du bloc « alertes » du tableau de bord.

    Attributes:
        driver_display_name: Conducteur concerne.
        occurred_on_label: Jour concerne, au format ``JJ/MM/AAAA``.
        description: Description prudente de la situation.
        status_label: Libelle du statut (« Situation a verifier », ...).
        severity_label: Libelle de criticite interne.
    """

    driver_display_name: str
    occurred_on_label: str
    description: str
    status_label: str
    severity_label: str


@dataclass(frozen=True, slots=True)
class DashboardData:
    """Ensemble des indicateurs du tableau de bord.

    Attributes:
        drivers_count: Nombre de conducteurs suivis.
        vehicles_count: Nombre de vehicules enregistres.
        files_count: Nombre total de fichiers importes.
        c1b_count: Nombre de fichiers de carte conducteur importes.
        v1b_count: Nombre de fichiers vehicule importes.
        pending_parsing_count: Nombre de fichiers archives non encore decodes.
        last_import_at: Date du dernier telechargement importe.
        open_alerts_count: Nombre d'alertes non encore verifiees.
        week_driving_seconds: Temps de conduite de la semaine en cours.
        week_rest_seconds: Temps de repos de la semaine en cours.
        active_drivers_this_week: Nombre de conducteurs actifs cette semaine.
        recent_activity: Lignes d'activite recente.
        alerts: Dernieres alertes.
        rules_active_count: Nombre de regles reglementaires actives.
        ruleset_version: Version du jeu de seuils applique.
        generated_at: Date de calcul des indicateurs.
    """

    drivers_count: int = 0
    vehicles_count: int = 0
    files_count: int = 0
    c1b_count: int = 0
    v1b_count: int = 0
    pending_parsing_count: int = 0
    last_import_at: datetime | None = None
    open_alerts_count: int = 0
    week_driving_seconds: int = 0
    week_rest_seconds: int = 0
    active_drivers_this_week: int = 0
    recent_activity: tuple[RecentActivityLine, ...] = ()
    alerts: tuple[AlertLine, ...] = ()
    rules_active_count: int = 0
    ruleset_version: str = ""
    generated_at: datetime = field(default_factory=utcnow)

    @property
    def last_import_label(self) -> str:
        """Date du dernier telechargement, ou ``"Aucun"``."""
        if self.last_import_at is None:
            return "Aucun"
        return self.last_import_at.strftime("%d/%m/%Y %H:%M")

    @property
    def week_driving_label(self) -> str:
        """Temps de conduite de la semaine, formate."""
        return format_duration(self.week_driving_seconds)

    @property
    def week_rest_label(self) -> str:
        """Temps de repos de la semaine, formate."""
        return format_duration(self.week_rest_seconds)

    @property
    def is_empty(self) -> bool:
        """Indique qu'aucune donnee n'a encore ete importee."""
        return self.drivers_count == 0 and self.files_count == 0

    @property
    def rules_notice(self) -> str | None:
        """Avertissement a afficher lorsqu'aucune regle n'est active.

        Returns:
            Un message explicatif, ou ``None`` si des regles sont actives.
        """
        if self.rules_active_count > 0:
            return None
        return (
            "Aucune regle reglementaire n'est active : les temps sont calcules, mais "
            "aucun depassement n'est recherche. Les seuils doivent d'abord etre saisis "
            "et verifies dans Parametres > Regles."
        )


class DashboardService(BaseService):
    """Agrege les indicateurs affiches sur le tableau de bord."""

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
            registry: Regles actives, pour informer l'utilisateur de leur nombre.
            ruleset: Jeu de seuils applique.
        """
        super().__init__(database)  # type: ignore[arg-type]
        self._registry = registry if registry is not None else default_registry()
        self._ruleset = ruleset if ruleset is not None else empty_ruleset()

    def load(
        self, *, recent_limit: int = 5, alerts_limit: int = 5, reference: datetime | None = None
    ) -> DashboardData:
        """Calcule les indicateurs du tableau de bord.

        Args:
            recent_limit: Nombre de lignes d'activite recente.
            alerts_limit: Nombre d'alertes affichees.
            reference: Instant de reference pour la semaine en cours.

        Returns:
            Les indicateurs, tous issus de la base.
        """
        moment = reference or utcnow()
        week_start, week_end = week_bounds(moment)

        with self._session() as session:
            drivers = DriverRepository(session)
            vehicles = VehicleRepository(session)
            imports = ImportRepository(session)
            activities = ActivityRepository(session)
            infringements = InfringementRepository(session)

            data = DashboardData(
                drivers_count=drivers.count(),
                vehicles_count=vehicles.count(),
                files_count=imports.count(),
                c1b_count=imports.count_by_type(FileType.C1B),
                v1b_count=imports.count_by_type(FileType.V1B),
                pending_parsing_count=(
                    imports.count_by_status(ParsingStatus.PENDING)
                    + imports.count_by_status(ParsingStatus.UNSUPPORTED)
                ),
                last_import_at=imports.last_import_datetime(),
                open_alerts_count=infringements.count_open(),
                week_driving_seconds=activities.total_duration(
                    activity_type=ActivityType.DRIVING,
                    period_start=week_start,
                    period_end=week_end,
                ),
                week_rest_seconds=activities.total_duration(
                    activity_type=ActivityType.REST,
                    period_start=week_start,
                    period_end=week_end,
                ),
                active_drivers_this_week=activities.count_drivers_with_activity(
                    period_start=week_start, period_end=week_end
                ),
                recent_activity=self._recent_activity(session, limit=recent_limit),
                alerts=self._alerts(session, limit=alerts_limit),
                rules_active_count=len(self._registry),
                ruleset_version=self._ruleset.version,
                generated_at=moment,
            )

        logger.debug(
            "Tableau de bord : %d conducteur(s), %d fichier(s), %d alerte(s) ouverte(s)",
            data.drivers_count,
            data.files_count,
            data.open_alerts_count,
        )
        return data

    # ------------------------------------------------------------------ #
    # Interne
    # ------------------------------------------------------------------ #
    @staticmethod
    def _recent_activity(session: object, *, limit: int) -> tuple[RecentActivityLine, ...]:
        """Construit les lignes d'activite recente, une par conducteur et par jour."""
        from app.analysis.activities import split_by_day, to_intervals

        activity_repository = ActivityRepository(session)  # type: ignore[arg-type]
        driver_repository = DriverRepository(session)  # type: ignore[arg-type]

        latest = activity_repository.latest_activity_datetime()
        if latest is None:
            return ()

        window_start = latest - timedelta(days=7)
        lines: list[RecentActivityLine] = []
        for driver in driver_repository.list_ordered():
            activities = activity_repository.list_for_driver(
                driver.id, period_start=window_start, period_end=latest + timedelta(seconds=1)
            )
            if not activities:
                continue
            by_day = split_by_day(to_intervals(activities))
            for day, intervals in sorted(by_day.items(), reverse=True):
                service = [
                    interval
                    for interval in intervals
                    if interval.activity_type is not ActivityType.REST
                ]
                if not service:
                    continue
                lines.append(
                    RecentActivityLine(
                        driver_display_name=driver.display_name,
                        day_label=day.strftime("%d/%m/%Y"),
                        first_start=min(interval.start for interval in service),
                        last_end=max(interval.end for interval in service),
                        driving_seconds=sum(
                            interval.duration_seconds
                            for interval in intervals
                            if interval.activity_type is ActivityType.DRIVING
                        ),
                    )
                )
                break

        lines.sort(key=lambda line: line.last_end, reverse=True)
        return tuple(lines[:limit])

    @staticmethod
    def _alerts(session: object, *, limit: int) -> tuple[AlertLine, ...]:
        """Construit les lignes d'alerte les plus recentes."""
        repository = InfringementRepository(session)  # type: ignore[arg-type]
        return tuple(
            AlertLine(
                driver_display_name=item.driver.display_name,
                occurred_on_label=item.occurred_on.strftime("%d/%m/%Y"),
                description=item.description,
                status_label=item.status.label,
                severity_label=item.severity.label,
            )
            for item in repository.list_recent(limit=limit)
        )

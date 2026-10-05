"""Service de production des rapports.

Les generateurs (``app.reports.pdf``, ``app.reports.excel``, ``app.reports.csv_export``)
recoivent des objets deja calcules par
:class:`~app.services.card_report_service.CardReportService` : un generateur de
rapport n'interroge jamais la base et ne recalcule aucun temps.

* rapport conducteur : les six rubriques du rapport de carte (Excel : une feuille par
  rubrique ; PDF : une section par rubrique ; CSV : les activites) ;
* rapport entreprise : une ligne de synthese par conducteur ayant des activites sur
  la periode.

Contenu attendu du rapport conducteur (section 13) : identite, periode, activites,
temps de conduite, temps de repos, anomalies, evenements, fichier source.

Contenu attendu du rapport entreprise : liste des conducteurs, periodes analysees,
anomalies, statistiques.

Exigence de tracabilite : tout rapport presentant un depassement apparent devra citer
la source du seuil applique et la version du jeu de regles utilise, informations deja
portees par ``RuleResult.regulation_reference`` et ``RuleEvaluation.ruleset_version``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from pathlib import Path
from zoneinfo import ZoneInfo

from app.config.logging_config import get_logger
from app.config.settings import Settings, get_settings
from app.core.exceptions import ReportError
from app.core.timeutils import ensure_utc
from app.services.base import BaseService

__all__ = ["ReportFormat", "ReportRequest", "ReportService"]

logger = get_logger(__name__)


class ReportFormat(StrEnum):
    """Format de sortie d'un rapport.

    Attributes:
        PDF: Document PDF (ReportLab).
        EXCEL: Classeur Excel (openpyxl).
        CSV: Fichier texte separe par des virgules.
    """

    PDF = "PDF"
    EXCEL = "EXCEL"
    CSV = "CSV"

    @property
    def label(self) -> str:
        """Libelle affichable."""
        return {ReportFormat.PDF: "PDF", ReportFormat.EXCEL: "Excel", ReportFormat.CSV: "CSV"}[self]

    @property
    def extension(self) -> str:
        """Extension de fichier correspondante."""
        return {ReportFormat.PDF: ".pdf", ReportFormat.EXCEL: ".xlsx", ReportFormat.CSV: ".csv"}[
            self
        ]


@dataclass(frozen=True, slots=True)
class ReportRequest:
    """Demande de rapport.

    Attributes:
        report_format: Format de sortie souhaite.
        period_start: Debut de la periode couverte (UTC).
        period_end: Fin de la periode couverte (UTC).
        driver_ids: Conducteurs concernes ; vide signifie « toute l'entreprise ».
        output_path: Chemin de sortie ; ``None`` pour un nom genere automatiquement.
    """

    report_format: ReportFormat
    period_start: datetime
    period_end: datetime
    driver_ids: tuple[int, ...] = ()
    output_path: Path | None = None

    def __post_init__(self) -> None:
        """Refuse une periode vide ou inversee."""
        if self.period_end <= self.period_start:
            raise ValueError("la fin de la periode du rapport doit suivre son debut")

    @property
    def is_company_report(self) -> bool:
        """Indique un rapport entreprise plutot qu'un rapport conducteur."""
        return not self.driver_ids


class ReportService(BaseService):
    """Production des rapports conducteur et entreprise."""

    def __init__(self, database: object | None = None, *, settings: Settings | None = None) -> None:
        """Initialise le service.

        Args:
            database: Base a utiliser.
            settings: Configuration, pour determiner le repertoire d'export.
        """
        super().__init__(database)  # type: ignore[arg-type]
        self._settings = settings or get_settings()

    @property
    def export_directory(self) -> Path:
        """Repertoire de sortie des rapports."""
        return self._settings.exports_dir

    def suggest_output_path(self, request: ReportRequest) -> Path:
        """Propose un nom de fichier de sortie.

        Le nom comporte la periode couverte et le type de rapport, afin que les
        exports restent identifiables sans ouvrir le fichier.

        Args:
            request: Demande de rapport.

        Returns:
            Un chemin dans le repertoire d'export.
        """
        if request.output_path is not None:
            return request.output_path
        scope = "entreprise" if request.is_company_report else f"conducteur-{request.driver_ids[0]}"
        zone = ZoneInfo(self._settings.timezone_display)
        first_day = ensure_utc(request.period_start).astimezone(zone)
        last_day = (ensure_utc(request.period_end) - timedelta(seconds=1)).astimezone(zone)
        stamp = f"{first_day:%Y%m%d}-{last_day:%Y%m%d}"
        return self.export_directory / f"rapport-{scope}-{stamp}{request.report_format.extension}"

    def generate(self, request: ReportRequest) -> Path:
        """Produit un rapport.

        Args:
            request: Demande de rapport.

        Returns:
            Le chemin du fichier produit.

        Raises:
            ReportError: Aucun conducteur n'a de donnees sur la periode (rapport
                entreprise), ou le fichier n'a pas pu etre ecrit.
            CardReportError: Le conducteur demande n'existe pas.
        """
        from app import __version__
        from app.reports.csv_export import write_csv
        from app.reports.excel import write_excel
        from app.reports.pdf import write_pdf
        from app.reports.tables import card_report_tables, summary_table
        from app.services.card_report_service import CardReportService

        builder = CardReportService(self.database, settings=self._settings)
        if request.is_company_report:
            reports = tuple(
                report
                for driver_id in self._driver_ids()
                if (
                    report := builder.build(
                        driver_id,
                        period_start=request.period_start,
                        period_end=request.period_end,
                    )
                ).work_periods
            )
            if not reports:
                raise ReportError(
                    "Aucune donnee a exporter sur cette periode.",
                    cause="Aucun conducteur n'a d'activite de travail enregistree sur la periode.",
                    action="Choisissez une autre periode ou importez les cartes concernees.",
                )
            tables = (summary_table(reports),)
            header = (
                f"tachy-linux {__version__}, rapport entreprise"
                f"{' ' + self._settings.company_name if self._settings.company_name else ''}"
            )
        else:
            report = builder.build(
                request.driver_ids[0],
                period_start=request.period_start,
                period_end=request.period_end,
            )
            tables = card_report_tables(report)
            header = f"tachy-linux {__version__}, {report.title}"

        path = self.suggest_output_path(request)
        try:
            if request.report_format is ReportFormat.EXCEL:
                write_excel(path, header, tables)
            elif request.report_format is ReportFormat.PDF:
                write_pdf(path, header, tables)
            else:
                activities = next((table for table in tables if table.title == "Activites"), None)
                write_csv(path, activities or tables[0])
        except OSError as exc:
            raise ReportError(
                "Le rapport n'a pas pu etre enregistre.",
                cause="Le repertoire d'export est inaccessible ou le fichier est ouvert.",
                action=(
                    "Fermez le fichier s'il est ouvert, puis verifiez les droits sur "
                    f"{path.parent}."
                ),
                technical_detail=str(exc),
            ) from exc
        logger.info("Rapport %s produit : %s", request.report_format.value, path.name)
        return path

    def _driver_ids(self) -> list[int]:
        """Identifiants de tous les conducteurs, tries par nom."""
        from app.database.repositories import DriverRepository

        with self._session() as session:
            return [driver.id for driver in DriverRepository(session).list_ordered()]

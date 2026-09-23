"""Service de production des rapports.

ETAT : NON IMPLEMENTE (phase 9 de la feuille de route).

Le contrat est fixe des maintenant afin que l'interface, les tests et la future API
puissent s'y referer. Les generateurs (``app.reports.pdf``, ``app.reports.excel``,
``app.reports.csv``) recevront des objets de transfert deja calcules par
``AnalysisService`` : un generateur de rapport ne doit jamais interroger la base ni
recalculer un temps.

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
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from app.config.logging_config import get_logger
from app.config.settings import Settings, get_settings
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
        stamp = f"{request.period_start.strftime('%Y%m%d')}-{request.period_end.strftime('%Y%m%d')}"
        return self.export_directory / f"rapport-{scope}-{stamp}{request.report_format.extension}"

    def generate(self, request: ReportRequest) -> Path:
        """Produit un rapport.

        Args:
            request: Demande de rapport.

        Returns:
            Le chemin du fichier produit.

        Raises:
            NotImplementedError: Fonctionnalite prevue en phase 9.
        """
        raise NotImplementedError(
            "La production des rapports PDF, Excel et CSV est prevue en phase 9. "
            "Le contrat de service et le nommage des fichiers sont deja fixes."
        )

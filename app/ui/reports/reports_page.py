"""Rapports PDF, Excel et CSV.

La production effective est prevue en phase 9. La page expose des maintenant le
contrat : perimetre du rapport, periode, format, et emplacement d'export. Elle indique
clairement que la generation n'est pas encore disponible plutot que de produire un
document incomplet.
"""

from __future__ import annotations

from datetime import timedelta

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.bootstrap import ApplicationContext
from app.core.timeutils import utcnow
from app.services.driver_service import DriverService
from app.services.report_service import ReportFormat, ReportRequest, ReportService
from app.ui.common.errors import show_error
from app.ui.common.page import Page
from app.ui.common.widgets import NoticeBanner

__all__ = ["ReportsPage"]


class ReportsPage(Page):
    """Preparation d'un rapport conducteur ou entreprise."""

    title = "Rapports"
    subtitle = "Rapport conducteur ou rapport entreprise, sur une periode donnee."

    def __init__(self, context: ApplicationContext, parent: QWidget | None = None) -> None:
        self._drivers = DriverService(context.database)
        self._service = ReportService(context.database, settings=context.settings)
        super().__init__(context, parent)

    def build(self) -> None:
        """Construit le formulaire de demande de rapport."""
        self.content_layout.addWidget(
            NoticeBanner(
                "Phase 9 : la generation des rapports PDF, Excel et CSV n'est pas encore "
                "disponible. Le contrat de service, le contenu attendu et le nommage des "
                "fichiers exportes sont deja definis.",
                level="warning",
            )
        )

        box = QGroupBox("Parametres du rapport")
        outer = QVBoxLayout(box)
        form = QFormLayout()
        form.setContentsMargins(10, 6, 10, 6)

        self._scope = QComboBox()
        self._scope.addItem("Entreprise (tous les conducteurs)", None)
        form.addRow("Perimetre", self._scope)

        self._format = QComboBox()
        for report_format in ReportFormat:
            self._format.addItem(report_format.label, report_format)
        form.addRow("Format", self._format)

        today = QDate.currentDate()
        self._start = QDateEdit(today.addDays(-30))
        self._start.setCalendarPopup(True)
        self._start.setDisplayFormat("dd/MM/yyyy")
        form.addRow("Debut de periode", self._start)

        self._end = QDateEdit(today)
        self._end.setCalendarPopup(True)
        self._end.setDisplayFormat("dd/MM/yyyy")
        form.addRow("Fin de periode", self._end)

        self._output = QLabel("-")
        self._output.setWordWrap(True)
        form.addRow("Fichier propose", self._output)
        outer.addLayout(form)

        actions = QHBoxLayout()
        actions.addStretch(1)
        preview_button = QPushButton("Calculer le nom du fichier")
        preview_button.clicked.connect(self._on_preview)
        actions.addWidget(preview_button)

        generate_button = QPushButton("Generer le rapport")
        generate_button.setObjectName("PrimaryButton")
        generate_button.clicked.connect(self._on_generate)
        actions.addWidget(generate_button)
        outer.addLayout(actions)

        self.content_layout.addWidget(box)
        self.content_layout.addStretch(1)

    def refresh(self) -> None:
        """Recharge la liste des conducteurs disponibles pour le perimetre."""
        drivers = self._drivers.list_drivers()
        previous = self._scope.currentData()
        self._scope.blockSignals(True)
        self._scope.clear()
        self._scope.addItem("Entreprise (tous les conducteurs)", None)
        for driver in drivers:
            self._scope.addItem(driver.display_name, driver.id)
        if previous is not None:
            index = self._scope.findData(previous)
            if index >= 0:
                self._scope.setCurrentIndex(index)
        self._scope.blockSignals(False)

    def _build_request(self) -> ReportRequest:
        """Construit la demande de rapport depuis le formulaire."""
        start = self._start.date().toPython()
        end = self._end.date().toPython()
        driver_id = self._scope.currentData()
        reference = utcnow()
        return ReportRequest(
            report_format=self._format.currentData(),
            period_start=reference.replace(
                year=start.year,
                month=start.month,
                day=start.day,
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            ),
            period_end=reference.replace(
                year=end.year,
                month=end.month,
                day=end.day,
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )
            + timedelta(days=1),
            driver_ids=(driver_id,) if driver_id is not None else (),
        )

    def _on_preview(self) -> None:
        """Affiche le chemin de sortie propose."""
        path = self._service.suggest_output_path(self._build_request())
        self._output.setText(str(path))
        self.notify(f"Fichier propose : {path.name}")

    def _on_generate(self) -> None:
        """Tente de generer le rapport ; l'indisponibilite est expliquee clairement."""
        try:
            self._service.generate(self._build_request())
        except Exception as exc:  # noqa: BLE001 - garde-fou d'interface
            show_error(self, exc, title="Generation du rapport")

"""Statistiques et controles de flotte.

Activite et distances cumulees, exports Excel, exces de vitesse, conduites sans
carte, continuite, delais de telechargement, conducteurs et vehicules inconnus. Le
resultat de chaque bouton s'affiche dans le tableau du bas et peut etre exporte.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from PySide6.QtCore import QDate, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDateEdit,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app import APP_NAME, __version__
from app.bootstrap import ApplicationContext
from app.reports.excel import write_excel
from app.reports.model import ReportTable
from app.services.fleet_report_service import FleetReportService
from app.ui.common.errors import show_error, show_information
from app.ui.common.page import Page
from app.ui.common.widgets import ReadOnlyTable

__all__ = ["FleetToolsPage"]


class FleetToolsPage(Page):
    """Statistiques, controles et exports de flotte."""

    title = "Statistiques et controles"
    subtitle = (
        "Cumuls d'activite et de distance, controles de continuite et de delais de "
        "telechargement, sur la periode choisie."
    )

    def __init__(self, context: ApplicationContext, parent: QWidget | None = None) -> None:
        self._service = FleetReportService(context.database, settings=context.settings)
        self._current: ReportTable | None = None
        super().__init__(context, parent)

    # ------------------------------------------------------------------ #
    # Construction
    # ------------------------------------------------------------------ #
    def build(self) -> None:
        """Construit la periode, la grille de boutons et le tableau de resultat."""
        period = QHBoxLayout()
        period.addWidget(QLabel("Periode du"))
        today = QDate.currentDate()
        self._start = QDateEdit(QDate(today.year(), today.month(), 1))
        self._end = QDateEdit(today)
        for widget in (self._start, self._end):
            widget.setCalendarPopup(True)
            widget.setDisplayFormat("dd/MM/yyyy")
        period.addWidget(self._start)
        period.addWidget(QLabel("au"))
        period.addWidget(self._end)
        period.addStretch(1)
        self.content_layout.addLayout(period)

        box = QGroupBox("Statistiques et controles")
        grid = QGridLayout(box)
        grid.setColumnStretch(3, 1)

        def button(label: str, handler: Callable[[], None]) -> QPushButton:
            widget = QPushButton(label)
            widget.clicked.connect(handler)
            return widget

        self._activity_daily = QCheckBox("Detail journalier")
        self._activity_daily.setChecked(True)
        self._minutes = QRadioButton("Heures, minutes")
        self._minutes.setChecked(True)
        self._centesimal = QRadioButton("Heures, centiemes")
        units = QButtonGroup(self)
        units.addButton(self._minutes)
        units.addButton(self._centesimal)
        grid.addWidget(button("Activite cumulee", self._on_activity), 0, 0)
        grid.addWidget(self._activity_daily, 0, 1)
        grid.addWidget(self._minutes, 0, 2)
        grid.addWidget(self._centesimal, 0, 3)

        self._driver_distance_daily = QCheckBox("Detail journalier")
        self._driver_distance_daily.setChecked(True)
        grid.addWidget(button("Distance cumulee conducteur", self._on_driver_distance), 1, 0)
        grid.addWidget(self._driver_distance_daily, 1, 1)

        self._vehicle_distance_daily = QCheckBox("Detail journalier")
        self._vehicle_distance_daily.setChecked(True)
        grid.addWidget(button("Distance cumulee vehicule", self._on_vehicle_distance), 2, 0)
        grid.addWidget(self._vehicle_distance_daily, 2, 1)

        grid.addWidget(button("Export Excel", self._on_export), 3, 0)
        grid.addWidget(button("Export Excel detaille", self._on_export_detailed), 4, 0)

        self._minimum_km = QSpinBox()
        self._minimum_km.setRange(0, 9999)
        self._minimum_km.setValue(2)
        self._minimum_km.setSuffix(" km")
        grid.addWidget(button("Exces de vitesse", self._on_speeding), 5, 0)
        grid.addWidget(button("Conduites sans carte de plus de", self._on_without_card), 5, 1)
        grid.addWidget(self._minimum_km, 5, 2)

        grid.addWidget(button("Export des anomalies", self._on_export_anomalies), 6, 0)
        grid.addWidget(button("Continuite conducteurs", self._on_driver_continuity), 6, 1)
        grid.addWidget(button("Continuite vehicules", self._on_vehicle_continuity), 6, 2)
        grid.addWidget(button("Delai archivage conducteurs", self._on_driver_delays), 7, 1)
        grid.addWidget(button("Delai archivage vehicules", self._on_vehicle_delays), 7, 2)
        grid.addWidget(button("Conducteurs inconnus", self._on_unknown_drivers), 8, 1)
        grid.addWidget(button("Vehicules inconnus", self._on_unknown_vehicles), 8, 2)
        self.content_layout.addWidget(box)

        result = QGroupBox("Resultat")
        layout = QVBoxLayout(result)
        self._result_title = QLabel("Choisissez une statistique ou un controle ci-dessus.")
        self._result_title.setObjectName("PageSubtitle")
        layout.addWidget(self._result_title)
        self._table = ReadOnlyTable(("",), sortable=False)
        self._table.setMinimumHeight(260)
        layout.addWidget(self._table)
        self._note = QLabel("")
        self._note.setWordWrap(True)
        self._note.setObjectName("PageSubtitle")
        layout.addWidget(self._note)
        actions = QHBoxLayout()
        actions.addStretch(1)
        self._export_result = QPushButton("Exporter ce resultat en Excel")
        self._export_result.setEnabled(False)
        self._export_result.clicked.connect(self._on_export_result)
        actions.addWidget(self._export_result)
        layout.addLayout(actions)
        self.content_layout.addWidget(result, stretch=1)

    def refresh(self) -> None:
        """Rien a recharger : chaque resultat est calcule a la demande."""

    # ------------------------------------------------------------------ #
    # Periode et affichage
    # ------------------------------------------------------------------ #
    def _period(self) -> tuple[datetime, datetime] | None:
        """Bornes UTC de la periode choisie, ou ``None`` si elle est inversee."""
        if self._start.date() > self._end.date():
            show_information(
                self, "La date de debut est posterieure a la date de fin.", title="Periode"
            )
            return None
        return self._service.local_day_bounds(
            self._start.date().toPython(), self._end.date().toPython()
        )

    def _show(self, compute: Callable[[datetime, datetime], ReportTable]) -> None:
        """Calcule un resultat sur la periode et l'affiche."""
        period = self._period()
        if period is None:
            return
        try:
            table = compute(*period)
        except Exception as exc:  # noqa: BLE001 - garde-fou d'interface
            show_error(self, exc, title="Statistiques")
            return
        self._current = table
        self._result_title.setText(f"{table.title} - {len(table.rows)} ligne(s)")
        self._table.setColumnCount(len(table.headers))
        self._table.setHorizontalHeaderLabels(list(table.headers))
        self._table.set_rows(table.rows)
        self._note.setText(table.note)
        self._export_result.setEnabled(True)
        self.notify(f"{table.title} : {len(table.rows)} ligne(s)")

    # ------------------------------------------------------------------ #
    # Actions
    # ------------------------------------------------------------------ #
    def _on_activity(self) -> None:
        self._show(
            lambda start, end: self._service.cumulative_activity(
                start,
                end,
                daily=self._activity_daily.isChecked(),
                centesimal=self._centesimal.isChecked(),
            )
        )

    def _on_driver_distance(self) -> None:
        self._show(
            lambda start, end: self._service.driver_distance(
                start, end, daily=self._driver_distance_daily.isChecked()
            )
        )

    def _on_vehicle_distance(self) -> None:
        self._show(
            lambda start, end: self._service.vehicle_distance(
                start, end, daily=self._vehicle_distance_daily.isChecked()
            )
        )

    def _on_speeding(self) -> None:
        self._show(self._service.speeding)

    def _on_without_card(self) -> None:
        self._show(
            lambda start, end: self._service.driving_without_card(
                start, end, minimum_km=self._minimum_km.value()
            )
        )

    def _on_driver_continuity(self) -> None:
        self._show(self._service.driver_continuity)

    def _on_vehicle_continuity(self) -> None:
        self._show(self._service.vehicle_continuity)

    def _on_driver_delays(self) -> None:
        self._show(lambda _start, _end: self._service.driver_download_delays())

    def _on_vehicle_delays(self) -> None:
        self._show(lambda _start, _end: self._service.vehicle_download_delays())

    def _on_unknown_drivers(self) -> None:
        self._show(lambda _start, _end: self._service.unknown_drivers())

    def _on_unknown_vehicles(self) -> None:
        self._show(self._service.unknown_vehicles)

    # ------------------------------------------------------------------ #
    # Exports
    # ------------------------------------------------------------------ #
    def _on_export(self) -> None:
        self._export("synthese", lambda start, end: (self._service.summary(start, end),))

    def _on_export_detailed(self) -> None:
        self._export("detaille", self._service.detailed_tables)

    def _on_export_anomalies(self) -> None:
        self._export(
            "anomalies",
            lambda start, end: self._service.anomaly_tables(
                start, end, minimum_km=self._minimum_km.value()
            ),
        )

    def _on_export_result(self) -> None:
        if self._current is not None:
            table = self._current
            self._export(table.title.lower().replace(" ", "-"), lambda _start, _end: (table,))

    def _export(
        self,
        name: str,
        compute: Callable[[datetime, datetime], tuple[ReportTable, ...]],
    ) -> None:
        """Ecrit un classeur Excel dans le repertoire des exports."""
        period = self._period()
        if period is None:
            return
        first = self._start.date().toString("yyyyMMdd")
        last = self._end.date().toString("yyyyMMdd")
        path = self.context.settings.exports_dir / f"flotte-{name}-{first}-{last}.xlsx"
        company = self.context.settings.company_name
        header = ", ".join(
            part
            for part in (
                f"{APP_NAME} {__version__}",
                f"flotte {company}".strip(),
                f"{self._start.date().toString('dd/MM/yyyy')} - "
                f"{self._end.date().toString('dd/MM/yyyy')}",
            )
        )
        try:
            write_excel(path, header, compute(*period))
        except Exception as exc:  # noqa: BLE001 - garde-fou d'interface
            show_error(self, exc, title="Export Excel")
            return
        self.notify(f"Export enregistre : {path.name}")
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))
        show_information(self, f"Export enregistre :\n{path}", title="Export Excel")

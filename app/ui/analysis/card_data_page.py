"""Donnees d'une carte conducteur : les six rubriques du rapport de carte.

Informations de la carte, evenements, periodes de travail journalieres, activites,
vehicules et pays, sur la periode choisie, avec export Excel, PDF ou CSV. Les
tableaux affiches sont ceux des exports : les chiffres sont identiques.
"""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.bootstrap import ApplicationContext
from app.reports.tables import ReportTable, card_report_tables
from app.services.card_report_service import CardReport, CardReportService
from app.services.driver_service import DriverService, DriverSummary
from app.services.report_service import ReportFormat, ReportRequest, ReportService
from app.ui.common.errors import show_error, show_information
from app.ui.common.page import Page
from app.ui.common.widgets import NoticeBanner, ReadOnlyTable

__all__ = ["CardDataPage"]


class CardDataPage(Page):
    """Rubriques du rapport de carte d'un conducteur."""

    title = "Donnees de la carte"
    subtitle = (
        "Informations, evenements, periodes de travail, activites, vehicules et pays "
        "decodes des cartes conducteur importees."
    )

    def __init__(self, context: ApplicationContext, parent: QWidget | None = None) -> None:
        self._drivers = DriverService(context.database)
        self._reports = CardReportService(context.database, settings=context.settings)
        self._exports = ReportService(context.database, settings=context.settings)
        self._driver_list: tuple[DriverSummary, ...] = ()
        self._report: CardReport | None = None
        super().__init__(context, parent)

    def build(self) -> None:
        """Construit la barre de selection, les onglets et les boutons d'export."""
        self._notice = NoticeBanner("", level="info")
        self._notice.setVisible(False)
        self.content_layout.addWidget(self._notice)

        filters = QHBoxLayout()
        filters.addWidget(QLabel("Conducteur"))
        self._driver_filter = QComboBox()
        self._driver_filter.setMinimumWidth(240)
        self._driver_filter.currentIndexChanged.connect(self._on_driver_changed)
        filters.addWidget(self._driver_filter)

        filters.addWidget(QLabel("Du"))
        today = QDate.currentDate()
        self._start = QDateEdit(QDate(today.year(), today.month(), 1))
        self._start.setCalendarPopup(True)
        self._start.setDisplayFormat("dd/MM/yyyy")
        filters.addWidget(self._start)
        filters.addWidget(QLabel("au"))
        self._end = QDateEdit(today)
        self._end.setCalendarPopup(True)
        self._end.setDisplayFormat("dd/MM/yyyy")
        filters.addWidget(self._end)

        show_button = QPushButton("Afficher")
        show_button.setObjectName("PrimaryButton")
        show_button.clicked.connect(self.safe_refresh)
        filters.addWidget(show_button)
        filters.addStretch(1)
        self.content_layout.addLayout(filters)

        self._tabs = QTabWidget()
        self._tables: list[tuple[ReadOnlyTable, QLabel]] = []
        self.content_layout.addWidget(self._tabs, stretch=1)

        actions = QHBoxLayout()
        actions.addStretch(1)
        for report_format in (ReportFormat.EXCEL, ReportFormat.PDF, ReportFormat.CSV):
            button = QPushButton(f"Exporter en {report_format.label}")
            button.clicked.connect(lambda _checked=False, value=report_format: self._export(value))
            actions.addWidget(button)
        self.content_layout.addLayout(actions)

    # ------------------------------------------------------------------ #
    # Chargement
    # ------------------------------------------------------------------ #
    def refresh(self) -> None:
        """Recharge les conducteurs et le rapport de la periode choisie."""
        self._reload_drivers()
        driver_id = self._driver_filter.currentData()
        if driver_id is None:
            self._report = None
            self._show_tables(())
            self._notice.set_text(
                "Aucun conducteur n'est enregistre. Inserez une carte conducteur dans le "
                "lecteur, ou importez un fichier .C1B."
            )
            self._notice.setVisible(True)
            return
        if self._start.date() > self._end.date():
            show_information(
                self,
                "La date de debut est posterieure a la date de fin.",
                title="Periode invalide",
            )
            return

        start, end = self._reports.local_day_bounds(
            self._start.date().toPython(), self._end.date().toPython()
        )
        self._report = self._reports.build(driver_id, period_start=start, period_end=end)
        self._show_tables(card_report_tables(self._report))
        messages = list(self._report.warnings)
        if self._report.files_count == 0:
            messages.append(
                "Aucun telechargement de carte n'est rattache a ce conducteur : seules les "
                "donnees saisies manuellement sont affichees."
            )
        self._notice.set_text(" ".join(messages))
        self._notice.setVisible(bool(messages))
        self.notify(
            f"{len(self._report.work_periods)} periode(s) de travail, "
            f"{len(self._report.activities)} activite(s) sur la periode"
        )

    def _reload_drivers(self) -> None:
        """Recharge la liste des conducteurs en conservant la selection."""
        drivers = self._drivers.list_drivers()
        if drivers == self._driver_list:
            return
        self._driver_list = drivers
        previous = self._driver_filter.currentData()
        self._driver_filter.blockSignals(True)
        self._driver_filter.clear()
        for driver in drivers:
            self._driver_filter.addItem(f"{driver.display_name} ({driver.card_number})", driver.id)
        if previous is not None:
            index = self._driver_filter.findData(previous)
            if index >= 0:
                self._driver_filter.setCurrentIndex(index)
        self._driver_filter.blockSignals(False)
        self._select_last_activity_month()

    def _on_driver_changed(self) -> None:
        """Place la periode sur le dernier mois d'activite du conducteur choisi."""
        self._select_last_activity_month()
        self.safe_refresh()

    def _select_last_activity_month(self) -> None:
        """Positionne la periode sur le mois de la derniere activite connue."""
        driver_id = self._driver_filter.currentData()
        summary = next((item for item in self._driver_list if item.id == driver_id), None)
        last: date | None = summary.last_activity_end if summary else None
        if last is None:
            return
        self._start.setDate(QDate(last.year, last.month, 1))
        self._end.setDate(QDate(last.year, last.month, last.day))

    def _show_tables(self, tables: tuple[ReportTable, ...]) -> None:
        """Affiche un onglet par rubrique."""
        while len(self._tables) < len(tables):
            holder = QWidget()
            layout = QVBoxLayout(holder)
            layout.setContentsMargins(4, 4, 4, 4)
            # Les rubriques sont deja ordonnees et certaines comportent des lignes
            # d'intitule ou de total : le tri par colonne les desorganiserait.
            table = ReadOnlyTable(("",), sortable=False)
            note = QLabel("")
            note.setWordWrap(True)
            note.setObjectName("PageSubtitle")
            layout.addWidget(table)
            layout.addWidget(note)
            self._tabs.addTab(holder, "")
            self._tables.append((table, note))
        for index, (widget, note) in enumerate(self._tables):
            visible = index < len(tables)
            self._tabs.setTabVisible(index, visible)
            if not visible:
                continue
            content = tables[index]
            self._tabs.setTabText(index, f"{content.title} ({len(content.rows)})")
            widget.setColumnCount(len(content.headers))
            widget.setHorizontalHeaderLabels(list(content.headers))
            widget.set_rows(content.rows)
            note.setText(content.note)
            note.setVisible(bool(content.note))

    # ------------------------------------------------------------------ #
    # Export
    # ------------------------------------------------------------------ #
    def _export(self, report_format: ReportFormat) -> None:
        """Exporte le rapport affiche dans le repertoire des exports."""
        driver_id = self._driver_filter.currentData()
        if driver_id is None or self._report is None:
            show_information(self, "Affichez d'abord le rapport d'un conducteur.", title="Export")
            return
        request = ReportRequest(
            report_format=report_format,
            period_start=self._report.period_start,
            period_end=self._report.period_end,
            driver_ids=(driver_id,),
        )
        try:
            path = self._exports.generate(request)
        except Exception as exc:  # noqa: BLE001 - garde-fou d'interface
            show_error(self, exc, title="Export du rapport")
            return
        self.notify(f"Rapport enregistre : {path.name}")
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))
        show_information(self, f"Rapport enregistre :\n{path}", title="Export du rapport")

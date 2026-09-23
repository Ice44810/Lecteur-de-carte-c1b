"""Frise des activites d'un conducteur.

Vue journaliere, hebdomadaire et mensuelle, avec filtres sur le conducteur et sur le
type d'activite. Les periodes **sans enregistrement** apparaissent explicitement comme
telles : elles ne sont jamais presentees comme du repos.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.bootstrap import ApplicationContext
from app.core.enums import ActivityType
from app.core.timeutils import format_duration, utcnow, week_bounds
from app.services.analysis_service import AnalysisService
from app.services.driver_service import DriverService, DriverSummary
from app.ui.common.page import Page
from app.ui.common.widgets import NoticeBanner, ReadOnlyTable

__all__ = ["ActivitiesPage"]

_VIEW_DAY = "Jour"
_VIEW_WEEK = "Semaine"
_VIEW_MONTH = "Mois"


class ActivitiesPage(Page):
    """Consultation des activites d'un conducteur."""

    title = "Activites"
    subtitle = (
        "Frise des activites enregistrees. Les periodes sans enregistrement sont "
        "signalees comme telles et ne sont pas assimilees a du repos."
    )

    def __init__(self, context: ApplicationContext, parent: QWidget | None = None) -> None:
        self._drivers = DriverService(context.database)
        self._analysis = AnalysisService(context.database)
        self._driver_list: tuple[DriverSummary, ...] = ()
        super().__init__(context, parent)

    def build(self) -> None:
        """Construit la barre de filtres, la frise et le bloc de totaux."""
        self._empty_notice = NoticeBanner(
            "Aucune activite n'est enregistree pour l'instant. Les activites seront "
            "alimentees par l'import de fichiers C1B et V1B (phases 3, 4 et 10)."
        )
        self.content_layout.addWidget(self._empty_notice)

        filters = QHBoxLayout()

        filters.addWidget(QLabel("Conducteur"))
        self._driver_filter = QComboBox()
        self._driver_filter.setMinimumWidth(220)
        self._driver_filter.currentIndexChanged.connect(self.safe_refresh)
        filters.addWidget(self._driver_filter)

        filters.addWidget(QLabel("Vue"))
        self._view_filter = QComboBox()
        self._view_filter.addItems([_VIEW_DAY, _VIEW_WEEK, _VIEW_MONTH])
        self._view_filter.currentIndexChanged.connect(self.safe_refresh)
        filters.addWidget(self._view_filter)

        filters.addWidget(QLabel("Date"))
        self._date_edit = QDateEdit()
        self._date_edit.setCalendarPopup(True)
        self._date_edit.setDisplayFormat("dd/MM/yyyy")
        self._date_edit.setDate(QDate.currentDate())
        self._date_edit.dateChanged.connect(self.safe_refresh)
        filters.addWidget(self._date_edit)

        filters.addWidget(QLabel("Activite"))
        self._type_filter = QComboBox()
        self._type_filter.addItem("Toutes", None)
        for activity_type in ActivityType:
            self._type_filter.addItem(activity_type.label, activity_type)
        self._type_filter.currentIndexChanged.connect(self.safe_refresh)
        filters.addWidget(self._type_filter)

        reload_button = QPushButton("Actualiser")
        reload_button.clicked.connect(self.safe_refresh)
        filters.addWidget(reload_button)
        filters.addStretch(1)
        self.content_layout.addLayout(filters)

        self._table = ReadOnlyTable(("Jour", "Plage horaire", "Activite", "Duree"))
        self.content_layout.addWidget(self._table)

        self._totals_box = QGroupBox("Totaux de la periode")
        totals_layout = QVBoxLayout(self._totals_box)
        totals_layout.setContentsMargins(10, 6, 10, 10)
        self._totals_label = QLabel("-")
        self._totals_label.setWordWrap(True)
        totals_layout.addWidget(self._totals_label)
        self.content_layout.addWidget(self._totals_box)

    def refresh(self) -> None:
        """Recharge la liste des conducteurs, la frise et les totaux."""
        self._reload_drivers()

        driver_id = self._driver_filter.currentData()
        if driver_id is None:
            self._table.set_rows(())
            self._totals_label.setText("Selectionnez un conducteur pour afficher ses activites.")
            return

        period_start, period_end = self._current_period()
        selected_type = self._type_filter.currentData()

        entries = []
        cursor = period_start
        while cursor < period_end:
            day_entries = self._analysis.daily_timeline(
                driver_id,
                cursor.date(),
                activity_types=(selected_type,) if selected_type is not None else None,
            )
            entries.extend(day_entries)
            cursor += timedelta(days=1)

        self._table.set_rows(
            tuple(
                (
                    entry.start.strftime("%d/%m/%Y"),
                    entry.time_range,
                    entry.label,
                    entry.duration_label,
                )
                for entry in entries
            )
        )

        analysis = self._analysis.analyze_period(
            driver_id, period_start=period_start, period_end=period_end
        )
        self._totals_label.setText(
            " | ".join(
                (
                    f"Conduite : {format_duration(analysis.driving_seconds)}",
                    f"Travail : {format_duration(analysis.working_seconds)}",
                    f"Disponibilite : {format_duration(analysis.availability_seconds)}",
                    f"Repos : {format_duration(analysis.rest_seconds)}",
                    f"Activites : {analysis.activities_count}",
                )
            )
            + (
                f"\n{len(analysis.gaps)} periode(s) sans enregistrement sur l'intervalle."
                if analysis.gaps
                else ""
            )
        )
        self._empty_notice.setVisible(not analysis.has_data)
        self.notify(analysis.summary_message())

    def _reload_drivers(self) -> None:
        """Recharge la liste deroulante des conducteurs en conservant la selection."""
        drivers = self._drivers.list_drivers()
        if drivers == self._driver_list:
            return
        self._driver_list = drivers

        previous = self._driver_filter.currentData()
        self._driver_filter.blockSignals(True)
        self._driver_filter.clear()
        if not drivers:
            self._driver_filter.addItem("Aucun conducteur", None)
        for driver in drivers:
            self._driver_filter.addItem(driver.display_name, driver.id)
        if previous is not None:
            index = self._driver_filter.findData(previous)
            if index >= 0:
                self._driver_filter.setCurrentIndex(index)
        self._driver_filter.blockSignals(False)

    def _current_period(self) -> tuple[datetime, datetime]:
        """Retourne les bornes de la periode correspondant a la vue choisie."""
        selected: date = self._date_edit.date().toPython()
        reference = datetime(selected.year, selected.month, selected.day, tzinfo=UTC)
        view = self._view_filter.currentText()

        if view == _VIEW_DAY:
            return reference, reference + timedelta(days=1)
        if view == _VIEW_WEEK:
            return week_bounds(reference)
        start = reference.replace(day=1)
        end = (
            start.replace(year=start.year + 1, month=1)
            if start.month == 12
            else start.replace(month=start.month + 1)
        )
        return start, end

    @staticmethod
    def _today() -> date:
        """Retourne la date du jour en UTC."""
        return utcnow().date()

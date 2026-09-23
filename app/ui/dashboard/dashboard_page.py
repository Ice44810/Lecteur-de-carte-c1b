"""Tableau de bord.

Toutes les valeurs affichees proviennent de :class:`DashboardService`, donc de la base.
Aucun chiffre n'est ecrit en dur. Lorsque la base est vide, la page l'indique
explicitement plutot que d'afficher des zeros sans explication.
"""

from __future__ import annotations

from PySide6.QtWidgets import QGridLayout, QGroupBox, QVBoxLayout, QWidget

from app.bootstrap import ApplicationContext
from app.services.dashboard_service import DashboardService
from app.ui.common.page import Page
from app.ui.common.widgets import IndicatorCard, NoticeBanner, ReadOnlyTable

__all__ = ["DashboardPage"]


class DashboardPage(Page):
    """Page d'accueil presentant les indicateurs de l'entreprise."""

    title = "Tableau de bord"
    subtitle = "Synthese de l'activite tachygraphique de l'entreprise."

    def __init__(self, context: ApplicationContext, parent: QWidget | None = None) -> None:
        self._service = DashboardService(context.database)
        super().__init__(context, parent)

    def build(self) -> None:
        """Construit les cartes d'indicateurs et les tableaux de synthese."""
        self._notice = NoticeBanner("", level="warning")
        self._notice.setVisible(False)
        self.content_layout.addWidget(self._notice)

        indicators = QGridLayout()
        indicators.setSpacing(12)

        self._drivers_card = IndicatorCard("Conducteurs suivis")
        self._files_card = IndicatorCard("Cartes importees")
        self._alerts_card = IndicatorCard("Situations a verifier")
        self._last_download_card = IndicatorCard("Dernier telechargement")
        self._driving_card = IndicatorCard("Conduite (semaine)")
        self._rest_card = IndicatorCard("Repos (semaine)")

        for column, card in enumerate(
            (self._drivers_card, self._files_card, self._alerts_card)
        ):
            indicators.addWidget(card, 0, column)
        for column, card in enumerate(
            (self._last_download_card, self._driving_card, self._rest_card)
        ):
            indicators.addWidget(card, 1, column)

        self.content_layout.addLayout(indicators)

        self._activity_table = ReadOnlyTable(
            ("Conducteur", "Journee", "Plage de service", "Conduite")
        )
        self._activity_table.setMinimumHeight(140)
        self.content_layout.addWidget(self._wrap("Activite recente", self._activity_table))

        self._alerts_table = ReadOnlyTable(
            ("Conducteur", "Jour", "Situation", "Statut", "Criticite")
        )
        self._alerts_table.setMinimumHeight(140)
        self.content_layout.addWidget(self._wrap("Alertes", self._alerts_table))

    def refresh(self) -> None:
        """Recharge les indicateurs depuis la base."""
        data = self._service.load()

        self._drivers_card.set_value(
            str(data.drivers_count),
            f"{data.active_drivers_this_week} actif(s) cette semaine",
        )
        self._files_card.set_value(
            str(data.files_count),
            f"{data.c1b_count} C1B / {data.v1b_count} V1B"
            + (
                f" - {data.pending_parsing_count} en attente de decodage"
                if data.pending_parsing_count
                else ""
            ),
        )
        self._alerts_card.set_value(
            str(data.open_alerts_count),
            "Situations non encore verifiees"
            if data.open_alerts_count
            else "Aucune verification en attente",
        )
        self._last_download_card.set_value(data.last_import_label)
        self._driving_card.set_value(data.week_driving_label, "Semaine en cours (lundi a lundi)")
        self._rest_card.set_value(data.week_rest_label, "Semaine en cours (lundi a lundi)")

        self._activity_table.set_rows(
            tuple(
                (line.driver_display_name, line.day_label, line.time_range, line.driving_label)
                for line in data.recent_activity
            )
        )
        self._alerts_table.set_rows(
            tuple(
                (
                    line.driver_display_name,
                    line.occurred_on_label,
                    line.description,
                    line.status_label,
                    line.severity_label,
                )
                for line in data.alerts
            )
        )

        self._update_notice(data)
        self.notify(
            f"Tableau de bord actualise - {data.drivers_count} conducteur(s), "
            f"{data.files_count} fichier(s) importe(s)"
        )

    def _update_notice(self, data: object) -> None:
        """Affiche le bandeau explicatif adapte a l'etat de la base."""
        messages: list[str] = []
        if getattr(data, "is_empty", False):
            messages.append(
                "Aucune donnee n'a encore ete importee. Commencez par creer vos "
                "conducteurs, ou importez un fichier depuis la page Imports."
            )
        notice = getattr(data, "rules_notice", None)
        if notice:
            messages.append(notice)

        if messages:
            self._notice.set_text("\n\n".join(messages))
            self._notice.setVisible(True)
        else:
            self._notice.setVisible(False)

    @staticmethod
    def _wrap(title: str, widget: QWidget) -> QGroupBox:
        """Place un widget dans un cadre titre."""
        box = QGroupBox(title)
        layout = QVBoxLayout(box)
        layout.setContentsMargins(10, 6, 10, 10)
        layout.addWidget(widget)
        return box

"""Anomalies et depassements apparents.

La page affiche l'etat du moteur de regles avant d'afficher des resultats : tant
qu'aucune regle verifiee n'est active, l'utilisateur doit savoir qu'aucun controle
reglementaire n'est effectue, plutot que d'interpreter une liste vide comme une absence
d'anomalie.
"""

from __future__ import annotations

from PySide6.QtWidgets import QGroupBox, QVBoxLayout, QWidget

from app.analysis.rules import RULE_CATALOGUE, default_registry, empty_ruleset
from app.bootstrap import ApplicationContext
from app.database.repositories import InfringementRepository
from app.ui.common.page import Page
from app.ui.common.widgets import NoticeBanner, ReadOnlyTable

__all__ = ["AnomaliesPage"]


class AnomaliesPage(Page):
    """Liste des situations a verifier et etat du moteur de regles."""

    title = "Anomalies et depassements apparents"
    subtitle = (
        "L'application signale des situations a verifier. Elle ne qualifie pas "
        "juridiquement une infraction : seule une autorite de controle peut le faire."
    )

    def __init__(self, context: ApplicationContext, parent: QWidget | None = None) -> None:
        self._registry = default_registry()
        self._ruleset = empty_ruleset()
        super().__init__(context, parent)

    def build(self) -> None:
        """Construit le bandeau d'etat, la liste des alertes et le catalogue de regles."""
        self._state_notice = NoticeBanner("", level="warning")
        self.content_layout.addWidget(self._state_notice)

        self._alerts_table = ReadOnlyTable(
            (
                "Jour",
                "Conducteur",
                "Regle",
                "Statut",
                "Criticite",
                "Mesure",
                "Seuil",
                "Source du seuil",
            )
        )
        self.content_layout.addWidget(
            self._wrap("Situations detectees", self._alerts_table, stretch=2)
        )

        self._catalogue_table = ReadOnlyTable(
            ("Code", "Regle", "Texte de reference a verifier", "Etat")
        )
        self._catalogue_table.set_rows(
            tuple(
                (
                    planned.code,
                    planned.title,
                    planned.reference_to_verify,
                    planned.status.label,
                )
                for planned in RULE_CATALOGUE
            )
        )
        self.content_layout.addWidget(
            self._wrap("Regles prevues et sources a verifier", self._catalogue_table, stretch=3)
        )

    def refresh(self) -> None:
        """Recharge les alertes enregistrees et l'etat du moteur de regles."""
        with self.context.database.session() as session:
            infringements = InfringementRepository(session).list_recent(limit=200)
            rows = tuple(
                (
                    item.occurred_on.strftime("%d/%m/%Y"),
                    item.driver.display_name,
                    item.rule_code,
                    item.status.label,
                    item.severity.label,
                    self._format_value(item.measured_value, item.unit),
                    self._format_value(item.allowed_value, item.unit),
                    item.regulation_reference or "-",
                )
                for item in infringements
            )

        self._alerts_table.set_rows(rows)

        active = len(self._registry)
        usable = len(self._ruleset.usable_parameters)
        if active == 0:
            self._state_notice.set_text(
                "Aucune regle reglementaire n'est active dans cette version. Les temps de "
                "conduite, de travail et de repos sont calcules et consultables, mais "
                f"aucun depassement n'est recherche. Les {len(RULE_CATALOGUE)} regles "
                "prevues sont listees ci-dessous avec le texte a consulter : une regle ne "
                "sera activee qu'apres verification de son seuil face a sa source."
            )
        else:
            self._state_notice.set_text(
                f"{active} regle(s) active(s), {usable} seuil(s) verifie(s) "
                f"(jeu de regles {self._ruleset.version})."
            )

        self.notify(f"{len(rows)} situation(s) enregistree(s) - {active} regle(s) active(s)")

    @staticmethod
    def _format_value(value: float | None, unit: str) -> str:
        """Formate une valeur mesuree ou un seuil selon son unite."""
        if value is None:
            return "-"
        if unit == "seconds":
            from app.core.timeutils import format_duration

            return format_duration(int(value))
        return f"{value:g} {unit}"

    @staticmethod
    def _wrap(title: str, widget: QWidget, *, stretch: int = 1) -> QGroupBox:
        """Place un widget dans un cadre titre."""
        box = QGroupBox(title)
        layout = QVBoxLayout(box)
        layout.setContentsMargins(10, 6, 10, 10)
        layout.addWidget(widget, stretch=stretch)
        return box

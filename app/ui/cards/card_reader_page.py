"""Page « Lecteur de carte ».

Cette page est pleinement operationnelle pour ce qui concerne le **diagnostic** :
detection des lecteurs, etat du service PC/SC, presence d'une carte, et affichage d'une
cause et d'une action pour chaque situation d'erreur (section 16 du cahier des charges).

Le telechargement du contenu de la carte, en revanche, n'est pas disponible : la
sequence de commandes propre aux cartes tachygraphiques n'a pas ete confirmee a partir
d'une source officielle. La page l'indique explicitement et enumere les points a lever.
"""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from app.card_reader import CardDetector, TachographCard, create_reader, pcsc_diagnostics
from app.parser.specification import questions_for
from app.ui.common.errors import show_error
from app.ui.common.page import Page
from app.ui.common.widgets import NoticeBanner, ReadOnlyTable

__all__ = ["CardReaderPage"]

POLL_INTERVAL_MS = 2000
"""Periode d'interrogation du lecteur, en millisecondes."""


class CardReaderPage(Page):
    """Diagnostic du lecteur et etat de la carte inseree."""

    title = "Lecteur de carte"
    subtitle = (
        "Etat du service PC/SC, lecteurs detectes et carte inseree. "
        "Le service pcscd doit etre installe et actif."
    )

    def build(self) -> None:
        """Construit le bloc de diagnostic, la liste des lecteurs et les actions."""
        self._reader = create_reader()
        self._detector = CardDetector(self._reader)
        self._timer = QTimer(self)
        self._timer.setInterval(POLL_INTERVAL_MS)
        self._timer.timeout.connect(self._poll)

        self._diagnostic_notice = NoticeBanner("", level="warning")
        self.content_layout.addWidget(self._diagnostic_notice)

        status_box = QGroupBox("Etat courant")
        status_layout = QFormLayout(status_box)
        status_layout.setContentsMargins(10, 6, 10, 10)

        self._status_value = QLabel("-")
        self._reader_value = QLabel("-")
        self._atr_value = QLabel("-")
        self._cause_value = QLabel("-")
        self._cause_value.setWordWrap(True)
        self._action_value = QLabel("-")
        self._action_value.setWordWrap(True)

        status_layout.addRow("Etat", self._status_value)
        status_layout.addRow("Lecteur", self._reader_value)
        status_layout.addRow("ATR de la carte", self._atr_value)
        status_layout.addRow("Cause", self._cause_value)
        status_layout.addRow("Action", self._action_value)
        self.content_layout.addWidget(status_box)

        self._readers_table = ReadOnlyTable(("#", "Lecteur detecte"))
        self._readers_table.setMaximumHeight(120)
        readers_box = QGroupBox("Lecteurs disponibles")
        readers_layout = QVBoxLayout(readers_box)
        readers_layout.setContentsMargins(10, 6, 10, 10)
        readers_layout.addWidget(self._readers_table)
        self.content_layout.addWidget(readers_box)

        self._questions_table = ReadOnlyTable(("Point a confirmer", "Reference a consulter"))
        self._questions_table.set_rows(
            tuple((question.code, question.reference) for question in questions_for("card"))
        )
        questions_box = QGroupBox("Points a confirmer avant la lecture de carte")
        questions_layout = QVBoxLayout(questions_box)
        questions_layout.setContentsMargins(10, 6, 10, 10)
        questions_layout.addWidget(self._questions_table)
        self.content_layout.addWidget(questions_box)

        actions = QHBoxLayout()
        actions.addStretch(1)
        refresh_button = QPushButton("Rafraichir le diagnostic")
        refresh_button.clicked.connect(self.safe_refresh)
        actions.addWidget(refresh_button)

        self._download_button = QPushButton("Telecharger la carte")
        self._download_button.setObjectName("PrimaryButton")
        self._download_button.clicked.connect(self._on_download)
        actions.addWidget(self._download_button)
        self.content_layout.addLayout(actions)
        self.content_layout.addStretch(1)

    def refresh(self) -> None:
        """Recharge le diagnostic et demarre l'interrogation periodique."""
        self._poll()
        if self.context.settings.pcsc_enabled and not self._timer.isActive():
            self._timer.start()

    def hideEvent(self, event: object) -> None:  # noqa: N802 - signature Qt
        """Arrete l'interrogation periodique lorsque la page n'est plus visible."""
        self._timer.stop()
        super().hideEvent(event)  # type: ignore[arg-type]

    def _poll(self) -> None:
        """Interroge le lecteur et met a jour l'affichage."""
        available, cause, action = pcsc_diagnostics()
        events = self._detector.refresh()
        presence = self._detector.current

        if presence is not None:
            self._status_value.setText(presence.status.label)
            self._reader_value.setText(
                presence.reader.display_name if presence.reader is not None else "-"
            )
            self._atr_value.setText(presence.atr or "-")
            self._download_button.setEnabled(presence.status.is_ready_to_read)
        else:  # pragma: no cover - premier appel toujours renseigne
            self._download_button.setEnabled(False)

        self._cause_value.setText(cause or "-")
        self._action_value.setText(action or "Aucune action requise.")

        try:
            readers = self._reader.list_readers()
        except Exception:  # noqa: BLE001 - l'indisponibilite est deja diagnostiquee
            readers = ()
        self._readers_table.set_rows(
            tuple((str(item.index), item.display_name) for item in readers)
        )

        self._diagnostic_notice.set_text(
            "Le telechargement direct de la carte n'est pas disponible dans cette version : "
            "la sequence de commandes propre aux cartes tachygraphiques doit d'abord etre "
            "confirmee a partir de la specification officielle (points listes ci-dessous). "
            "Le diagnostic du lecteur, lui, est operationnel."
            if available
            else (f"{cause} {action}")
        )

        for event in events:
            self.notify(event.message)

    def _on_download(self) -> None:
        """Tente un telechargement ; l'indisponibilite est expliquee proprement."""
        card = TachographCard(self._reader)
        try:
            card.download()
        except Exception as exc:  # noqa: BLE001 - garde-fou d'interface
            show_error(self, exc, title="Telechargement de la carte")

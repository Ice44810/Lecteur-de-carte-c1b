"""Page « Lecteur de carte ».

Diagnostic du lecteur (etat du service PC/SC, lecteurs detectes, carte inseree) et
telechargement de la carte conducteur. Le telechargement est declenche
automatiquement a l'insertion de la carte par le surveillant de la fenetre
principale (:class:`~app.ui.cards.card_watcher.CardWatcher`) ; le bouton
« Telecharger la carte » permet de le relancer manuellement.
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

from app.card_reader import CardDetector, create_reader, pcsc_diagnostics
from app.card_reader.interface import CardPresence
from app.config.logging_config import get_logger
from app.parser.specification import questions_for
from app.services.card_service import CardDownloadService
from app.ui.cards.card_watcher import POLL_INTERVAL_MS, CardWatcher
from app.ui.common.errors import show_error, show_information
from app.ui.common.page import Page
from app.ui.common.widgets import NoticeBanner, ReadOnlyTable

__all__ = ["CardReaderPage"]

logger = get_logger(__name__)


class CardReaderPage(Page):
    """Diagnostic du lecteur, etat de la carte et telechargement."""

    title = "Lecteur de carte"
    subtitle = (
        "Etat du service PC/SC, lecteurs detectes et carte inseree. Une carte conducteur "
        "inseree est telechargee et archivee automatiquement."
    )

    def build(self) -> None:
        """Construit le bloc de diagnostic, la liste des lecteurs et les actions."""
        self._watcher: CardWatcher | None = None
        self._local_reader = None
        self._local_detector: CardDetector | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(POLL_INTERVAL_MS)
        self._timer.timeout.connect(self._background_poll)

        self._diagnostic_notice = NoticeBanner("", level="info")
        self.content_layout.addWidget(self._diagnostic_notice)

        status_box = QGroupBox("Etat courant")
        status_layout = QFormLayout(status_box)
        status_layout.setContentsMargins(10, 6, 10, 10)

        self._status_value = QLabel("-")
        self._reader_value = QLabel("-")
        self._atr_value = QLabel("-")
        self._auto_value = QLabel("-")
        self._download_value = QLabel("Aucun telechargement pendant cette session")
        self._download_value.setWordWrap(True)
        self._cause_value = QLabel("-")
        self._cause_value.setWordWrap(True)
        self._action_value = QLabel("-")
        self._action_value.setWordWrap(True)

        status_layout.addRow("Etat", self._status_value)
        status_layout.addRow("Lecteur", self._reader_value)
        status_layout.addRow("ATR de la carte", self._atr_value)
        status_layout.addRow("Telechargement automatique", self._auto_value)
        status_layout.addRow("Dernier telechargement", self._download_value)
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

        self._questions_table = ReadOnlyTable(("Point de specification", "Reference", "Etat"))
        self._questions_table.set_rows(
            tuple(
                (question.code, question.reference, question.status.label)
                for question in questions_for("card")
            )
        )
        questions_box = QGroupBox("Sources de la sequence de lecture")
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

    # ------------------------------------------------------------------ #
    # Rafraichissement
    # ------------------------------------------------------------------ #
    def refresh(self) -> None:
        """Recharge le diagnostic.

        Le surveillant de la fenetre principale est utilise s'il existe ; sinon la
        page interroge elle-meme le lecteur tant qu'elle est affichee. Lorsque le
        lecteur est desactive (``TACHOLIBRE_PCSC_ENABLED=false``), la pile PC/SC n'est
        pas interrogee du tout.
        """
        if not self.context.settings.pcsc_enabled:
            self._timer.stop()
            self._show_disabled()
            return

        self._auto_value.setText(
            "Active : une carte inseree est telechargee et archivee"
            if self.context.settings.card_auto_download
            else "Desactive (TACHOLIBRE_CARD_AUTO_DOWNLOAD=false) : utilisez le bouton"
        )
        watcher = self._find_watcher()
        if watcher is not None:
            self._show_presence(watcher.presence)
            self._update_diagnostic()
            return

        self._poll_locally()
        if not self._timer.isActive():
            self._timer.start()

    def hideEvent(self, event: object) -> None:  # noqa: N802 - signature Qt
        """Arrete l'interrogation locale lorsque la page n'est plus visible."""
        self._timer.stop()
        super().hideEvent(event)  # type: ignore[arg-type]

    def _find_watcher(self) -> CardWatcher | None:
        """Retrouve le surveillant de la fenetre principale et s'y abonne une fois."""
        if self._watcher is not None:
            return self._watcher
        watcher = getattr(self.window(), "card_watcher", None)
        if not isinstance(watcher, CardWatcher):
            return None
        self._watcher = watcher
        watcher.presence_changed.connect(self._on_presence_changed)
        watcher.download_started.connect(self._on_download_started)
        watcher.download_finished.connect(self._on_download_finished)
        watcher.download_failed.connect(self._on_download_failed)
        return watcher

    def _poll_locally(self) -> None:
        """Interroge le lecteur sans surveillant (page ouverte seule)."""
        if self._local_detector is None:
            self._local_reader = create_reader()
            self._local_detector = CardDetector(self._local_reader)
        events = self._local_detector.refresh()
        self._show_presence(self._local_detector.current)
        self._update_diagnostic()
        for event in events:
            self.notify(event.message)

    def _background_poll(self) -> None:
        """Interrogation periodique : une erreur est journalisee, jamais affichee en boucle."""
        try:
            self._poll_locally()
        except Exception as exc:  # noqa: BLE001 - garde-fou du minuteur
            logger.exception("Interrogation du lecteur de carte en echec")
            self._timer.stop()
            self._status_value.setText("Diagnostic interrompu")
            self._cause_value.setText(str(exc) or type(exc).__name__)
            self._action_value.setText(
                "Cliquez sur « Rafraichir le diagnostic ». Le detail figure dans le journal."
            )

    # ------------------------------------------------------------------ #
    # Affichage
    # ------------------------------------------------------------------ #
    def _show_presence(self, presence: CardPresence | None) -> None:
        """Affiche l'etat du lecteur et de la carte."""
        busy = self._watcher is not None and self._watcher.is_busy
        if presence is None:
            self._status_value.setText("-")
            self._reader_value.setText("-")
            self._atr_value.setText("-")
            self._download_button.setEnabled(False)
            return
        self._status_value.setText("Telechargement en cours..." if busy else presence.status.label)
        self._reader_value.setText(
            presence.reader.display_name if presence.reader is not None else "-"
        )
        self._atr_value.setText(presence.atr or "-")
        self._download_button.setEnabled(presence.status.is_ready_to_read and not busy)

    def _update_diagnostic(self) -> None:
        """Met a jour la cause, l'action et la liste des lecteurs."""
        available, cause, action = pcsc_diagnostics()
        self._cause_value.setText(cause or "-")
        self._action_value.setText(action or "Aucune action requise.")

        reader = self._watcher.reader if self._watcher is not None else self._local_reader
        try:
            readers = reader.list_readers() if reader is not None else ()
        except Exception:  # noqa: BLE001 - l'indisponibilite est deja diagnostiquee
            readers = ()
        self._readers_table.set_rows(
            tuple((str(item.index), item.display_name) for item in readers)
        )

        self._diagnostic_notice.set_text(
            "Inserez une carte conducteur : elle est lue en lecture seule (aucune donnee "
            "n'est ecrite sur la carte), puis le fichier .C1B obtenu est archive et "
            "inscrit dans l'historique des telechargements. Le decodage de son contenu "
            "n'est pas encore disponible."
            if available
            else f"{cause} {action}"
        )

    def _show_disabled(self) -> None:
        """Affiche l'etat d'un lecteur desactive par la configuration."""
        self._status_value.setText("Lecteur desactive")
        self._reader_value.setText("-")
        self._atr_value.setText("-")
        self._auto_value.setText("-")
        self._cause_value.setText(
            "L'usage du lecteur de carte est desactive dans la configuration."
        )
        self._action_value.setText(
            "Pour l'activer, positionnez TACHOLIBRE_PCSC_ENABLED=true puis relancez l'application."
        )
        self._readers_table.set_rows(())
        self._download_button.setEnabled(False)
        self._diagnostic_notice.set_text(
            "Le lecteur de carte est desactive (TACHOLIBRE_PCSC_ENABLED=false) : aucun "
            "diagnostic PC/SC n'est effectue."
        )

    # ------------------------------------------------------------------ #
    # Evenements du surveillant
    # ------------------------------------------------------------------ #
    def _on_presence_changed(self, presence: object) -> None:
        """Met a jour l'affichage lorsque l'etat du lecteur change."""
        if isinstance(presence, CardPresence):
            self._show_presence(presence)

    def _on_download_started(self) -> None:
        """Signale un telechargement en cours."""
        self._status_value.setText("Telechargement en cours...")
        self._download_value.setText("Lecture de la carte en cours, ne la retirez pas.")
        self._download_button.setEnabled(False)

    def _on_download_finished(self, result: object) -> None:
        """Affiche le resultat d'un telechargement reussi."""
        summary = getattr(result, "summary", None)
        self._download_value.setText(summary() if callable(summary) else "Termine.")
        if self._watcher is not None:
            self._show_presence(self._watcher.presence)

    def _on_download_failed(self, error: object) -> None:
        """Affiche l'echec d'un telechargement (le detail est presente par la fenetre)."""
        message = getattr(error, "message", None) or str(error)
        self._download_value.setText(f"Echec : {message}")
        if self._watcher is not None:
            self._show_presence(self._watcher.presence)

    # ------------------------------------------------------------------ #
    # Action manuelle
    # ------------------------------------------------------------------ #
    def _on_download(self) -> None:
        """Lance le telechargement de la carte inseree."""
        if self._watcher is not None:
            if not self._watcher.download():
                self.notify("Un telechargement est deja en cours")
            return

        # Sans surveillant (page ouverte seule) : telechargement direct.
        if self._local_reader is None:
            self._local_reader = create_reader()
        service = CardDownloadService(self.context.database, settings=self.context.settings)
        try:
            result = service.download_and_import(self._local_reader)
        except Exception as exc:  # noqa: BLE001 - garde-fou d'interface
            self._on_download_failed(exc)
            show_error(self, exc, title="Telechargement de la carte")
            return
        self._on_download_finished(result)
        show_information(self, result.summary(), title="Telechargement de la carte")

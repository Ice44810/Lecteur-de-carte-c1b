"""Surveillance du lecteur et telechargement automatique des cartes.

Le surveillant interroge le lecteur a intervalle regulier pendant toute la session,
quelle que soit la page affichee. Lorsqu'une carte est inseree, et si
``TACHOLIBRE_CARD_AUTO_DOWNLOAD`` est actif, il lance le telechargement puis l'import en
tache de fond : l'interface reste utilisable pendant la lecture, qui peut durer
plusieurs dizaines de secondes.

Toute la logique metier est dans :class:`~app.services.card_service.CardDownloadService` ;
ce module ne fait qu'orchestrer le rythme et les fils d'execution.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal

from app.bootstrap import ApplicationContext
from app.card_reader import CardDetector, CardEventType, CardReaderInterface, create_reader
from app.card_reader.interface import CardPresence
from app.config.logging_config import get_logger
from app.services.card_service import CardDownloadService

__all__ = ["CardWatcher", "POLL_INTERVAL_MS"]

logger = get_logger(__name__)

POLL_INTERVAL_MS = 2000
"""Periode d'interrogation du lecteur, en millisecondes."""


class _DownloadSignals(QObject):
    """Signaux emis par la tache de telechargement vers le fil de l'interface."""

    finished = Signal(object)
    failed = Signal(object)


class _DownloadTask(QRunnable):
    """Telechargement et import d'une carte, execute hors du fil de l'interface."""

    def __init__(self, service: CardDownloadService, reader: CardReaderInterface) -> None:
        super().__init__()
        self.signals = _DownloadSignals()
        self._service = service
        self._reader = reader

    def run(self) -> None:
        """Execute le telechargement et transmet le resultat ou l'erreur."""
        try:
            result = self._service.download_and_import(self._reader)
        except Exception as exc:  # noqa: BLE001 - toute erreur est remontee a l'interface
            logger.exception("Telechargement de la carte en echec")
            self.signals.failed.emit(exc)
            return
        self.signals.finished.emit(result)


class CardWatcher(QObject):
    """Surveille le lecteur et telecharge les cartes inserees.

    Args:
        context: Contexte applicatif (configuration et base).
        reader: Lecteur a surveiller ; par defaut, celui fourni par
            :func:`app.card_reader.create_reader`.
        parent: Objet parent Qt.

    Signals:
        presence_changed: Nouvel etat du lecteur (:class:`CardPresence`).
        event_message: Message court a afficher dans la barre d'etat.
        download_started: Un telechargement commence.
        download_finished: Telechargement et import termines
            (:class:`~app.services.card_service.CardImportResult`).
        download_failed: Le telechargement a echoue (exception).
    """

    presence_changed = Signal(object)
    event_message = Signal(str)
    download_started = Signal()
    download_finished = Signal(object)
    download_failed = Signal(object)

    def __init__(
        self,
        context: ApplicationContext,
        *,
        reader: CardReaderInterface | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = context.settings
        self._reader = reader if reader is not None else create_reader()
        self._detector = CardDetector(self._reader)
        self._service = CardDownloadService(context.database, settings=context.settings)
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self._busy = False
        self._task: _DownloadTask | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(POLL_INTERVAL_MS)
        self._timer.timeout.connect(self.poll)

    # ------------------------------------------------------------------ #
    # Etat
    # ------------------------------------------------------------------ #
    @property
    def reader(self) -> CardReaderInterface:
        """Lecteur surveille."""
        return self._reader

    @property
    def presence(self) -> CardPresence | None:
        """Dernier etat observe, ou ``None`` avant la premiere interrogation."""
        return self._detector.current

    @property
    def is_busy(self) -> bool:
        """Indique qu'un telechargement est en cours."""
        return self._busy

    @property
    def auto_download(self) -> bool:
        """Indique que le telechargement suit automatiquement l'insertion."""
        return self._settings.card_auto_download

    # ------------------------------------------------------------------ #
    # Cycle de vie
    # ------------------------------------------------------------------ #
    def start(self) -> None:
        """Demarre la surveillance (sans effet si le lecteur est desactive)."""
        if not self._settings.pcsc_enabled:
            logger.info("Lecteur de carte desactive par la configuration")
            return
        self.poll()
        self._timer.start()

    def stop(self) -> None:
        """Arrete la surveillance et attend la fin d'un telechargement en cours."""
        self._timer.stop()
        self._pool.waitForDone()

    # ------------------------------------------------------------------ #
    # Surveillance
    # ------------------------------------------------------------------ #
    def poll(self) -> None:
        """Interroge le lecteur ; une insertion declenche le telechargement automatique.

        Pendant un telechargement, le lecteur n'est pas interroge : la carte est
        alors occupee par la lecture.
        """
        if self._busy:
            return
        try:
            events = self._detector.refresh()
        except Exception:  # noqa: BLE001 - un minuteur ne doit jamais lever
            logger.exception("Interrogation du lecteur de carte en echec")
            return
        if events:
            self.presence_changed.emit(self._detector.current)
        for event in events:
            self.event_message.emit(event.message)
            if event.event_type is CardEventType.CARD_INSERTED and self.auto_download:
                self.download()

    def download(self) -> bool:
        """Lance le telechargement de la carte inseree en tache de fond.

        Returns:
            ``False`` si un telechargement est deja en cours.
        """
        if self._busy:
            return False
        self._busy = True
        self.download_started.emit()
        self.event_message.emit("Telechargement de la carte en cours...")
        task = _DownloadTask(self._service, self._reader)
        task.signals.finished.connect(self._on_finished)
        task.signals.failed.connect(self._on_failed)
        self._task = task
        self._pool.start(task)
        return True

    def _on_finished(self, result: object) -> None:
        """Termine un telechargement reussi."""
        self._busy = False
        self._task = None
        self.download_finished.emit(result)

    def _on_failed(self, error: object) -> None:
        """Termine un telechargement en echec."""
        self._busy = False
        self._task = None
        self.download_failed.emit(error)

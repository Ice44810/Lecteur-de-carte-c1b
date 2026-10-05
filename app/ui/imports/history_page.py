"""Historique des telechargements.

Colonnes attendues en section 14 du cahier des charges : date, conducteur, type,
fichier, taille, SHA-256, statut. La recherche, le filtrage, l'ouverture du repertoire
d'archivage et l'affichage du detail sont disponibles.
"""

from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)

from app.bootstrap import ApplicationContext
from app.core.enums import FileType, ParsingStatus
from app.services.import_service import ImportRecord, ImportService
from app.ui.common.errors import show_error, show_information
from app.ui.common.formatting import format_local_datetime
from app.ui.common.page import Page
from app.ui.common.widgets import ReadOnlyTable

__all__ = ["ImportHistoryPage"]

_ALL = "Tous"


class ImportHistoryPage(Page):
    """Journal des fichiers importes."""

    title = "Historique des telechargements"
    subtitle = (
        "Journal des fichiers importes. L'empreinte SHA-256 garantit l'integrite de "
        "chaque fichier archive."
    )

    def __init__(self, context: ApplicationContext, parent: QWidget | None = None) -> None:
        self._service = ImportService(context.database, settings=context.settings)
        self._records: tuple[ImportRecord, ...] = ()
        self._timezone = context.settings.timezone_display
        super().__init__(context, parent)

    def build(self) -> None:
        """Construit la barre de filtres et le tableau."""
        filters = QHBoxLayout()

        self._search = QLineEdit()
        self._search.setPlaceholderText("Rechercher un nom de fichier ou une empreinte")
        self._search.setClearButtonEnabled(True)
        self._search.returnPressed.connect(self.safe_refresh)
        filters.addWidget(self._search, stretch=1)

        filters.addWidget(QLabel("Type"))
        self._type_filter = QComboBox()
        self._type_filter.addItem(_ALL, None)
        for file_type in FileType:
            self._type_filter.addItem(file_type.value, file_type)
        self._type_filter.currentIndexChanged.connect(self.safe_refresh)
        filters.addWidget(self._type_filter)

        filters.addWidget(QLabel("Statut"))
        self._status_filter = QComboBox()
        self._status_filter.addItem(_ALL, None)
        for status in ParsingStatus:
            self._status_filter.addItem(status.label, status)
        self._status_filter.currentIndexChanged.connect(self.safe_refresh)
        filters.addWidget(self._status_filter)

        refresh_button = QPushButton("Actualiser")
        refresh_button.clicked.connect(self.safe_refresh)
        filters.addWidget(refresh_button)
        self.content_layout.addLayout(filters)

        self._table = ReadOnlyTable(
            ("Date", "Conducteur", "Type", "Fichier", "Taille", "SHA-256", "Statut")
        )
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        self.content_layout.addWidget(self._table)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self._details_button = QPushButton("Afficher les details")
        self._details_button.setEnabled(False)
        self._details_button.clicked.connect(self._on_details)
        actions.addWidget(self._details_button)

        self._redecode_button = QPushButton("Decoder a nouveau")
        self._redecode_button.setEnabled(False)
        self._redecode_button.clicked.connect(self._on_redecode)
        actions.addWidget(self._redecode_button)

        pending_button = QPushButton("Decoder les fichiers en attente")
        pending_button.clicked.connect(self._on_redecode_pending)
        actions.addWidget(pending_button)

        self._open_folder_button = QPushButton("Ouvrir le dossier d'archivage")
        self._open_folder_button.setEnabled(False)
        self._open_folder_button.clicked.connect(self._on_open_folder)
        actions.addWidget(self._open_folder_button)
        self.content_layout.addLayout(actions)

    def refresh(self) -> None:
        """Recharge le journal en appliquant les filtres."""
        self._records = self._service.history(
            file_type=self._type_filter.currentData(),
            parsing_status=self._status_filter.currentData(),
            search=self._search.text() or None,
        )
        self._table.set_rows(
            tuple(
                (
                    format_local_datetime(record.imported_at, self._timezone),
                    record.driver_display_name or "-",
                    record.file_type.value,
                    record.filename,
                    record.human_size,
                    record.short_sha256,
                    record.parsing_status.label,
                )
                for record in self._records
            ),
            keys=tuple(record.id for record in self._records),
        )
        self._details_button.setEnabled(False)
        self._redecode_button.setEnabled(False)
        self._open_folder_button.setEnabled(False)
        self.notify(f"{len(self._records)} import(s) affiche(s)")

    def _selected_record(self) -> ImportRecord | None:
        """Retourne l'import selectionne, ou ``None``."""
        record_id = self._table.selected_key()
        if record_id is None:
            return None
        return next((record for record in self._records if record.id == record_id), None)

    def _on_selection_changed(self) -> None:
        """Active ou desactive les actions selon la selection."""
        has_selection = self._selected_record() is not None
        self._details_button.setEnabled(has_selection)
        self._redecode_button.setEnabled(has_selection)
        self._open_folder_button.setEnabled(has_selection)

    def _on_details(self) -> None:
        """Affiche le detail complet de l'import selectionne."""
        record = self._selected_record()
        if record is None:
            return
        lines = [
            f"Fichier : {record.filename}",
            f"Type : {record.file_type.label}",
            "Importe le : "
            + format_local_datetime(record.imported_at, self._timezone, pattern="%d/%m/%Y a %H:%M")
            + f" ({self._timezone})",
            f"Taille : {record.human_size} ({record.file_size} octets)",
            f"Empreinte SHA-256 : {record.sha256}",
            f"Statut de decodage : {record.parsing_status.label}",
            f"Fichier archive : {record.original_path}",
        ]
        if record.parsing_error:
            lines.append(f"Detail du decodage : {record.parsing_error}")
        show_information(self, "\n".join(lines), title="Detail de l'import")

    def _on_redecode(self) -> None:
        """Decode a nouveau le fichier selectionne depuis sa copie archivee."""
        record = self._selected_record()
        if record is None:
            return
        try:
            updated = self._service.redecode(record.id)
        except Exception as exc:  # noqa: BLE001 - garde-fou d'interface
            show_error(self, exc, title="Decodage du fichier")
            return
        self.safe_refresh()
        show_information(
            self,
            f"{updated.filename} : {updated.parsing_status.label}.\n\n"
            + (updated.parsing_error or ""),
            title="Decodage du fichier",
        )

    def _on_redecode_pending(self) -> None:
        """Decode les fichiers archives qui ne l'ont pas encore ete."""
        try:
            updated = self._service.redecode_pending()
        except Exception as exc:  # noqa: BLE001 - garde-fou d'interface
            show_error(self, exc, title="Decodage des fichiers")
            return
        self.safe_refresh()
        decoded = sum(1 for item in updated if item.driver_display_name)
        show_information(
            self,
            f"{len(updated)} fichier(s) examine(s), {decoded} rattache(s) a un conducteur.",
            title="Decodage des fichiers",
        )

    def _on_open_folder(self) -> None:
        """Ouvre le repertoire contenant la copie archivee."""
        record = self._selected_record()
        if record is None:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(record.directory)))
        self.notify(f"Dossier ouvert : {record.directory}")

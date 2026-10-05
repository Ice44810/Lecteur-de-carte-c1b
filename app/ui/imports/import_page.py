"""Import de fichiers tachygraphiques C1B et V1B.

Cette page met en oeuvre les etapes du flux d'import qui sont disponibles en phase 1,
c'est-a-dire celles qui **n'ecrivent rien** : validation de l'extension, calcul de
l'empreinte SHA-256 et detection de doublon. L'etape d'archivage et d'enregistrement
est annoncee clairement comme prevue en phase 3, plutot que simulee.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.bootstrap import ApplicationContext
from app.core.enums import FileType
from app.services.import_service import FileInspection, ImportService
from app.ui.common.errors import show_error
from app.ui.common.page import Page
from app.ui.common.widgets import NoticeBanner

__all__ = ["ImportPage"]


class ImportPage(Page):
    """Selection et examen d'un fichier avant import."""

    title = "Import de fichiers"
    subtitle = (
        "Selectionnez un fichier .C1B (carte conducteur) ou .V1B (vehicule). "
        "Le fichier original n'est jamais modifie."
    )

    def __init__(self, context: ApplicationContext, parent: QWidget | None = None) -> None:
        self._service = ImportService(context.database)
        self._inspection: FileInspection | None = None
        super().__init__(context, parent)

    def build(self) -> None:
        """Construit la zone de selection et le compte rendu d'examen."""
        self.content_layout.addWidget(
            NoticeBanner(
                "Phase 1 : la selection, la validation, le calcul de l'empreinte SHA-256 "
                "et la detection des doublons sont operationnels. L'archivage du fichier "
                "et son enregistrement en base sont prevus en phase 3 ; le decodage du "
                "contenu binaire en phase 4, apres confirmation des structures avec la "
                "specification officielle.",
                level="warning",
            )
        )

        selection = QHBoxLayout()
        self._path_label = QLabel("Aucun fichier selectionne")
        self._path_label.setObjectName("PageSubtitle")
        selection.addWidget(self._path_label, stretch=1)

        browse_c1b = QPushButton("Selectionner un fichier C1B...")
        browse_c1b.setObjectName("PrimaryButton")
        browse_c1b.clicked.connect(lambda: self._browse(FileType.C1B))
        selection.addWidget(browse_c1b)

        browse_v1b = QPushButton("Selectionner un fichier V1B...")
        browse_v1b.clicked.connect(lambda: self._browse(FileType.V1B))
        selection.addWidget(browse_v1b)
        self.content_layout.addLayout(selection)

        self.content_layout.addWidget(self._build_report_box())

        actions = QHBoxLayout()
        actions.addStretch(1)
        self._import_button = QPushButton("Importer et archiver le fichier")
        self._import_button.setEnabled(False)
        self._import_button.clicked.connect(self._on_import)
        actions.addWidget(self._import_button)
        self.content_layout.addLayout(actions)
        self.content_layout.addStretch(1)

    def _build_report_box(self) -> QGroupBox:
        """Construit le cadre presentant le resultat de l'examen du fichier."""
        box = QGroupBox("Controles effectues")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(10, 6, 10, 10)

        form = QFormLayout()
        self._type_value = QLabel("-")
        self._size_value = QLabel("-")
        self._sha_value = QLabel("-")
        self._sha_value.setWordWrap(True)
        self._duplicate_value = QLabel("-")
        self._decoding_value = QLabel("-")

        form.addRow("Type de fichier", self._type_value)
        form.addRow("Taille", self._size_value)
        form.addRow("Empreinte SHA-256", self._sha_value)
        form.addRow("Doublon", self._duplicate_value)
        form.addRow("Decodage du contenu", self._decoding_value)
        layout.addLayout(form)
        return box

    def refresh(self) -> None:
        """Rien a recharger : la page reflete la derniere selection."""

    def _browse(self, file_type: FileType) -> None:
        """Ouvre le selecteur de fichier puis examine le fichier choisi."""
        pattern = f"Fichiers {file_type.value} (*.{file_type.value} *.{file_type.value.lower()})"
        path, _ = QFileDialog.getOpenFileName(
            self,
            f"Selectionner un fichier {file_type.value}",
            str(self.context.settings.imports_dir),
            f"{pattern};;Tous les fichiers (*)",
        )
        if not path:
            return
        self._inspect(Path(path))

    def _inspect(self, path: Path) -> None:
        """Examine un fichier et affiche le compte rendu."""
        self._path_label.setText(str(path))
        try:
            inspection = self._service.inspect(path)
        except Exception as exc:  # noqa: BLE001 - garde-fou d'interface
            self._inspection = None
            self._import_button.setEnabled(False)
            self._reset_report()
            show_error(self, exc, title="Examen du fichier")
            return

        self._inspection = inspection
        self._type_value.setText(inspection.file_type.label)
        self._size_value.setText(inspection.human_size)
        self._sha_value.setText(inspection.sha256)
        self._duplicate_value.setText(
            inspection.duplicate_message or "Nouveau fichier : aucun doublon detecte"
        )
        self._decoding_value.setText(
            "Disponible"
            if inspection.decoding_available
            else (
                "Indisponible dans cette version : les structures binaires doivent "
                "d'abord etre confirmees avec la specification officielle"
            )
        )
        self._import_button.setEnabled(not inspection.is_duplicate)
        self.notify(
            f"Fichier examine : {inspection.filename} ({inspection.human_size}) - "
            + ("deja importe" if inspection.is_duplicate else "pret pour archivage")
        )

    def _reset_report(self) -> None:
        """Vide le compte rendu d'examen."""
        for label in (
            self._type_value,
            self._size_value,
            self._sha_value,
            self._duplicate_value,
            self._decoding_value,
        ):
            label.setText("-")

    def _on_import(self) -> None:
        """Declenche l'import ; la phase 3 n'etant pas livree, l'erreur est explicite."""
        if self._inspection is None:
            return
        try:
            self._service.import_file(self._inspection.path)
        except Exception as exc:  # noqa: BLE001 - garde-fou d'interface
            show_error(self, exc, title="Import du fichier")

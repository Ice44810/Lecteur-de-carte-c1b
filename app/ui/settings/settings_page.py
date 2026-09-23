"""Parametres de l'application.

Page en lecture seule pour l'essentiel : elle montre la configuration effective (chemins
resolus, base, journal, regles) afin que l'utilisateur ou le support puisse verifier ou
sont reellement stockees les donnees. La modification des parametres depuis l'interface
est prevue ulterieurement ; les valeurs sont deja surchargeables par variables
d'environnement (prefixe ``TACHY_``) ou par un fichier ``.env``.
"""

from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.analysis.rules import RULESET_FILENAME, load_ruleset
from app.bootstrap import ApplicationContext
from app.ui.common.page import Page
from app.ui.common.widgets import NoticeBanner, ReadOnlyTable

__all__ = ["SettingsPage"]

LOG_TAIL_LINES = 200
"""Nombre de lignes de journal affichees."""


class SettingsPage(Page):
    """Configuration effective, regles et journal technique."""

    title = "Parametres"
    subtitle = "Configuration effective de l'application et journal technique."

    def build(self) -> None:
        """Construit les blocs stockage, regles et journal."""
        self.content_layout.addWidget(
            NoticeBanner(
                "Les chemins ci-dessous sont resolus au demarrage. Ils peuvent etre "
                "modifies par les variables d'environnement TACHY_DATA_DIR, "
                "TACHY_LOG_LEVEL, TACHY_DATABASE_FILENAME, ou par un fichier .env "
                "place a la racine du projet."
            )
        )

        storage_box = QGroupBox("Entreprise et stockage")
        storage_form = QFormLayout(storage_box)
        storage_form.setContentsMargins(10, 6, 10, 10)

        self._company_value = QLabel("-")
        self._data_dir_value = QLabel("-")
        self._originals_value = QLabel("-")
        self._exports_value = QLabel("-")
        self._database_value = QLabel("-")
        self._log_value = QLabel("-")
        self._schema_value = QLabel("-")
        for label in (
            self._data_dir_value,
            self._originals_value,
            self._exports_value,
            self._database_value,
            self._log_value,
        ):
            label.setWordWrap(True)

        storage_form.addRow("Entreprise", self._company_value)
        storage_form.addRow("Racine des donnees", self._data_dir_value)
        storage_form.addRow("Fichiers originaux", self._originals_value)
        storage_form.addRow("Exports", self._exports_value)
        storage_form.addRow("Base de donnees", self._database_value)
        storage_form.addRow("Journal", self._log_value)
        storage_form.addRow("Version du schema", self._schema_value)

        storage_actions = QHBoxLayout()
        storage_actions.addStretch(1)
        open_data = QPushButton("Ouvrir le dossier de donnees")
        open_data.clicked.connect(self._open_data_directory)
        storage_actions.addWidget(open_data)
        storage_form.addRow("", self._wrap_row(storage_actions))

        self.content_layout.addWidget(storage_box)

        self._rules_table = ReadOnlyTable(("Parametre", "Valeur", "Unite", "Source", "Etat"))
        self._rules_table.setMaximumHeight(160)
        rules_box = QGroupBox("Regles configurees")
        rules_layout = QVBoxLayout(rules_box)
        rules_layout.setContentsMargins(10, 6, 10, 10)
        self._rules_notice = QLabel("-")
        self._rules_notice.setWordWrap(True)
        self._rules_notice.setObjectName("PageSubtitle")
        rules_layout.addWidget(self._rules_notice)
        rules_layout.addWidget(self._rules_table)
        self.content_layout.addWidget(rules_box)

        log_box = QGroupBox("Journal de l'application")
        log_layout = QVBoxLayout(log_box)
        log_layout.setContentsMargins(10, 6, 10, 10)
        self._log_view = QTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        log_layout.addWidget(self._log_view)

        log_actions = QHBoxLayout()
        log_actions.addStretch(1)
        reload_log = QPushButton("Recharger le journal")
        reload_log.clicked.connect(self._load_log)
        log_actions.addWidget(reload_log)
        log_layout.addLayout(log_actions)
        self.content_layout.addWidget(log_box)

    def refresh(self) -> None:
        """Recharge la configuration, les regles et le journal."""
        settings = self.context.settings

        self._company_value.setText(settings.company_name or "(non renseignee)")
        self._data_dir_value.setText(str(settings.data_dir))
        self._originals_value.setText(str(settings.originals_dir))
        self._exports_value.setText(str(settings.exports_dir))
        self._database_value.setText(str(settings.database_path))
        self._log_value.setText(f"{settings.log_path} (niveau {settings.log_level})")
        self._schema_value.setText(str(self.context.schema_version))

        ruleset = load_ruleset(settings.data_dir / RULESET_FILENAME)
        self._rules_table.set_rows(
            tuple(
                (
                    parameter.code,
                    f"{parameter.value:g}",
                    parameter.unit,
                    parameter.source,
                    parameter.status.label,
                )
                for parameter in ruleset.parameters.values()
            )
        )
        if ruleset.is_empty:
            self._rules_notice.setText(
                "Aucun seuil verifie n'est configure : aucun depassement n'est recherche. "
                f"Pour en ajouter, creez le fichier {settings.data_dir / RULESET_FILENAME}. "
                "Chaque seuil doit citer le texte qui le fixe et etre marque comme confirme."
            )
        else:
            self._rules_notice.setText(
                f"Jeu de regles {ruleset.version} : {len(ruleset.parameters)} parametre(s), "
                f"dont {len(ruleset.usable_parameters)} verifie(s) et applicable(s)."
            )

        self._load_log()
        self.notify("Parametres actualises")

    def _load_log(self) -> None:
        """Affiche les dernieres lignes du journal."""
        log_path = self.context.settings.log_path
        if not log_path.is_file():
            self._log_view.setPlainText(
                f"Aucun journal disponible pour l'instant ({log_path})."
            )
            return
        try:
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as exc:
            self._log_view.setPlainText(f"Le journal n'a pas pu etre lu : {exc}")
            return
        self._log_view.setPlainText("\n".join(lines[-LOG_TAIL_LINES:]))

    def _open_data_directory(self) -> None:
        """Ouvre le repertoire de donnees dans le gestionnaire de fichiers."""
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.context.settings.data_dir)))
        self.notify(f"Dossier ouvert : {self.context.settings.data_dir}")

    @staticmethod
    def _wrap_row(layout: QHBoxLayout) -> QWidget:
        """Place une disposition horizontale dans un widget, pour un QFormLayout."""
        holder = QWidget()
        holder.setLayout(layout)
        return holder

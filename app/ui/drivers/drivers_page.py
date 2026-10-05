"""Liste des conducteurs et creation d'une fiche."""

from __future__ import annotations

from datetime import date

from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.bootstrap import ApplicationContext
from app.core.timeutils import utcnow
from app.services.driver_service import DriverService
from app.ui.common.errors import show_error, show_information
from app.ui.common.page import Page
from app.ui.common.widgets import NoticeBanner, ReadOnlyTable

__all__ = ["DriversPage"]


class DriversPage(Page):
    """Referentiel des conducteurs de l'entreprise."""

    title = "Conducteurs"
    subtitle = (
        "Referentiel des conducteurs. Le numero de carte identifie le conducteur de maniere unique."
    )

    def __init__(self, context: ApplicationContext, parent: QWidget | None = None) -> None:
        self._service = DriverService(context.database)
        super().__init__(context, parent)

    def build(self) -> None:
        """Construit la barre de recherche, le tableau et le formulaire de creation."""
        self.content_layout.addWidget(
            NoticeBanner(
                "Le decodage automatique des cartes n'est pas encore disponible : les "
                "fiches peuvent etre creees manuellement pour preparer le referentiel. "
                "Une donnee saisie ici ne sera jamais ecrasee silencieusement par un "
                "decodage ulterieur."
            )
        )

        search_row = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText("Rechercher un nom, un prenom ou un numero de carte")
        self._search.setClearButtonEnabled(True)
        self._search.returnPressed.connect(self.safe_refresh)
        search_row.addWidget(self._search)

        search_button = QPushButton("Rechercher")
        search_button.clicked.connect(self.safe_refresh)
        search_row.addWidget(search_button)
        self.content_layout.addLayout(search_row)

        self._table = ReadOnlyTable(
            (
                "Numero de carte",
                "Nom",
                "Prenom",
                "Pays",
                "Expiration carte",
                "Fichiers",
                "Activites",
                "Derniere activite",
            )
        )
        self.content_layout.addWidget(self._table)

        self.content_layout.addWidget(self._build_creation_form())

    def _build_creation_form(self) -> QGroupBox:
        """Construit le formulaire de creation d'une fiche conducteur."""
        box = QGroupBox("Ajouter un conducteur")
        outer = QVBoxLayout(box)
        form = QFormLayout()
        form.setContentsMargins(10, 6, 10, 6)

        self._card_number = QLineEdit()
        self._card_number.setPlaceholderText("Numero figurant sur la carte conducteur")
        self._last_name = QLineEdit()
        self._first_name = QLineEdit()
        self._country = QLineEdit()
        self._country.setMaxLength(3)
        self._country.setPlaceholderText("FR")

        form.addRow("Numero de carte *", self._card_number)
        form.addRow("Nom", self._last_name)
        form.addRow("Prenom", self._first_name)
        form.addRow("Pays emetteur", self._country)
        outer.addLayout(form)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self._create_button = QPushButton("Enregistrer le conducteur")
        self._create_button.setObjectName("PrimaryButton")
        self._create_button.clicked.connect(self._on_create)
        actions.addWidget(self._create_button)
        outer.addLayout(actions)
        return box

    def refresh(self) -> None:
        """Recharge la liste des conducteurs."""
        today: date = utcnow().date()
        drivers = self._service.search(self._search.text())
        self._table.set_rows(
            tuple(
                (
                    driver.card_number,
                    driver.last_name or "-",
                    driver.first_name or "-",
                    driver.card_issuing_country or "-",
                    driver.card_expiry_status(today),
                    str(driver.files_count),
                    str(driver.activities_count),
                    driver.last_activity_end.strftime("%d/%m/%Y")
                    if driver.last_activity_end
                    else "-",
                )
                for driver in drivers
            )
        )
        self.notify(f"{len(drivers)} conducteur(s) affiche(s)")

    def _on_create(self) -> None:
        """Cree une fiche conducteur depuis le formulaire."""
        card_number = self._card_number.text().strip()
        if not card_number:
            show_information(
                self,
                "Le numero de carte est obligatoire : il identifie le conducteur.",
                title="Champ manquant",
            )
            return
        try:
            summary = self._service.create(
                card_number=card_number,
                first_name=self._first_name.text().strip() or None,
                last_name=self._last_name.text().strip() or None,
                card_issuing_country=self._country.text().strip().upper() or None,
            )
        except Exception as exc:  # noqa: BLE001 - garde-fou d'interface
            show_error(self, exc, title="Creation du conducteur")
            return

        self._card_number.clear()
        self._first_name.clear()
        self._last_name.clear()
        self._country.clear()
        self.notify(f"Conducteur enregistre : {summary.display_name}")
        self.safe_refresh()

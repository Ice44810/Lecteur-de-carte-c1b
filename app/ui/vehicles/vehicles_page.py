"""Liste des vehicules et creation d'une fiche."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.bootstrap import ApplicationContext
from app.services.vehicle_service import VehicleService
from app.ui.common.errors import show_error, show_information
from app.ui.common.page import Page
from app.ui.common.widgets import NoticeBanner, ReadOnlyTable

__all__ = ["VehiclesPage"]


class VehiclesPage(Page):
    """Referentiel des vehicules de l'entreprise."""

    title = "Vehicules"
    subtitle = "Referentiel des vehicules. L'immatriculation identifie le vehicule."

    def __init__(self, context: ApplicationContext, parent: QWidget | None = None) -> None:
        self._service = VehicleService(context.database)
        super().__init__(context, parent)

    def build(self) -> None:
        """Construit le tableau et le formulaire de creation."""
        self.content_layout.addWidget(
            NoticeBanner(
                "Les fiches vehicules seront completees automatiquement lors de l'import "
                "de fichiers V1B. En attendant, elles peuvent etre saisies manuellement."
            )
        )

        self._table = ReadOnlyTable(
            ("Immatriculation", "Pays", "VIN", "Identifiant tachygraphe", "Activites", "Flotte")
        )
        self.content_layout.addWidget(self._table)
        self.content_layout.addLayout(self._build_fleet_actions())

        box = QGroupBox("Ajouter un vehicule")
        outer = QVBoxLayout(box)
        form = QFormLayout()
        form.setContentsMargins(10, 6, 10, 6)

        self._registration = QLineEdit()
        self._registration.setPlaceholderText("AB-123-CD")
        self._country = QLineEdit()
        self._country.setMaxLength(3)
        self._country.setPlaceholderText("FR")
        self._vin = QLineEdit()

        form.addRow("Immatriculation *", self._registration)
        form.addRow("Pays d'immatriculation", self._country)
        form.addRow("VIN", self._vin)
        outer.addLayout(form)

        actions = QHBoxLayout()
        actions.addStretch(1)
        create_button = QPushButton("Enregistrer le vehicule")
        create_button.setObjectName("PrimaryButton")
        create_button.clicked.connect(self._on_create)
        actions.addWidget(create_button)
        outer.addLayout(actions)

        self.content_layout.addWidget(box)

    def refresh(self) -> None:
        """Recharge la liste des vehicules."""
        vehicles = self._service.list_vehicles()
        self._table.set_rows(
            tuple(
                (
                    vehicle.registration,
                    vehicle.registration_country or "-",
                    vehicle.vin or "-",
                    vehicle.tachograph_identifier or "-",
                    str(vehicle.activities_count),
                    "Oui" if vehicle.in_fleet else "A confirmer",
                )
                for vehicle in vehicles
            ),
            keys=tuple(vehicle.id for vehicle in vehicles),
        )
        self.notify(f"{len(vehicles)} vehicule(s) affiche(s)")

    def _build_fleet_actions(self) -> QHBoxLayout:
        """Boutons de confirmation de l'appartenance a la flotte."""
        actions = QHBoxLayout()
        hint = QLabel(
            "« A confirmer » : fiche creee automatiquement par l'import d'une carte. "
            "Confirmez les vehicules de votre flotte ; les autres apparaissent dans "
            "Statistiques > Vehicules inconnus."
        )
        hint.setObjectName("PageSubtitle")
        hint.setWordWrap(True)
        actions.addWidget(hint, stretch=1)
        confirm_button = QPushButton("Confirmer dans la flotte")
        confirm_button.clicked.connect(lambda: self._set_in_fleet(True))
        actions.addWidget(confirm_button)
        remove_button = QPushButton("Retirer de la flotte")
        remove_button.clicked.connect(lambda: self._set_in_fleet(False))
        actions.addWidget(remove_button)
        return actions

    def _set_in_fleet(self, in_fleet: bool) -> None:
        """Change l'appartenance a la flotte de la fiche selectionnee."""
        identifier = self._table.selected_key()
        if not isinstance(identifier, int):
            show_information(self, "Selectionnez d'abord une ligne du tableau.", title="Flotte")
            return
        try:
            summary = self._service.set_in_fleet(identifier, in_fleet)
        except Exception as exc:  # noqa: BLE001 - garde-fou d'interface
            show_error(self, exc, title="Flotte")
            return
        self.notify(
            f"{summary.display_name} : "
            + ("confirme dans la flotte" if in_fleet else "retire de la flotte")
        )
        self.safe_refresh()

    def _on_create(self) -> None:
        """Cree une fiche vehicule depuis le formulaire."""
        registration = self._registration.text().strip()
        if not registration:
            show_information(self, "L'immatriculation est obligatoire.", title="Champ manquant")
            return
        try:
            summary = self._service.create(
                registration=registration,
                registration_country=self._country.text().strip().upper() or None,
                vin=self._vin.text().strip().upper() or None,
            )
        except Exception as exc:  # noqa: BLE001 - garde-fou d'interface
            show_error(self, exc, title="Creation du vehicule")
            return

        self._registration.clear()
        self._country.clear()
        self._vin.clear()
        self.notify(f"Fiche vehicule enregistree : {summary.display_name}")
        self.safe_refresh()

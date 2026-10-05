"""Description de la navigation laterale.

La navigation est declaree en donnees, pas en code : ajouter une page consiste a
ajouter une entree a :data:`NAVIGATION`. La fenetre principale construit la barre
laterale et la pile de pages a partir de cette description, et instancie chaque page
**a la demande** (premiere visite), ce qui garde le demarrage rapide.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

__all__ = ["NavigationItem", "NavigationSection", "NAVIGATION"]


@dataclass(frozen=True, slots=True)
class NavigationItem:
    """Entree de navigation.

    Attributes:
        key: Identifiant stable de la page.
        label: Libelle affiche dans la barre laterale.
        factory: Fonction d'import differe retournant la classe de page.
    """

    key: str
    label: str
    factory: Callable[[], type]


@dataclass(frozen=True, slots=True)
class NavigationSection:
    """Groupe d'entrees de navigation.

    Attributes:
        title: Intitule du groupe, ou chaine vide pour un groupe sans titre.
        items: Entrees du groupe.
    """

    title: str
    items: tuple[NavigationItem, ...] = field(default_factory=tuple)


def _dashboard_page() -> type:
    """Importe la page du tableau de bord."""
    from app.ui.dashboard.dashboard_page import DashboardPage

    return DashboardPage


def _drivers_page() -> type:
    """Importe la page des conducteurs."""
    from app.ui.drivers.drivers_page import DriversPage

    return DriversPage


def _vehicles_page() -> type:
    """Importe la page des vehicules."""
    from app.ui.vehicles.vehicles_page import VehiclesPage

    return VehiclesPage


def _import_page() -> type:
    """Importe la page d'import de fichiers."""
    from app.ui.imports.import_page import ImportPage

    return ImportPage


def _history_page() -> type:
    """Importe la page d'historique des telechargements."""
    from app.ui.imports.history_page import ImportHistoryPage

    return ImportHistoryPage


def _activities_page() -> type:
    """Importe la page des activites."""
    from app.ui.analysis.activities_page import ActivitiesPage

    return ActivitiesPage


def _anomalies_page() -> type:
    """Importe la page des anomalies."""
    from app.ui.analysis.anomalies_page import AnomaliesPage

    return AnomaliesPage


def _reports_page() -> type:
    """Importe la page des rapports."""
    from app.ui.reports.reports_page import ReportsPage

    return ReportsPage


def _card_reader_page() -> type:
    """Importe la page du lecteur de carte."""
    from app.ui.cards.card_reader_page import CardReaderPage

    return CardReaderPage


def _settings_page() -> type:
    """Importe la page des parametres."""
    from app.ui.settings.settings_page import SettingsPage

    return SettingsPage


NAVIGATION: tuple[NavigationSection, ...] = (
    NavigationSection(
        title="",
        items=(NavigationItem("dashboard", "Tableau de bord", _dashboard_page),),
    ),
    NavigationSection(
        title="Referentiel",
        items=(
            NavigationItem("drivers", "Conducteurs", _drivers_page),
            NavigationItem("vehicles", "Vehicules", _vehicles_page),
        ),
    ),
    NavigationSection(
        title="Imports",
        items=(
            NavigationItem("import", "Importer un fichier", _import_page),
            NavigationItem("history", "Historique", _history_page),
        ),
    ),
    NavigationSection(
        title="Analyses",
        items=(
            NavigationItem("activities", "Activites", _activities_page),
            NavigationItem("anomalies", "Anomalies", _anomalies_page),
            NavigationItem("reports", "Rapports", _reports_page),
        ),
    ),
    NavigationSection(
        title="Materiel",
        items=(NavigationItem("cards", "Lecteur de carte", _card_reader_page),),
    ),
    NavigationSection(
        title="Configuration",
        items=(NavigationItem("settings", "Parametres", _settings_page),),
    ),
)
"""Structure du menu lateral, dans l'ordre d'affichage."""

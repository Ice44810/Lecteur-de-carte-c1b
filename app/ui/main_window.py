"""Fenetre principale de l'application.

Organisation : barre laterale de navigation a gauche, zone principale a droite, barre
d'etat en bas. Les pages sont instanciees a la premiere visite et conservees ensuite.

La fenetre ne contient aucune logique metier : elle assemble, navigue et affiche des
messages. Chaque page dialogue avec ses propres services.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from app import __version__
from app.bootstrap import ApplicationContext
from app.config.logging_config import get_logger
from app.ui.common.errors import show_error
from app.ui.common.page import Page
from app.ui.navigation import NAVIGATION, NavigationItem
from app.ui.theme import STYLESHEET

__all__ = ["MainWindow"]

logger = get_logger(__name__)

SIDEBAR_WIDTH = 220
WINDOW_MINIMUM_SIZE = (1100, 700)


class MainWindow(QMainWindow):
    """Fenetre principale.

    Args:
        context: Contexte applicatif issu de :func:`app.bootstrap.bootstrap`.
        parent: Widget parent.
    """

    def __init__(self, context: ApplicationContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._context = context
        self._pages: dict[str, Page] = {}
        self._containers: dict[str, QWidget] = {}
        self._items: dict[str, NavigationItem] = {}
        self._buttons: dict[str, QPushButton] = {}

        self.setWindowTitle(f"{context.settings.app_name} - gestion et analyse tachygraphique")
        self.setMinimumSize(*WINDOW_MINIMUM_SIZE)
        self.setStyleSheet(STYLESHEET)

        central = QWidget(self)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_sidebar())

        self._stack = QStackedWidget()
        layout.addWidget(self._stack, stretch=1)
        self.setCentralWidget(central)

        self._build_status_bar()
        self._select_first_page()

    # ------------------------------------------------------------------ #
    # Construction
    # ------------------------------------------------------------------ #
    def _build_sidebar(self) -> QWidget:
        """Construit la barre laterale de navigation."""
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(SIDEBAR_WIDTH)
        sidebar.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        title = QLabel(self._context.settings.app_name)
        title.setObjectName("SidebarTitle")
        layout.addWidget(title)

        subtitle = QLabel(f"Version {__version__}")
        subtitle.setObjectName("SidebarSubtitle")
        layout.addWidget(subtitle)

        self._button_group = QButtonGroup(self)
        self._button_group.setExclusive(True)

        for section in NAVIGATION:
            if section.title:
                section_label = QLabel(section.title.upper())
                section_label.setObjectName("SidebarSection")
                layout.addWidget(section_label)
            for item in section.items:
                layout.addWidget(self._build_nav_button(item))

        layout.addStretch(1)

        footer = QLabel("Donnees stockees localement")
        footer.setObjectName("SidebarSubtitle")
        footer.setWordWrap(True)
        layout.addWidget(footer)
        return sidebar

    def _build_nav_button(self, item: NavigationItem) -> QPushButton:
        """Construit un bouton de navigation pour une entree de menu."""
        button = QPushButton(item.label)
        button.setObjectName("SidebarButton")
        button.setCheckable(True)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(lambda _checked=False, key=item.key: self.navigate_to(key))

        self._items[item.key] = item
        self._buttons[item.key] = button
        self._button_group.addButton(button)
        return button

    def _build_status_bar(self) -> None:
        """Construit la barre d'etat."""
        status = QStatusBar()
        self.setStatusBar(status)

        self._context_label = QLabel(
            f"Base : {self._context.settings.database_path.name} "
            f"(schema v{self._context.schema_version})"
        )
        status.addPermanentWidget(self._context_label)
        status.showMessage("Application prete")

    # ------------------------------------------------------------------ #
    # Navigation
    # ------------------------------------------------------------------ #
    @property
    def context(self) -> ApplicationContext:
        """Contexte applicatif partage."""
        return self._context

    @property
    def current_page(self) -> Page | None:
        """Page actuellement affichee, ou ``None``.

        Chaque page est encapsulee dans une zone defilante : la correspondance se fait
        donc via le conteneur affiche dans la pile.
        """
        current = self._stack.currentWidget()
        for key, container in self._containers.items():
            if container is current:
                return self._pages.get(key)
        return None

    def page(self, key: str) -> Page | None:
        """Retourne une page deja instanciee, ou ``None``.

        Args:
            key: Identifiant de la page.

        Returns:
            La page si elle a deja ete visitee.
        """
        return self._pages.get(key)

    def navigate_to(self, key: str) -> None:
        """Affiche une page et recharge ses donnees.

        Args:
            key: Identifiant de la page a afficher.

        Raises:
            KeyError: L'identifiant ne correspond a aucune entree de navigation.
        """
        if key not in self._items:
            raise KeyError(f"page inconnue : {key}")

        button = self._buttons[key]
        if not button.isChecked():
            button.setChecked(True)

        page = self._pages.get(key)
        if page is None:
            page = self._create_page(key)
            if page is None:
                return

        self._stack.setCurrentWidget(self._containers[key])
        page.safe_refresh()
        logger.debug("Navigation vers la page %s", key)

    def _create_page(self, key: str) -> Page | None:
        """Instancie une page a la demande.

        Un echec de construction n'interrompt pas l'application : un widget
        d'explication est affiche a la place, et l'erreur est presentee sous la forme
        message / cause / action.

        Args:
            key: Identifiant de la page.

        Returns:
            La page construite, ou ``None`` si la construction a echoue.
        """
        item = self._items[key]
        try:
            page_class = item.factory()
            page = page_class(self._context)
        except Exception as exc:  # noqa: BLE001 - garde-fou d'interface
            logger.exception("La page %s n'a pas pu etre construite", key)
            show_error(self, exc, title=item.label)
            self._install_placeholder(key, item)
            return None

        assert isinstance(page, Page)
        page.status_message.connect(self.show_status)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        self._stack.addWidget(scroll)

        self._pages[key] = page
        self._containers[key] = scroll
        return page

    def _install_placeholder(self, key: str, item: NavigationItem) -> None:
        """Affiche un message a la place d'une page qui n'a pas pu etre construite."""
        placeholder = QWidget()
        layout = QVBoxLayout(placeholder)
        layout.setContentsMargins(24, 24, 24, 24)
        label = QLabel(
            f"La page « {item.label} » n'a pas pu etre ouverte.\n\n"
            "Aucune donnee n'a ete modifiee. Le detail technique figure dans le journal "
            "de l'application (Parametres > Journal)."
        )
        label.setWordWrap(True)
        layout.addWidget(label)
        layout.addStretch(1)
        self._stack.addWidget(placeholder)
        self._containers[key] = placeholder
        self._stack.setCurrentWidget(placeholder)

    def _select_first_page(self) -> None:
        """Affiche la premiere page de la navigation au demarrage."""
        for section in NAVIGATION:
            for item in section.items:
                self.navigate_to(item.key)
                return

    # ------------------------------------------------------------------ #
    # Barre d'etat
    # ------------------------------------------------------------------ #
    def show_status(self, message: str, *, timeout_ms: int = 8000) -> None:
        """Affiche un message temporaire dans la barre d'etat.

        Args:
            message: Message a afficher.
            timeout_ms: Duree d'affichage en millisecondes.
        """
        self.statusBar().showMessage(message, timeout_ms)

    @property
    def status_text(self) -> str:
        """Message courant de la barre d'etat, utilise par les tests."""
        return self.statusBar().currentMessage()

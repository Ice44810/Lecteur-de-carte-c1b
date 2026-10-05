"""Classe de base des pages de l'application.

Une page est un widget place dans la zone principale. Elle recoit le contexte
applicatif (configuration et base) a sa construction, construit ses services, et
implemente :meth:`Page.refresh` pour recharger ses donnees.

Regle structurante : une page n'execute aucune requete SQL et ne contient aucune regle
metier. Elle appelle un service et met en forme le resultat.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from app.bootstrap import ApplicationContext
from app.config.logging_config import get_logger
from app.ui.common.errors import show_error
from app.ui.common.widgets import PageHeader

__all__ = ["Page"]

logger = get_logger(__name__)


class Page(QWidget):
    """Page de l'application.

    Args:
        context: Contexte applicatif partage.
        parent: Widget parent.

    Attributes:
        title: Titre affiche en en-tete et dans la navigation.
        subtitle: Phrase d'explication affichee sous le titre.
    """

    title: str = ""
    subtitle: str = ""

    status_message = Signal(str)
    """Emis pour afficher un message dans la barre d'etat de la fenetre."""

    def __init__(self, context: ApplicationContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._context = context
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(20, 18, 20, 18)
        self._layout.setSpacing(14)

        self._header = PageHeader(self.title, self.subtitle)
        self._layout.addWidget(self._header)

        self.build()

    @property
    def context(self) -> ApplicationContext:
        """Contexte applicatif (configuration, base)."""
        return self._context

    @property
    def content_layout(self) -> QVBoxLayout:
        """Disposition verticale de la page, sous l'en-tete."""
        return self._layout

    @property
    def header(self) -> PageHeader:
        """En-tete de la page."""
        return self._header

    def build(self) -> None:
        """Construit le contenu de la page.

        Appelee une fois a la construction. A surcharger.
        """

    def refresh(self) -> None:
        """Recharge les donnees de la page.

        Appelee a chaque affichage de la page. A surcharger.
        """

    def safe_refresh(self) -> None:
        """Recharge la page en presentant proprement une eventuelle erreur.

        Une page qui echoue ne doit pas fermer l'application : l'erreur est affichee
        sous la forme message / cause / action, et l'utilisateur peut continuer a
        naviguer.
        """
        try:
            self.refresh()
        except Exception as exc:  # noqa: BLE001 - garde-fou d'interface
            logger.exception("Echec du rafraichissement de la page %s", type(self).__name__)
            show_error(self, exc, title=self.title or "Erreur")

    def notify(self, message: str) -> None:
        """Affiche un message dans la barre d'etat de la fenetre principale."""
        self.status_message.emit(message)

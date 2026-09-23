"""Presentation des erreurs a l'utilisateur.

Exigence de la section 19 du cahier des charges : ne jamais afficher une stack trace.
Une erreur se presente en trois temps :

.. code-block:: text

    "Impossible de lire la carte."
    Cause  : "Le service PC/SC n'est pas disponible."
    Action : "Verifiez que le service pcscd est actif."

Le detail technique est journalise et reste consultable dans la boite de dialogue via
« Afficher le detail technique », sans encombrer le message principal.
"""

from __future__ import annotations

from PySide6.QtWidgets import QMessageBox, QWidget

from app.config.logging_config import get_logger
from app.core.exceptions import TachyError

__all__ = ["show_error", "show_information", "confirm", "format_error"]

logger = get_logger(__name__)


def format_error(error: Exception) -> tuple[str, str, str, str | None]:
    """Traduit une exception en elements affichables.

    Args:
        error: Exception a presenter.

    Returns:
        Un quadruplet ``(message, cause, action, detail_technique)``. Une exception
        inattendue recoit un message generique : l'utilisateur n'a pas a decoder un
        message d'erreur Python.
    """
    if isinstance(error, TachyError):
        message, cause, action = error.user_report()
        return message, cause, action, error.technical_detail
    if isinstance(error, NotImplementedError):
        return (
            "Cette fonctionnalite n'est pas encore disponible.",
            str(error) or "La fonctionnalite est prevue dans une prochaine etape.",
            "Consultez la feuille de route dans le fichier README.md du projet.",
            None,
        )
    return (
        "Une erreur inattendue est survenue.",
        "L'operation n'a pas pu etre menee a son terme.",
        "Aucune donnee n'a ete supprimee. Consultez le journal de l'application "
        "(Parametres > Journal) puis signalez l'anomalie.",
        f"{type(error).__name__}: {error}",
    )


def show_error(parent: QWidget | None, error: Exception, *, title: str = "Erreur") -> None:
    """Affiche une erreur sous la forme message / cause / action.

    Args:
        parent: Fenetre parente de la boite de dialogue.
        error: Exception a presenter.
        title: Titre de la boite de dialogue.
    """
    message, cause, action, detail = format_error(error)
    logger.error("%s | cause: %s | detail: %s", message, cause, detail or "-")

    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle(title)
    box.setText(message)
    box.setInformativeText(f"Cause :\n{cause}\n\nAction :\n{action}")
    if detail:
        box.setDetailedText(detail)
    box.setStandardButtons(QMessageBox.StandardButton.Ok)
    box.exec()


def show_information(parent: QWidget | None, message: str, *, title: str = "Information") -> None:
    """Affiche un message d'information simple."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Information)
    box.setWindowTitle(title)
    box.setText(message)
    box.setStandardButtons(QMessageBox.StandardButton.Ok)
    box.exec()


def confirm(parent: QWidget | None, question: str, *, title: str = "Confirmation") -> bool:
    """Demande une confirmation a l'utilisateur.

    Args:
        parent: Fenetre parente.
        question: Question posee.
        title: Titre de la boite de dialogue.

    Returns:
        ``True`` si l'utilisateur confirme.
    """
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Question)
    box.setWindowTitle(title)
    box.setText(question)
    box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    box.setDefaultButton(QMessageBox.StandardButton.No)
    return box.exec() == QMessageBox.StandardButton.Yes

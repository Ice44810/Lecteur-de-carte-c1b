"""Couche interface graphique (PySide6).

Cette couche ne contient aucune logique metier et aucune requete SQL : chaque page
appelle un service, qui appelle un depot, qui seul dialogue avec la base.

Les imports de ce module restent volontairement legers : importer ``app.ui`` ne doit
pas construire de widget ni exiger un serveur graphique. Les pages sont importees a la
demande par :mod:`app.ui.navigation`.
"""

from __future__ import annotations

__all__ = ["MainWindow"]


def __getattr__(name: str) -> object:
    """Expose ``MainWindow`` sans importer PySide6 au chargement du paquet."""
    if name == "MainWindow":
        from app.ui.main_window import MainWindow

        return MainWindow
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

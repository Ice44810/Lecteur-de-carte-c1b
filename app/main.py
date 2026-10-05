"""Point d'entree de l'application.

Lancement normal :

.. code-block:: bash

    python -m app.main

Le demarrage est volontairement decoupe en deux temps :

1. :func:`app.bootstrap.bootstrap` prepare la configuration, les repertoires, la
   journalisation et la base (aucune dependance a Qt) ;
2. la fenetre principale est construite et affichee.

Une erreur de la premiere etape est fatale : elle est presentee sous la forme
message / cause / action, dans une boite de dialogue si un serveur graphique est
disponible, sinon sur la sortie d'erreur. L'utilisateur ne voit jamais une simple
pile d'appels (section 19 du cahier des charges) ; le detail technique part dans
``logs/app.log``.

Le mode ``--check`` execute uniquement la premiere etape : il sert aux tests, a
l'integration continue et au diagnostic d'une installation sans ecran.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from app import __version__
from app.bootstrap import ApplicationContext, bootstrap
from app.config.logging_config import get_logger
from app.config.settings import Settings

__all__ = ["main", "build_parser", "run_checks"]

logger = get_logger(__name__)

EXIT_OK = 0
EXIT_STARTUP_FAILURE = 1


def build_parser() -> argparse.ArgumentParser:
    """Construit l'analyseur d'arguments de la ligne de commande.

    Returns:
        L'analyseur configure.
    """
    parser = argparse.ArgumentParser(
        prog="tachy-linux",
        description=(
            "Archivage et analyse de fichiers tachygraphiques (C1B / V1B) "
            "pour entreprises de transport routier."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"tachy-linux {__version__}",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        metavar="CHEMIN",
        help=(
            "Racine des donnees applicatives (equivaut a la variable "
            "d'environnement TACHY_DATA_DIR)."
        ),
    )
    parser.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"),
        default=None,
        help="Niveau de journalisation du fichier de log.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "Verifie la configuration, les repertoires et le schema de base "
            "puis quitte, sans ouvrir l'interface graphique."
        ),
    )
    return parser


def _build_settings(arguments: argparse.Namespace) -> Settings | None:
    """Construit une configuration a partir des options de la ligne de commande.

    Args:
        arguments: Options analysees.

    Returns:
        Une configuration explicite, ou ``None`` pour utiliser la configuration
        partagee issue de l'environnement.
    """
    overrides: dict[str, object] = {}
    if arguments.data_dir is not None:
        overrides["data_dir"] = arguments.data_dir
    if arguments.log_level is not None:
        overrides["log_level"] = arguments.log_level
    if not overrides:
        return None
    return Settings(**overrides)  # type: ignore[arg-type]


def _graphical_session_available() -> bool:
    """Indique si une boite de dialogue peut etre affichee a un utilisateur.

    Sans serveur d'affichage, Qt interrompt brutalement le processus a la creation de
    l'application (erreur fatale non interceptable) ; avec la plate-forme
    ``offscreen``, une boite modale bloquerait indefiniment sans que personne ne
    puisse la fermer. Dans ces deux cas, la sortie d'erreur suffit.
    """
    if os.environ.get("QT_QPA_PLATFORM", "").startswith(("offscreen", "minimal")):
        return False
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _report_startup_failure(error: Exception, *, interactive: bool = True) -> None:
    """Presente une erreur de demarrage sans exiger de serveur graphique.

    Le message est toujours ecrit sur la sortie d'erreur. La boite de dialogue Qt
    n'est ajoutee que pour un lancement interactif disposant d'un affichage.

    Args:
        error: Exception ayant interrompu le demarrage.
        interactive: ``False`` en mode ``--check`` : aucune boite de dialogue ne
            doit alors bloquer un diagnostic automatise.
    """
    from app.ui.common.errors import format_error

    message, cause, action, detail = format_error(error)
    logger.critical("Demarrage impossible : %s | %s", message, detail or "-")

    print(message, file=sys.stderr)
    print(f"Cause  : {cause}", file=sys.stderr)
    print(f"Action : {action}", file=sys.stderr)

    if not interactive or not _graphical_session_available():
        return
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox

        application = QApplication.instance() or QApplication(sys.argv[:1])
        box = QMessageBox()
        box.setIcon(QMessageBox.Icon.Critical)
        box.setWindowTitle("Demarrage impossible")
        box.setText(message)
        box.setInformativeText(f"Cause :\n{cause}\n\nAction :\n{action}")
        if detail:
            box.setDetailedText(detail)
        box.exec()
        del application
    except Exception:  # noqa: BLE001 - sans serveur graphique, le texte suffit
        logger.debug("Boite de dialogue de demarrage indisponible", exc_info=True)


def run_checks(context: ApplicationContext) -> str:
    """Produit un compte rendu de demarrage lisible (mode ``--check``).

    Args:
        context: Contexte applicatif initialise.

    Returns:
        Le compte rendu multiligne.
    """
    settings = context.settings
    lines = [
        f"tachy-linux {__version__}",
        f"Racine des donnees   : {settings.data_dir}",
        f"Fichiers originaux   : {settings.originals_dir}",
        f"Base de donnees      : {settings.database_path}",
        f"Journal              : {settings.log_path}",
        f"Schema de base       : version {context.schema_version}",
    ]
    if context.applied_migrations:
        lines.append("Migrations appliquees : " + ", ".join(context.applied_migrations))
    else:
        lines.append("Migrations appliquees : aucune (schema deja a jour)")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """Demarre l'application.

    Args:
        argv: Arguments de la ligne de commande (par defaut ``sys.argv[1:]``).

    Returns:
        Le code de sortie du processus.
    """
    arguments = build_parser().parse_args(argv)

    try:
        context = bootstrap(_build_settings(arguments))
    except Exception as exc:  # noqa: BLE001 - dernier filet avant la sortie
        _report_startup_failure(exc, interactive=not arguments.check)
        return EXIT_STARTUP_FAILURE

    if arguments.check:
        print(run_checks(context))
        return EXIT_OK

    from PySide6.QtWidgets import QApplication

    from app.ui.cards.card_watcher import CardWatcher
    from app.ui.main_window import MainWindow

    application = QApplication.instance() or QApplication(sys.argv[:1])
    application.setApplicationName(context.settings.app_name)
    application.setApplicationVersion(__version__)
    application.setOrganizationName(context.settings.company_name or "tachy-linux")

    watcher = CardWatcher(context)
    window = MainWindow(context, card_watcher=watcher)
    window.show()
    watcher.start()
    logger.info("Interface affichee")
    try:
        return int(application.exec())
    finally:
        watcher.stop()


if __name__ == "__main__":
    raise SystemExit(main())

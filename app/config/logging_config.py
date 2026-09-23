"""Configuration de la journalisation.

Deux destinations :

* ``logs/app.log`` : fichier tournant (rotation par taille), niveau configurable ;
* la sortie standard : uniquement les messages importants, pour ne pas polluer le
  terminal de l'utilisateur.

Protection des donnees personnelles (section 21 du cahier des charges) : les
numeros de carte conducteur et les noms ne doivent pas etre journalises en clair.
La fonction :func:`mask_card_number` fournit la forme masquee a utiliser dans les
messages de log.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

from app.config.settings import Settings, get_settings

__all__ = [
    "LOG_FORMAT",
    "configure_logging",
    "get_logger",
    "mask_card_number",
    "is_configured",
]

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
CONSOLE_FORMAT = "%(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_ROOT_LOGGER_NAME = "app"
_configured = False


def is_configured() -> bool:
    """Indique si :func:`configure_logging` a deja ete appelee dans ce processus."""
    return _configured


def mask_card_number(card_number: str | None) -> str:
    """Masque un numero de carte pour la journalisation.

    Args:
        card_number: Numero de carte complet, ou ``None``.

    Returns:
        Une forme masquee ne conservant que les quatre derniers caracteres,
        par exemple ``"************1234"``. Retourne ``"<absent>"`` si la valeur
        est vide.
    """
    if not card_number:
        return "<absent>"
    visible = card_number[-4:]
    return "*" * max(len(card_number) - 4, 0) + visible


def configure_logging(
    settings: Settings | None = None,
    *,
    force: bool = False,
    log_path: Path | None = None,
) -> logging.Logger:
    """Installe les gestionnaires de journalisation de l'application.

    Args:
        settings: Configuration a utiliser. Par defaut, la configuration partagee.
        force: Reinstalle les gestionnaires meme s'ils existent deja.
        log_path: Chemin de fichier de journal explicite (utile pour les tests).

    Returns:
        Le logger racine de l'application (``"app"``).
    """
    global _configured

    settings = settings or get_settings()
    logger = logging.getLogger(_ROOT_LOGGER_NAME)

    if _configured and not force:
        return logger

    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    logger.setLevel(logging.DEBUG)
    # Les journaux de l'application ne remontent pas au logger racine afin de ne
    # pas etre dupliques par une configuration tierce.
    logger.propagate = False

    target = log_path or settings.log_path
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        file_handler: logging.Handler = logging.handlers.RotatingFileHandler(
            target,
            maxBytes=settings.log_max_bytes,
            backupCount=settings.log_backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(settings.log_level)
        file_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
        logger.addHandler(file_handler)
    except OSError:
        # Journalisation fichier impossible (droits, disque plein) : l'application
        # doit continuer a fonctionner, la console prend le relais.
        logger.addHandler(logging.NullHandler())

    console_handler = logging.StreamHandler(stream=sys.stderr)
    console_handler.setLevel(settings.console_log_level)
    console_handler.setFormatter(logging.Formatter(CONSOLE_FORMAT, datefmt=DATE_FORMAT))
    logger.addHandler(console_handler)

    _configured = True
    logger.debug("Journalisation initialisee (fichier: %s)", target)
    return logger


def get_logger(name: str) -> logging.Logger:
    """Retourne un logger enfant du logger applicatif.

    Args:
        name: Nom du module appelant, typiquement ``__name__``.

    Returns:
        Le logger correspondant, rattache a la hierarchie ``"app"``.
    """
    if name.startswith(_ROOT_LOGGER_NAME):
        return logging.getLogger(name)
    return logging.getLogger(f"{_ROOT_LOGGER_NAME}.{name}")

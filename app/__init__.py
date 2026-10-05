"""TachoLibre : lecture, archivage et analyse des donnees tachygraphiques.

Application de bureau pour Windows, macOS et Linux.

Le decoupage des couches suit strictement la chaine de traitement suivante :

    DONNEE BRUTE  -> DONNEE DECODEE -> DONNEE METIER -> ANALYSE -> ALERTE -> RAPPORT
    (fichier C1B)    (parser)          (models DB)     (analysis)  (rules)   (reports)

Chaque etage est isole dans un sous-paquet distinct et ne connait que l'etage
immediatement inferieur. L'interface graphique (``app.ui``) ne parle qu'aux
services (``app.services``), jamais directement a la base de donnees.
"""

__all__ = [
    "APP_NAME",
    "APP_SLUG",
    "ENV_PREFIX",
    "LEGACY_APP_SLUG",
    "LEGACY_ENV_PREFIX",
    "__version__",
]

__version__ = "0.1.0"

APP_NAME = "TachoLibre"
"""Nom affiche de l'application."""

APP_SLUG = "tacholibre"
"""Nom technique : commande, paquet, dossiers sous Linux."""

ENV_PREFIX = "TACHOLIBRE_"
"""Prefixe des variables d'environnement de configuration."""

LEGACY_APP_SLUG = "tachy-linux"
"""Ancien nom technique, dont les dossiers sont encore reconnus."""

LEGACY_ENV_PREFIX = "TACHY_"
"""Ancien prefixe des variables d'environnement, encore accepte."""

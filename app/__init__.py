"""tachy-linux : application desktop Linux d'archivage et d'analyse tachygraphique.

Le decoupage des couches suit strictement la chaine de traitement suivante :

    DONNEE BRUTE  -> DONNEE DECODEE -> DONNEE METIER -> ANALYSE -> ALERTE -> RAPPORT
    (fichier C1B)    (parser)          (models DB)     (analysis)  (rules)   (reports)

Chaque etage est isole dans un sous-paquet distinct et ne connait que l'etage
immediatement inferieur. L'interface graphique (``app.ui``) ne parle qu'aux
services (``app.services``), jamais directement a la base de donnees.
"""

__all__ = ["__version__"]

__version__ = "0.1.0"

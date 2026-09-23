"""Migrations de schema de la base locale.

Pour ajouter une migration :

1. creer un module ``m<NNNN>_<description>.py`` dans ce paquet ;
2. y definir ``upgrade(connection)`` ainsi qu'un objet ``migration`` de type
   :class:`~app.database.migrations.runner.Migration` ;
3. l'ajouter a :data:`MIGRATIONS` ci-dessous, en conservant l'ordre croissant.

Regles :

* une migration deja publiee n'est jamais modifiee (on en ajoute une nouvelle) ;
* une migration ne supprime jamais de donnees utilisateur ;
* toute migration doit etre couverte par un test dans ``tests/database/``.
"""

from app.database.migrations.m0001_initial_schema import migration as m0001
from app.database.migrations.runner import Migration, MigrationRunner

__all__ = ["MIGRATIONS", "Migration", "MigrationRunner", "build_runner"]

MIGRATIONS: tuple[Migration, ...] = (m0001,)
"""Liste ordonnee des migrations connues de cette version du logiciel."""


def build_runner(engine: object) -> MigrationRunner:
    """Construit un runner configure avec l'ensemble des migrations connues.

    Args:
        engine: Moteur SQLAlchemy cible.

    Returns:
        Un :class:`MigrationRunner` pret a l'emploi.
    """
    from sqlalchemy import Engine

    if not isinstance(engine, Engine):  # pragma: no cover - garde-fou de typage
        raise TypeError("build_runner attend un Engine SQLAlchemy")
    return MigrationRunner(engine, MIGRATIONS)

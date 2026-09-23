"""Amorcage de l'application.

Sequence de demarrage, volontairement unique et partagee entre l'interface
graphique, les tests d'integration et les futurs points d'entree (API REST,
outils en ligne de commande) :

1. lecture de la configuration ;
2. creation des repertoires de donnees ;
3. initialisation de la journalisation ;
4. ouverture de la base ;
5. application des migrations de schema en attente.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config.logging_config import configure_logging, get_logger
from app.config.settings import Settings, get_settings
from app.database.database import Database, get_database
from app.database.migrations import MigrationRunner, build_runner

__all__ = ["ApplicationContext", "bootstrap"]

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ApplicationContext:
    """Ressources partagees issues du demarrage.

    Attributes:
        settings: Configuration effective.
        database: Base locale ouverte et migree.
        schema_version: Version de schema apres migration.
        applied_migrations: Noms des migrations appliquees pendant ce demarrage.
    """

    settings: Settings
    database: Database
    schema_version: int
    applied_migrations: tuple[str, ...]


def bootstrap(
    settings: Settings | None = None,
    *,
    database: Database | None = None,
    run_migrations: bool | None = None,
) -> ApplicationContext:
    """Prepare l'application et retourne son contexte.

    Args:
        settings: Configuration a utiliser (par defaut la configuration partagee).
        database: Base deja ouverte (utilise par les tests pour injecter une base
            temporaire ou en memoire).
        run_migrations: Force ou desactive l'application des migrations. Par
            defaut, suit le parametre ``auto_migrate``.

    Returns:
        Le contexte applicatif initialise.

    Raises:
        StorageError: Les repertoires de donnees n'ont pas pu etre crees.
        MigrationError: Une migration de schema a echoue.
    """
    settings = settings or get_settings()
    settings.ensure_directories()
    configure_logging(settings)

    logger.info("Demarrage de %s", settings.app_name)
    logger.debug("Racine des donnees : %s", settings.data_dir)

    database = database or get_database(settings)
    database.check_connection()

    applied: tuple[str, ...] = ()
    runner: MigrationRunner = build_runner(database.engine)
    should_migrate = settings.auto_migrate if run_migrations is None else run_migrations
    if should_migrate:
        applied = tuple(
            f"{migration.version:04d} {migration.name}" for migration in runner.upgrade()
        )
    elif not runner.is_up_to_date():
        logger.warning(
            "Le schema de base n'est pas a jour (version %s, attendue %s) "
            "et les migrations automatiques sont desactivees.",
            runner.current_version(),
            runner.target_version(),
        )

    context = ApplicationContext(
        settings=settings,
        database=database,
        schema_version=runner.current_version(),
        applied_migrations=applied,
    )
    logger.info("Base prete (schema version %s)", context.schema_version)
    return context

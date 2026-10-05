"""Amorcage de l'application.

Sequence de demarrage, volontairement unique et partagee entre l'interface
graphique, les tests d'integration et les futurs points d'entree (API REST,
outils en ligne de commande) :

1. lecture de la configuration ;
2. creation des repertoires de donnees ;
3. initialisation de la journalisation ;
4. ouverture de la base ;
5. application des migrations de schema en attente ;
6. chargement du jeu de seuils du moteur de regles (``rules.json``).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.analysis.rules import RULESET_FILENAME, RuleSet, empty_ruleset, load_ruleset
from app.config.logging_config import configure_logging, get_logger
from app.config.settings import Settings, get_settings
from app.core.exceptions import MigrationError, RuleConfigurationError
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
        ruleset: Jeu de seuils applique par toutes les analyses de la session.
        ruleset_error: Erreur de lecture de ``rules.json``, le cas echeant. Le jeu
            vide est alors applique : aucun seuil n'est jamais devine.
    """

    settings: Settings
    database: Database
    schema_version: int
    applied_migrations: tuple[str, ...]
    ruleset: RuleSet = empty_ruleset()
    ruleset_error: RuleConfigurationError | None = None


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
        MigrationError: Une migration de schema a echoue, ou la base a ete creee par
            une version plus recente du logiciel.
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
    _refuse_newer_schema(runner)
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

    ruleset, ruleset_error = _load_ruleset(settings)

    context = ApplicationContext(
        settings=settings,
        database=database,
        schema_version=runner.current_version(),
        applied_migrations=applied,
        ruleset=ruleset,
        ruleset_error=ruleset_error,
    )
    logger.info("Base prete (schema version %s)", context.schema_version)
    return context


def _refuse_newer_schema(runner: MigrationRunner) -> None:
    """Refuse d'ouvrir une base dont le schema est plus recent que le logiciel.

    Une version anterieure du logiciel ne connait pas les colonnes ajoutees depuis :
    l'utiliser sur une telle base risquerait d'ecrire des donnees incoherentes.

    Raises:
        MigrationError: Le schema de la base est plus recent que celui attendu.
    """
    current, target = runner.current_version(), runner.target_version()
    if current > target:
        raise MigrationError(
            "La base de donnees provient d'une version plus recente de l'application.",
            cause=(
                f"Le schema de la base est en version {current}, alors que cette version "
                f"du logiciel ne connait que la version {target}."
            ),
            action=(
                "Utilisez la version la plus recente de l'application. La base n'a pas "
                "ete modifiee."
            ),
            technical_detail=f"schema {current} > attendu {target}",
        )


def _load_ruleset(settings: Settings) -> tuple[RuleSet, RuleConfigurationError | None]:
    """Charge le jeu de seuils, sans jamais bloquer le demarrage.

    Un fichier ``rules.json`` invalide ne doit pas empecher d'archiver ni de consulter
    les donnees : le jeu vide est applique (aucun depassement recherche) et l'erreur
    est conservee pour etre presentee dans la page Parametres.

    Returns:
        Le jeu de seuils et l'eventuelle erreur de lecture.
    """
    try:
        return load_ruleset(settings.data_dir / RULESET_FILENAME), None
    except RuleConfigurationError as exc:
        logger.error("Jeu de regles ignore : %s (%s)", exc.message, exc.technical_detail)
        return empty_ruleset(), exc

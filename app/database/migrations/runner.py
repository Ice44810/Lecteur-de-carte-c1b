"""Mecanisme de migration de schema.

Pourquoi ne pas utiliser Alembic ? Parce que la base est un fichier local
appartenant a l'utilisateur, souvent manipule sans terminal : la mise a jour doit
etre automatique, tracable et lisible. Ce runner reste volontairement minimal et
explicite, et pourra etre remplace par Alembic le jour ou une base PostgreSQL
partagee entrera en jeu (phase 14/15).

Principes :

* chaque migration porte un numero de version entier strictement croissant ;
* une migration deja appliquee ne l'est jamais deux fois (table ``schema_migrations``) ;
* chaque migration s'execute dans une transaction : en cas d'echec, la base reste
  dans son etat precedent et une :class:`MigrationError` est levee ;
* aucune migration ne supprime de donnees.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import SQLAlchemyError

from app.config.logging_config import get_logger
from app.core.exceptions import MigrationError
from app.core.timeutils import utcnow

__all__ = [
    "Migration",
    "MigrationRunner",
    "SCHEMA_MIGRATIONS_TABLE",
]

logger = get_logger(__name__)

SCHEMA_MIGRATIONS_TABLE = "schema_migrations"

_CREATE_TRACKING_TABLE = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA_MIGRATIONS_TABLE} (
    version     INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    applied_at  TEXT NOT NULL
)
"""


@dataclass(frozen=True, slots=True)
class Migration:
    """Une migration de schema unitaire.

    Attributes:
        version: Numero de version, unique et strictement croissant.
        name: Description courte, journalisee lors de l'application.
        upgrade: Fonction appliquant la migration sur une connexion ouverte.
    """

    version: int
    name: str
    upgrade: Callable[[Connection], None]


class MigrationRunner:
    """Applique les migrations manquantes sur une base.

    Args:
        engine: Moteur cible.
        migrations: Liste des migrations connues (ordre indifferent).

    Raises:
        MigrationError: Deux migrations partagent le meme numero de version.
    """

    def __init__(self, engine: Engine, migrations: Sequence[Migration]) -> None:
        self._engine = engine
        self._migrations = sorted(migrations, key=lambda migration: migration.version)
        self._validate_versions()

    def _validate_versions(self) -> None:
        """Verifie l'unicite des numeros de version."""
        versions = [migration.version for migration in self._migrations]
        duplicates = {version for version in versions if versions.count(version) > 1}
        if duplicates:
            raise MigrationError(
                "Le jeu de migrations est incoherent.",
                cause=f"Numeros de version en doublon : {sorted(duplicates)}.",
                action="Corrigez la declaration des migrations avant de relancer l'application.",
            )

    # ------------------------------------------------------------------ #
    # Etat
    # ------------------------------------------------------------------ #
    def ensure_tracking_table(self) -> None:
        """Cree la table de suivi des migrations si elle n'existe pas."""
        with self._engine.begin() as connection:
            connection.execute(text(_CREATE_TRACKING_TABLE))

    def applied_versions(self) -> list[int]:
        """Retourne la liste triee des versions deja appliquees."""
        self.ensure_tracking_table()
        with self._engine.connect() as connection:
            rows = connection.execute(
                text(f"SELECT version FROM {SCHEMA_MIGRATIONS_TABLE} ORDER BY version")
            ).all()
        return [int(row[0]) for row in rows]

    def current_version(self) -> int:
        """Retourne la version de schema courante (``0`` si la base est vierge)."""
        applied = self.applied_versions()
        return applied[-1] if applied else 0

    def target_version(self) -> int:
        """Retourne la version de schema attendue par cette version du logiciel."""
        return self._migrations[-1].version if self._migrations else 0

    def pending(self) -> list[Migration]:
        """Retourne les migrations restant a appliquer, dans l'ordre."""
        applied = set(self.applied_versions())
        return [migration for migration in self._migrations if migration.version not in applied]

    def is_up_to_date(self) -> bool:
        """Indique si le schema est a jour."""
        return not self.pending()

    # ------------------------------------------------------------------ #
    # Application
    # ------------------------------------------------------------------ #
    def upgrade(self) -> list[Migration]:
        """Applique toutes les migrations manquantes.

        Returns:
            La liste des migrations effectivement appliquees.

        Raises:
            MigrationError: Une migration a echoue ; la base reste inchangee pour
                cette migration et les suivantes ne sont pas tentees.
        """
        pending = self.pending()
        if not pending:
            logger.debug("Schema de base deja a jour (version %s)", self.current_version())
            return []

        applied: list[Migration] = []
        for migration in pending:
            logger.info("Application de la migration %04d - %s", migration.version, migration.name)
            try:
                with self._engine.begin() as connection:
                    migration.upgrade(connection)
                    self._record(connection, migration, utcnow())
            except SQLAlchemyError as exc:
                logger.error(
                    "Echec de la migration %04d - %s : %s",
                    migration.version,
                    migration.name,
                    exc,
                )
                raise MigrationError(
                    "La mise a jour de la base de donnees a echoue.",
                    cause=(
                        f"La migration {migration.version:04d} ({migration.name}) "
                        "n'a pas pu etre appliquee."
                    ),
                    action=(
                        "Aucune donnee n'a ete supprimee. Conservez une copie du fichier "
                        "de base et du journal, puis signalez l'anomalie."
                    ),
                    technical_detail=str(exc),
                ) from exc
            applied.append(migration)

        logger.info("Schema de base en version %s", self.current_version())
        return applied

    @staticmethod
    def _record(connection: Connection, migration: Migration, moment: datetime) -> None:
        """Enregistre l'application d'une migration dans la table de suivi."""
        connection.execute(
            text(
                f"INSERT INTO {SCHEMA_MIGRATIONS_TABLE} (version, name, applied_at) "
                "VALUES (:version, :name, :applied_at)"
            ),
            {
                "version": migration.version,
                "name": migration.name,
                "applied_at": moment.isoformat(),
            },
        )

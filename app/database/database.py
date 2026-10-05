"""Moteur SQLAlchemy, sessions et initialisation de la base locale.

Cette classe est le seul point de l'application qui connait le SGBD utilise.
Les depots recoivent une ``Session`` ; ils ne creent jamais de moteur. Une
implementation PostgreSQL consistera donc simplement a fournir une autre URL
(cf. section 23 du cahier des charges).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.config.logging_config import get_logger
from app.config.settings import Settings, get_settings
from app.core.exceptions import DatabaseError
from app.database.models import Base

__all__ = ["Database", "get_database", "reset_database"]

logger = get_logger(__name__)


def _configure_sqlite_connection(dbapi_connection: Any, _connection_record: Any) -> None:
    """Applique les PRAGMA SQLite necessaires a chaque nouvelle connexion.

    * ``foreign_keys=ON`` : SQLite ignore les cles etrangeres par defaut, ce qui
      rendrait les contraintes ``ondelete`` inoperantes ;
    * ``journal_mode=WAL`` : lectures concurrentes pendant un import ;
    * ``synchronous=NORMAL`` : compromis durabilite/performance acceptable en WAL ;
    * ``busy_timeout`` : evite un echec immediat si la base est momentanement prise.
    """
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=5000")
    finally:
        cursor.close()


class Database:
    """Encapsule un moteur SQLAlchemy et sa fabrique de sessions.

    Args:
        url: URL SQLAlchemy de la base.
        echo: Active la trace SQL (developpement uniquement).
        create_parent_dir: Cree le repertoire parent du fichier SQLite si besoin.
    """

    def __init__(self, url: str, *, echo: bool = False, create_parent_dir: bool = True) -> None:
        self._url = url
        if create_parent_dir:
            self._ensure_parent_directory(url)
        self._engine: Engine = create_engine(
            url,
            echo=echo,
            future=True,
            # SQLite refuse par defaut le partage d'une connexion entre threads.
            # L'interface Qt delegue les imports a des workers : on autorise donc
            # le partage, la serialisation etant assuree par le pool SQLAlchemy.
            connect_args={"check_same_thread": False} if url.startswith("sqlite") else {},
        )
        if self._engine.dialect.name == "sqlite":
            event.listen(self._engine, "connect", _configure_sqlite_connection)
        self._session_factory = sessionmaker(
            bind=self._engine,
            expire_on_commit=False,
            autoflush=False,
        )
        logger.debug("Moteur de base initialise (%s)", self.safe_url)

    # ------------------------------------------------------------------ #
    # Proprietes
    # ------------------------------------------------------------------ #
    @property
    def engine(self) -> Engine:
        """Moteur SQLAlchemy sous-jacent."""
        return self._engine

    @property
    def url(self) -> str:
        """URL complete de la base."""
        return self._url

    @property
    def safe_url(self) -> str:
        """URL sans eventuel mot de passe, utilisable dans les journaux."""
        return self._engine.url.render_as_string(hide_password=True)

    # ------------------------------------------------------------------ #
    # Sessions
    # ------------------------------------------------------------------ #
    def create_session(self) -> Session:
        """Cree une session non geree (l'appelant est responsable de la fermer)."""
        return self._session_factory()

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Fournit une session transactionnelle.

        La transaction est validee a la sortie normale du bloc, annulee en cas
        d'exception. Une erreur SQLAlchemy est traduite en :class:`DatabaseError`
        afin que l'interface dispose d'un message exploitable.

        Yields:
            La session ouverte.

        Raises:
            DatabaseError: Erreur d'acces a la base.
        """
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except SQLAlchemyError as exc:
            session.rollback()
            logger.error("Erreur de base de donnees : %s", exc)
            raise DatabaseError(technical_detail=str(exc)) from exc
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ------------------------------------------------------------------ #
    # Schema
    # ------------------------------------------------------------------ #
    def create_all(self) -> None:
        """Cree toutes les tables declarees (utilise par les tests et le bootstrap)."""
        Base.metadata.create_all(self._engine)

    def drop_all(self) -> None:
        """Supprime toutes les tables declarees.

        Reserve aux tests : l'application ne supprime jamais de donnees
        automatiquement (section 17 du cahier des charges).
        """
        Base.metadata.drop_all(self._engine)

    def check_connection(self) -> bool:
        """Verifie que la base est joignable.

        Returns:
            ``True`` si une requete triviale aboutit.

        Raises:
            DatabaseError: La base est injoignable.
        """
        try:
            with self._engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except SQLAlchemyError as exc:
            raise DatabaseError(technical_detail=str(exc)) from exc
        return True

    def dispose(self) -> None:
        """Ferme toutes les connexions du pool."""
        self._engine.dispose()

    # ------------------------------------------------------------------ #
    # Interne
    # ------------------------------------------------------------------ #
    @staticmethod
    def _ensure_parent_directory(url: str) -> None:
        """Cree le repertoire du fichier SQLite si l'URL en designe un."""
        prefix_candidates = ("sqlite+pysqlite:///", "sqlite:///")
        for prefix in prefix_candidates:
            if url.startswith(prefix):
                raw_path = url[len(prefix) :]
                if raw_path and raw_path != ":memory:":
                    Path(raw_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
                return


_database: Database | None = None


def get_database(settings: Settings | None = None) -> Database:
    """Retourne l'instance de base partagee du processus.

    Args:
        settings: Configuration a utiliser lors de la premiere creation.

    Returns:
        L'unique instance :class:`Database`.
    """
    global _database
    if _database is None:
        settings = settings or get_settings()
        _database = Database(settings.database_url, echo=settings.sql_echo)
    return _database


def reset_database() -> None:
    """Libere l'instance partagee (tests, changement de configuration)."""
    global _database
    if _database is not None:
        _database.dispose()
    _database = None

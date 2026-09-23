"""Tests du moteur de base et de la gestion des sessions."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text

from app.config.settings import Settings
from app.core.exceptions import DatabaseError
from app.database.database import Database, get_database, reset_database
from app.database.models import Driver


def test_les_pragma_sqlite_sont_appliques(database: Database) -> None:
    """Les cles etrangeres doivent etre actives : SQLite les ignore par defaut."""
    with database.engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar() == 1
        assert connection.execute(text("PRAGMA journal_mode")).scalar() == "wal"


def test_le_repertoire_de_la_base_est_cree(tmp_path: Path) -> None:
    cible = tmp_path / "profond" / "sous" / "repertoire" / "tachy.sqlite3"
    database = Database(f"sqlite+pysqlite:///{cible}")
    try:
        assert cible.parent.is_dir()
    finally:
        database.dispose()


def test_check_connection_reussit(database: Database) -> None:
    assert database.check_connection() is True


def test_session_valide_a_la_sortie_du_bloc(migrated_database: Database) -> None:
    with migrated_database.session() as session:
        session.add(Driver(card_number="CARTE-COMMIT-001"))

    with migrated_database.session() as session:
        assert session.query(Driver).count() == 1


def test_session_annule_en_cas_d_exception(migrated_database: Database) -> None:
    with pytest.raises(RuntimeError):
        with migrated_database.session() as session:
            session.add(Driver(card_number="CARTE-ROLLBACK-001"))
            session.flush()
            raise RuntimeError("echec metier simule")

    with migrated_database.session() as session:
        assert session.query(Driver).count() == 0


def test_erreur_sql_traduite_en_erreur_exploitable(migrated_database: Database) -> None:
    with pytest.raises(DatabaseError) as exc_info:
        with migrated_database.session() as session:
            session.add(Driver(card_number="CARTE-UNIQUE-001"))
            session.add(Driver(card_number="CARTE-UNIQUE-001"))

    message, cause, action = exc_info.value.user_report()
    assert message and cause and action
    assert exc_info.value.technical_detail


def test_safe_url_ne_contient_pas_de_mot_de_passe(database: Database) -> None:
    assert "://" in database.safe_url


def test_get_database_retourne_une_instance_partagee(settings: Settings) -> None:
    reset_database()
    try:
        assert get_database(settings) is get_database()
    finally:
        reset_database()


def test_drop_all_est_reserve_aux_tests(migrated_database: Database) -> None:
    """``drop_all`` existe pour les tests ; l'application ne supprime jamais de donnees."""
    from sqlalchemy import inspect

    migrated_database.drop_all()

    assert "drivers" not in inspect(migrated_database.engine).get_table_names()

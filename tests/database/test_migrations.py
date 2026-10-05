"""Tests du mecanisme de migration de schema."""

from __future__ import annotations

import pytest
from sqlalchemy import Connection, inspect, text

from app.config.settings import Settings
from app.core.exceptions import MigrationError
from app.database.database import Database
from app.database.migrations import MIGRATIONS, build_runner
from app.database.migrations.m0001_initial_schema import EXPECTED_TABLES
from app.database.migrations.runner import SCHEMA_MIGRATIONS_TABLE, Migration, MigrationRunner


def test_base_vierge_est_en_version_zero(database: Database) -> None:
    runner = build_runner(database.engine)

    assert runner.current_version() == 0
    assert not runner.is_up_to_date()


def test_upgrade_cree_toutes_les_tables_attendues(database: Database) -> None:
    runner = build_runner(database.engine)

    applied = runner.upgrade()

    assert [migration.version for migration in applied] == [1, 2]
    tables = set(inspect(database.engine).get_table_names())
    assert set(EXPECTED_TABLES) <= tables
    assert SCHEMA_MIGRATIONS_TABLE in tables


def test_upgrade_est_idempotent(database: Database) -> None:
    runner = build_runner(database.engine)
    runner.upgrade()

    assert runner.upgrade() == []
    assert runner.is_up_to_date()
    assert runner.current_version() == runner.target_version()


def test_upgrade_enregistre_la_version_appliquee(database: Database) -> None:
    runner = build_runner(database.engine)
    runner.upgrade()

    with database.engine.connect() as connection:
        rows = connection.execute(
            text(f"SELECT version, name, applied_at FROM {SCHEMA_MIGRATIONS_TABLE}")
        ).all()

    assert len(rows) == len(MIGRATIONS)
    assert rows[0][0] == 1
    assert rows[0][1]
    assert rows[0][2]


def test_versions_en_doublon_refusees(database: Database) -> None:
    def _noop(_connection: Connection) -> None:
        return None

    with pytest.raises(MigrationError, match="incoherent") as erreur:
        MigrationRunner(
            database.engine,
            [Migration(1, "premiere", _noop), Migration(1, "doublon", _noop)],
        )

    assert "doublon" in erreur.value.cause


def test_migration_en_echec_est_signalee_sans_perdre_de_donnees(database: Database) -> None:
    def _valide(connection: Connection) -> None:
        connection.execute(text("CREATE TABLE donnees_importantes (id INTEGER PRIMARY KEY)"))

    def _invalide(connection: Connection) -> None:
        connection.execute(text("CREATE TABLE ceci n est pas du SQL"))

    runner = MigrationRunner(
        database.engine,
        [Migration(1, "table valide", _valide), Migration(2, "migration cassee", _invalide)],
    )

    with pytest.raises(MigrationError) as exc_info:
        runner.upgrade()

    message, cause, action = exc_info.value.user_report()
    assert "0002" in cause
    assert "supprimee" in action
    assert message
    assert runner.current_version() == 1
    assert "donnees_importantes" in inspect(database.engine).get_table_names()


def test_bootstrap_amene_la_base_a_la_version_cible(settings: Settings) -> None:
    from app.bootstrap import bootstrap

    database = Database(settings.database_url)
    try:
        context = bootstrap(settings, database=database)

        assert context.schema_version == build_runner(database.engine).target_version()
        assert context.applied_migrations
    finally:
        database.dispose()


def test_bootstrap_sans_migration_automatique_ne_modifie_pas_la_base(settings: Settings) -> None:
    from app.bootstrap import bootstrap

    database = Database(settings.database_url)
    try:
        context = bootstrap(settings, database=database, run_migrations=False)

        assert context.schema_version == 0
        assert context.applied_migrations == ()
    finally:
        database.dispose()


def test_la_migration_0002_complete_une_base_en_version_1(database: Database) -> None:
    """Une base creee par la version precedente recoit les nouvelles colonnes."""
    from sqlalchemy import text

    from app.database.migrations import m0001, m0002
    from app.database.migrations.runner import MigrationRunner

    MigrationRunner(database.engine, (m0001,)).upgrade()
    with database.engine.begin() as connexion:
        connexion.execute(text("ALTER TABLE activities DROP COLUMN card_inserted"))
        connexion.execute(text("DROP INDEX ix_tachograph_files_content_sha256"))
        connexion.execute(text("ALTER TABLE tachograph_files DROP COLUMN content_sha256"))

    MigrationRunner(database.engine, (m0001, m0002)).upgrade()

    colonnes = {item["name"] for item in inspect(database.engine).get_columns("activities")}
    assert {"card_inserted", "manual_entry", "crew"} <= colonnes
    colonnes = {item["name"] for item in inspect(database.engine).get_columns("tachograph_files")}
    assert "content_sha256" in colonnes

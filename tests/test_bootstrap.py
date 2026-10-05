"""Tests de la sequence de demarrage.

L'amorcage est le seul chemin d'initialisation de l'application : il doit creer les
repertoires, ouvrir la base, appliquer les migrations et retourner un contexte
exploitable. Un echec doit etre explicite et ne jamais laisser la base a moitie migree.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.bootstrap import ApplicationContext, bootstrap
from app.config.settings import Settings
from app.database.database import Database
from app.database.migrations import build_runner


def test_l_amorcage_retourne_un_contexte_complet(settings: Settings, database: Database) -> None:
    contexte = bootstrap(settings, database=database)

    assert isinstance(contexte, ApplicationContext)
    assert contexte.settings is settings
    assert contexte.database is database
    assert contexte.schema_version > 0


def test_l_amorcage_cree_les_repertoires_de_donnees(settings: Settings, database: Database) -> None:
    bootstrap(settings, database=database)

    for repertoire in settings.managed_directories:
        assert repertoire.is_dir()


def test_l_amorcage_applique_les_migrations_en_attente(
    settings: Settings, database: Database
) -> None:
    contexte = bootstrap(settings, database=database)

    assert contexte.applied_migrations
    assert build_runner(database.engine).is_up_to_date() is True


def test_un_second_amorcage_n_applique_aucune_migration(
    settings: Settings, database: Database
) -> None:
    bootstrap(settings, database=database)

    contexte = bootstrap(settings, database=database)

    assert contexte.applied_migrations == ()
    assert contexte.schema_version > 0


def test_les_migrations_peuvent_etre_desactivees(settings: Settings, database: Database) -> None:
    contexte = bootstrap(settings, database=database, run_migrations=False)

    assert contexte.applied_migrations == ()
    assert contexte.schema_version == 0


def test_l_amorcage_cree_le_journal(settings: Settings, database: Database) -> None:
    contexte = bootstrap(settings, database=database)

    assert contexte.settings.log_dir.is_dir()


def test_l_amorcage_ouvre_une_base_fonctionnelle(settings: Settings, database: Database) -> None:
    contexte = bootstrap(settings, database=database)

    with contexte.database.session() as session:
        assert session.is_active


def test_un_repertoire_de_donnees_impossible_produit_un_message_exploitable(
    tmp_path: Path,
) -> None:
    from app.core.exceptions import StorageError

    obstacle = tmp_path / "obstacle"
    obstacle.write_text("ceci est un fichier, pas un repertoire", encoding="utf-8")
    configuration = Settings(data_dir=obstacle / "data", log_dir=tmp_path / "logs")

    with pytest.raises(StorageError) as erreur:
        bootstrap(configuration)

    message, cause, action = erreur.value.user_report()
    assert message and cause
    assert "TACHY_DATA_DIR" in action
    assert "Traceback" not in message


def test_le_contexte_est_immuable(settings: Settings, database: Database) -> None:
    """Le contexte est partage par toute l'interface : il ne doit pas etre modifiable."""
    contexte = bootstrap(settings, database=database)

    with pytest.raises(AttributeError):
        contexte.schema_version = 99  # type: ignore[misc]

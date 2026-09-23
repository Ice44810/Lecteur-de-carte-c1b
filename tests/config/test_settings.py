"""Tests de la configuration.

Exigence de la section 27 du cahier des charges : aucun chemin absolu ecrit en dur,
tout passe par ``pathlib`` et par des variables d'environnement prefixees ``TACHY_``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config.settings import Settings, get_settings, reset_settings_cache
from app.core.exceptions import StorageError


def test_les_chemins_derivent_de_la_racine_de_donnees(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "donnees")

    assert settings.imports_dir == settings.data_dir / "imports"
    assert settings.originals_dir == settings.data_dir / "originals"
    assert settings.exports_dir == settings.data_dir / "exports"
    assert settings.database_dir == settings.data_dir / "database"
    assert settings.database_path == settings.database_dir / settings.database_filename


def test_la_racine_est_absolue_et_developpee(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    settings = Settings(data_dir=Path("relatif"))

    assert settings.data_dir.is_absolute()


def test_url_de_base_est_une_url_sqlite(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)

    assert settings.database_url.startswith("sqlite+pysqlite:///")
    assert str(settings.database_path) in settings.database_url


def test_variables_d_environnement_prefixees(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TACHY_DATA_DIR", str(tmp_path / "depuis-env"))
    monkeypatch.setenv("TACHY_LOG_LEVEL", "ERROR")
    reset_settings_cache()

    settings = Settings()

    assert settings.data_dir == (tmp_path / "depuis-env").resolve()
    assert settings.log_level == "ERROR"


def test_niveau_de_journalisation_invalide_refuse(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        Settings(data_dir=tmp_path, log_level="VERBEUX")


def test_nom_de_base_avec_separateur_refuse(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="database_filename"):
        Settings(data_dir=tmp_path, database_filename="sous/repertoire.sqlite3")


def test_ensure_directories_cree_tous_les_repertoires(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "nouveau", log_dir=tmp_path / "nouveau" / "logs")

    settings.ensure_directories()

    for directory in settings.managed_directories:
        assert directory.is_dir()


def test_ensure_directories_explique_un_echec(tmp_path: Path) -> None:
    obstacle = tmp_path / "fichier"
    obstacle.write_text("je ne suis pas un repertoire", encoding="utf-8")
    settings = Settings(data_dir=obstacle / "donnees")

    with pytest.raises(StorageError) as exc_info:
        settings.ensure_directories()

    message, cause, action = exc_info.value.user_report()
    assert "TACHY_DATA_DIR" in action
    assert message and cause


def test_get_settings_est_mis_en_cache() -> None:
    reset_settings_cache()

    assert get_settings() is get_settings()

    reset_settings_cache()

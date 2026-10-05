"""Tests des emplacements de donnees selon le systeme, et de la reprise de l'ancien nom."""

from __future__ import annotations

from pathlib import Path, PureWindowsPath

import pytest

from app.config.platform_paths import default_data_dir, default_log_dir, platform_family
from app.config.settings import Settings

HOME = Path("/home/utilisateur")


@pytest.mark.parametrize(
    ("valeur", "famille"),
    [("win32", "windows"), ("darwin", "macos"), ("linux", "linux"), ("freebsd14", "linux")],
)
def test_la_famille_de_systeme_est_reconnue(valeur: str, famille: str) -> None:
    assert platform_family(valeur) == famille


def test_windows_range_les_donnees_dans_localappdata() -> None:
    environnement = {"LOCALAPPDATA": r"C:\Users\Marie\AppData\Local"}

    donnees = default_data_dir(platform="win32", environ=environnement, home=HOME)
    journaux = default_log_dir(platform="win32", environ=environnement, home=HOME)

    assert PureWindowsPath(str(donnees)).parts[-1] == "TachoLibre"
    assert str(donnees).startswith(r"C:\Users\Marie\AppData\Local")
    assert journaux.parts[-2:] == ("TachoLibre", "logs")


def test_windows_sans_localappdata_se_replie_sur_le_profil() -> None:
    assert default_data_dir(platform="win32", environ={}, home=HOME) == (
        HOME / "AppData" / "Local" / "TachoLibre"
    )


def test_macos_suit_les_conventions_de_library() -> None:
    assert default_data_dir(platform="darwin", environ={}, home=HOME) == (
        HOME / "Library" / "Application Support" / "TachoLibre"
    )
    assert default_log_dir(platform="darwin", environ={}, home=HOME) == (
        HOME / "Library" / "Logs" / "TachoLibre"
    )


def test_linux_suit_les_conventions_xdg(tmp_path: Path) -> None:
    environnement = {
        "XDG_DATA_HOME": str(tmp_path / "data"),
        "XDG_STATE_HOME": str(tmp_path / "state"),
    }

    assert default_data_dir(platform="linux", environ=environnement, home=HOME) == (
        tmp_path / "data" / "tacholibre"
    )
    assert default_log_dir(platform="linux", environ=environnement, home=HOME) == (
        tmp_path / "state" / "tacholibre" / "logs"
    )


def test_linux_reprend_le_dossier_de_l_ancien_nom(tmp_path: Path) -> None:
    """Les donnees d'une version anterieure restent utilisees, sans etre deplacees."""
    ancien = tmp_path / ".local" / "share" / "tachy-linux"
    ancien.mkdir(parents=True)

    assert default_data_dir(platform="linux", environ={}, home=tmp_path) == ancien


def test_le_nouveau_dossier_l_emporte_des_qu_il_existe(tmp_path: Path) -> None:
    (tmp_path / ".local" / "share" / "tachy-linux").mkdir(parents=True)
    nouveau = tmp_path / ".local" / "share" / "tacholibre"
    nouveau.mkdir()

    assert default_data_dir(platform="linux", environ={}, home=tmp_path) == nouveau


def test_l_ancien_prefixe_de_variable_reste_accepte(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("TACHOLIBRE_LOG_LEVEL", raising=False)
    monkeypatch.setenv("TACHY_LOG_LEVEL", "ERROR")

    assert Settings(data_dir=tmp_path).log_level == "ERROR"


def test_le_nouveau_prefixe_l_emporte_sur_l_ancien(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TACHY_LOG_LEVEL", "ERROR")
    monkeypatch.setenv("TACHOLIBRE_LOG_LEVEL", "WARNING")

    assert Settings(data_dir=tmp_path).log_level == "WARNING"


def test_la_base_de_l_ancien_nom_est_reutilisee(tmp_path: Path) -> None:
    reglages = Settings(data_dir=tmp_path)
    reglages.database_dir.mkdir(parents=True)
    ancienne = reglages.database_dir / "tachy.sqlite3"
    ancienne.write_bytes(b"")

    assert reglages.database_path == ancienne


def test_une_nouvelle_installation_utilise_le_nouveau_nom_de_base(tmp_path: Path) -> None:
    assert Settings(data_dir=tmp_path).database_path.name == "tacholibre.sqlite3"


def test_un_nom_de_base_avec_separateur_windows_est_refuse(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        Settings(data_dir=tmp_path, database_filename=r"sous\base.sqlite3")

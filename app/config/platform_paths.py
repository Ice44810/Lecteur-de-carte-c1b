"""Emplacements des donnees et des journaux selon le systeme d'exploitation.

Conventions de chaque systeme :

* Windows : donnees dans ``%LOCALAPPDATA%/TachoLibre``, journaux dans son
  sous-dossier ``logs`` ;
* macOS : donnees dans ``~/Library/Application Support/TachoLibre``, journaux dans
  ``~/Library/Logs/TachoLibre`` ;
* Linux : donnees dans ``$XDG_DATA_HOME/tacholibre`` (par defaut
  ``~/.local/share/tacholibre``), journaux dans ``$XDG_STATE_HOME/tacholibre/logs``
  (par defaut ``~/.local/state/tacholibre/logs``).

Les donnees vont sous ``%LOCALAPPDATA%`` et non ``%APPDATA%`` sous Windows : la base et
les fichiers archives sont propres au poste et ne doivent pas suivre un profil
itinerant.

Reprise de l'ancien nom : sous Linux, si les dossiers ``tachy-linux`` d'une version
anterieure existent et que les nouveaux n'existent pas encore, les anciens restent
utilises. Rien n'est deplace ni copie automatiquement.

Les fonctions recoivent systeme, environnement et dossier personnel en parametres,
afin d'etre testables sur n'importe quel systeme.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from pathlib import Path

from app import APP_NAME, APP_SLUG, LEGACY_APP_SLUG

__all__ = ["default_data_dir", "default_log_dir", "platform_family"]


def platform_family(platform: str | None = None) -> str:
    """Retourne ``"windows"``, ``"macos"`` ou ``"linux"`` (tout autre Unix compris)."""
    value = platform if platform is not None else sys.platform
    if value.startswith("win"):
        return "windows"
    if value == "darwin":
        return "macos"
    return "linux"


def _windows_base(environ: Mapping[str, str], home: Path) -> Path:
    local = environ.get("LOCALAPPDATA")
    return Path(local) if local else home / "AppData" / "Local"


def default_data_dir(
    *,
    platform: str | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    """Racine des donnees applicatives pour le systeme courant."""
    env = os.environ if environ is None else environ
    user_home = home if home is not None else Path.home()
    family = platform_family(platform)
    if family == "windows":
        return _windows_base(env, user_home) / APP_NAME
    if family == "macos":
        return user_home / "Library" / "Application Support" / APP_NAME
    base = (
        Path(env["XDG_DATA_HOME"]) if env.get("XDG_DATA_HOME") else user_home / ".local" / "share"
    )
    return _prefer_legacy(base / APP_SLUG, base / LEGACY_APP_SLUG)


def default_log_dir(
    *,
    platform: str | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    """Repertoire des journaux pour le systeme courant."""
    env = os.environ if environ is None else environ
    user_home = home if home is not None else Path.home()
    family = platform_family(platform)
    if family == "windows":
        return _windows_base(env, user_home) / APP_NAME / "logs"
    if family == "macos":
        return user_home / "Library" / "Logs" / APP_NAME
    base = (
        Path(env["XDG_STATE_HOME"]) if env.get("XDG_STATE_HOME") else user_home / ".local" / "state"
    )
    return _prefer_legacy(base / APP_SLUG / "logs", base / LEGACY_APP_SLUG / "logs")


def _prefer_legacy(current: Path, legacy: Path) -> Path:
    """Conserve le dossier de l'ancien nom tant que le nouveau n'existe pas."""
    if not current.exists() and legacy.exists():
        return legacy
    return current

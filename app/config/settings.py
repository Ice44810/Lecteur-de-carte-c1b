"""Parametres de l'application.

Tous les chemins sont manipules avec ``pathlib`` et resolus dynamiquement : aucun
chemin absolu de type ``/home/<utilisateur>/...`` n'est ecrit en dur (section 27
du cahier des charges).

Ordre de priorite de la racine de donnees :

1. variable d'environnement ``TACHY_DATA_DIR`` (ou ``.env``) ;
2. repertoire ``data/`` du depot lorsque l'application tourne depuis les sources
   (mode developpement, detecte par la presence de ``pyproject.toml``) ;
3. ``$XDG_DATA_HOME/tachy-linux`` (par defaut ``~/.local/share/tachy-linux``)
   lorsque l'application est installee sur le systeme.

Toutes les variables d'environnement utilisent le prefixe ``TACHY_``. Exemple :

.. code-block:: bash

    TACHY_DATA_DIR=/srv/tachy TACHY_LOG_LEVEL=DEBUG python -m app.main
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.exceptions import StorageError

__all__ = ["Settings", "get_settings", "reset_settings_cache", "project_root"]

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

_APP_DIR_NAME = "tachy-linux"


def project_root() -> Path:
    """Retourne la racine du depot lorsque l'application tourne depuis les sources.

    Returns:
        Le repertoire contenant ``pyproject.toml``, ou le repertoire parent du
        paquet ``app`` si le marqueur est absent (cas d'une installation).
    """
    package_dir = Path(__file__).resolve().parent.parent  # .../app
    candidate = package_dir.parent
    return candidate


def _default_data_dir() -> Path:
    """Determine la racine de donnees par defaut (voir docstring du module)."""
    root = project_root()
    if (root / "pyproject.toml").is_file():
        return root / "data"
    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg_data_home) if xdg_data_home else Path.home() / ".local" / "share"
    return base / _APP_DIR_NAME


def _default_log_dir() -> Path:
    """Determine le repertoire de journaux par defaut."""
    root = project_root()
    if (root / "pyproject.toml").is_file():
        return root / "logs"
    xdg_state_home = os.environ.get("XDG_STATE_HOME")
    base = Path(xdg_state_home) if xdg_state_home else Path.home() / ".local" / "state"
    return base / _APP_DIR_NAME / "logs"


class Settings(BaseSettings):
    """Parametres de configuration valides de l'application.

    Attributes:
        app_name: Nom affiche dans l'interface.
        company_name: Raison sociale de l'entreprise de transport (en-tetes de rapports).
        data_dir: Racine de toutes les donnees applicatives.
        log_level: Niveau de journalisation du fichier de log.
        console_log_level: Niveau de journalisation de la sortie standard.
        database_filename: Nom du fichier SQLite.
        sql_echo: Active la trace SQL de SQLAlchemy (developpement uniquement).
        auto_migrate: Applique les migrations de schema au demarrage.
        pcsc_enabled: Autorise l'utilisation du lecteur PC/SC.
        timezone_display: Fuseau utilise pour l'affichage (le stockage reste en UTC).
    """

    model_config = SettingsConfigDict(
        env_prefix="TACHY_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        validate_assignment=True,
    )

    app_name: str = "tachy-linux"
    company_name: str = ""

    data_dir: Path = Field(default_factory=_default_data_dir)
    log_dir: Path = Field(default_factory=_default_log_dir)

    database_filename: str = "tachy.sqlite3"
    sql_echo: bool = False
    auto_migrate: bool = True

    log_level: LogLevel = "INFO"
    console_log_level: LogLevel = "WARNING"
    log_max_bytes: int = Field(default=5 * 1024 * 1024, gt=0)
    log_backup_count: int = Field(default=5, ge=0)

    pcsc_enabled: bool = True
    timezone_display: str = "Europe/Paris"

    @field_validator("data_dir", "log_dir", mode="after")
    @classmethod
    def _expand(cls, value: Path) -> Path:
        """Developpe ``~`` et rend le chemin absolu."""
        return value.expanduser().resolve()

    @field_validator("database_filename", mode="after")
    @classmethod
    def _validate_filename(cls, value: str) -> str:
        """Refuse un nom de fichier contenant un separateur de chemin."""
        if not value or "/" in value or value in {".", ".."}:
            raise ValueError("database_filename doit etre un simple nom de fichier")
        return value

    # ------------------------------------------------------------------ #
    # Chemins derives
    # ------------------------------------------------------------------ #
    @computed_field  # type: ignore[prop-decorator]
    @property
    def imports_dir(self) -> Path:
        """Repertoire de travail des imports en cours."""
        return self.data_dir / "imports"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def originals_dir(self) -> Path:
        """Repertoire d'archivage immuable des fichiers originaux."""
        return self.data_dir / "originals"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def exports_dir(self) -> Path:
        """Repertoire de sortie des rapports (PDF, Excel, CSV)."""
        return self.data_dir / "exports"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_dir(self) -> Path:
        """Repertoire contenant la base SQLite."""
        return self.data_dir / "database"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_path(self) -> Path:
        """Chemin complet du fichier SQLite."""
        return self.database_dir / self.database_filename

    @computed_field  # type: ignore[prop-decorator]
    @property
    def log_path(self) -> Path:
        """Chemin complet du fichier de journal principal."""
        return self.log_dir / "app.log"

    @property
    def database_url(self) -> str:
        """URL SQLAlchemy de la base locale.

        Les services ne doivent pas construire cette URL eux-memes : une
        implementation PostgreSQL pourra remplacer cette propriete sans modifier
        les couches superieures (cf. section 23 du cahier des charges).
        """
        return f"sqlite+pysqlite:///{self.database_path}"

    @property
    def managed_directories(self) -> tuple[Path, ...]:
        """Liste des repertoires que l'application doit creer au demarrage."""
        return (
            self.data_dir,
            self.imports_dir,
            self.originals_dir,
            self.exports_dir,
            self.database_dir,
            self.log_dir,
        )

    def ensure_directories(self) -> None:
        """Cree les repertoires applicatifs manquants.

        Raises:
            StorageError: Un repertoire n'a pas pu etre cree.
        """
        for directory in self.managed_directories:
            try:
                directory.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise StorageError(
                    f"Le repertoire {directory} n'a pas pu etre cree.",
                    cause="Les droits d'ecriture sont insuffisants ou le disque est plein.",
                    action=(
                        "Choisissez un autre repertoire de donnees "
                        "(variable TACHY_DATA_DIR) ou corrigez les permissions."
                    ),
                    technical_detail=str(exc),
                ) from exc


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Retourne l'instance de configuration partagee (mise en cache).

    Returns:
        L'unique instance ``Settings`` du processus.
    """
    return Settings()


def reset_settings_cache() -> None:
    """Vide le cache de configuration.

    Utilise par les tests et apres une modification des parametres depuis
    l'interface, afin de relire l'environnement.
    """
    get_settings.cache_clear()

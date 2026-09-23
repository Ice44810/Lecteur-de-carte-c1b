"""Fixtures partagees par toute la suite de tests.

Principes retenus :

* **aucun test n'ecrit dans le repertoire de donnees reel** : ``TACHY_DATA_DIR`` est
  redirige vers un repertoire temporaire pour toute la session, avant le premier
  import d'un module applicatif qui lirait la configuration ;
* **chaque test dispose d'une base vierge**, creee par le vrai mecanisme de
  migration afin que celui-ci soit teste en meme temps que le reste ;
* **les caches de processus sont vides entre les tests** (configuration et base
  partagees), pour eviter toute dependance d'ordre.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.bootstrap import ApplicationContext, bootstrap
from app.config.settings import Settings, reset_settings_cache
from app.core.enums import ActivityType, FileType, ParsingStatus
from app.database.database import Database, reset_database
from app.database.models import Activity, Driver, TachographFile, Vehicle

# --------------------------------------------------------------------------- #
# Isolation de l'environnement
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True, scope="session")
def _isolated_environment(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    """Redirige la racine de donnees vers un repertoire temporaire de session."""
    root = tmp_path_factory.mktemp("tachy-data")
    previous = {
        key: os.environ.get(key) for key in ("TACHY_DATA_DIR", "TACHY_LOG_DIR", "TACHY_LOG_LEVEL")
    }
    os.environ["TACHY_DATA_DIR"] = str(root)
    os.environ["TACHY_LOG_DIR"] = str(root / "logs")
    os.environ["TACHY_LOG_LEVEL"] = "DEBUG"
    # Toute creation de widget pendant les tests doit rester sans ecran : sans cette
    # variable, Qt interrompt brutalement le processus au lieu de lever une exception.
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    reset_settings_cache()
    yield root
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    reset_settings_cache()


@pytest.fixture(autouse=True)
def _reset_process_caches() -> Iterator[None]:
    """Vide les caches partages avant et apres chaque test."""
    reset_settings_cache()
    reset_database()
    yield
    reset_database()
    reset_settings_cache()


# --------------------------------------------------------------------------- #
# Configuration et base
# --------------------------------------------------------------------------- #
@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Configuration pointant sur un repertoire de donnees propre au test."""
    return Settings(data_dir=tmp_path / "data", log_dir=tmp_path / "logs")


@pytest.fixture
def database(settings: Settings) -> Iterator[Database]:
    """Base SQLite temporaire, schema cree par les migrations."""
    instance = Database(settings.database_url)
    try:
        yield instance
    finally:
        instance.dispose()


@pytest.fixture
def context(settings: Settings, database: Database) -> ApplicationContext:
    """Contexte applicatif complet (configuration, base migree)."""
    return bootstrap(settings, database=database)


@pytest.fixture
def migrated_database(context: ApplicationContext) -> Database:
    """Base dont le schema est deja a jour."""
    return context.database


# --------------------------------------------------------------------------- #
# Donnees de reference
# --------------------------------------------------------------------------- #
@pytest.fixture
def driver(migrated_database: Database) -> Driver:
    """Conducteur de test enregistre en base."""
    with migrated_database.session() as session:
        record = Driver(
            card_number="TESTCARD0000001",
            first_name="Camille",
            last_name="Durand",
            card_issuing_country="F",
        )
        session.add(record)
        session.flush()
        session.expunge(record)
    return record


@pytest.fixture
def vehicle(migrated_database: Database) -> Vehicle:
    """Vehicule de test enregistre en base."""
    with migrated_database.session() as session:
        record = Vehicle(registration="AA-123-BB", registration_country="F")
        session.add(record)
        session.flush()
        session.expunge(record)
    return record


@pytest.fixture
def reference_day() -> datetime:
    """Journee de reference des tests : mardi 15 septembre 2026, 00:00 UTC."""
    return datetime(2026, 9, 15, tzinfo=UTC)


@pytest.fixture
def add_activity(migrated_database: Database, driver: Driver):
    """Retourne une fonction d'ajout d'activite en base.

    La fonction retournee accepte un type d'activite et deux instants, et retourne
    l'identifiant de l'activite creee.
    """

    def _add(
        activity_type: ActivityType,
        start: datetime,
        end: datetime,
        *,
        driver_id: int | None = None,
        vehicle_id: int | None = None,
        source_file_id: int | None = None,
    ) -> int:
        with migrated_database.session() as session:
            activity = Activity.from_bounds(
                driver_id=driver_id if driver_id is not None else driver.id,
                activity_type=activity_type,
                start_datetime=start,
                end_datetime=end,
                vehicle_id=vehicle_id,
                source_file_id=source_file_id,
            )
            session.add(activity)
            session.flush()
            return int(activity.id)

    return _add


@pytest.fixture
def add_file(migrated_database: Database):
    """Retourne une fonction d'enregistrement d'un fichier importe en base."""

    def _add(
        *,
        filename: str = "carte.C1B",
        file_type: FileType = FileType.C1B,
        sha256: str | None = None,
        file_size: int = 1024,
        imported_at: datetime | None = None,
        parsing_status: ParsingStatus = ParsingStatus.PENDING,
        driver_id: int | None = None,
        original_path: str = "/tmp/originals/carte.C1B",
    ) -> int:
        digest = sha256 or (f"{abs(hash(filename)):064x}"[:64])
        with migrated_database.session() as session:
            record = TachographFile(
                filename=filename,
                file_type=file_type,
                sha256=digest,
                original_path=original_path,
                file_size=file_size,
                imported_at=imported_at or datetime(2026, 9, 20, 8, 30, tzinfo=UTC),
                parsing_status=parsing_status,
                driver_id=driver_id,
            )
            session.add(record)
            session.flush()
            return int(record.id)

    return _add


# --------------------------------------------------------------------------- #
# Fichiers binaires de test
# --------------------------------------------------------------------------- #
@pytest.fixture
def empty_c1b_file(tmp_path: Path) -> Path:
    """Fichier ``.C1B`` de 0 octet."""
    path = tmp_path / "vide.C1B"
    path.write_bytes(b"")
    return path


@pytest.fixture
def opaque_c1b_file(tmp_path: Path) -> Path:
    """Fichier ``.C1B`` de contenu arbitraire.

    Le contenu est volontairement **quelconque** : aucun octet ne pretend
    reproduire la structure d'un vrai telechargement de carte, ce qui serait
    inventer une donnee tachygraphique. Il sert a verifier l'archivage, le calcul
    d'empreinte et le comportement du decodage face a une structure non confirmee.
    """
    path = tmp_path / "conducteur.C1B"
    path.write_bytes(bytes(range(256)) * 4)
    return path


@pytest.fixture
def opaque_v1b_file(tmp_path: Path) -> Path:
    """Fichier ``.V1B`` de contenu arbitraire (meme reserve que pour le C1B)."""
    path = tmp_path / "vehicule.V1B"
    path.write_bytes(bytes(reversed(range(256))) * 4)
    return path


@pytest.fixture
def unsupported_file(tmp_path: Path) -> Path:
    """Fichier d'extension non prise en charge."""
    path = tmp_path / "document.pdf"
    path.write_bytes(b"%PDF-1.7 contenu non tachygraphique")
    return path

"""Migration 0001 : creation du schema initial.

Le schema initial est genere depuis les metadonnees SQLAlchemy plutot qu'ecrit en
SQL a la main : c'est la seule migration pour laquelle cette approche est sure,
puisqu'elle part d'une base vierge. Les migrations suivantes devront contenir du
SQL explicite (``ALTER TABLE`` ...), afin de ne pas dependre de l'etat courant des
modeles.
"""

from __future__ import annotations

from sqlalchemy import Connection, inspect

from app.database.migrations.runner import Migration
from app.database.models import Base

__all__ = ["migration"]

VERSION = 1
NAME = "schema initial (conducteurs, vehicules, fichiers, activites, analyses, anomalies)"

EXPECTED_TABLES = (
    "drivers",
    "vehicles",
    "tachograph_files",
    "activities",
    "analyses",
    "infringements",
)


def upgrade(connection: Connection) -> None:
    """Cree les tables initiales si elles sont absentes.

    Args:
        connection: Connexion ouverte dans la transaction de migration.
    """
    Base.metadata.create_all(bind=connection, checkfirst=True)

    inspector = inspect(connection)
    existing = set(inspector.get_table_names())
    missing = [table for table in EXPECTED_TABLES if table not in existing]
    if missing:  # pragma: no cover - garde-fou, ne doit jamais se produire
        raise RuntimeError(f"Tables manquantes apres creation du schema : {missing}")


migration = Migration(version=VERSION, name=NAME, upgrade=upgrade)

"""Migration 0002 : donnees decodees des cartes conducteur.

Ajouts, sans suppression ni modification de donnees existantes :

* ``activities`` : statut de la carte (inseree ou non), saisie manuelle, equipage ;
* ``drivers`` : debut de validite et autorite de delivrance de la carte, langue,
  permis de conduire ;
* ``tachograph_files`` : empreinte du contenu hors signatures, qui reconnait deux
  telechargements d'une meme carte dont seules les signatures different (les
  signatures ECDSA de 2e generation changent a chaque telechargement).

Chaque colonne n'est ajoutee que si elle est absente : une base creee par la migration
0001 d'une version recente du logiciel peut deja les contenir.
"""

from __future__ import annotations

from sqlalchemy import Connection, inspect, text

from app.database.migrations.runner import Migration

__all__ = ["migration"]

VERSION = 2
NAME = "donnees decodees des cartes (statut des activites, permis, empreinte du contenu)"

COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("activities", "card_inserted", "BOOLEAN"),
    ("activities", "manual_entry", "BOOLEAN"),
    ("activities", "crew", "BOOLEAN"),
    ("drivers", "card_validity_begin", "DATE"),
    ("drivers", "card_issuing_authority", "VARCHAR(64)"),
    ("drivers", "preferred_language", "VARCHAR(2)"),
    ("drivers", "licence_number", "VARCHAR(16)"),
    ("drivers", "licence_issuing_authority", "VARCHAR(64)"),
    ("drivers", "licence_issuing_country", "VARCHAR(3)"),
    ("tachograph_files", "content_sha256", "VARCHAR(64)"),
)


def upgrade(connection: Connection) -> None:
    """Ajoute les colonnes absentes et l'index de l'empreinte du contenu."""
    inspector = inspect(connection)
    for table, column, sql_type in COLUMNS:
        existing = {item["name"] for item in inspector.get_columns(table)}
        if column not in existing:
            connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}"))
    connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_tachograph_files_content_sha256 "
            "ON tachograph_files (content_sha256)"
        )
    )


migration = Migration(version=VERSION, name=NAME, upgrade=upgrade)

"""Migration 0003 : appartenance des conducteurs et des vehicules a la flotte.

Le decodage d'une carte ajoute au referentiel tous les vehicules utilises par le
conducteur, y compris ceux d'autres entreprises. La colonne ``in_fleet`` distingue :

* ``1`` : appartenance confirmee (fiche saisie, ou confirmee par l'utilisateur) ;
* ``NULL`` : fiche creee automatiquement par un import, a confirmer.

Reprise des donnees existantes : une fiche qui n'a ete alimentee par aucun import
(aucun fichier pour un conducteur, aucune activite pour un vehicule) a
necessairement ete saisie, elle est donc marquee comme appartenant a la flotte.
"""

from __future__ import annotations

from sqlalchemy import Connection, inspect, text

from app.database.migrations.runner import Migration

__all__ = ["migration"]

VERSION = 3
NAME = "appartenance des conducteurs et des vehicules a la flotte"


def upgrade(connection: Connection) -> None:
    """Ajoute ``in_fleet`` et marque les fiches saisies manuellement."""
    inspector = inspect(connection)
    for table in ("drivers", "vehicles"):
        if "in_fleet" not in {item["name"] for item in inspector.get_columns(table)}:
            connection.execute(text(f"ALTER TABLE {table} ADD COLUMN in_fleet BOOLEAN"))
    connection.execute(
        text(
            "UPDATE drivers SET in_fleet = 1 WHERE in_fleet IS NULL AND id NOT IN "
            "(SELECT driver_id FROM tachograph_files WHERE driver_id IS NOT NULL)"
        )
    )
    connection.execute(
        text(
            "UPDATE vehicles SET in_fleet = 1 WHERE in_fleet IS NULL AND id NOT IN "
            "(SELECT vehicle_id FROM activities WHERE vehicle_id IS NOT NULL)"
        )
    )


migration = Migration(version=VERSION, name=NAME, upgrade=upgrade)

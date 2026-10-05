"""Couche d'acces aux donnees : moteur, modeles, depots et migrations.

Aucune couche superieure (services, interface) ne doit importer SQLAlchemy
directement : elle passe par les depots (``app.database.repositories``). Cette
regle permettra de substituer une implementation PostgreSQL sans toucher aux
services (cf. section 23 du cahier des charges).
"""

from app.database.database import Database, get_database, reset_database

__all__ = ["Database", "get_database", "reset_database"]

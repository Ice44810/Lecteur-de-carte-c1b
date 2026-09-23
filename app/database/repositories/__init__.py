"""Depots d'acces aux donnees.

Un depot traduit une intention metier en requete. Il ne contient jamais de regle
metier, et ne valide jamais la transaction : cette responsabilite appartient au
service appelant.
"""

from app.database.repositories.activity_repository import ActivityRepository
from app.database.repositories.analysis_repository import AnalysisRepository
from app.database.repositories.base import BaseRepository
from app.database.repositories.driver_repository import DriverRepository
from app.database.repositories.import_repository import ImportRepository
from app.database.repositories.infringement_repository import InfringementRepository
from app.database.repositories.vehicle_repository import VehicleRepository

__all__ = [
    "ActivityRepository",
    "AnalysisRepository",
    "BaseRepository",
    "DriverRepository",
    "ImportRepository",
    "InfringementRepository",
    "VehicleRepository",
]

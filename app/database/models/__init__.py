"""Modeles ORM de l'application.

Importer ce paquet suffit a enregistrer toutes les tables dans
``Base.metadata`` : c'est indispensable avant toute creation de schema ou
migration.
"""

from app.database.models.activity import Activity
from app.database.models.analysis import Analysis
from app.database.models.base import Base, TimestampMixin
from app.database.models.driver import Driver
from app.database.models.enums import (
    ActivityType,
    FileType,
    ParsingStatus,
    RuleStatus,
    Severity,
)
from app.database.models.infringement import Infringement
from app.database.models.tachograph_file import TachographFile
from app.database.models.types import UTCDateTime
from app.database.models.vehicle import Vehicle

__all__ = [
    "Activity",
    "ActivityType",
    "Analysis",
    "Base",
    "Driver",
    "FileType",
    "Infringement",
    "ParsingStatus",
    "RuleStatus",
    "Severity",
    "TachographFile",
    "TimestampMixin",
    "UTCDateTime",
    "Vehicle",
]

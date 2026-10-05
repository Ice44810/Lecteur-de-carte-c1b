"""Contrats des depots (``Protocol``).

Les services sont types contre ces protocoles, jamais contre les implementations
SQLAlchemy. Le jour ou les donnees viendront d'une API REST adossee a PostgreSQL
(phases 14 et 15), il suffira de fournir des classes respectant ces protocoles :
aucun service n'aura a etre modifie.

Seules les operations reellement utilisees par les services figurent ici : un
protocole doit rester le plus petit possible.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Protocol, runtime_checkable

from app.database.models import (
    Activity,
    ActivityType,
    Analysis,
    Driver,
    Infringement,
    TachographFile,
    Vehicle,
)

__all__ = [
    "DriverRepositoryProtocol",
    "VehicleRepositoryProtocol",
    "ImportRepositoryProtocol",
    "ActivityRepositoryProtocol",
    "AnalysisRepositoryProtocol",
    "InfringementRepositoryProtocol",
]


@runtime_checkable
class DriverRepositoryProtocol(Protocol):
    """Acces aux conducteurs."""

    def get(self, entity_id: int) -> Driver | None: ...

    def get_by_card_number(self, card_number: str) -> Driver | None: ...

    def list_all(self, *, limit: int | None = ..., offset: int = ...) -> list[Driver]: ...

    def count(self) -> int: ...

    def add(self, entity: Driver) -> Driver: ...


@runtime_checkable
class VehicleRepositoryProtocol(Protocol):
    """Acces aux vehicules."""

    def get(self, entity_id: int) -> Vehicle | None: ...

    def get_by_registration(self, registration: str) -> Vehicle | None: ...

    def list_all(self, *, limit: int | None = ..., offset: int = ...) -> list[Vehicle]: ...

    def count(self) -> int: ...

    def add(self, entity: Vehicle) -> Vehicle: ...


@runtime_checkable
class ImportRepositoryProtocol(Protocol):
    """Acces au journal des fichiers importes."""

    def get(self, entity_id: int) -> TachographFile | None: ...

    def get_by_sha256(self, sha256: str) -> TachographFile | None: ...

    def exists_sha256(self, sha256: str) -> bool: ...

    def count(self) -> int: ...

    def add(self, entity: TachographFile) -> TachographFile: ...

    def list_recent(self, *, limit: int = ...) -> list[TachographFile]: ...

    def last_import_datetime(self) -> datetime | None: ...


@runtime_checkable
class ActivityRepositoryProtocol(Protocol):
    """Acces aux activites des conducteurs."""

    def add_all(self, entities: list[Activity]) -> list[Activity]: ...

    def list_for_driver(
        self,
        driver_id: int,
        *,
        period_start: datetime | None = ...,
        period_end: datetime | None = ...,
        activity_types: tuple[ActivityType, ...] | None = ...,
        vehicle_id: int | None = ...,
    ) -> list[Activity]: ...

    def duration_by_type(
        self,
        driver_id: int,
        *,
        period_start: datetime,
        period_end: datetime,
    ) -> dict[ActivityType, int]: ...


@runtime_checkable
class AnalysisRepositoryProtocol(Protocol):
    """Acces aux analyses enregistrees."""

    def add(self, entity: Analysis) -> Analysis: ...

    def latest_for_driver(self, driver_id: int) -> Analysis | None: ...


@runtime_checkable
class InfringementRepositoryProtocol(Protocol):
    """Acces aux anomalies et depassements apparents."""

    def add_all(self, entities: list[Infringement]) -> list[Infringement]: ...

    def count_open(self) -> int: ...

    def list_recent(self, *, limit: int = ...) -> list[Infringement]: ...

    def list_for_driver(
        self,
        driver_id: int,
        *,
        period_start: date | None = ...,
        period_end: date | None = ...,
    ) -> list[Infringement]: ...

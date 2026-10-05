"""Tests des contrats de depot.

Ces tests protegent une decision d'architecture : les services sont types contre des
protocoles, jamais contre les implementations SQLAlchemy. Le jour ou les donnees
viendront d'une API REST adossee a PostgreSQL, il suffira de fournir des classes
respectant ces protocoles.

Verifier ici que chaque depot concret satisfait bien son protocole evite qu'une
signature derive silencieusement et rende la substitution impossible.
"""

from __future__ import annotations

import pytest

from app.database.database import Database
from app.database.repositories import (
    ActivityRepository,
    AnalysisRepository,
    DriverRepository,
    ImportRepository,
    InfringementRepository,
    VehicleRepository,
)
from app.database.repositories.interfaces import (
    ActivityRepositoryProtocol,
    AnalysisRepositoryProtocol,
    DriverRepositoryProtocol,
    ImportRepositoryProtocol,
    InfringementRepositoryProtocol,
    VehicleRepositoryProtocol,
)

COUPLES = (
    (DriverRepository, DriverRepositoryProtocol),
    (VehicleRepository, VehicleRepositoryProtocol),
    (ImportRepository, ImportRepositoryProtocol),
    (ActivityRepository, ActivityRepositoryProtocol),
    (AnalysisRepository, AnalysisRepositoryProtocol),
    (InfringementRepository, InfringementRepositoryProtocol),
)


@pytest.mark.parametrize(
    ("depot", "protocole"), COUPLES, ids=[depot.__name__ for depot, _ in COUPLES]
)
def test_chaque_depot_satisfait_son_contrat(
    migrated_database: Database, depot: type, protocole: type
) -> None:
    with migrated_database.session() as session:
        assert isinstance(depot(session), protocole)


def test_un_objet_quelconque_ne_satisfait_pas_un_contrat() -> None:
    """Le contrat doit etre discriminant, sinon il ne protege rien."""
    assert not isinstance(object(), DriverRepositoryProtocol)


def test_les_contrats_restent_minimaux() -> None:
    """Un protocole ne doit exposer que ce dont les services ont besoin."""
    methodes = {nom for nom in dir(AnalysisRepositoryProtocol) if not nom.startswith("_")}

    assert methodes == {"add", "latest_for_driver"}

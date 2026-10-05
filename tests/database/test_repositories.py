"""Tests des depots (couche d'acces aux donnees)."""

from __future__ import annotations

from datetime import UTC, date, datetime

from app.core.enums import ActivityType, FileType, ParsingStatus, RuleStatus, Severity
from app.database.database import Database
from app.database.models import Driver, Infringement, Vehicle
from app.database.repositories import (
    ActivityRepository,
    DriverRepository,
    ImportRepository,
    InfringementRepository,
    VehicleRepository,
)


# --------------------------------------------------------------------------- #
# Conducteurs
# --------------------------------------------------------------------------- #
def test_get_by_card_number(migrated_database: Database, driver: Driver) -> None:
    with migrated_database.session() as session:
        trouve = DriverRepository(session).get_by_card_number(driver.card_number)

    assert trouve is not None
    assert trouve.id == driver.id


def test_get_or_create_ne_cree_pas_deux_fois(migrated_database: Database) -> None:
    with migrated_database.session() as session:
        premier, cree = DriverRepository(session).get_or_create("CARTE-OC-001")
        assert cree is True
        identifiant = premier.id

    with migrated_database.session() as session:
        second, cree = DriverRepository(session).get_or_create("CARTE-OC-001")
        assert cree is False
        assert second.id == identifiant


def test_search_par_nom_et_par_carte(migrated_database: Database, driver: Driver) -> None:
    with migrated_database.session() as session:
        repository = DriverRepository(session)

        assert [item.id for item in repository.search("Durand")] == [driver.id]
        assert [item.id for item in repository.search("TESTCARD")] == [driver.id]
        assert repository.search("introuvable") == []


def test_liste_ordonnee(migrated_database: Database) -> None:
    with migrated_database.session() as session:
        session.add_all(
            [
                Driver(card_number="C-2", last_name="Zola"),
                Driver(card_number="C-1", last_name="Aubert"),
            ]
        )

    with migrated_database.session() as session:
        noms = [item.last_name for item in DriverRepository(session).list_ordered()]

    assert noms == ["Aubert", "Zola"]


# --------------------------------------------------------------------------- #
# Vehicules
# --------------------------------------------------------------------------- #
def test_vehicule_par_immatriculation(migrated_database: Database, vehicle: Vehicle) -> None:
    with migrated_database.session() as session:
        trouve = VehicleRepository(session).get_by_registration(vehicle.registration)

    assert trouve is not None
    assert trouve.id == vehicle.id


# --------------------------------------------------------------------------- #
# Imports
# --------------------------------------------------------------------------- #
def test_deduplication_par_empreinte(migrated_database: Database, add_file) -> None:
    empreinte = "1" * 64
    add_file(filename="original.C1B", sha256=empreinte)

    with migrated_database.session() as session:
        repository = ImportRepository(session)

        assert repository.exists_sha256(empreinte) is True
        assert repository.exists_sha256("2" * 64) is False


def test_recherche_d_empreinte_insensible_a_la_casse(migrated_database: Database, add_file) -> None:
    add_file(filename="original.C1B", sha256="ab" * 32)

    with migrated_database.session() as session:
        assert ImportRepository(session).get_by_sha256("AB" * 32) is not None


def test_filtres_de_l_historique(migrated_database: Database, add_file, driver: Driver) -> None:
    add_file(filename="carte.C1B", file_type=FileType.C1B, sha256="3" * 64, driver_id=driver.id)
    add_file(filename="vehicule.V1B", file_type=FileType.V1B, sha256="4" * 64)

    with migrated_database.session() as session:
        repository = ImportRepository(session)

        assert len(repository.list_filtered(file_type=FileType.C1B)) == 1
        assert len(repository.list_filtered(file_type=FileType.V1B)) == 1
        assert len(repository.list_filtered(driver_id=driver.id)) == 1
        assert len(repository.list_filtered(search="vehicule")) == 1
        assert len(repository.list_filtered(search="3333")) == 1
        assert len(repository.list_filtered(parsing_status=ParsingStatus.SUCCESS)) == 0


def test_comptages_et_dernier_import(migrated_database: Database, add_file) -> None:
    add_file(
        filename="ancien.C1B",
        sha256="5" * 64,
        imported_at=datetime(2026, 9, 1, 8, 0, tzinfo=UTC),
    )
    add_file(
        filename="recent.C1B",
        sha256="6" * 64,
        imported_at=datetime(2026, 9, 20, 17, 45, tzinfo=UTC),
    )

    with migrated_database.session() as session:
        repository = ImportRepository(session)

        assert repository.count() == 2
        assert repository.count_by_type(FileType.C1B) == 2
        assert repository.count_by_status(ParsingStatus.PENDING) == 2
        assert repository.last_import_datetime() == datetime(2026, 9, 20, 17, 45, tzinfo=UTC)
        assert [item.filename for item in repository.list_pending_parsing()] == [
            "ancien.C1B",
            "recent.C1B",
        ]


# --------------------------------------------------------------------------- #
# Activites
# --------------------------------------------------------------------------- #
def test_les_activites_chevauchant_la_periode_sont_retenues(
    migrated_database: Database, driver: Driver, add_activity
) -> None:
    """Un repos commence la veille doit rester visible sur la journee analysee."""
    add_activity(
        ActivityType.REST,
        datetime(2026, 9, 14, 22, 0, tzinfo=UTC),
        datetime(2026, 9, 15, 6, 0, tzinfo=UTC),
    )

    with migrated_database.session() as session:
        trouvees = ActivityRepository(session).list_for_driver(
            driver.id,
            period_start=datetime(2026, 9, 15, tzinfo=UTC),
            period_end=datetime(2026, 9, 16, tzinfo=UTC),
        )

    assert len(trouvees) == 1


def test_total_par_type_ne_compte_que_les_activites_contenues(
    migrated_database: Database, driver: Driver, add_activity
) -> None:
    add_activity(
        ActivityType.DRIVING,
        datetime(2026, 9, 15, 8, 0, tzinfo=UTC),
        datetime(2026, 9, 15, 12, 0, tzinfo=UTC),
    )
    add_activity(
        ActivityType.DRIVING,
        datetime(2026, 9, 15, 23, 0, tzinfo=UTC),
        datetime(2026, 9, 16, 1, 0, tzinfo=UTC),
    )

    with migrated_database.session() as session:
        totaux = ActivityRepository(session).duration_by_type(
            driver.id,
            period_start=datetime(2026, 9, 15, tzinfo=UTC),
            period_end=datetime(2026, 9, 16, tzinfo=UTC),
        )

    assert totaux == {ActivityType.DRIVING: 4 * 3600}


def test_total_duration_et_derniere_activite(
    migrated_database: Database, driver: Driver, add_activity
) -> None:
    add_activity(
        ActivityType.DRIVING,
        datetime(2026, 9, 15, 8, 0, tzinfo=UTC),
        datetime(2026, 9, 15, 11, 0, tzinfo=UTC),
    )
    add_activity(
        ActivityType.REST,
        datetime(2026, 9, 15, 11, 0, tzinfo=UTC),
        datetime(2026, 9, 15, 12, 0, tzinfo=UTC),
    )

    with migrated_database.session() as session:
        repository = ActivityRepository(session)

        assert (
            repository.total_duration(
                activity_type=ActivityType.DRIVING,
                period_start=datetime(2026, 9, 15, tzinfo=UTC),
                period_end=datetime(2026, 9, 16, tzinfo=UTC),
            )
            == 3 * 3600
        )
        assert repository.latest_activity_datetime(driver.id) == datetime(
            2026, 9, 15, 12, 0, tzinfo=UTC
        )
        assert (
            repository.count_drivers_with_activity(
                period_start=datetime(2026, 9, 15, tzinfo=UTC),
                period_end=datetime(2026, 9, 16, tzinfo=UTC),
            )
            == 1
        )


def test_tracabilite_activite_vers_fichier_source(
    migrated_database: Database, add_file, add_activity
) -> None:
    file_id = add_file(filename="source.C1B", sha256="7" * 64)
    add_activity(
        ActivityType.DRIVING,
        datetime(2026, 9, 15, 8, 0, tzinfo=UTC),
        datetime(2026, 9, 15, 9, 0, tzinfo=UTC),
        source_file_id=file_id,
    )

    with migrated_database.session() as session:
        assert len(ActivityRepository(session).list_for_file(file_id)) == 1


# --------------------------------------------------------------------------- #
# Anomalies
# --------------------------------------------------------------------------- #
def test_comptage_des_anomalies_ouvertes(migrated_database: Database, driver: Driver) -> None:
    with migrated_database.session() as session:
        session.add_all(
            [
                Infringement(
                    driver_id=driver.id,
                    occurred_on=date(2026, 9, 15),
                    rule_code="A",
                    status=RuleStatus.VIOLATION,
                    severity=Severity.HIGH,
                    description="Depassement apparent.",
                ),
                Infringement(
                    driver_id=driver.id,
                    occurred_on=date(2026, 9, 16),
                    rule_code="B",
                    status=RuleStatus.WARNING,
                    severity=Severity.LOW,
                    description="Situation a verifier.",
                    acknowledged_at=datetime(2026, 9, 17, tzinfo=UTC),
                ),
            ]
        )

    with migrated_database.session() as session:
        repository = InfringementRepository(session)

        assert repository.count() == 2
        assert repository.count_open() == 1
        assert repository.count_by_status(RuleStatus.VIOLATION) == 1
        assert repository.count_by_severity() == {Severity.HIGH: 1, Severity.LOW: 1}


def test_un_depot_ne_valide_jamais_de_lui_meme(migrated_database: Database) -> None:
    """La decision de validation appartient au service, pas au depot."""
    session = migrated_database.create_session()
    try:
        DriverRepository(session).add(Driver(card_number="CARTE-SANS-COMMIT"))
        session.flush()
        session.rollback()
    finally:
        session.close()

    with migrated_database.session() as session:
        assert DriverRepository(session).count() == 0

"""Tests des modeles de donnees metier."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from app.core.enums import ActivityType, FileType, ParsingStatus, RuleStatus, Severity
from app.core.exceptions import DatabaseError
from app.database.database import Database
from app.database.models import Activity, Driver, Infringement, TachographFile, Vehicle


# --------------------------------------------------------------------------- #
# Conducteur
# --------------------------------------------------------------------------- #
def test_le_nom_affiche_utilise_la_carte_a_defaut_de_nom() -> None:
    assert Driver(card_number="F0000000000001").display_name == "Carte F0000000000001"


def test_le_nom_affiche_combine_nom_et_prenom() -> None:
    driver = Driver(card_number="F1", first_name="Camille", last_name="Durand")

    assert driver.display_name == "DURAND Camille"


def test_carte_expiree(driver: Driver) -> None:
    driver.card_expiry_date = date(2026, 1, 31)

    assert driver.is_card_expired(date(2026, 9, 15)) is True
    assert driver.is_card_expired(date(2025, 12, 31)) is False


def test_carte_sans_date_d_expiration_ne_permet_aucune_conclusion() -> None:
    """Sans information, le modele retourne ``None`` plutot que de conclure."""
    assert Driver(card_number="F1").is_card_expired(date(2026, 9, 15)) is None


def test_numero_de_carte_unique(migrated_database: Database) -> None:
    with pytest.raises(DatabaseError):
        with migrated_database.session() as session:
            session.add(Driver(card_number="DOUBLON-001"))
            session.add(Driver(card_number="DOUBLON-001"))


def test_repr_ne_contient_pas_de_donnee_personnelle() -> None:
    driver = Driver(card_number="F1234567890", first_name="Camille", last_name="Durand")

    representation = repr(driver)

    assert "Camille" not in representation
    assert "Durand" not in representation


# --------------------------------------------------------------------------- #
# Fichier importe
# --------------------------------------------------------------------------- #
def test_empreinte_unique_empeche_le_doublon(migrated_database: Database) -> None:
    empreinte = "b" * 64

    with migrated_database.session() as session:
        session.add(
            TachographFile(
                filename="premier.C1B",
                file_type=FileType.C1B,
                sha256=empreinte,
                original_path="/originals/premier.C1B",
                file_size=10,
            )
        )

    with pytest.raises(DatabaseError):
        with migrated_database.session() as session:
            session.add(
                TachographFile(
                    filename="second.C1B",
                    file_type=FileType.C1B,
                    sha256=empreinte,
                    original_path="/originals/second.C1B",
                    file_size=10,
                )
            )


def test_empreinte_de_mauvaise_longueur_refusee(migrated_database: Database) -> None:
    with pytest.raises(DatabaseError):
        with migrated_database.session() as session:
            session.add(
                TachographFile(
                    filename="court.C1B",
                    file_type=FileType.C1B,
                    sha256="trop-court",
                    original_path="/originals/court.C1B",
                    file_size=10,
                )
            )


def test_taille_negative_refusee(migrated_database: Database) -> None:
    with pytest.raises(DatabaseError):
        with migrated_database.session() as session:
            session.add(
                TachographFile(
                    filename="negatif.C1B",
                    file_type=FileType.C1B,
                    sha256="c" * 64,
                    original_path="/originals/negatif.C1B",
                    file_size=-1,
                )
            )


def test_etat_de_decodage_par_defaut(migrated_database: Database, add_file) -> None:
    file_id = add_file(filename="attente.C1B", sha256="d" * 64)

    with migrated_database.session() as session:
        record = session.get(TachographFile, file_id)
        assert record is not None
        assert record.parsing_status is ParsingStatus.PENDING


def test_taille_lisible_et_empreinte_courte() -> None:
    record = TachographFile(
        filename="x.C1B",
        file_type=FileType.C1B,
        sha256="e" * 64,
        original_path="/originals/x.C1B",
        file_size=2048,
    )

    assert record.human_size == "2.0 Ko"
    assert record.short_sha256 == "e" * 12 + "..."


# --------------------------------------------------------------------------- #
# Vehicule
# --------------------------------------------------------------------------- #
def test_immatriculation_unique(migrated_database: Database) -> None:
    with pytest.raises(DatabaseError):
        with migrated_database.session() as session:
            session.add(Vehicle(registration="AA-999-ZZ"))
            session.add(Vehicle(registration="AA-999-ZZ"))


# --------------------------------------------------------------------------- #
# Activite
# --------------------------------------------------------------------------- #
def test_from_bounds_calcule_la_duree(driver: Driver) -> None:
    activity = Activity.from_bounds(
        driver_id=driver.id,
        activity_type=ActivityType.DRIVING,
        start_datetime=datetime(2026, 9, 15, 8, 0, tzinfo=UTC),
        end_datetime=datetime(2026, 9, 15, 10, 30, tzinfo=UTC),
    )

    assert activity.duration_seconds == 9000


def test_from_bounds_refuse_un_intervalle_inverse(driver: Driver) -> None:
    with pytest.raises(ValueError):
        Activity.from_bounds(
            driver_id=driver.id,
            activity_type=ActivityType.DRIVING,
            start_datetime=datetime(2026, 9, 15, 10, 0, tzinfo=UTC),
            end_datetime=datetime(2026, 9, 15, 8, 0, tzinfo=UTC),
        )


def test_activite_inversee_refusee_par_la_contrainte(
    migrated_database: Database, driver: Driver
) -> None:
    with pytest.raises(DatabaseError):
        with migrated_database.session() as session:
            session.add(
                Activity(
                    driver_id=driver.id,
                    activity_type=ActivityType.DRIVING,
                    start_datetime=datetime(2026, 9, 15, 10, 0, tzinfo=UTC),
                    end_datetime=datetime(2026, 9, 15, 8, 0, tzinfo=UTC),
                    duration_seconds=0,
                )
            )


def test_les_dates_sont_relues_en_utc(
    migrated_database: Database, driver: Driver, add_activity
) -> None:
    """Le stockage est naif ; la relecture doit rendre un instant conscient du fuseau."""
    activity_id = add_activity(
        ActivityType.DRIVING,
        datetime(2026, 9, 15, 8, 0, tzinfo=UTC),
        datetime(2026, 9, 15, 9, 0, tzinfo=UTC),
    )

    with migrated_database.session() as session:
        activity = session.get(Activity, activity_id)
        assert activity is not None
        assert activity.start_datetime.tzinfo is not None
        assert activity.start_datetime == datetime(2026, 9, 15, 8, 0, tzinfo=UTC)


def test_la_cle_etrangere_conducteur_est_verifiee(migrated_database: Database) -> None:
    with pytest.raises(DatabaseError):
        with migrated_database.session() as session:
            session.add(
                Activity.from_bounds(
                    driver_id=99_999,
                    activity_type=ActivityType.DRIVING,
                    start_datetime=datetime(2026, 9, 15, 8, 0, tzinfo=UTC),
                    end_datetime=datetime(2026, 9, 15, 9, 0, tzinfo=UTC),
                )
            )


# --------------------------------------------------------------------------- #
# Anomalie
# --------------------------------------------------------------------------- #
def test_une_anomalie_conserve_sa_source_reglementaire(
    migrated_database: Database, driver: Driver
) -> None:
    with migrated_database.session() as session:
        session.add(
            Infringement(
                driver_id=driver.id,
                occurred_on=date(2026, 9, 15),
                rule_code="DAILY_DRIVING_MAX",
                status=RuleStatus.VIOLATION,
                severity=Severity.MEDIUM,
                description="Depassement apparent du temps de conduite journalier.",
                regulation_reference="Reglement (CE) no 561/2006, article 6 - a verifier",
            )
        )

    with migrated_database.session() as session:
        record = session.query(Infringement).one()
        assert record.regulation_reference
        assert record.is_acknowledged is False


def test_le_vocabulaire_des_anomalies_reste_prudent(
    migrated_database: Database, driver: Driver
) -> None:
    record = Infringement(
        driver_id=driver.id,
        occurred_on=date(2026, 9, 15),
        rule_code="DAILY_DRIVING_MAX",
        status=RuleStatus.VIOLATION,
        severity=Severity.MEDIUM,
        description="Depassement apparent.",
    )

    assert record.status.label == "Depassement apparent"


def test_to_dict_expose_les_colonnes(driver: Driver) -> None:
    donnees = driver.to_dict()

    assert donnees["card_number"] == driver.card_number
    assert "id" in donnees

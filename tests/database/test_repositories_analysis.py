"""Tests des depots d'analyses et d'alertes, et du depot generique.

Deux comportements structurants sont verifies ici :

* une analyse n'est **jamais ecrasee** : relancer un calcul ajoute une ligne, ce qui
  permet de retracer les controles effectues et les seuils appliques ;
* une alerte enregistree reste rattachee a son analyse et a sa source reglementaire.

Les operations generiques du depot de base sont testees au meme endroit, car elles
conditionnent le comportement de tous les autres depots.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from app.core.enums import RuleStatus, Severity
from app.database.database import Database
from app.database.models import Analysis, Driver, Infringement
from app.database.repositories import AnalysisRepository, DriverRepository
from app.database.repositories.infringement_repository import InfringementRepository

JOUR = datetime(2026, 9, 15, tzinfo=UTC)


def _analyse(driver_id: int, *, jours: int = 0, version: str = "test-1") -> Analysis:
    """Construit une analyse couvrant une journee, decalee de ``jours``."""
    debut = JOUR + timedelta(days=jours)
    return Analysis(
        driver_id=driver_id,
        period_start=debut,
        period_end=debut + timedelta(days=1),
        driving_seconds=4 * 3600,
        work_seconds=3600,
        rest_seconds=9 * 3600,
        ruleset_version=version,
    )


def _alerte(
    driver_id: int,
    *,
    jour: date = date(2026, 9, 15),
    status: RuleStatus = RuleStatus.VIOLATION,
    severity: Severity = Severity.MEDIUM,
    analysis_id: int | None = None,
) -> Infringement:
    """Construit une alerte enregistrable."""
    return Infringement(
        driver_id=driver_id,
        analysis_id=analysis_id,
        occurred_on=jour,
        rule_code="TEST_DEPASSEMENT",
        status=status,
        severity=severity,
        description="Depassement apparent a verifier.",
        regulation_reference="Source de test - a confirmer",
    )


# --------------------------------------------------------------------------- #
# Depot des analyses
# --------------------------------------------------------------------------- #
def test_une_base_neuve_ne_contient_aucune_analyse(migrated_database: Database) -> None:
    with migrated_database.session() as session:
        assert AnalysisRepository(session).count() == 0
        assert AnalysisRepository(session).latest_for_driver(1) is None


def test_relancer_une_analyse_ajoute_une_ligne(migrated_database: Database, driver: Driver) -> None:
    """Aucun cliche n'est ecrase : l'historique des controles est conserve."""
    with migrated_database.session() as session:
        depot = AnalysisRepository(session)
        depot.add(_analyse(driver.id, version="test-1"))
        depot.add(_analyse(driver.id, version="test-2"))

    with migrated_database.session() as session:
        assert AnalysisRepository(session).count() == 2


def test_la_derniere_analyse_est_retrouvee(migrated_database: Database, driver: Driver) -> None:
    with migrated_database.session() as session:
        depot = AnalysisRepository(session)
        depot.add(_analyse(driver.id, jours=0))
        depot.add(_analyse(driver.id, jours=3))

    with migrated_database.session() as session:
        derniere = AnalysisRepository(session).latest_for_driver(driver.id)
        assert derniere is not None
        assert derniere.period_start == JOUR + timedelta(days=3)


def test_les_analyses_d_un_conducteur_sont_triees_du_plus_recent(
    migrated_database: Database, driver: Driver
) -> None:
    with migrated_database.session() as session:
        depot = AnalysisRepository(session)
        for decalage in (0, 1, 2):
            depot.add(_analyse(driver.id, jours=decalage))

    with migrated_database.session() as session:
        analyses = AnalysisRepository(session).list_for_driver(driver.id)
        assert [item.period_start for item in analyses] == [
            JOUR + timedelta(days=2),
            JOUR + timedelta(days=1),
            JOUR,
        ]


def test_les_analyses_se_filtrent_par_periode(migrated_database: Database, driver: Driver) -> None:
    with migrated_database.session() as session:
        depot = AnalysisRepository(session)
        depot.add(_analyse(driver.id, jours=0))
        depot.add(_analyse(driver.id, jours=10))

    with migrated_database.session() as session:
        analyses = AnalysisRepository(session).list_for_driver(
            driver.id,
            period_start=JOUR + timedelta(days=5),
            period_end=JOUR + timedelta(days=20),
        )
        assert len(analyses) == 1
        assert analyses[0].period_start == JOUR + timedelta(days=10)


def test_le_nombre_d_analyses_retournees_est_limitable(
    migrated_database: Database, driver: Driver
) -> None:
    with migrated_database.session() as session:
        depot = AnalysisRepository(session)
        for decalage in range(4):
            depot.add(_analyse(driver.id, jours=decalage))

    with migrated_database.session() as session:
        assert len(AnalysisRepository(session).list_for_driver(driver.id, limit=2)) == 2


def test_les_analyses_recentes_tous_conducteurs_sont_listees(
    migrated_database: Database, driver: Driver
) -> None:
    with migrated_database.session() as session:
        autre, _ = DriverRepository(session).get_or_create("TESTCARD0000002")
        session.flush()
        depot = AnalysisRepository(session)
        depot.add(_analyse(driver.id))
        depot.add(_analyse(autre.id))

    with migrated_database.session() as session:
        assert len(AnalysisRepository(session).list_recent(limit=10)) == 2


def test_une_analyse_conserve_la_version_des_seuils_appliques(
    migrated_database: Database, driver: Driver
) -> None:
    """Sans cette information, un resultat passe ne serait plus interpretable."""
    with migrated_database.session() as session:
        AnalysisRepository(session).add(_analyse(driver.id, version="1.2.3"))

    with migrated_database.session() as session:
        analyse = AnalysisRepository(session).latest_for_driver(driver.id)
        assert analyse is not None
        assert analyse.ruleset_version == "1.2.3"
        assert analyse.total_recorded_seconds == 14 * 3600


# --------------------------------------------------------------------------- #
# Depot des alertes
# --------------------------------------------------------------------------- #
def test_les_alertes_d_un_conducteur_sont_listees(
    migrated_database: Database, driver: Driver
) -> None:
    with migrated_database.session() as session:
        depot = InfringementRepository(session)
        depot.add(_alerte(driver.id, jour=date(2026, 9, 15)))
        depot.add(_alerte(driver.id, jour=date(2026, 9, 18)))

    with migrated_database.session() as session:
        alertes = InfringementRepository(session).list_for_driver(driver.id)
        assert [item.occurred_on for item in alertes] == [
            date(2026, 9, 18),
            date(2026, 9, 15),
        ]


def test_les_alertes_se_filtrent_par_periode(migrated_database: Database, driver: Driver) -> None:
    with migrated_database.session() as session:
        depot = InfringementRepository(session)
        depot.add(_alerte(driver.id, jour=date(2026, 9, 1)))
        depot.add(_alerte(driver.id, jour=date(2026, 9, 20)))

    with migrated_database.session() as session:
        alertes = InfringementRepository(session).list_for_driver(
            driver.id, period_start=date(2026, 9, 15), period_end=date(2026, 9, 30)
        )
        assert [item.occurred_on for item in alertes] == [date(2026, 9, 20)]


def test_les_alertes_se_filtrent_par_statut(migrated_database: Database, driver: Driver) -> None:
    with migrated_database.session() as session:
        depot = InfringementRepository(session)
        depot.add(_alerte(driver.id, status=RuleStatus.WARNING))
        depot.add(_alerte(driver.id, status=RuleStatus.VIOLATION))

    with migrated_database.session() as session:
        alertes = InfringementRepository(session).list_for_driver(
            driver.id, statuses=(RuleStatus.WARNING,)
        )
        assert len(alertes) == 1
        assert alertes[0].status is RuleStatus.WARNING


def test_les_alertes_restent_rattachees_a_leur_analyse(
    migrated_database: Database, driver: Driver
) -> None:
    with migrated_database.session() as session:
        analyse = AnalysisRepository(session).add(_analyse(driver.id))
        session.flush()
        InfringementRepository(session).add(_alerte(driver.id, analysis_id=analyse.id))
        identifiant = analyse.id

    with migrated_database.session() as session:
        alertes = InfringementRepository(session).list_for_analysis(identifiant)
        assert len(alertes) == 1
        assert alertes[0].regulation_reference


def test_une_analyse_sans_alerte_retourne_une_liste_vide(
    migrated_database: Database, driver: Driver
) -> None:
    with migrated_database.session() as session:
        assert InfringementRepository(session).list_for_analysis(4242) == []


# --------------------------------------------------------------------------- #
# Depot generique
# --------------------------------------------------------------------------- #
def test_la_pagination_du_depot_generique(migrated_database: Database) -> None:
    with migrated_database.session() as session:
        depot = DriverRepository(session)
        depot.add_all([Driver(card_number=f"TESTCARD000000{index}") for index in range(1, 4)])

    with migrated_database.session() as session:
        depot = DriverRepository(session)
        assert len(depot.list_all()) == 3
        assert len(depot.list_all(limit=2)) == 2
        assert len(depot.list_all(limit=2, offset=2)) == 1


def test_l_existence_d_une_entite_est_testable(migrated_database: Database, driver: Driver) -> None:
    with migrated_database.session() as session:
        depot = DriverRepository(session)
        assert depot.exists(driver.id) is True
        assert depot.exists(9999) is False


def test_la_mise_a_jour_refuse_un_attribut_inconnu(
    migrated_database: Database, driver: Driver
) -> None:
    """Garde-fou : une faute de frappe ne doit pas passer silencieusement."""
    with migrated_database.session() as session:
        depot = DriverRepository(session)
        entite = depot.get(driver.id)
        assert entite is not None

        with pytest.raises(AttributeError, match="attribut"):
            depot.update(entite, champ_inexistant="valeur")


def test_la_mise_a_jour_applique_les_valeurs_fournies(
    migrated_database: Database, driver: Driver
) -> None:
    with migrated_database.session() as session:
        depot = DriverRepository(session)
        entite = depot.get(driver.id)
        assert entite is not None
        depot.update(entite, first_name="Alex")

    with migrated_database.session() as session:
        relu = DriverRepository(session).get(driver.id)
        assert relu is not None
        assert relu.first_name == "Alex"


def test_la_suppression_reste_possible_mais_explicite(
    migrated_database: Database, driver: Driver
) -> None:
    """L'application ne supprime jamais d'elle-meme : la suppression est demandee."""
    with migrated_database.session() as session:
        depot = DriverRepository(session)
        entite = depot.get(driver.id)
        assert entite is not None
        depot.delete(entite)

    with migrated_database.session() as session:
        assert DriverRepository(session).get(driver.id) is None


def test_le_vidage_permet_d_obtenir_les_identifiants(migrated_database: Database) -> None:
    with migrated_database.session() as session:
        depot = DriverRepository(session)
        entite = depot.add(Driver(card_number="TESTCARD0000009"))
        assert entite.id is None

        depot.flush()

        assert entite.id is not None


def test_le_depot_expose_sa_session(migrated_database: Database) -> None:
    with migrated_database.session() as session:
        assert DriverRepository(session).session is session

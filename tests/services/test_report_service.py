"""Tests du service de production des rapports.

La production elle-meme est prevue en phase 9. Ce qui est fixe, et donc teste des
maintenant : le contrat de demande, le nommage des fichiers de sortie et le refus
explicite d'une fonctionnalite non livree.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.config.settings import Settings
from app.database.database import Database
from app.services.report_service import ReportFormat, ReportRequest, ReportService

DEBUT = datetime(2026, 9, 1, tzinfo=UTC)
FIN = datetime(2026, 9, 30, tzinfo=UTC)


@pytest.fixture
def service(migrated_database: Database, settings: Settings) -> ReportService:
    """Service de rapports branche sur la base et la configuration du test."""
    return ReportService(migrated_database, settings=settings)


# --------------------------------------------------------------------------- #
# Formats
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("format_rapport", "libelle", "extension"),
    [
        (ReportFormat.PDF, "PDF", ".pdf"),
        (ReportFormat.EXCEL, "Excel", ".xlsx"),
        (ReportFormat.CSV, "CSV", ".csv"),
    ],
)
def test_chaque_format_declare_son_libelle_et_son_extension(
    format_rapport: ReportFormat, libelle: str, extension: str
) -> None:
    assert format_rapport.label == libelle
    assert format_rapport.extension == extension


# --------------------------------------------------------------------------- #
# Demande de rapport
# --------------------------------------------------------------------------- #
def test_une_demande_sans_conducteur_est_un_rapport_entreprise() -> None:
    demande = ReportRequest(report_format=ReportFormat.PDF, period_start=DEBUT, period_end=FIN)

    assert demande.is_company_report is True


def test_une_demande_ciblee_est_un_rapport_conducteur() -> None:
    demande = ReportRequest(
        report_format=ReportFormat.PDF,
        period_start=DEBUT,
        period_end=FIN,
        driver_ids=(7,),
    )

    assert demande.is_company_report is False


# --------------------------------------------------------------------------- #
# Nommage des fichiers
# --------------------------------------------------------------------------- #
def test_le_repertoire_d_export_provient_de_la_configuration(
    service: ReportService, settings: Settings
) -> None:
    assert service.export_directory == settings.exports_dir


def test_le_nom_propose_identifie_la_periode_et_le_perimetre(
    service: ReportService,
) -> None:
    demande = ReportRequest(report_format=ReportFormat.PDF, period_start=DEBUT, period_end=FIN)

    chemin = service.suggest_output_path(demande)

    assert chemin.name == "rapport-entreprise-20260901-20260930.pdf"
    assert chemin.parent == service.export_directory


def test_le_nom_propose_mentionne_le_conducteur(service: ReportService) -> None:
    demande = ReportRequest(
        report_format=ReportFormat.EXCEL,
        period_start=DEBUT,
        period_end=FIN,
        driver_ids=(7,),
    )

    assert service.suggest_output_path(demande).name == (
        "rapport-conducteur-7-20260901-20260930.xlsx"
    )


def test_un_chemin_explicite_est_respecte(service: ReportService, tmp_path: Path) -> None:
    cible = tmp_path / "mon-rapport.csv"
    demande = ReportRequest(
        report_format=ReportFormat.CSV,
        period_start=DEBUT,
        period_end=FIN,
        output_path=cible,
    )

    assert service.suggest_output_path(demande) == cible


def test_le_nom_propose_n_ecrit_aucun_fichier(service: ReportService) -> None:
    demande = ReportRequest(report_format=ReportFormat.PDF, period_start=DEBUT, period_end=FIN)

    chemin = service.suggest_output_path(demande)

    assert not chemin.exists()


# --------------------------------------------------------------------------- #
# Production differee en phase 9
# --------------------------------------------------------------------------- #
def test_la_production_echoue_explicitement(service: ReportService) -> None:
    demande = ReportRequest(report_format=ReportFormat.PDF, period_start=DEBUT, period_end=FIN)

    with pytest.raises(NotImplementedError, match="phase 9"):
        service.generate(demande)


def test_aucun_fichier_partiel_n_est_laisse_derriere(
    service: ReportService, tmp_path: Path
) -> None:
    """Une fonctionnalite non livree ne doit pas creer de fichier vide trompeur."""
    cible = tmp_path / "rapport-partiel.pdf"
    demande = ReportRequest(
        report_format=ReportFormat.PDF,
        period_start=DEBUT,
        period_end=FIN,
        output_path=cible,
    )

    with pytest.raises(NotImplementedError):
        service.generate(demande)

    assert not cible.exists()

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
from app.core.exceptions import ReportError
from app.database.database import Database
from app.services.driver_service import DriverService
from app.services.import_service import ImportService
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
# Production
# --------------------------------------------------------------------------- #
@pytest.fixture
def conducteur_importe(context, tmp_path: Path) -> int:
    from tests.services.test_import_service import carte_synthetique

    service = ImportService(context.database, settings=context.settings)
    ligne = service.import_file(carte_synthetique(tmp_path))
    fiche = DriverService(context.database).get_by_card_number("F123456789012301")
    assert ligne.driver_display_name and fiche is not None
    return fiche.id


@pytest.mark.parametrize("format_", list(ReportFormat))
def test_un_rapport_conducteur_est_produit_dans_chaque_format(
    service: ReportService, conducteur_importe: int, format_: ReportFormat
) -> None:
    chemin = service.generate(
        ReportRequest(
            report_format=format_,
            period_start=datetime(2025, 9, 1, tzinfo=UTC),
            period_end=datetime(2025, 11, 1, tzinfo=UTC),
            driver_ids=(conducteur_importe,),
        )
    )

    assert chemin.is_file()
    assert chemin.stat().st_size > 0
    assert chemin.suffix == format_.extension


def test_le_rapport_excel_comporte_une_feuille_par_rubrique(
    service: ReportService, conducteur_importe: int
) -> None:
    from openpyxl import load_workbook

    chemin = service.generate(
        ReportRequest(
            report_format=ReportFormat.EXCEL,
            period_start=datetime(2025, 9, 1, tzinfo=UTC),
            period_end=datetime(2025, 11, 1, tzinfo=UTC),
            driver_ids=(conducteur_importe,),
        )
    )

    classeur = load_workbook(chemin)
    assert classeur.sheetnames == [
        "Info carte de conducteur",
        "Evenements",
        "Periodes de travail journaliere",  # limite Excel : 31 caracteres
        "Activites",
        "Vehicules",
        "Pays",
    ]
    assert "DUPONT MARIE" in classeur["Activites"]["A1"].value


def test_un_rapport_entreprise_sans_donnee_est_refuse_explicitement(
    service: ReportService,
) -> None:
    demande = ReportRequest(report_format=ReportFormat.EXCEL, period_start=DEBUT, period_end=FIN)

    with pytest.raises(ReportError) as erreur:
        service.generate(demande)

    assert "Aucune donnee" in erreur.value.message
    assert not service.suggest_output_path(demande).exists()


def test_une_periode_inversee_est_refusee() -> None:
    with pytest.raises(ValueError, match="periode"):
        ReportRequest(
            report_format=ReportFormat.PDF,
            period_start=datetime(2026, 9, 30, tzinfo=UTC),
            period_end=datetime(2026, 9, 1, tzinfo=UTC),
        )


def test_un_format_transmis_sous_forme_de_texte_est_accepte(service: ReportService) -> None:
    """Une liste deroulante Qt restitue ``"PDF"`` et non ``ReportFormat.PDF``."""
    demande = ReportRequest(report_format="PDF", period_start=DEBUT, period_end=FIN)  # type: ignore[arg-type]

    assert demande.report_format is ReportFormat.PDF
    assert service.suggest_output_path(demande).suffix == ".pdf"


def test_un_format_inconnu_est_refuse() -> None:
    with pytest.raises(ValueError):
        ReportRequest(report_format="DOCX", period_start=DEBUT, period_end=FIN)  # type: ignore[arg-type]

"""Tests du service d'import.

Points couverts, tous exiges par le cahier des charges :

* un fichier invalide, un fichier vide et un fichier d'extension inconnue sont refuses
  ou signales avec un message, une cause et une action ;
* l'empreinte SHA-256 est calculee et le doublon detecte, avec le message exact
  « Ce fichier a deja ete importe le JJ/MM/AAAA. » ;
* **le fichier d'origine n'est jamais modifie** par l'examen ;
* l'import archive une copie immuable et verifiee, enregistre le fichier dans le
  journal avec un etat de decodage honnete, et refuse un doublon.
"""

from __future__ import annotations

import stat
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from app.bootstrap import ApplicationContext
from app.core.enums import FileType, ParsingStatus
from app.core.exceptions import DuplicateFileError, StorageError, UnsupportedFileTypeError
from app.core.hashing import sha256_file
from app.database.database import Database
from app.services.driver_service import DriverService
from app.services.import_service import FileInspection, ImportService
from app.services.vehicle_service import VehicleService
from tests.parser.c1b_synthetique import CarteSynthetique, mot_activite


@pytest.fixture
def service(migrated_database: Database, context: ApplicationContext) -> ImportService:
    """Service d'import branche sur la base et le repertoire temporaires du test."""
    return ImportService(migrated_database, settings=context.settings)


# --------------------------------------------------------------------------- #
# Validation de l'extension
# --------------------------------------------------------------------------- #
def test_un_fichier_c1b_est_reconnu(service: ImportService, opaque_c1b_file: Path) -> None:
    examen = service.inspect(opaque_c1b_file)

    assert examen.file_type is FileType.C1B
    assert examen.filename == "conducteur.C1B"
    assert examen.file_size == opaque_c1b_file.stat().st_size


def test_un_fichier_v1b_est_reconnu(service: ImportService, opaque_v1b_file: Path) -> None:
    assert service.inspect(opaque_v1b_file).file_type is FileType.V1B


def test_une_extension_inconnue_est_refusee(service: ImportService, unsupported_file: Path) -> None:
    with pytest.raises(UnsupportedFileTypeError) as erreur:
        service.inspect(unsupported_file)

    message, cause, action = erreur.value.user_report()
    assert message and action
    assert ".C1B" in cause or ".C1B" in action


def test_un_fichier_absent_produit_un_message_exploitable(
    service: ImportService, tmp_path: Path
) -> None:
    with pytest.raises(StorageError) as erreur:
        service.inspect(tmp_path / "jamais-cree.C1B")

    message, cause, action = erreur.value.user_report()
    assert "introuvable" in message
    assert cause and action
    assert "Traceback" not in message


def test_un_fichier_vide_est_examine_sans_echec(
    service: ImportService, empty_c1b_file: Path
) -> None:
    """Un fichier vide doit etre examinable : c'est le decodage qui le refusera."""
    examen = service.inspect(empty_c1b_file)

    assert examen.file_size == 0
    assert examen.sha256 == sha256_file(empty_c1b_file)


# --------------------------------------------------------------------------- #
# Empreinte et integrite du fichier d'origine
# --------------------------------------------------------------------------- #
def test_l_empreinte_correspond_au_contenu(service: ImportService, opaque_c1b_file: Path) -> None:
    examen = service.inspect(opaque_c1b_file)

    assert examen.sha256 == sha256_file(opaque_c1b_file)
    assert len(examen.sha256) == 64


def test_l_examen_ne_modifie_jamais_le_fichier_d_origine(
    service: ImportService, opaque_c1b_file: Path
) -> None:
    contenu = opaque_c1b_file.read_bytes()
    empreinte_disque = opaque_c1b_file.stat()

    service.inspect(opaque_c1b_file)

    assert opaque_c1b_file.read_bytes() == contenu
    assert opaque_c1b_file.stat().st_mtime == empreinte_disque.st_mtime
    assert opaque_c1b_file.stat().st_size == empreinte_disque.st_size


def test_l_examen_n_ecrit_rien_en_base(service: ImportService, opaque_c1b_file: Path) -> None:
    service.inspect(opaque_c1b_file)

    assert service.count() == 0


def test_deux_fichiers_de_meme_contenu_ont_la_meme_empreinte(
    service: ImportService, opaque_c1b_file: Path, tmp_path: Path
) -> None:
    copie = tmp_path / "copie.C1B"
    copie.write_bytes(opaque_c1b_file.read_bytes())

    assert service.inspect(copie).sha256 == service.inspect(opaque_c1b_file).sha256


# --------------------------------------------------------------------------- #
# Detection de doublon
# --------------------------------------------------------------------------- #
def test_un_fichier_nouveau_n_est_pas_un_doublon(
    service: ImportService, opaque_c1b_file: Path
) -> None:
    examen = service.inspect(opaque_c1b_file)

    assert examen.is_duplicate is False
    assert examen.duplicate_message is None
    assert examen.existing_file_id is None


def test_un_contenu_deja_importe_est_signale(
    service: ImportService, opaque_c1b_file: Path, add_file
) -> None:
    identifiant = add_file(sha256=sha256_file(opaque_c1b_file))

    examen = service.inspect(opaque_c1b_file)

    assert examen.is_duplicate is True
    assert examen.existing_file_id == identifiant


def test_le_message_de_doublon_indique_la_date_de_l_import_existant(
    service: ImportService, opaque_c1b_file: Path, add_file
) -> None:
    """Message attendu tel quel : « Ce fichier a deja ete importe le 20/09/2026. »"""
    add_file(
        sha256=sha256_file(opaque_c1b_file),
        imported_at=datetime(2026, 9, 20, 8, 30, tzinfo=UTC),
    )

    examen = service.inspect(opaque_c1b_file)

    assert examen.duplicate_message == "Ce fichier a deja ete importe le 20/09/2026."


def test_un_doublon_permet_d_ouvrir_l_import_existant(
    service: ImportService, opaque_c1b_file: Path, add_file
) -> None:
    identifiant = add_file(sha256=sha256_file(opaque_c1b_file))

    examen = service.inspect(opaque_c1b_file)
    details = service.get_details(examen.existing_file_id or 0)

    assert details is not None
    assert details.id == identifiant


def test_un_nom_different_ne_masque_pas_un_doublon(
    service: ImportService, opaque_c1b_file: Path, tmp_path: Path, add_file
) -> None:
    add_file(filename="autre-nom.C1B", sha256=sha256_file(opaque_c1b_file))
    copie = tmp_path / "renomme.C1B"
    copie.write_bytes(opaque_c1b_file.read_bytes())

    assert service.inspect(copie).is_duplicate is True


# --------------------------------------------------------------------------- #
# Etat du decodage
# --------------------------------------------------------------------------- #
def test_l_examen_annonce_que_le_decodage_c1b_est_disponible(
    service: ImportService, opaque_c1b_file: Path, opaque_v1b_file: Path
) -> None:
    """Le C1B est decode ; le V1B, aux structures non referencees, ne l'est pas."""
    assert service.inspect(opaque_c1b_file).decoding_available is True
    assert service.inspect(opaque_v1b_file).decoding_available is False


# --------------------------------------------------------------------------- #
# Journal des telechargements
# --------------------------------------------------------------------------- #
def test_le_journal_est_vide_sur_une_base_neuve(service: ImportService) -> None:
    assert service.history() == ()
    assert service.count() == 0
    assert service.last_import_datetime() is None


def test_le_journal_liste_les_imports_enregistres(service: ImportService, add_file) -> None:
    add_file(filename="a.C1B", sha256="a" * 64)
    add_file(filename="b.V1B", file_type=FileType.V1B, sha256="b" * 64)

    journal = service.history()

    assert {ligne.filename for ligne in journal} == {"a.C1B", "b.V1B"}
    assert service.count() == 2


def test_le_journal_se_filtre_par_type(service: ImportService, add_file) -> None:
    add_file(filename="a.C1B", sha256="a" * 64)
    add_file(filename="b.V1B", file_type=FileType.V1B, sha256="b" * 64)

    assert len(service.history(file_type=FileType.C1B)) == 1
    assert service.count_by_type(FileType.V1B) == 1


def test_le_journal_se_filtre_par_etat_de_decodage(service: ImportService, add_file) -> None:
    add_file(filename="a.C1B", sha256="a" * 64, parsing_status=ParsingStatus.PENDING)
    add_file(filename="b.C1B", sha256="b" * 64, parsing_status=ParsingStatus.UNSUPPORTED)

    lignes = service.history(parsing_status=ParsingStatus.UNSUPPORTED)

    assert [ligne.filename for ligne in lignes] == ["b.C1B"]


def test_le_journal_se_recherche_par_nom(service: ImportService, add_file) -> None:
    add_file(filename="carte-durand.C1B", sha256="a" * 64)
    add_file(filename="carte-martin.C1B", sha256="b" * 64)

    lignes = service.history(search="durand")

    assert [ligne.filename for ligne in lignes] == ["carte-durand.C1B"]


def test_le_journal_expose_une_taille_lisible(service: ImportService, add_file) -> None:
    add_file(sha256="a" * 64, file_size=2048)

    ligne = service.history()[0]

    assert ligne.human_size == "2.0 Ko"
    assert ligne.short_sha256 == "a" * 12 + "..."


def test_le_journal_expose_le_repertoire_d_archivage(service: ImportService, add_file) -> None:
    add_file(sha256="a" * 64, original_path="/var/data/originals/2026/carte.C1B")

    assert service.history()[0].directory == Path("/var/data/originals/2026")


def test_le_detail_d_un_import_inexistant_est_nul(service: ImportService) -> None:
    assert service.get_details(4242) is None


def test_la_date_du_dernier_import_est_retournee(service: ImportService, add_file) -> None:
    add_file(sha256="a" * 64, imported_at=datetime(2026, 9, 1, tzinfo=UTC))
    add_file(sha256="b" * 64, imported_at=datetime(2026, 9, 21, tzinfo=UTC))

    dernier = service.last_import_datetime()

    assert dernier is not None
    assert dernier.date() == datetime(2026, 9, 21, tzinfo=UTC).date()


# --------------------------------------------------------------------------- #
# Import effectif : archivage et journal
# --------------------------------------------------------------------------- #
def test_l_import_archive_une_copie_identique_en_lecture_seule(
    service: ImportService, opaque_c1b_file: Path
) -> None:
    ligne = service.import_file(opaque_c1b_file)

    copie = Path(ligne.original_path)
    assert copie.is_file()
    assert copie.is_relative_to(service.originals_directory)
    assert copie.read_bytes() == opaque_c1b_file.read_bytes()
    assert sha256_file(copie) == ligne.sha256
    assert not copie.stat().st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)


def test_l_import_ne_modifie_pas_le_fichier_source(
    service: ImportService, opaque_c1b_file: Path
) -> None:
    avant = (opaque_c1b_file.read_bytes(), opaque_c1b_file.stat().st_mtime_ns)

    service.import_file(opaque_c1b_file)

    assert opaque_c1b_file.exists()
    assert (opaque_c1b_file.read_bytes(), opaque_c1b_file.stat().st_mtime_ns) == avant


def test_l_import_enregistre_le_fichier_au_journal(
    service: ImportService, opaque_c1b_file: Path
) -> None:
    ligne = service.import_file(opaque_c1b_file)

    assert service.count() == 1
    assert ligne.filename == "conducteur.C1B"
    assert ligne.file_type is FileType.C1B
    assert ligne.file_size == opaque_c1b_file.stat().st_size
    assert ligne.imported_at is not None
    assert service.history()[0].id == ligne.id


def test_un_fichier_sans_structure_de_carte_est_archive_en_echec(
    service: ImportService, opaque_c1b_file: Path
) -> None:
    """Aucune donnee n'est inventee : l'etat dit pourquoi le contenu n'est pas lu."""
    ligne = service.import_file(opaque_c1b_file)

    assert ligne.parsing_status is ParsingStatus.FAILED
    assert ligne.parsing_error is not None
    assert "structure" in ligne.parsing_error
    assert ligne.driver_display_name is None


def test_un_fichier_v1b_reste_non_pris_en_charge(
    service: ImportService, opaque_v1b_file: Path
) -> None:
    ligne = service.import_file(opaque_v1b_file)

    assert ligne.parsing_status is ParsingStatus.UNSUPPORTED
    assert "specification officielle" in (ligne.parsing_error or "")


# --------------------------------------------------------------------------- #
# Decodage et enregistrement d'une carte
# --------------------------------------------------------------------------- #
def carte_synthetique(
    tmp_path: Path,
    nom: str = "carte.C1B",
    *,
    signature: bytes = b"\xaa" * 128,
    **options: object,
) -> Path:
    """Ecrit une carte synthetique (donnees fictives) et retourne son chemin."""
    valeurs: dict[str, object] = {
        "jours": [
            (
                date(2025, 10, 1),
                [
                    mot_activite(0, "REPOS"),
                    mot_activite(6 * 60, "CONDUITE"),
                    mot_activite(10 * 60, "REPOS"),
                ],
            )
        ],
        "vehicules": [
            (
                datetime(2025, 10, 1, 6, tzinfo=UTC),
                datetime(2025, 10, 1, 10, tzinfo=UTC),
                "AB-123-CD",
                1000,
                1300,
            )
        ],
    }
    valeurs.update(options)
    chemin = tmp_path / nom
    chemin.write_bytes(CarteSynthetique(**valeurs).fichier(signature=signature))  # type: ignore[arg-type]
    return chemin


def test_une_carte_importee_alimente_conducteur_vehicules_et_activites(
    service: ImportService, migrated_database: Database, tmp_path: Path
) -> None:
    ligne = service.import_file(carte_synthetique(tmp_path))

    assert ligne.parsing_status is ParsingStatus.SUCCESS
    assert ligne.driver_display_name == "DUPONT MARIE"
    assert "3 activite(s) ajoutee(s)" in (ligne.parsing_error or "")
    fiche = DriverService(migrated_database).get_by_card_number("F123456789012301")
    assert fiche is not None
    assert (fiche.activities_count, fiche.files_count) == (3, 1)
    assert fiche.card_expiry_date == date(2027, 1, 31)
    assert [item.registration for item in VehicleService(migrated_database).list_vehicles()] == [
        "AB-123-CD"
    ]


def test_un_second_telechargement_ne_differant_que_par_ses_signatures_est_un_doublon(
    service: ImportService, tmp_path: Path
) -> None:
    premier = service.import_file(carte_synthetique(tmp_path, "a.C1B", signature=b"\x01" * 128))

    with pytest.raises(DuplicateFileError) as erreur:
        service.import_file(carte_synthetique(tmp_path, "b.C1B", signature=b"\x02" * 128))

    assert erreur.value.existing_file_id == premier.id


def test_un_telechargement_plus_recent_n_ajoute_que_les_nouvelles_activites(
    service: ImportService, migrated_database: Database, tmp_path: Path
) -> None:
    jour = date(2025, 10, 1)
    premiere_journee = [mot_activite(0, "REPOS"), mot_activite(6 * 60, "CONDUITE")]
    service.import_file(carte_synthetique(tmp_path, "a.C1B", jours=[(jour, premiere_journee)]))

    ligne = service.import_file(
        carte_synthetique(
            tmp_path,
            "b.C1B",
            jours=[(jour, premiere_journee), (date(2025, 10, 2), [mot_activite(0, "REPOS")])],
        )
    )

    assert "1 activite(s) ajoutee(s)" in (ligne.parsing_error or "")
    fiche = DriverService(migrated_database).get_by_card_number("F123456789012301")
    assert fiche is not None
    assert fiche.activities_count == 3


def test_une_saisie_manuelle_n_est_pas_ecrasee_par_le_decodage(
    service: ImportService, migrated_database: Database, tmp_path: Path
) -> None:
    DriverService(migrated_database).create(card_number="F123456789012301", last_name="SAISI")

    service.import_file(carte_synthetique(tmp_path))

    fiche = DriverService(migrated_database).get_by_card_number("F123456789012301")
    assert fiche is not None
    assert (fiche.last_name, fiche.first_name) == ("SAISI", "MARIE")


def test_le_decodage_peut_etre_rejoue_sans_doublon(
    service: ImportService, migrated_database: Database, tmp_path: Path
) -> None:
    ligne = service.import_file(carte_synthetique(tmp_path))

    rejoue = service.redecode(ligne.id)

    assert rejoue.parsing_status is ParsingStatus.SUCCESS
    assert "0 activite(s) ajoutee(s)" in (rejoue.parsing_error or "")
    fiche = DriverService(migrated_database).get_by_card_number("F123456789012301")
    assert fiche is not None and fiche.activities_count == 3


def test_les_fichiers_en_attente_sont_decodes_a_la_demande(
    service: ImportService, add_file, tmp_path: Path
) -> None:
    archive = carte_synthetique(tmp_path)
    identifiant = add_file(
        sha256="c" * 64,
        parsing_status=ParsingStatus.UNSUPPORTED,
        original_path=str(archive),
    )

    (ligne,) = service.redecode_pending()

    assert ligne.id == identifiant
    assert ligne.parsing_status is ParsingStatus.SUCCESS
    assert ligne.driver_display_name == "DUPONT MARIE"


def test_un_fichier_vide_est_archive_avec_l_etat_echec(
    service: ImportService, empty_c1b_file: Path
) -> None:
    ligne = service.import_file(empty_c1b_file)

    assert ligne.parsing_status is ParsingStatus.FAILED
    assert "vide.C1B est vide" in (ligne.parsing_error or "")
    assert Path(ligne.original_path).is_file()


def test_un_doublon_est_refuse_meme_renomme(
    service: ImportService, opaque_c1b_file: Path, tmp_path: Path
) -> None:
    premier = service.import_file(opaque_c1b_file)
    copie = tmp_path / "renomme.C1B"
    copie.write_bytes(opaque_c1b_file.read_bytes())

    with pytest.raises(DuplicateFileError) as erreur:
        service.import_file(copie)

    assert erreur.value.existing_file_id == premier.id
    assert "deja ete importe" in erreur.value.message
    assert service.count() == 1


def test_une_copie_laissee_par_un_import_interrompu_est_reutilisee(
    service: ImportService, opaque_c1b_file: Path
) -> None:
    digest = sha256_file(opaque_c1b_file)
    orpheline = service.originals_directory / digest[:2] / f"{digest}.C1B"
    orpheline.parent.mkdir(parents=True, exist_ok=True)
    orpheline.write_bytes(opaque_c1b_file.read_bytes())

    ligne = service.import_file(opaque_c1b_file)

    assert Path(ligne.original_path) == orpheline


def test_une_archive_alteree_n_est_jamais_ecrasee(
    service: ImportService, opaque_c1b_file: Path
) -> None:
    digest = sha256_file(opaque_c1b_file)
    alteree = service.originals_directory / digest[:2] / f"{digest}.C1B"
    alteree.parent.mkdir(parents=True, exist_ok=True)
    alteree.write_bytes(b"contenu different")

    with pytest.raises(StorageError):
        service.import_file(opaque_c1b_file)

    assert alteree.read_bytes() == b"contenu different"
    assert service.count() == 0


def test_une_extension_inconnue_n_est_pas_archivee(
    service: ImportService, unsupported_file: Path
) -> None:
    with pytest.raises(UnsupportedFileTypeError):
        service.import_file(unsupported_file)

    assert service.count() == 0
    assert not any(service.originals_directory.rglob("*.*"))


# --------------------------------------------------------------------------- #
# Objet de transfert
# --------------------------------------------------------------------------- #
def test_un_doublon_sans_date_reste_signale() -> None:
    """Incoherence de donnees : le message doit rester prudent et non fautif."""
    examen = FileInspection(
        path=Path("/tmp/x.C1B"),
        filename="x.C1B",
        file_type=FileType.C1B,
        file_size=1,
        sha256="0" * 64,
        is_duplicate=True,
        existing_imported_at=None,
    )

    assert examen.duplicate_message == "Ce fichier a deja ete importe."


@pytest.mark.parametrize(
    ("octets", "attendu"),
    [(0, "0 o"), (512, "512 o"), (1024, "1.0 Ko"), (1024 * 1024, "1.0 Mo")],
)
def test_la_taille_est_presentee_lisiblement(octets: int, attendu: str) -> None:
    examen = FileInspection(
        path=Path("/tmp/x.C1B"),
        filename="x.C1B",
        file_type=FileType.C1B,
        file_size=octets,
        sha256="0" * 64,
        is_duplicate=False,
    )

    assert examen.human_size == attendu

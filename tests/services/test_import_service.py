"""Tests du service d'import.

Points couverts, tous exiges par le cahier des charges :

* un fichier invalide, un fichier vide et un fichier d'extension inconnue sont refuses
  ou signales avec un message, une cause et une action ;
* l'empreinte SHA-256 est calculee et le doublon detecte, avec le message exact
  « Ce fichier a deja ete importe le JJ/MM/AAAA. » ;
* **le fichier d'origine n'est jamais modifie** par l'examen ;
* l'ecriture effective, prevue en phase 3, echoue explicitement plutot que
  silencieusement.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.core.enums import FileType, ParsingStatus
from app.core.exceptions import StorageError, UnsupportedFileTypeError
from app.core.hashing import sha256_file
from app.database.database import Database
from app.services.import_service import FileInspection, ImportService


@pytest.fixture
def service(migrated_database: Database) -> ImportService:
    """Service d'import branche sur la base temporaire du test."""
    return ImportService(migrated_database)


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
def test_l_examen_annonce_que_le_decodage_n_est_pas_disponible(
    service: ImportService, opaque_c1b_file: Path
) -> None:
    """L'utilisateur doit savoir que le fichier sera archive, mais pas encore decode."""
    assert service.inspect(opaque_c1b_file).decoding_available is False


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
# Ecriture differee en phase 3
# --------------------------------------------------------------------------- #
def test_l_import_effectif_echoue_explicitement(
    service: ImportService, opaque_c1b_file: Path
) -> None:
    """Une fonctionnalite non livree doit le dire, et ne rien ecrire a moitie."""
    with pytest.raises(NotImplementedError, match="phase 3"):
        service.import_file(opaque_c1b_file)

    assert service.count() == 0


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

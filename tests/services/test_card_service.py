"""Tests du service de telechargement de carte : lecture, fichier .C1B, import."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.bootstrap import ApplicationContext
from app.core.enums import FileType, ParsingStatus
from app.core.exceptions import CardCommunicationError
from app.parser.c1b_parser import decode_container
from app.services.card_service import CardDownloadService
from app.services.import_service import ImportService
from tests.card_reader.carte_simulee import CarteSimulee, fichiers_g1
from tests.parser.c1b_synthetique import CarteSynthetique, mot_activite


@pytest.fixture
def service(context: ApplicationContext) -> CardDownloadService:
    return CardDownloadService(context.database, settings=context.settings)


def carte_conducteur() -> CarteSimulee:
    """Carte simulee dont les fichiers G1 portent des donnees fictives decodables."""
    from datetime import date

    synthetique = CarteSynthetique(
        jours=[(date(2025, 10, 1), [mot_activite(0, "REPOS"), mot_activite(360, "CONDUITE")])]
    )
    fichiers = fichiers_g1()
    fichiers.update(
        {
            fid: valeur
            for (fid, suffixe), valeur in decode_container(synthetique.fichier()).items()
            if suffixe == 0
        }
    )
    return CarteSimulee(g1=fichiers)


def test_une_carte_inseree_est_telechargee_decodee_puis_importee(
    service: CardDownloadService, context: ApplicationContext
) -> None:
    resultat = service.download_and_import(carte_conducteur().lecteur())

    assert resultat.record is not None
    assert resultat.record.file_type is FileType.C1B
    assert resultat.record.parsing_status is ParsingStatus.SUCCESS
    assert resultat.record.driver_display_name == "DUPONT MARIE"
    assert resultat.path.parent == context.settings.imports_dir
    assert resultat.path.read_bytes() == resultat.download.payload
    assert Path(resultat.record.original_path).read_bytes() == resultat.download.payload
    assert "import #" in resultat.summary()


def test_un_second_telechargement_identique_n_est_pas_reimporte(
    service: CardDownloadService, context: ApplicationContext
) -> None:
    premier = service.download_and_import(CarteSimulee().lecteur())

    second = service.download_and_import(CarteSimulee().lecteur())

    assert second.is_duplicate
    assert second.existing_file_id == premier.record.id
    assert "deja ete importees" in second.summary()
    assert ImportService(context.database, settings=context.settings).count() == 1
    assert second.path != premier.path


def test_la_connexion_est_fermee_meme_en_cas_d_echec(service: CardDownloadService) -> None:
    lecteur = CarteSimulee(g1=fichiers_g1(type_carte=2)).lecteur()

    with pytest.raises(CardCommunicationError):
        service.download_and_import(lecteur)

    assert lecteur.is_connected is False


def test_un_echec_de_lecture_n_ecrit_aucun_fichier(
    service: CardDownloadService, context: ApplicationContext
) -> None:
    with pytest.raises(CardCommunicationError):
        service.download_and_import(CarteSimulee(g1=fichiers_g1(type_carte=2)).lecteur())

    assert not list(context.settings.imports_dir.glob("*.C1B"))

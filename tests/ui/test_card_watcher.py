"""Tests du telechargement automatique a l'insertion d'une carte."""

from __future__ import annotations

from dataclasses import replace

import pytest
from PySide6.QtCore import QCoreApplication

from app.bootstrap import ApplicationContext
from app.card_reader.mock_reader import MockCardReader
from app.ui.cards.card_watcher import CardWatcher
from app.ui.main_window import MainWindow
from tests.card_reader.carte_simulee import CarteSimulee
from tests.ui.conftest import DialogRecorder


def attendre(watcher: CardWatcher) -> None:
    """Attend la fin du telechargement et livre les signaux en attente."""
    watcher.stop()
    for _ in range(5):
        QCoreApplication.processEvents()


def lecteur_vide(carte: CarteSimulee) -> MockCardReader:
    lecteur = carte.lecteur()
    lecteur.remove_card()
    return lecteur


def test_une_carte_inseree_est_telechargee_automatiquement(
    application, context: ApplicationContext
) -> None:
    lecteur = lecteur_vide(CarteSimulee())
    watcher = CardWatcher(context, reader=lecteur)
    resultats: list[object] = []
    watcher.download_finished.connect(resultats.append)

    watcher.poll()
    assert resultats == []
    lecteur.insert_card(atr="3B FE 96 00")
    watcher.poll()
    attendre(watcher)

    assert len(resultats) == 1
    assert resultats[0].record is not None
    assert watcher.is_busy is False


def test_une_carte_restee_inseree_n_est_telechargee_qu_une_fois(
    application, context: ApplicationContext
) -> None:
    lecteur = lecteur_vide(CarteSimulee())
    watcher = CardWatcher(context, reader=lecteur)
    resultats: list[object] = []
    watcher.download_finished.connect(resultats.append)

    watcher.poll()
    lecteur.insert_card()
    watcher.poll()
    attendre(watcher)
    watcher.poll()
    watcher.poll()
    attendre(watcher)

    assert len(resultats) == 1


def test_le_telechargement_automatique_peut_etre_desactive(
    application, context: ApplicationContext
) -> None:
    contexte = replace(
        context, settings=context.settings.model_copy(update={"card_auto_download": False})
    )
    lecteur = lecteur_vide(CarteSimulee())
    watcher = CardWatcher(contexte, reader=lecteur)
    debuts: list[None] = []
    watcher.download_started.connect(lambda: debuts.append(None))

    watcher.poll()
    lecteur.insert_card()
    watcher.poll()
    attendre(watcher)

    assert debuts == []


def test_un_echec_est_presente_a_l_utilisateur(
    application, context: ApplicationContext, dialogs: DialogRecorder
) -> None:
    lecteur = lecteur_vide(CarteSimulee(g2=None, g1={}))
    watcher = CardWatcher(context, reader=lecteur)
    fenetre = MainWindow(context, card_watcher=watcher)
    erreurs: list[object] = []
    watcher.download_failed.connect(erreurs.append)

    watcher.poll()
    lecteur.insert_card()
    watcher.poll()
    attendre(watcher)

    assert len(erreurs) == 1
    assert dialogs.count == 1
    assert "carte" in fenetre.status_text.lower()


def test_un_telechargement_reussi_est_annonce_dans_la_fenetre(
    application, context: ApplicationContext, dialogs: DialogRecorder
) -> None:
    lecteur = lecteur_vide(CarteSimulee())
    watcher = CardWatcher(context, reader=lecteur)
    fenetre = MainWindow(context, card_watcher=watcher)
    fenetre.navigate_to("history")

    watcher.poll()
    lecteur.insert_card()
    watcher.poll()
    attendre(watcher)

    assert "archivee" in fenetre.status_text
    assert fenetre.page("history")._table.rowCount() == 1
    assert dialogs.count == 1


def test_la_page_du_lecteur_suit_le_surveillant(
    application, context: ApplicationContext, dialogs: DialogRecorder
) -> None:
    lecteur = lecteur_vide(CarteSimulee())
    watcher = CardWatcher(context, reader=lecteur)
    fenetre = MainWindow(context, card_watcher=watcher)
    fenetre.navigate_to("cards")
    page = fenetre.page("cards")

    watcher.poll()
    lecteur.insert_card()
    watcher.poll()
    attendre(watcher)

    assert "archivee" in page._download_value.text()


@pytest.mark.parametrize("actif", [False])
def test_un_lecteur_desactive_n_est_jamais_interroge(
    application, context: ApplicationContext, actif: bool
) -> None:
    contexte = replace(
        context, settings=context.settings.model_copy(update={"pcsc_enabled": actif})
    )
    carte = CarteSimulee()
    watcher = CardWatcher(contexte, reader=carte.lecteur())

    watcher.start()
    attendre(watcher)

    assert watcher.presence is None
    assert carte.commandes == []


def test_chaque_bouton_des_statistiques_produit_un_resultat(
    application, context: ApplicationContext, dialogs: DialogRecorder, monkeypatch, tmp_path
) -> None:
    from PySide6.QtCore import QDate
    from PySide6.QtGui import QDesktopServices
    from PySide6.QtWidgets import QPushButton

    from app.services.import_service import ImportService
    from tests.services.test_import_service import carte_synthetique

    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: True)
    ImportService(context.database, settings=context.settings).import_file(
        carte_synthetique(tmp_path)
    )
    fenetre = MainWindow(context)
    fenetre.navigate_to("fleet_tools")
    page = fenetre.page("fleet_tools")
    page._start.setDate(QDate(2025, 10, 1))
    page._end.setDate(QDate(2025, 10, 31))

    for bouton in page.findChildren(QPushButton):
        bouton.click()

    assert all(titre != "Statistiques" for titre, *_ in dialogs.shown)
    assert sorted(path.name for path in context.settings.exports_dir.glob("flotte-*.xlsx")) == [
        "flotte-anomalies-20251001-20251031.xlsx",
        "flotte-detaille-20251001-20251031.xlsx",
        "flotte-synthese-20251001-20251031.xlsx",
        "flotte-vehicules-inconnus-20251001-20251031.xlsx",
    ]


@pytest.mark.parametrize("format_", ["PDF", "EXCEL", "CSV"])
def test_la_page_rapports_produit_chaque_format(
    application, context: ApplicationContext, dialogs: DialogRecorder, tmp_path, format_: str
) -> None:
    """Regression : le format choisi dans la liste deroulante arrive sous forme de texte."""
    from PySide6.QtCore import QDate

    from app.services.import_service import ImportService
    from tests.services.test_import_service import carte_synthetique

    ImportService(context.database, settings=context.settings).import_file(
        carte_synthetique(tmp_path)
    )
    fenetre = MainWindow(context)
    fenetre.navigate_to("reports")
    page = fenetre.page("reports")
    page._scope.setCurrentIndex(1)
    page._format.setCurrentIndex(page._format.findData(format_))
    page._start.setDate(QDate(2025, 10, 1))
    page._end.setDate(QDate(2025, 10, 31))

    page._on_preview()
    page._on_generate()

    assert dialogs.texts() == [f"Rapport enregistre :\n{page._output.text()}"]
    assert page._output.text().endswith({"PDF": ".pdf", "EXCEL": ".xlsx", "CSV": ".csv"}[format_])

"""Tests de la fenetre principale et de la navigation.

Objectif : verifier que **toutes** les pages declarees dans la navigation se
construisent et se rafraichissent sans erreur sur une base vide, puis sur une base
contenant des donnees. Une page qui echoue doit etre remplacee par une explication,
sans fermer l'application.

Ces tests couvrent aussi une exigence de fond : aucune page ne doit presenter
spontanement une boite d'erreur a l'ouverture.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.bootstrap import ApplicationContext
from app.core.enums import ActivityType
from app.ui.main_window import MainWindow
from app.ui.navigation import NAVIGATION
from tests.ui.conftest import DialogRecorder

pytestmark = pytest.mark.ui

TOUTES_LES_CLES = tuple(item.key for section in NAVIGATION for item in section.items)


@pytest.fixture
def window(application, context: ApplicationContext) -> MainWindow:
    """Fenetre principale construite sur une base temporaire migree."""
    return MainWindow(context)


# --------------------------------------------------------------------------- #
# Construction
# --------------------------------------------------------------------------- #
def test_la_navigation_declare_les_dix_pages_attendues() -> None:
    assert TOUTES_LES_CLES == (
        "dashboard",
        "drivers",
        "vehicles",
        "import",
        "history",
        "activities",
        "anomalies",
        "reports",
        "cards",
        "settings",
    )


def test_la_fenetre_s_ouvre_sur_le_tableau_de_bord(
    window: MainWindow, dialogs: DialogRecorder
) -> None:
    assert window.current_page is not None
    assert window.page("dashboard") is window.current_page
    assert dialogs.count == 0


def test_le_titre_mentionne_l_application(window: MainWindow, context: ApplicationContext) -> None:
    assert context.settings.app_name in window.windowTitle()


def test_la_barre_d_etat_rend_compte_du_chargement(window: MainWindow) -> None:
    """Le tableau de bord annonce ce qu'il a charge, chiffres issus de la base."""
    assert window.status_text == (
        "Tableau de bord actualise - 0 conducteur(s), 0 fichier(s) importe(s)"
    )


def test_les_pages_ne_sont_construites_qu_a_la_premiere_visite(window: MainWindow) -> None:
    assert window.page("reports") is None

    window.navigate_to("reports")

    assert window.page("reports") is not None


# --------------------------------------------------------------------------- #
# Navigation
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("cle", TOUTES_LES_CLES)
def test_chaque_page_s_ouvre_sans_erreur(
    window: MainWindow, dialogs: DialogRecorder, cle: str
) -> None:
    window.navigate_to(cle)

    assert window.page(cle) is not None
    assert dialogs.count == 0, f"la page {cle} a affiche : {dialogs.texts()}"


def test_toutes_les_pages_s_ouvrent_a_la_suite(window: MainWindow, dialogs: DialogRecorder) -> None:
    for cle in TOUTES_LES_CLES:
        window.navigate_to(cle)

    assert len(TOUTES_LES_CLES) == len(
        [cle for cle in TOUTES_LES_CLES if window.page(cle) is not None]
    )
    assert dialogs.count == 0


def test_la_page_affichee_suit_la_navigation(window: MainWindow) -> None:
    window.navigate_to("drivers")

    assert window.current_page is window.page("drivers")


def test_un_second_passage_ne_reconstruit_pas_la_page(window: MainWindow) -> None:
    window.navigate_to("vehicles")
    premiere = window.page("vehicles")

    window.navigate_to("dashboard")
    window.navigate_to("vehicles")

    assert window.page("vehicles") is premiere


def test_le_bouton_de_navigation_suit_la_page_affichee(window: MainWindow) -> None:
    window.navigate_to("history")

    assert window._buttons["history"].isChecked() is True
    assert window._buttons["dashboard"].isChecked() is False


def test_une_page_inconnue_est_refusee(window: MainWindow) -> None:
    with pytest.raises(KeyError, match="page inconnue"):
        window.navigate_to("page-qui-n-existe-pas")


# --------------------------------------------------------------------------- #
# Rafraichissement avec des donnees
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("cle", TOUTES_LES_CLES)
def test_chaque_page_se_rafraichit_avec_des_donnees(
    window: MainWindow,
    dialogs: DialogRecorder,
    driver,
    vehicle,
    add_activity,
    add_file,
    cle: str,
) -> None:
    jour = datetime(2026, 9, 15, tzinfo=UTC)
    add_activity(ActivityType.DRIVING, jour + timedelta(hours=7), jour + timedelta(hours=11))
    add_file(sha256="a" * 64, driver_id=driver.id)

    window.navigate_to(cle)
    page = window.page(cle)
    assert page is not None
    page.safe_refresh()

    assert dialogs.count == 0, f"la page {cle} a affiche : {dialogs.texts()}"


# --------------------------------------------------------------------------- #
# Robustesse
# --------------------------------------------------------------------------- #
def test_l_echec_d_un_rafraichissement_n_interrompt_pas_l_application(
    window: MainWindow, dialogs: DialogRecorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    page = window.page("dashboard")
    assert page is not None

    def echec() -> None:
        raise RuntimeError("panne simulee de la source de donnees")

    monkeypatch.setattr(page, "refresh", echec)
    page.safe_refresh()

    assert dialogs.count == 1
    assert dialogs.texts() == ["Une erreur inattendue est survenue."]


def test_un_message_de_page_remonte_dans_la_barre_d_etat(window: MainWindow) -> None:
    page = window.page("dashboard")
    assert page is not None

    page.notify("3 fichiers importes")

    assert window.status_text == "3 fichiers importes"


def test_la_fenetre_expose_son_contexte(window: MainWindow, context: ApplicationContext) -> None:
    assert window.context is context

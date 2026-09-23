"""Tests du point d'entree de l'application.

L'application doit demarrer avec ``python -m app.main``. Le mode ``--check`` permet de
verifier l'installation sans ecran : c'est lui qui est teste ici, l'ouverture de la
fenetre etant couverte par les tests d'interface.

Un echec de demarrage doit produire un message, une cause et une action sur la sortie
d'erreur, jamais une pile d'appels.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app import __version__
from app.main import EXIT_OK, EXIT_STARTUP_FAILURE, build_parser, main, run_checks


# --------------------------------------------------------------------------- #
# Ligne de commande
# --------------------------------------------------------------------------- #
def test_les_options_par_defaut_sont_neutres() -> None:
    arguments = build_parser().parse_args([])

    assert arguments.check is False
    assert arguments.data_dir is None
    assert arguments.log_level is None


def test_le_repertoire_de_donnees_est_surchargeable() -> None:
    arguments = build_parser().parse_args(["--data-dir", "/srv/tachy"])

    assert arguments.data_dir == Path("/srv/tachy")


def test_le_niveau_de_journalisation_est_surchargeable() -> None:
    assert build_parser().parse_args(["--log-level", "DEBUG"]).log_level == "DEBUG"


def test_un_niveau_de_journalisation_invalide_est_refuse() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--log-level", "VERBEUX"])


def test_la_version_est_affichee_puis_le_programme_s_arrete(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as sortie:
        main(["--version"])

    assert sortie.value.code == 0
    assert __version__ in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# Mode verification
# --------------------------------------------------------------------------- #
def test_le_mode_verification_demarre_sans_interface(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["--check", "--data-dir", str(tmp_path / "donnees")])

    assert code == EXIT_OK
    sortie = capsys.readouterr().out
    assert "tachy-linux" in sortie
    assert "Schema de base" in sortie


def test_le_mode_verification_cree_la_base_et_les_repertoires(tmp_path: Path) -> None:
    racine = tmp_path / "donnees"

    main(["--check", "--data-dir", str(racine)])

    assert (racine / "originals").is_dir()
    assert (racine / "database").is_dir()
    assert (racine / "exports").is_dir()


def test_le_compte_rendu_cite_tous_les_chemins_utiles(
    settings, database, capsys: pytest.CaptureFixture[str]
) -> None:
    from app.bootstrap import bootstrap

    contexte = bootstrap(settings, database=database)

    compte_rendu = run_checks(contexte)

    assert str(settings.data_dir) in compte_rendu
    assert str(settings.originals_dir) in compte_rendu
    assert str(settings.database_path) in compte_rendu
    assert str(settings.log_path) in compte_rendu
    assert f"version {contexte.schema_version}" in compte_rendu


def test_le_compte_rendu_liste_les_migrations_appliquees(settings, database) -> None:
    from app.bootstrap import bootstrap

    contexte = bootstrap(settings, database=database)

    assert "Migrations appliquees" in run_checks(contexte)


def test_le_compte_rendu_le_dit_quand_le_schema_est_a_jour(settings, database) -> None:
    from app.bootstrap import bootstrap

    bootstrap(settings, database=database)
    contexte = bootstrap(settings, database=database)

    assert "aucune (schema deja a jour)" in run_checks(contexte)


# --------------------------------------------------------------------------- #
# Echec de demarrage
# --------------------------------------------------------------------------- #
@pytest.fixture
def boites_muettes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empeche toute boite de dialogue modale de bloquer la suite de tests."""
    message_box = pytest.importorskip("PySide6.QtWidgets").QMessageBox
    monkeypatch.setattr(message_box, "exec", lambda self: 0, raising=False)


def test_un_demarrage_impossible_est_explique_sur_la_sortie_d_erreur(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], boites_muettes: None
) -> None:
    obstacle = tmp_path / "obstacle"
    obstacle.write_text("ceci est un fichier, pas un repertoire", encoding="utf-8")

    code = main(["--check", "--data-dir", str(obstacle / "donnees")])

    assert code == EXIT_STARTUP_FAILURE
    erreur = capsys.readouterr().err
    assert "Cause  :" in erreur
    assert "Action :" in erreur
    assert "Traceback" not in erreur

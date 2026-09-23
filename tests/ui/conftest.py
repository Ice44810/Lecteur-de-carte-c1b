"""Fixtures des tests d'interface.

Deux precautions indispensables pour que ces tests soient executables sans ecran et
sans blocage :

* la plate-forme Qt ``offscreen`` est imposee avant toute creation de ``QApplication`` ;
* les boites de dialogue modales sont interceptees : ``QMessageBox.exec`` est remplace
  par un enregistrement. Sans cela, le premier message d'erreur ferait attendre la
  suite de tests indefiniment.

L'interception est aussi un moyen de **verifier** qu'aucune erreur inattendue n'est
presentee a l'utilisateur pendant la navigation.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass, field

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6", reason="PySide6 est necessaire aux tests d'interface")

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

pytestmark = pytest.mark.ui


@dataclass
class DialogRecorder:
    """Journal des boites de dialogue qui auraient ete affichees.

    Attributes:
        shown: Titres et textes des boites interceptees.
    """

    shown: list[tuple[str, str, str]] = field(default_factory=list)

    @property
    def count(self) -> int:
        """Nombre de boites interceptees."""
        return len(self.shown)

    @property
    def titles(self) -> list[str]:
        """Titres des boites interceptees."""
        return [title for title, _, _ in self.shown]

    def texts(self) -> list[str]:
        """Messages principaux des boites interceptees."""
        return [text for _, text, _ in self.shown]

    def clear(self) -> None:
        """Vide le journal."""
        self.shown.clear()


@pytest.fixture(scope="session")
def application() -> Iterator[QApplication]:
    """Instance unique de ``QApplication`` pour toute la session de tests."""
    existing = QApplication.instance()
    app = existing if isinstance(existing, QApplication) else QApplication([])
    yield app
    app.processEvents()


@pytest.fixture(autouse=True)
def dialogs(monkeypatch: pytest.MonkeyPatch) -> DialogRecorder:
    """Intercepte les boites de dialogue modales au lieu de les afficher."""
    recorder = DialogRecorder()

    def fake_exec(self: QMessageBox) -> int:
        recorder.shown.append((self.windowTitle(), self.text(), self.informativeText()))
        return int(QMessageBox.StandardButton.Ok)

    monkeypatch.setattr(QMessageBox, "exec", fake_exec, raising=False)
    monkeypatch.setattr(QMessageBox, "exec_", fake_exec, raising=False)
    return recorder

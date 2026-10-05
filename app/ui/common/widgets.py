"""Widgets reutilisables de l'interface.

Ces composants ne contiennent aucune logique metier : ils affichent ce qu'on leur
donne. Toute valeur provient d'un service (section 25 du cahier des charges).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

__all__ = [
    "IndicatorCard",
    "NoticeBanner",
    "PageHeader",
    "SectionTitle",
    "ReadOnlyTable",
    "EmptyState",
]


class PageHeader(QWidget):
    """En-tete d'une page : titre et sous-titre explicatif.

    Args:
        title: Titre de la page.
        subtitle: Phrase expliquant a quoi sert la page.
        parent: Widget parent.
    """

    def __init__(self, title: str, subtitle: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self._title = QLabel(title)
        self._title.setObjectName("PageTitle")
        layout.addWidget(self._title)

        self._subtitle = QLabel(subtitle)
        self._subtitle.setObjectName("PageSubtitle")
        self._subtitle.setWordWrap(True)
        self._subtitle.setVisible(bool(subtitle))
        layout.addWidget(self._subtitle)

    def set_subtitle(self, text: str) -> None:
        """Met a jour le sous-titre."""
        self._subtitle.setText(text)
        self._subtitle.setVisible(bool(text))


class SectionTitle(QLabel):
    """Intitule de section a l'interieur d'une page."""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text.upper(), parent)
        self.setObjectName("CardTitle")


class IndicatorCard(QFrame):
    """Carte d'indicateur du tableau de bord.

    Args:
        title: Intitule de l'indicateur.
        value: Valeur affichee.
        hint: Precision affichee sous la valeur.
        parent: Widget parent.
    """

    def __init__(
        self,
        title: str,
        value: str = "-",
        hint: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)

        self._title = QLabel(title.upper())
        self._title.setObjectName("CardTitle")
        layout.addWidget(self._title)

        self._value = QLabel(value)
        self._value.setObjectName("CardValue")
        layout.addWidget(self._value)

        self._hint = QLabel(hint)
        self._hint.setObjectName("CardHint")
        self._hint.setWordWrap(True)
        self._hint.setVisible(bool(hint))
        layout.addWidget(self._hint)

    def set_value(self, value: str, hint: str = "") -> None:
        """Met a jour la valeur et la precision affichees."""
        self._value.setText(value)
        self._hint.setText(hint)
        self._hint.setVisible(bool(hint))

    @property
    def value_text(self) -> str:
        """Valeur actuellement affichee, utilisee par les tests."""
        return self._value.text()


class NoticeBanner(QFrame):
    """Bandeau d'information ou d'avertissement.

    Sert notamment a expliquer ce que l'application ne fait pas encore, plutot que de
    laisser l'utilisateur devant une page vide sans explication.

    Args:
        text: Message affiche.
        level: ``"info"`` ou ``"warning"``.
        parent: Widget parent.
    """

    def __init__(self, text: str, level: str = "info", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Notice" if level == "info" else "NoticeWarning")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)

        self._label = QLabel(text)
        self._label.setObjectName("NoticeText")
        self._label.setWordWrap(True)
        self._label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self._label)

    def set_text(self, text: str) -> None:
        """Met a jour le message affiche."""
        self._label.setText(text)

    @property
    def text(self) -> str:
        """Message actuellement affiche, utilise par les tests."""
        return self._label.text()


class ReadOnlyTable(QTableWidget):
    """Tableau en lecture seule, configure pour un usage professionnel.

    Args:
        headers: Intitules des colonnes.
        parent: Widget parent.
    """

    def __init__(self, headers: tuple[str, ...], parent: QWidget | None = None) -> None:
        super().__init__(0, len(headers), parent)
        self.setHorizontalHeaderLabels(list(headers))
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.setAlternatingRowColors(True)
        self.verticalHeader().setVisible(False)
        self.setSortingEnabled(True)
        self.horizontalHeader().setStretchLastSection(True)

    def set_rows(self, rows: tuple[tuple[str, ...], ...]) -> None:
        """Remplace le contenu du tableau.

        Args:
            rows: Lignes a afficher, chacune comportant autant de valeurs que de
                colonnes.
        """
        self.setSortingEnabled(False)
        self.setRowCount(0)
        for row_values in rows:
            row = self.rowCount()
            self.insertRow(row)
            for column, value in enumerate(row_values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                self.setItem(row, column, item)
        self.setSortingEnabled(True)
        self.resizeColumnsToContents()


class EmptyState(QWidget):
    """Message affiche lorsqu'une liste est vide.

    Args:
        title: Titre du message.
        explanation: Explication et action suggeree.
        parent: Widget parent.
    """

    def __init__(self, title: str, explanation: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 24, 0, 24)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        heading = QLabel(title)
        heading.setObjectName("PageTitle")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(heading)

        detail = QLabel(explanation)
        detail.setObjectName("PageSubtitle")
        detail.setWordWrap(True)
        detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(detail)

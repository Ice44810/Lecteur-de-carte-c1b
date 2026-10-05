"""Widgets reutilisables de l'interface.

Ces composants ne contiennent aucune logique metier : ils affichent ce qu'on leur
donne. Toute valeur provient d'un service (section 25 du cahier des charges).
"""

from __future__ import annotations

import re
from collections.abc import Hashable, Sequence

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


ROW_KEY_ROLE = Qt.ItemDataRole.UserRole
"""Role Qt portant l'identifiant metier d'une ligne (premiere colonne)."""

SORT_KEY_ROLE = Qt.ItemDataRole.UserRole + 1
"""Role Qt portant la cle de tri d'une cellule."""

_DATE_PATTERN = re.compile(r"^(\d{2})/(\d{2})/(\d{4})(?:\D+(\d{2}):(\d{2}))?")
_DURATION_PATTERN = re.compile(r"^(\d+)h(\d{2})$")
_INTEGER_PATTERN = re.compile(r"^-?\d+$")


def sort_key(value: str) -> tuple[int, object]:
    """Calcule la cle de tri d'une valeur affichee.

    Les tableaux affichent des textes formates pour l'utilisateur ; un tri purement
    alphabetique classerait « 02/10/2026 » avant « 15/09/2026 », ou « 10 » avant
    « 9 ». Les dates ``JJ/MM/AAAA [HH:MM]``, les durees ``HHhMM`` et les entiers sont
    donc tries selon leur valeur ; les tirets d'absence de valeur sont places en fin.

    Args:
        value: Texte affiche dans la cellule.

    Returns:
        Une cle comparable a toute autre cle produite par cette fonction.
    """
    text = value.strip()
    if text in {"", "-"}:
        return (3, "")
    if match := _DATE_PATTERN.match(text):
        day, month, year, hour, minute = match.groups()
        return (0, (int(year), int(month), int(day), int(hour or 0), int(minute or 0)))
    if match := _DURATION_PATTERN.match(text):
        return (1, int(match.group(1)) * 60 + int(match.group(2)))
    if _INTEGER_PATTERN.match(text):
        return (1, int(text))
    return (2, text.casefold())


class _SortableItem(QTableWidgetItem):
    """Cellule triee selon sa cle de tri plutot que selon son texte."""

    def __lt__(self, other: QTableWidgetItem) -> bool:  # type: ignore[override]
        """Compare deux cellules d'une meme colonne."""
        mine = self.data(SORT_KEY_ROLE)
        theirs = other.data(SORT_KEY_ROLE)
        if mine is None or theirs is None:
            return super().__lt__(other)
        return bool(mine < theirs)


class ReadOnlyTable(QTableWidget):
    """Tableau en lecture seule, configure pour un usage professionnel.

    Le tri par colonne est actif (sauf ``sortable=False``) : une ligne ne doit donc
    jamais etre retrouvee par son numero. Tant que l'utilisateur ne trie pas, l'ordre
    des lignes fournies est conserve. Chaque ligne peut porter un identifiant (``keys`` de
    :meth:`set_rows`), relu par :meth:`selected_key` quel que soit l'ordre affiche.

    Args:
        headers: Intitules des colonnes.
        parent: Widget parent.
        sortable: Autorise le tri par clic sur un en-tete. A desactiver pour les
            tableaux structures (lignes d'intitule ou de total).
    """

    def __init__(
        self,
        headers: tuple[str, ...],
        parent: QWidget | None = None,
        *,
        sortable: bool = True,
    ) -> None:
        super().__init__(0, len(headers), parent)
        self._sortable = sortable
        self.setHorizontalHeaderLabels(list(headers))
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.setAlternatingRowColors(True)
        self.verticalHeader().setVisible(False)
        # Aucune colonne de tri au depart : l'ordre fourni (chronologique en general)
        # est conserve tant que l'utilisateur ne clique pas sur un en-tete. Sans cela,
        # Qt trierait chaque chargement par la premiere colonne, en ordre decroissant.
        self.horizontalHeader().setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        self.setSortingEnabled(sortable)
        self.horizontalHeader().setStretchLastSection(True)

    def set_rows(
        self,
        rows: tuple[tuple[str, ...], ...],
        *,
        keys: Sequence[Hashable] | None = None,
    ) -> None:
        """Remplace le contenu du tableau.

        Args:
            rows: Lignes a afficher, chacune comportant autant de valeurs que de
                colonnes.
            keys: Identifiant de chaque ligne (meme longueur que ``rows``), restitue
                par :meth:`selected_key`.

        Raises:
            ValueError: ``keys`` n'a pas la meme longueur que ``rows``.
        """
        if keys is not None and len(keys) != len(rows):
            raise ValueError("keys doit comporter un identifiant par ligne")
        self.setSortingEnabled(False)
        self.setRowCount(0)
        for index, row_values in enumerate(rows):
            row = self.rowCount()
            self.insertRow(row)
            for column, value in enumerate(row_values):
                item = _SortableItem(value)
                item.setToolTip(value)
                item.setData(SORT_KEY_ROLE, sort_key(value))
                if column == 0 and keys is not None:
                    item.setData(ROW_KEY_ROLE, keys[index])
                self.setItem(row, column, item)
        self.setSortingEnabled(self._sortable)
        self.resizeColumnsToContents()

    def selected_key(self) -> Hashable | None:
        """Retourne l'identifiant de la ligne selectionnee, ou ``None``.

        Returns:
            L'identifiant fourni a :meth:`set_rows` pour la ligne selectionnee,
            independamment du tri applique par l'utilisateur.
        """
        rows = {index.row() for index in self.selectedIndexes()}
        if len(rows) != 1:
            return None
        item = self.item(rows.pop(), 0)
        return item.data(ROW_KEY_ROLE) if item is not None else None


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

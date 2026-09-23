"""Apparence de l'application.

Parti pris graphique : sobre et dense, comme un outil d'exploitation utilise toute la
journee. Pas de couleur vive en dehors des indicateurs, une seule police, des
contrastes suffisants.

Les couleurs sont centralisees ici : aucune feuille de style n'est ecrite dans un
widget, afin qu'un changement d'apparence ne necessite pas de parcourir l'interface.
"""

from __future__ import annotations

from typing import Final

__all__ = ["Palette", "STYLESHEET"]


class Palette:
    """Couleurs de l'application."""

    BACKGROUND: Final = "#F4F6F8"
    SURFACE: Final = "#FFFFFF"
    SIDEBAR: Final = "#1E2A35"
    SIDEBAR_HOVER: Final = "#2B3A48"
    SIDEBAR_ACTIVE: Final = "#1F6FB2"
    SIDEBAR_TEXT: Final = "#D6DEE6"
    SIDEBAR_SECTION: Final = "#7D8B99"
    TEXT: Final = "#1E2A35"
    TEXT_MUTED: Final = "#5C6B7A"
    BORDER: Final = "#D8DEE4"
    ACCENT: Final = "#1F6FB2"
    SUCCESS: Final = "#4C9A5E"
    WARNING: Final = "#E8A33D"
    DANGER: Final = "#C0504D"
    INFO_BACKGROUND: Final = "#EAF2F9"
    WARNING_BACKGROUND: Final = "#FDF4E5"


STYLESHEET: Final = f"""
QMainWindow, QWidget {{
    background-color: {Palette.BACKGROUND};
    color: {Palette.TEXT};
    font-size: 13px;
}}

QFrame#Sidebar {{
    background-color: {Palette.SIDEBAR};
    border: none;
}}

QLabel#SidebarTitle {{
    color: #FFFFFF;
    font-size: 15px;
    font-weight: 600;
    padding: 16px 16px 4px 16px;
}}

QLabel#SidebarSubtitle {{
    color: {Palette.SIDEBAR_SECTION};
    font-size: 11px;
    padding: 0 16px 12px 16px;
}}

QLabel#SidebarSection {{
    color: {Palette.SIDEBAR_SECTION};
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 1px;
    padding: 14px 16px 4px 16px;
}}

QPushButton#SidebarButton {{
    background-color: transparent;
    color: {Palette.SIDEBAR_TEXT};
    border: none;
    border-left: 3px solid transparent;
    padding: 8px 16px;
    text-align: left;
    font-size: 13px;
}}

QPushButton#SidebarButton:hover {{
    background-color: {Palette.SIDEBAR_HOVER};
}}

QPushButton#SidebarButton:checked {{
    background-color: {Palette.SIDEBAR_HOVER};
    border-left: 3px solid {Palette.SIDEBAR_ACTIVE};
    color: #FFFFFF;
    font-weight: 600;
}}

QLabel#PageTitle {{
    font-size: 19px;
    font-weight: 600;
    color: {Palette.TEXT};
}}

QLabel#PageSubtitle {{
    font-size: 12px;
    color: {Palette.TEXT_MUTED};
}}

QFrame#Card {{
    background-color: {Palette.SURFACE};
    border: 1px solid {Palette.BORDER};
    border-radius: 4px;
}}

QLabel#CardTitle {{
    font-size: 11px;
    font-weight: 600;
    color: {Palette.TEXT_MUTED};
    letter-spacing: 0.5px;
}}

QLabel#CardValue {{
    font-size: 26px;
    font-weight: 600;
    color: {Palette.TEXT};
}}

QLabel#CardHint {{
    font-size: 11px;
    color: {Palette.TEXT_MUTED};
}}

QFrame#Notice {{
    background-color: {Palette.INFO_BACKGROUND};
    border: 1px solid {Palette.BORDER};
    border-left: 3px solid {Palette.ACCENT};
    border-radius: 3px;
}}

QFrame#NoticeWarning {{
    background-color: {Palette.WARNING_BACKGROUND};
    border: 1px solid {Palette.BORDER};
    border-left: 3px solid {Palette.WARNING};
    border-radius: 3px;
}}

QLabel#NoticeText {{
    color: {Palette.TEXT};
    font-size: 12px;
}}

QGroupBox {{
    background-color: {Palette.SURFACE};
    border: 1px solid {Palette.BORDER};
    border-radius: 4px;
    margin-top: 14px;
    padding-top: 10px;
    font-weight: 600;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: {Palette.TEXT_MUTED};
}}

QTableWidget, QTableView, QTreeWidget {{
    background-color: {Palette.SURFACE};
    border: 1px solid {Palette.BORDER};
    gridline-color: {Palette.BORDER};
    selection-background-color: {Palette.INFO_BACKGROUND};
    selection-color: {Palette.TEXT};
}}

QHeaderView::section {{
    background-color: #EDF1F4;
    color: {Palette.TEXT_MUTED};
    border: none;
    border-right: 1px solid {Palette.BORDER};
    border-bottom: 1px solid {Palette.BORDER};
    padding: 6px 8px;
    font-weight: 600;
}}

QPushButton {{
    background-color: {Palette.SURFACE};
    border: 1px solid {Palette.BORDER};
    border-radius: 3px;
    padding: 6px 14px;
}}

QPushButton:hover {{
    border-color: {Palette.ACCENT};
}}

QPushButton:disabled {{
    color: {Palette.TEXT_MUTED};
    background-color: #EDF1F4;
}}

QPushButton#PrimaryButton {{
    background-color: {Palette.ACCENT};
    color: #FFFFFF;
    border: 1px solid {Palette.ACCENT};
    font-weight: 600;
}}

QPushButton#PrimaryButton:hover {{
    background-color: #1A5F99;
}}

QPushButton#PrimaryButton:disabled {{
    background-color: #9FB8CC;
    border-color: #9FB8CC;
    color: #F0F4F8;
}}

QLineEdit, QComboBox, QDateEdit, QSpinBox {{
    background-color: {Palette.SURFACE};
    border: 1px solid {Palette.BORDER};
    border-radius: 3px;
    padding: 5px 8px;
}}

QLineEdit:focus, QComboBox:focus, QDateEdit:focus {{
    border-color: {Palette.ACCENT};
}}

QStatusBar {{
    background-color: {Palette.SURFACE};
    border-top: 1px solid {Palette.BORDER};
    color: {Palette.TEXT_MUTED};
}}

QStatusBar::item {{
    border: none;
}}

QTextEdit {{
    background-color: {Palette.SURFACE};
    border: 1px solid {Palette.BORDER};
    border-radius: 3px;
}}

QScrollArea {{
    border: none;
    background-color: transparent;
}}
"""
"""Feuille de style Qt appliquee a l'ensemble de l'application."""

"""Composants d'interface partages."""

from app.ui.common.errors import confirm, format_error, show_error, show_information
from app.ui.common.page import Page
from app.ui.common.widgets import (
    EmptyState,
    IndicatorCard,
    NoticeBanner,
    PageHeader,
    ReadOnlyTable,
    SectionTitle,
)

__all__ = [
    "EmptyState",
    "IndicatorCard",
    "NoticeBanner",
    "Page",
    "PageHeader",
    "ReadOnlyTable",
    "SectionTitle",
    "confirm",
    "format_error",
    "show_error",
    "show_information",
]

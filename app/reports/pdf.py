"""Export PDF d'un rapport : une rubrique par section, au format A4 paysage."""

from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.reports.model import ReportTable

__all__ = ["write_pdf"]

_EMPHASIS = colors.HexColor("#BFE8E8")
_HEADER = colors.HexColor("#DDE3E8")


def write_pdf(path: Path, header: str, tables: tuple[ReportTable, ...]) -> Path:
    """Ecrit un document PDF.

    Args:
        path: Fichier de destination (``.pdf``).
        header: En-tete du document.
        tables: Rubriques du rapport.

    Returns:
        Le chemin du fichier ecrit.
    """
    styles = getSampleStyleSheet()
    cell_style = styles["BodyText"].clone("cell", fontSize=7, leading=8.5)
    story: list[object] = []
    for index, table in enumerate(tables):
        if index:
            story.append(PageBreak())
        story.append(Paragraph(escape(header), styles["Normal"]))
        story.append(Paragraph(escape(table.title), styles["Heading2"]))
        data = [
            [Paragraph(f"<b>{escape(title)}</b>", cell_style) for title in table.headers],
            *[[Paragraph(escape(value or ""), cell_style) for value in row] for row in table.rows],
        ]
        if len(data) == 1:
            data.append([Paragraph("-", cell_style)] + [""] * (len(table.headers) - 1))
        grid = Table(data, repeatRows=1)
        commands: list[tuple[object, ...]] = [
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ("BACKGROUND", (0, 0), (-1, 0), _HEADER),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]
        for row in table.emphasized:
            commands.append(("BACKGROUND", (0, row + 1), (-1, row + 1), _EMPHASIS))
            # Ligne d'intitule seul (interruption, sous-titre) : etalee sur la largeur.
            if row < len(table.rows) and not any(table.rows[row][1:]):
                commands.append(("SPAN", (0, row + 1), (-1, row + 1)))
        grid.setStyle(TableStyle(commands))
        story.append(grid)
        if table.note:
            story.append(Spacer(1, 3 * mm))
            story.append(Paragraph(escape(table.note), styles["Italic"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    document = SimpleDocTemplate(
        str(path),
        pagesize=landscape(A4),
        leftMargin=10 * mm,
        rightMargin=10 * mm,
        topMargin=10 * mm,
        bottomMargin=10 * mm,
        title=header,
    )
    document.build(story)
    return path

"""Modele ``Vehicle`` : vehicule equipe d'un tachygraphe."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.models.base import Base, TimestampMixin

if TYPE_CHECKING:  # pragma: no cover - imports de typage uniquement
    from app.database.models.activity import Activity
    from app.database.models.tachograph_file import TachographFile

__all__ = ["Vehicle"]


class Vehicle(TimestampMixin, Base):
    """Vehicule identifie par son immatriculation.

    Le VIN et l'identifiant du tachygraphe ne sont renseignes que lorsqu'ils ont
    ete decodes depuis un fichier V1B ou saisis par l'exploitant.
    """

    __tablename__ = "vehicles"

    id: Mapped[int] = mapped_column(primary_key=True)

    registration: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        unique=True,
        index=True,
        doc="Numero d'immatriculation, identifiant metier du vehicule.",
    )
    registration_country: Mapped[str | None] = mapped_column(
        String(3), doc="Code pays d'immatriculation, si decode."
    )
    vin: Mapped[str | None] = mapped_column(
        String(24), unique=True, doc="Numero d'identification du vehicule (VIN), si connu."
    )
    tachograph_identifier: Mapped[str | None] = mapped_column(
        String(64), doc="Identifiant de l'unite embarquee, si decode."
    )

    notes: Mapped[str | None] = mapped_column(String(500), doc="Commentaire libre de l'exploitant.")

    activities: Mapped[list[Activity]] = relationship(back_populates="vehicle")
    files: Mapped[list[TachographFile]] = relationship(back_populates="vehicle")

    @property
    def display_name(self) -> str:
        """Immatriculation du vehicule, utilisee comme libelle dans l'interface."""
        return self.registration

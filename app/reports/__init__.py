"""Generation des rapports (ANALYSE -> RAPPORT).

Un generateur recoit des donnees deja calculees par les services et se contente de
les mettre en forme. Il n'interroge pas la base et ne recalcule aucun temps, afin
qu'un chiffre affiche dans l'interface et le meme chiffre dans un export ne puissent
jamais diverger.

* ``tables.py`` : mise en tableaux, commune a l'ecran et aux exports ;
* ``excel.py`` : classeurs Excel (openpyxl), une feuille par rubrique ;
* ``pdf.py`` : documents PDF (ReportLab) ;
* ``csv_export.py`` : export CSV.
"""

__all__: list[str] = []

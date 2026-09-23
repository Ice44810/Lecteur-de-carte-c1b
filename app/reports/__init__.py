"""Generation des rapports (ANALYSE -> RAPPORT).

ETAT : NON IMPLEMENTE (phase 9 de la feuille de route).

Regle de conception a respecter lors de l'implementation : un generateur recoit des
donnees deja calculees par ``app.services.analysis_service`` et se contente de les
mettre en forme. Il n'interroge pas la base et ne recalcule aucun temps, afin qu'un
chiffre affiche dans l'interface et le meme chiffre dans un PDF ne puissent jamais
diverger.

Modules prevus :

* ``excel.py`` : classeurs Excel (openpyxl) ;
* ``pdf.py`` : documents PDF (ReportLab) ;
* ``csv_export.py`` : export CSV ;
* ``templates/`` : gabarits de mise en page partages.
"""

__all__: list[str] = []

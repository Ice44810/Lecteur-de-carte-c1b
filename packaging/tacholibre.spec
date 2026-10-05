# -*- mode: python ; coding: utf-8 -*-
"""Construction de l'executable autonome TachoLibre (PyInstaller).

A lancer depuis la racine du depot, sur le systeme cible :

    pip install ".[package,pcsc]"
    pyinstaller packaging/tacholibre.spec

Resultat dans ``dist/`` : ``TachoLibre.exe`` (Windows), ``TachoLibre.app`` (macOS),
``TachoLibre/`` (Linux). PyInstaller ne fait pas de compilation croisee : chaque
systeme construit son propre executable.
"""

import os
import sys
from importlib.util import find_spec

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = collect_data_files("reportlab")
hiddenimports = collect_submodules("app") + ["sqlalchemy.dialects.sqlite"]
if sys.platform.startswith("win"):
    datas += collect_data_files("tzdata")
    hiddenimports += collect_submodules("tzdata")
if find_spec("smartcard") is not None:
    hiddenimports += collect_submodules("smartcard")

analysis = Analysis(
    [os.path.join(SPECPATH, "launcher.py")],
    pathex=[os.path.join(SPECPATH, "..")],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["pytest", "ruff"],
)
pyz = PYZ(analysis.pure)

executable = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="TachoLibre",
    console=False,
)
collection = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    name="TachoLibre",
)

if sys.platform == "darwin":
    app = BUNDLE(
        collection,
        name="TachoLibre.app",
        bundle_identifier="org.tacholibre.TachoLibre",
        info_plist={"NSHighResolutionCapable": True},
    )

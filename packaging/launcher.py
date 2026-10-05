"""Point d'entree de l'executable autonome construit par PyInstaller."""

import sys

from app.main import main

if __name__ == "__main__":
    sys.exit(main())

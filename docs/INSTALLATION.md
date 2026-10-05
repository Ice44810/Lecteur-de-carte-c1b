# Installation de TachoLibre

TachoLibre fonctionne sous **Windows 10/11**, **macOS 12 ou plus récent** et
**Linux**. Deux façons de l'installer :

- **exécutable autonome** : rien d'autre à installer, il se construit une fois par
  système (section 6) ;
- **depuis les sources** : sections 1 à 5, pour le développement ou en attendant
  un exécutable.

Le lecteur de carte est facultatif : sans lui, l'application importe des fichiers
`.C1B` et fonctionne normalement.

## 1. Prérequis communs

- Python 3.11 ou plus récent ;
- pour le lecteur de carte : un lecteur USB PC/SC (norme CCID), comme la plupart
  des lecteurs vendus pour les cartes tachygraphiques.

| Système | Installer Python | Commande Python |
| --- | --- | --- |
| Windows | [python.org](https://www.python.org/downloads/) — cocher « Add python.exe to PATH » | `py` |
| macOS | [python.org](https://www.python.org/downloads/) ou `brew install python@3.12` | `python3` |
| Linux | paquets de la distribution (`sudo apt install python3 python3-venv`) | `python3` |

## 2. Installation depuis les sources

### Windows (PowerShell)

```powershell
git clone https://github.com/Ice44810/Lecteur-de-carte-c1b.git
cd Lecteur-de-carte-c1b
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install ".[pcsc]"
```

Si PowerShell refuse d'activer l'environnement (« l'exécution de scripts est
désactivée »), lancez une fois
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, ou utilisez l'invite de
commandes classique avec `.venv\Scripts\activate.bat`.

Le service Windows « Carte à puce » (SCardSvr) assure la lecture : rien d'autre à
installer. `pyscard` est fourni prêt à l'emploi pour Windows.

### macOS (Terminal)

```bash
git clone https://github.com/Ice44810/Lecteur-de-carte-c1b.git
cd Lecteur-de-carte-c1b
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install ".[pcsc]"
```

Le service PC/SC est intégré à macOS : rien d'autre à installer. `pyscard` est
fourni prêt à l'emploi pour macOS.

### Linux (Debian, Ubuntu)

Paquets système, puis l'application :

```bash
sudo apt install python3-venv pcscd pcsc-tools libpcsclite-dev python3-dev build-essential swig
git clone https://github.com/Ice44810/Lecteur-de-carte-c1b.git
cd Lecteur-de-carte-c1b
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install ".[pcsc]"
```

Sous Linux, `pyscard` est compilé à l'installation : `libpcsclite-dev`,
`python3-dev`, `build-essential` et `swig` sont nécessaires. `pcsc-tools` fournit
`pcsc_scan`, utile au diagnostic. Équivalent Fedora :

```bash
sudo dnf install python3-devel pcsc-lite pcsc-tools pcsc-lite-devel gcc swig
```

Le service `pcscd` démarre de lui-même à la première sollicitation. Pour le
démarrer explicitement : `sudo systemctl enable --now pcscd`.

**Bibliothèques Qt.** Sur un poste de bureau, elles sont déjà présentes. Sur un
serveur ou un conteneur :

```bash
sudo apt install libegl1 libgl1 libxkbcommon0 libdbus-1-3 libfontconfig1 libglib2.0-0
sudo apt install libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 libxcb-image0 \
    libxcb-keysyms1 libxcb-render-util0 libxcb-xkb1
```

Symptôme d'une bibliothèque manquante : `Could not load the Qt platform plugin
"xcb"`. Pour identifier la bibliothèque absente :

```bash
ldd "$(python -c 'import PySide6, os; print(os.path.dirname(PySide6.__file__))')"/Qt/plugins/platforms/libqxcb.so \
    | grep 'not found'
```

## 3. Lancement

Environnement activé (section 2), sur les trois systèmes :

```bash
python -m app.main            # interface graphique
python -m app.main --check    # vérification sans interface, puis sortie
```

Après `pip install .`, la commande `tacholibre` est aussi disponible.

Dans un nouveau terminal, réactivez d'abord l'environnement :
`.venv\Scripts\Activate.ps1` (Windows) ou `source .venv/bin/activate`
(macOS, Linux).

## 4. Emplacement des données

Depuis les sources, les données restent dans le dépôt (`data/` et `logs/`). Avec
un exécutable ou une installation, chaque système suit sa convention :

| Système | Données (base, originaux, exports) | Journaux |
| --- | --- | --- |
| Windows | `%LOCALAPPDATA%\TachoLibre\` | `%LOCALAPPDATA%\TachoLibre\logs\` |
| macOS | `~/Library/Application Support/TachoLibre/` | `~/Library/Logs/TachoLibre/` |
| Linux | `~/.local/share/tacholibre/` | `~/.local/state/tacholibre/logs/` |

Pour placer les données ailleurs (un partage réseau sauvegardé, par exemple) :

```powershell
# Windows
$env:TACHOLIBRE_DATA_DIR = "D:\TachoLibre"; python -m app.main
```

```bash
# macOS, Linux
TACHOLIBRE_DATA_DIR=/srv/tacholibre python -m app.main
```

**Sauvegarde.** Le dossier `originals/` contient les fichiers tels qu'ils ont été
remis par la carte ou le tachygraphe : c'est le contenu à sauvegarder en priorité,
la base pouvant être reconstruite à partir d'eux (Historique > Décoder les
fichiers en attente). Les fichiers originaux ne sont jamais modifiés ni supprimés
par l'application.

**Ancien nom (tachy-linux).** Une installation antérieure reste utilisée telle
quelle, sans rien déplacer : dossiers `~/.local/share/tachy-linux` et
`~/.local/state/tachy-linux`, base `tachy.sqlite3`, variables `TACHY_*`
(les nouvelles variables `TACHOLIBRE_*` l'emportent si les deux existent).

## 5. Diagnostic du lecteur de carte

L'application diagnostique chaque situation dans la page « Lecteur de carte » et
indique l'action adaptée au système. Vérifications complémentaires :

| Symptôme | Windows | macOS | Linux |
| --- | --- | --- | --- |
| Prise en charge non installée | `pip install pyscard` | `pip install pyscard` | paquets de la section 2, puis `pip install ".[pcsc]"` |
| Service PC/SC injoignable | `services.msc` > « Carte à puce » : Démarré, Automatique | rebrancher le lecteur, redémarrer | `systemctl status pcscd` puis `sudo systemctl start pcscd` |
| Aucun lecteur détecté | Gestionnaire de périphériques > Lecteurs de cartes à puce | Informations système > USB | `pcsc_scan`, puis `lsusb` |
| Carte non détectée | réinsérer la carte, puce vers le haut | idem | `pcsc_scan` (la carte apparaît-elle ?) |

Sous Linux, si `pcsc_scan` fonctionne mais pas l'application, vérifiez qu'aucune
politique de sécurité (AppArmor, SELinux) ou isolation de conteneur ne bloque
l'accès au service. Dans un conteneur, partagez la socket et le périphérique :
`-v /run/pcscd/pcscd.comm:/run/pcscd/pcscd.comm --device /dev/bus/usb`.

## 6. Construire un exécutable autonome

L'exécutable embarque Python et toutes les dépendances : il suffit ensuite de le
copier sur les postes. **Chaque système construit son propre exécutable** (on ne
peut pas produire un `.exe` Windows depuis Linux, ni l'inverse).

Environnement activé (section 2), depuis la racine du dépôt :

```bash
pip install ".[package,pcsc]"
pyinstaller --noconfirm packaging/tacholibre.spec
```

| Système | Résultat dans `dist/` | Lancement |
| --- | --- | --- |
| Windows | `TachoLibre\TachoLibre.exe` | double-clic |
| macOS | `TachoLibre.app` | double-clic (voir ci-dessous) |
| Linux | `TachoLibre/TachoLibre` | `./TachoLibre` |

Le dossier `dist/TachoLibre` (ou l'application `.app`) se distribue tel quel, par
exemple compressé en `.zip`.

**macOS.** Une application non signée est bloquée au premier lancement :
clic droit > Ouvrir, puis confirmer. Pour une diffusion large, signez et faites
notariser l'application avec un compte développeur Apple.

**Windows.** SmartScreen peut avertir au premier lancement d'un exécutable non
signé : « Informations complémentaires » > « Exécuter quand même ». Pour une
diffusion large, signez l'exécutable avec un certificat de signature de code.

## 7. Tests

```bash
pip install -r requirements-dev.txt
python -m pytest
```

Les tests s'exécutent sans écran (plate-forme Qt `offscreen`, positionnée
automatiquement) et sans lecteur. Le fichier `.github/workflows/tests.yml` les
lance sous Windows, macOS et Linux à chaque envoi sur GitHub.

## 8. Désinstallation

Supprimez le dossier du dépôt (et son `.venv`), ou le dossier de l'exécutable. Les
données ne sont pas supprimées : retirez aussi la racine de données (section 4)
**après avoir vérifié que les fichiers originaux ne vous sont plus nécessaires**,
les obligations de conservation des données tachygraphiques restant à la charge
de l'entreprise.

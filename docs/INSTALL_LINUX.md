# Installation sur Linux

Ce document couvre l'installation depuis les sources, les paquets système requis
et le diagnostic de la pile PC/SC. L'empaquetage (`.deb`, AppImage) fait l'objet
de la phase 13 et n'est pas encore disponible.

## 1. Prérequis

- une distribution Linux à jour (les commandes ci-dessous sont données pour
  Debian et Ubuntu, avec l'équivalent Fedora lorsqu'il diffère) ;
- Python 3.11 ou plus récent ;
- un environnement graphique pour l'interface, ou aucun si vous n'utilisez que
  le mode `--check`.

Vérification de la version de Python :

```bash
python3 --version
```

## 2. Paquets système

### Qt (interface graphique)

PySide6 est installé par `pip`, mais s'appuie sur des bibliothèques système.
Sur une installation de bureau complète elles sont généralement déjà présentes ;
sur un serveur ou un conteneur, elles doivent être ajoutées :

```bash
sudo apt install \
    libegl1 libgl1 libxkbcommon0 libdbus-1-3 libfontconfig1 libglib2.0-0
```

Ces paquets suffisent au mode `--check` et à l'exécution des tests. L'affichage
sur un serveur X en exige davantage, car le greffon `xcb` de Qt s'appuie sur
plusieurs bibliothèques XCB :

```bash
sudo apt install \
    libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 libxcb-image0 \
    libxcb-keysyms1 libxcb-render-util0 libxcb-xkb1
```

Équivalent Fedora :

```bash
sudo dnf install mesa-libEGL mesa-libGL libxkbcommon dbus-libs fontconfig glib2
sudo dnf install \
    libxkbcommon-x11 xcb-util-cursor xcb-util-wm xcb-util-image \
    xcb-util-keysyms xcb-util-renderutil libxcb
```

Symptôme d'une bibliothèque manquante : au démarrage, Qt signale
`Could not load the Qt platform plugin "xcb" in "" even though it was found`,
suivi d'un abandon du processus. Le nom du greffon est indiqué mais pas celui de
la bibliothèque absente ; pour l'identifier :

```bash
ldd "$(python -c 'import PySide6, os; print(os.path.dirname(PySide6.__file__))')"/Qt/plugins/platforms/libqxcb.so \
    | grep 'not found'
```

Chaque ligne affichée correspond à un paquet à installer. L'affichage détaillé du
chargement des greffons (`QT_DEBUG_PLUGINS=1 python -m app.main`) complète le
diagnostic si nécessaire.

### PC/SC (lecteur de carte, optionnel)

```bash
sudo apt install pcscd pcsc-tools libpcsclite-dev
sudo systemctl enable --now pcscd
```

Équivalent Fedora :

```bash
sudo dnf install pcsc-lite pcsc-tools pcsc-lite-devel
sudo systemctl enable --now pcscd
```

`libpcsclite-dev` (`pcsc-lite-devel`) est nécessaire à la compilation de
`pyscard` ; `pcsc-tools` fournit `pcsc_scan`, utile au diagnostic.

## 3. Installation de l'application

```bash
git clone https://github.com/Ice44810/Lecteur-de-carte-c1b.git
cd Lecteur-de-carte-c1b
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Support du lecteur de carte (à faire après l'installation des paquets système
ci-dessus) :

```bash
pip install ".[pcsc]"
```

Dépendances de développement (tests et analyse statique) :

```bash
pip install -r requirements-dev.txt
```

## 4. Vérification de l'installation

Sans interface graphique :

```bash
python -m app.main --check
```

La commande crée les répertoires applicatifs, applique les migrations de schéma
et affiche un compte rendu. Un code de sortie 0 signifie que le socle est
fonctionnel. En cas d'échec, le message est présenté sous la forme *message /
cause / action* ; le détail technique est dans `logs/app.log`.

Avec interface graphique :

```bash
python -m app.main
```

Exécution de la suite de tests :

```bash
python -m pytest
```

## 5. Emplacement des données

Depuis les sources, les données restent dans le dépôt (`data/` et `logs/`), ce
qui évite de disperser les fichiers pendant le développement. Une fois
l'application installée sur le système, elle utilise les emplacements standard
XDG.

| Contenu | Depuis les sources | Installée |
| --- | --- | --- |
| Fichiers originaux archivés | `data/originals/` | `~/.local/share/tachy-linux/originals/` |
| Base SQLite | `data/database/tachy.sqlite3` | `~/.local/share/tachy-linux/database/tachy.sqlite3` |
| Rapports produits | `data/exports/` | `~/.local/share/tachy-linux/exports/` |
| Journaux | `logs/app.log` | `~/.local/state/tachy-linux/logs/app.log` |

Pour placer les données ailleurs — un partage réseau sauvegardé, par exemple :

```bash
TACHY_DATA_DIR=/srv/tachy python -m app.main
```

Le répertoire doit être accessible en écriture à l'utilisateur qui lance
l'application. À défaut, le démarrage échoue avec une action explicite
(« choisissez un autre répertoire de données »).

**Sauvegarde.** `data/originals/` contient les fichiers tels qu'ils ont été
remis par le tachygraphe ou la carte ; c'est le contenu à sauvegarder en
priorité, la base pouvant être reconstruite à partir de ces fichiers. Les
fichiers originaux ne sont jamais modifiés ni supprimés par l'application.

## 6. Diagnostic de la pile PC/SC

L'application n'exige pas de lecteur : chaque situation est diagnostiquée et
présentée avec l'action correspondante. Le tableau ci-dessous reprend les mêmes
cas, pour un diagnostic en ligne de commande.

| Symptôme dans l'application | Vérification | Correction |
| --- | --- | --- |
| « La prise en charge du lecteur de carte n'est pas installée. » | `python -c "import smartcard"` | `sudo apt install pcscd libpcsclite-dev && pip install ".[pcsc]"` |
| « Le service de lecture de carte n'est pas accessible. » | `systemctl status pcscd` | `sudo systemctl start pcscd` |
| « Aucun lecteur de carte détecté. » | `pcsc_scan` puis `lsusb` | Rebrancher le lecteur, essayer un autre port |
| « Aucune carte insérée. » | `pcsc_scan` (la carte apparaît-elle ?) | Insérer la carte, puce vers le haut |
| « La carte insérée n'a pas été reconnue. » | `pcsc_scan` (l'ATR s'affiche-t-il ?) | Nettoyer la puce, essayer une autre carte |

`pcsc_scan` fonctionnant alors que l'application ne détecte rien indique un
problème de droits d'accès : vérifiez que `pcscd` tourne bien et que
l'utilisateur n'est pas confiné par une politique de sécurité (AppArmor,
SELinux) ou par l'isolation d'un conteneur.

### Cas particulier des conteneurs

Dans un conteneur, le service `pcscd` de l'hôte n'est pas visible par défaut.
Il faut partager sa socket et le périphérique USB :

```bash
docker run --rm -it \
    -v /run/pcscd/pcscd.comm:/run/pcscd/pcscd.comm \
    --device /dev/bus/usb \
    tachy-linux
```

Sans cela, l'application signale simplement que le service n'est pas accessible
et reste utilisable pour toutes ses autres fonctions.

## 7. Désinstallation

```bash
deactivate
rm -rf /chemin/vers/Lecteur-de-carte-c1b/.venv
```

Les données ne sont pas supprimées par cette opération. Pour les retirer aussi,
supprimez la racine de données (`data/` depuis les sources, ou
`~/.local/share/tachy-linux/`) — **après avoir vérifié que les fichiers
originaux qu'elle contient ne vous sont plus nécessaires**, les obligations de
conservation des données tachygraphiques restant à la charge de l'entreprise.

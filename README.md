# tachy-linux

Application de bureau Linux destinée aux entreprises de transport routier, pour
l'archivage et l'analyse des données tachygraphiques : fichiers de carte
conducteur (`.C1B`), fichiers d'unité embarquée (`.V1B`) et, à terme, lecture
directe d'une carte conducteur via un lecteur PC/SC.

**État : phase 1 (socle) terminée.** L'application démarre, gère son référentiel
conducteurs / véhicules, enregistre les fichiers importés et calcule les temps
d'activité. **Le décodage du contenu binaire des fichiers C1B et V1B n'est pas
implémenté**, et aucune règle réglementaire n'est active. Les deux sections
[Ce que l'application fait aujourd'hui](#ce-que-lapplication-fait-aujourdhui) et
[Ce qu'elle ne fait pas encore](#ce-quelle-ne-fait-pas-encore) détaillent cette
frontière, qui est délibérée : voir
[Principes de conception](#principes-de-conception).

---

## Sommaire

- [Installation](#installation)
- [Démarrage](#démarrage)
- [Ce que l'application fait aujourd'hui](#ce-que-lapplication-fait-aujourdhui)
- [Ce qu'elle ne fait pas encore](#ce-quelle-ne-fait-pas-encore)
- [Principes de conception](#principes-de-conception)
- [Architecture](#architecture)
- [Configuration](#configuration)
- [Tests et qualité](#tests-et-qualité)
- [Feuille de route](#feuille-de-route)
- [Documentation](#documentation)

---

## Installation

Prérequis : Linux, Python 3.11 ou plus récent. La procédure détaillée, y compris
les paquets système requis par Qt et par la pile PC/SC, est décrite dans
[`docs/INSTALL_LINUX.md`](docs/INSTALL_LINUX.md).

```bash
git clone https://github.com/Ice44810/Lecteur-de-carte-c1b.git
cd Lecteur-de-carte-c1b
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Le lecteur de carte est une dépendance optionnelle, car il exige des paquets
système :

```bash
sudo apt install pcscd pcsc-tools libpcsclite-dev
pip install ".[pcsc]"
```

L'application fonctionne sans cette pile : l'absence de `pyscard` ou de service
`pcscd` est traitée comme un diagnostic à afficher, pas comme une erreur.

## Démarrage

```bash
python -m app.main
```

Un mode de diagnostic sans interface graphique vérifie la configuration, les
répertoires et le schéma de base, puis rend la main :

```bash
python -m app.main --check
```

```
tachy-linux 0.1.0
Racine des donnees   : /srv/tachy
Fichiers originaux   : /srv/tachy/originals
Base de donnees      : /srv/tachy/database/tachy.sqlite3
Journal              : /home/exploitation/.local/state/tachy-linux/logs/app.log
Schema de base       : version 1
```

Options disponibles : `--data-dir CHEMIN`, `--log-level NIVEAU`, `--check`,
`--version`.

## Ce que l'application fait aujourd'hui

**Socle technique.** Configuration validée et centralisée, journalisation
rotative dans `logs/app.log`, base SQLite créée et migrée automatiquement au
démarrage (six tables : conducteurs, véhicules, fichiers, activités, analyses,
anomalies), et présentation de toute erreur sous la forme *message / cause /
action*.

**Interface.** Une fenêtre principale PySide6 avec dix pages : tableau de bord,
conducteurs, véhicules, import, historique, activités, anomalies, rapports,
lecteur de carte, paramètres. Les pages sont construites à la première visite et
lisent leurs données via la couche de services.

**Référentiel.** Création et consultation des conducteurs et des véhicules,
recherche par nom, numéro de carte ou immatriculation, et signalement des cartes
expirées lorsque la date d'expiration est connue.

**Réception des fichiers.** Un fichier soumis est identifié (extension, taille,
empreinte SHA-256) et confronté à l'historique. Un fichier déjà importé est
reconnu par son empreinte, y compris après un changement de nom, et
l'utilisateur est renvoyé vers l'import existant. **L'examen n'écrit rien dans le
fichier d'origine** — un test vérifie que les octets, la taille et la date de
modification sont inchangés.

**Calcul des temps.** À partir d'activités enregistrées en base, l'application
reconstitue une chronologie par journée et par semaine, cumule les durées par
type d'activité (conduite, travail, disponibilité, repos) et signale les
périodes sans enregistrement. Ces trous sont affichés comme tels et **ne sont
jamais assimilés à du repos**.

**Lecteur de carte.** Détection du lecteur et de la présence d'une carte,
diagnostic explicite de chaque situation (pile PC/SC absente, service arrêté,
lecteur débranché, carte absente, carte non reconnue), et simulateur permettant
de développer et de tester sans matériel.

## Ce qu'elle ne fait pas encore

Ces manques sont documentés, isolés derrière des interfaces, et couverts par des
tests qui vérifient que le refus est explicite.

| Fonction | État | Raison |
| --- | --- | --- |
| Décodage du contenu C1B | Non implémenté | 7 points de structure binaire à confirmer sur spécification officielle |
| Décodage du contenu V1B | Non implémenté | 3 points à confirmer |
| Extraction depuis une carte | Non implémenté | 4 points à confirmer (sélection d'application, identifiants de fichiers, séquence de lecture, assemblage) |
| Détection de dépassements | Aucune règle active | Aucun seuil réglementaire n'a été vérifié sur sa source |
| Rapports PDF et Excel | Non implémenté | Dépend du décodage |
| API REST et synchronisation TMS | Non implémenté | Phases 14 et 15 |
| Paquet `.deb` / AppImage | Non implémenté | Phase 13 |

Toute tentative d'utiliser une de ces fonctions lève une erreur applicative
portant un message, une cause et une action — jamais une valeur inventée.
Concrètement, `parse()` sur un fichier C1B lève `UnconfirmedStructureError` en
citant les points à confirmer, et le jeu de règles livré par défaut est vide
(version `0.0.0-empty`), ce qui est signalé sur le tableau de bord par la mention
« aucun dépassement n'est recherché ».

Le registre complet des incertitudes est dans
[`docs/INCERTITUDES_SPECIFICATION.md`](docs/INCERTITUDES_SPECIFICATION.md), et il
est également interrogeable depuis le code (`app.parser.specification`).

## Principes de conception

Ces règles sont issues du cahier des charges. Chacune est vérifiée par au moins
un test automatisé, de manière à ce qu'une régression soit détectée et non
seulement déconseillée.

1. **Aucune structure binaire n'est devinée.** Un offset, une longueur ou un
   codage non confirmé sur une source officielle n'est pas implémenté. Le code
   concerné lève `UnconfirmedStructureError` en citant les questions ouvertes.
2. **Aucune commande de carte n'est inventée.** Seules les formes génériques
   d'APDU définies par l'ISO/IEC 7816-4 sont implémentées. Aucun identifiant de
   fichier tachygraphique n'est codé, et lorsqu'une extraction est refusée,
   **aucune commande n'est transmise à la carte**.
3. **Aucun seuil réglementaire sans source.** Un seuil se saisit dans
   `rules.json` avec la référence du texte qui le fixe, puis doit être marqué
   comme confirmé pour devenir applicable. Un seuil non confirmé ne peut pas
   être appliqué : la règle qui en dépend est ignorée, et l'utilisateur en est
   informé.
4. **Aucune anomalie n'est présentée comme une infraction.** Le vocabulaire
   employé est « anomalie détectée », « situation à vérifier », « dépassement
   apparent ». Un test vérifie l'absence des termes *infraction*, *délit*,
   *sanction*, *amende* et *illégal* dans les messages produits.
5. **Le fichier d'origine est inviolable.** Il est archivé tel quel, jamais
   modifié, et jamais supprimé automatiquement.
6. **L'utilisateur ne voit jamais une pile d'appels.** Toute erreur est
   présentée en trois parties — message, cause, action — le détail technique
   partant dans le journal.
7. **Les données personnelles restent à leur place.** Nom et prénom
   n'apparaissent ni dans les `repr`, ni dans les journaux, ni dans les
   descriptions d'APDU.
8. **Les couches ne se mélangent pas.** Aucune logique métier ni aucune requête
   SQL dans les widgets ; les services ne connaissent ni SQLAlchemy ni SQLite.

## Architecture

Le flux applicatif est unidirectionnel :

```
Interface (PySide6)  ->  Services  ->  Dépôts  ->  Base SQLite
```

et la donnée traverse une chaîne dont chaque étape est isolée :

```
donnée brute -> donnée décodée -> donnée métier -> analyse -> alerte -> rapport
```

```
app/
├── core/          Briques transverses : énumérations, exceptions, empreintes, temps
├── config/        Paramètres validés (pydantic-settings) et journalisation
├── database/      Modèles SQLAlchemy, migrations, dépôts et leurs Protocol
├── parser/        Décodage C1B / V1B et registre des incertitudes
├── analysis/      Calcul des temps, moteur de règles et catalogue des règles prévues
├── card_reader/   APDU ISO 7816-4, PC/SC, simulateur, carte tachygraphique
├── services/      Cas d'usage, seule porte d'entrée de l'interface
├── reports/       Génération PDF / Excel (phase 9)
└── ui/            Fenêtre principale, navigation et pages
```

Les services ne dépendent que de `Protocol` : le remplacement de SQLite par
PostgreSQL ou par un client REST ne touche pas les couches supérieures. Les
détails sont dans [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Configuration

Toutes les variables d'environnement portent le préfixe `TACHY_` et peuvent
également être placées dans un fichier `.env`. Les chemins sont manipulés avec
`pathlib` ; aucun chemin absolu n'est écrit en dur.

| Variable | Défaut | Rôle |
| --- | --- | --- |
| `TACHY_DATA_DIR` | `data/` depuis les sources, sinon `~/.local/share/tachy-linux` | Racine des données |
| `TACHY_LOG_DIR` | `logs/` depuis les sources, sinon `~/.local/state/tachy-linux/logs` | Répertoire des journaux |
| `TACHY_LOG_LEVEL` | `INFO` | Niveau du journal `app.log` |
| `TACHY_CONSOLE_LOG_LEVEL` | `WARNING` | Niveau affiché sur la sortie standard |
| `TACHY_COMPANY_NAME` | vide | Raison sociale, utilisée en en-tête de rapport |
| `TACHY_AUTO_MIGRATE` | `true` | Applique les migrations au démarrage |
| `TACHY_PCSC_ENABLED` | `true` | Autorise l'usage du lecteur PC/SC |
| `TACHY_TIMEZONE_DISPLAY` | `Europe/Paris` | Fuseau d'affichage (le stockage reste en UTC) |

La racine de données contient `originals/` (archivage immuable), `imports/`
(travail), `database/` et `exports/`.

## Tests et qualité

```bash
pip install -r requirements-dev.txt
python -m pytest                                  # 716 tests
python -m pytest --cov=app --cov-report=term-missing
ruff check app tests && ruff format --check app tests
```

716 tests couvrent 98 % des instructions de `app` (hors interface et point
d'entrée, testés séparément). Les tests d'interface s'exécutent sans écran grâce
à `QT_QPA_PLATFORM=offscreen`, positionné automatiquement, et les tests PC/SC
n'exigent aucun matériel : la bibliothèque `pyscard` y est remplacée par un
double, ce qui permet de couvrir chaque cas d'erreur, y compris le retrait de la
carte en cours de lecture.

| Domaine | Tests |
| --- | --- |
| `tests/analysis` | 130 |
| `tests/card_reader` | 125 |
| `tests/services` | 118 |
| `tests/parser` | 96 |
| `tests/core` | 80 |
| `tests/database` | 80 |
| `tests/ui` | 49 |
| `tests/config` | 18 |
| Démarrage (`bootstrap`, `main`) | 20 |

Le projet n'est pas considéré comme livrable si un test échoue.

## Feuille de route

| # | Phase | État |
| --- | --- | --- |
| 1 | Socle : configuration, base, interface, tests | terminée |
| 2 | Modèles de données | terminée |
| 3 | Import et archivage des fichiers C1B | en attente du décodage |
| 4 | Décodage C1B | à faire — nécessite la spécification officielle |
| 5 | Activités conducteur | structures prêtes |
| 6 | Analyse des temps | primitives prêtes, persistance à faire |
| 7 | Moteur de règles | cadre prêt, aucune règle active |
| 8 | Tableau de bord | terminée |
| 9 | Rapports PDF et Excel | à faire |
| 10 | Import V1B | à faire |
| 11 | Lecteur PC/SC | terminée |
| 12 | Lecture d'une carte conducteur | à faire — nécessite la spécification officielle |
| 13 | Paquet Linux (`.deb`, AppImage) | à faire |
| 14 | API REST (FastAPI) | à faire |
| 15 | Synchronisation TMS | à faire |

## Documentation

- [`docs/INSTALL_LINUX.md`](docs/INSTALL_LINUX.md) — installation, paquets
  système, diagnostic de la pile PC/SC.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — couches, flux de données,
  conventions.
- [`docs/INCERTITUDES_SPECIFICATION.md`](docs/INCERTITUDES_SPECIFICATION.md) —
  les 14 points à confirmer avant tout décodage, et la procédure pour les lever.
- [`docs/REGLES.md`](docs/REGLES.md) — comment une règle réglementaire est
  documentée, configurée puis activée.

## Licence

Voir [`LICENSE`](LICENSE).

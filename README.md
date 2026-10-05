# TachoLibre

Application de bureau pour **Windows, macOS et Linux** destinée aux entreprises de
transport routier : lecture des cartes conducteur via un lecteur PC/SC, archivage
et analyse des données tachygraphiques (fichiers de carte conducteur `.C1B`,
fichiers d'unité embarquée `.V1B`).

**État.** L'application lit une carte conducteur dès son insertion dans un lecteur
PC/SC, décode les fichiers de carte (`.C1B`), enregistre conducteur, véhicules et
activités, calcule les temps et produit le rapport de carte (écran, Excel, PDF,
CSV). Le décodage a été validé sur une carte réelle en comparant chaque valeur à
celles d'un logiciel de lecture du marché. **Le décodage des fichiers d'unité
embarquée (`.V1B`) n'est pas implémenté**, et aucune règle réglementaire n'est
active. Les deux sections
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

Prérequis : Windows 10/11, macOS 12 ou Linux, et Python 3.11 ou plus récent. La
procédure complète pour chaque système, le diagnostic du lecteur et la
construction d'un exécutable autonome sont décrits dans
[`docs/INSTALLATION.md`](docs/INSTALLATION.md).

En bref, depuis les sources :

```bash
git clone https://github.com/Ice44810/Lecteur-de-carte-c1b.git
cd Lecteur-de-carte-c1b
python -m venv .venv            # Windows : py -m venv .venv
source .venv/bin/activate       # Windows : .venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install ".[pcsc]"           # lecteur de carte (Linux : paquets système d'abord)
```

Le lecteur de carte est facultatif : sous Windows et macOS, le service PC/SC est
intégré au système ; sous Linux, installez d'abord `pcscd` et `libpcsclite-dev`.
Sans lecteur, l'application fonctionne normalement et importe des fichiers `.C1B`.

**Exécutable autonome.** `pip install ".[package,pcsc]"` puis
`pyinstaller packaging/tacholibre.spec` produit `TachoLibre.exe` (Windows),
`TachoLibre.app` (macOS) ou `TachoLibre` (Linux) dans `dist/`. Chaque système
construit le sien.

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
TachoLibre 0.1.0
Racine des donnees   : /srv/tacholibre
Fichiers originaux   : /srv/tacholibre/originals
Base de donnees      : /srv/tacholibre/database/tacholibre.sqlite3
Journal              : /home/exploitation/.local/state/tacholibre/logs/app.log
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

**Archivage.** Le fichier est copié dans `originals/`, l'empreinte de la copie est
vérifiée, la copie passe en lecture seule et le fichier est inscrit dans
l'historique des téléchargements. Deux téléchargements d'une même carte qui ne
diffèrent que par leurs signatures (les signatures de 2e génération changent à
chaque lecture) sont reconnus comme un doublon. Un fichier vide ou tronqué est
archivé avec l'état « Échec ». Le décodage peut être rejoué sur les archives
depuis l'historique, sans nouvel import.

**Décodage des cartes (`.C1B`).** Identité du titulaire et de la carte, permis de
conduire, activités (avec le statut carte insérée, saisie manuelle ou inconnue, et
conducteur seul ou équipage), véhicules utilisés et kilométrages, lieux de début
et de fin de période, événements et anomalies, conditions particulières. Les
structures sont celles de l'appendice 1 de l'annexe IC du règlement (UE) 2016/799.
Les données propres à la 2e génération (positions GNSS) sont archivées mais pas
encore affichées. Une fiche saisie manuellement n'est jamais écrasée : seuls ses
champs vides sont complétés. Une activité déjà enregistrée par un téléchargement
précédent n'est pas dupliquée.

**Rapport de carte.** Page « Données de la carte » et exports Excel (une feuille
par rubrique), PDF et CSV : informations de la carte, événements, périodes de
travail journalières (avec l'interruption qui suit chacune et sa part dans les
24 heures), activités, véhicules et pays, en heure locale. Ce sont des mesures,
sans appréciation de conformité.

**Statistiques et contrôles de flotte.** Sur une période choisie :

- activité cumulée par conducteur (détail journalier facultatif, en heures-minutes
  ou en heures-centièmes) ;
- distance cumulée par conducteur et par véhicule ;
- exports Excel : synthèse, export détaillé, export des anomalies ;
- excès de vitesse enregistrés sur les cartes ;
- conduites sans carte au-delà d'un nombre de kilomètres choisi, et continuité des
  véhicules : un véhicule dont le compteur a avancé entre deux utilisations connues
  a roulé sans qu'aucune carte importée ne l'enregistre ;
- continuité des conducteurs : périodes sans aucun enregistrement ;
- délais de téléchargement : 28 jours pour les cartes, 90 jours pour les unités
  embarquées (règlement (UE) n° 581/2010, article 1er) ;
- conducteurs et véhicules inconnus : apparus à l'import d'une carte et non confirmés
  dans la flotte. Une fiche saisie manuellement est confirmée d'office ; les autres
  se confirment depuis les pages Conducteurs et Véhicules.

**Calcul des temps.** À partir d'activités enregistrées en base, l'application
reconstitue une chronologie par journée et par semaine, cumule les durées par
type d'activité (conduite, travail, disponibilité, repos) et signale les
périodes sans enregistrement. Ces trous sont affichés comme tels et **ne sont
jamais assimilés à du repos**.

**Lecteur de carte.** Détection du lecteur et de la présence d'une carte,
diagnostic explicite de chaque situation (pile PC/SC absente, service arrêté,
lecteur débranché, carte absente, carte non reconnue), et simulateur permettant
de développer et de tester sans matériel.

**Téléchargement automatique de la carte conducteur.** Dès qu'une carte conducteur
est insérée, l'application la lit en tâche de fond, assemble le fichier `.C1B`
(application de 1re génération et, si présente, de 2e génération, avec les
signatures calculées par la carte), l'écrit dans `imports/` puis l'archive et
l'inscrit dans l'historique, sans action de l'utilisateur. La lecture est **en
lecture seule** : aucune donnée n'est écrite sur la carte, si bien que la date de
dernier téléchargement qu'elle mémorise (`LastCardDownload`) n'est pas mise à jour.
Chaque commande et chaque identifiant cite son exigence dans le règlement
d'exécution (UE) 2016/799, annexe IC (appendices 2 et 7). Ces points sont à l'état
« En cours de validation » tant qu'un téléchargement réel n'a pas été vérifié avec
un outil tiers. Désactivable avec `TACHOLIBRE_CARD_AUTO_DOWNLOAD=false`.

## Ce qu'elle ne fait pas encore

Ces manques sont documentés, isolés derrière des interfaces, et couverts par des
tests qui vérifient que le refus est explicite.

| Fonction | État | Raison |
| --- | --- | --- |
| Affichage des données de 2e génération (GNSS) | Non implémenté | Archivées, non décodées |
| Vérification des signatures des fichiers de carte | Non implémenté | Chaîne de certificats à mettre en place |
| Décodage du contenu V1B | Non implémenté | 3 points à confirmer |
| Mise à jour de `LastCardDownload` sur la carte | Non implémenté | Écriture volontairement exclue avant validation sur cartes réelles |
| Détection de dépassements | Aucune règle active | Aucun seuil réglementaire n'a été vérifié sur sa source |
| API REST et synchronisation TMS | Non implémenté | Phases 14 et 15 |
| Paquet `.deb` / AppImage | Non implémenté | Phase 13 |

Toute tentative d'utiliser une de ces fonctions lève une erreur applicative
portant un message, une cause et une action — jamais une valeur inventée.
Concrètement, chaque méthode d'extraction du parser C1B lève
`UnconfirmedStructureError` en citant le point à confirmer — `parse()` les rassemble
en un résultat partiel dont les diagnostics listent ce qui n'a pas été lu — et le jeu
de règles livré par défaut est vide
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
2. **Aucune commande de carte n'est inventée.** Chaque commande et chaque
   identifiant de fichier cite l'exigence du règlement (UE) 2016/799 qui le
   définit. Tant qu'un point de spécification de la carte est à l'état « À
   confirmer », **aucune commande n'est transmise à la carte**.
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

Toutes les variables d'environnement portent le préfixe `TACHOLIBRE_` et peuvent
également être placées dans un fichier `.env`. L'ancien préfixe `TACHY_` reste
accepté. Les chemins sont manipulés avec `pathlib` ; aucun chemin absolu n'est
écrit en dur.

| Variable | Défaut | Rôle |
| --- | --- | --- |
| `TACHOLIBRE_DATA_DIR` | `data/` depuis les sources, sinon l'emplacement du système (voir ci-dessous) | Racine des données |
| `TACHOLIBRE_LOG_DIR` | `logs/` depuis les sources, sinon l'emplacement du système | Répertoire des journaux |
| `TACHOLIBRE_LOG_LEVEL` | `INFO` | Niveau du journal `app.log` |
| `TACHOLIBRE_CONSOLE_LOG_LEVEL` | `WARNING` | Niveau affiché sur la sortie standard |
| `TACHOLIBRE_COMPANY_NAME` | vide | Raison sociale, utilisée en en-tête de rapport |
| `TACHOLIBRE_AUTO_MIGRATE` | `true` | Applique les migrations au démarrage |
| `TACHOLIBRE_PCSC_ENABLED` | `true` | Autorise l'usage du lecteur PC/SC |
| `TACHOLIBRE_CARD_AUTO_DOWNLOAD` | `true` | Télécharge et importe la carte dès son insertion |
| `TACHOLIBRE_TIMEZONE_DISPLAY` | `Europe/Paris` | Fuseau d'affichage des horodatages d'import (le stockage et les frises d'activité restent en UTC) |

Emplacement des données hors mode développement : `%LOCALAPPDATA%\TachoLibre`
(Windows), `~/Library/Application Support/TachoLibre` (macOS),
`~/.local/share/tacholibre` (Linux). Une installation sous l'ancien nom
`tachy-linux` reste utilisée telle quelle.

La racine de données contient `originals/` (archivage immuable), `imports/`
(travail), `database/` et `exports/`.

## Tests et qualité

```bash
pip install -r requirements-dev.txt
python -m pytest                                  # 866 tests
python -m pytest --cov=app --cov-report=term-missing
ruff check app tests && ruff format --check app tests
```

866 tests couvrent 96 % des instructions de `app` (hors interface et point
d'entrée, testés séparément). Les tests d'interface s'exécutent sans écran grâce
à `QT_QPA_PLATFORM=offscreen`, positionné automatiquement, et les tests PC/SC
n'exigent aucun matériel : la bibliothèque `pyscard` y est remplacée par un
double, ce qui permet de couvrir chaque cas d'erreur, y compris le retrait de la
carte en cours de lecture.

| Domaine | Tests |
| --- | --- |
| `tests/services` | 174 |
| `tests/analysis` | 133 |
| `tests/card_reader` | 146 |
| `tests/parser` | 114 |
| `tests/core` | 80 |
| `tests/database` | 82 |
| `tests/ui` | 76 |
| `tests/config` | 34 |
| Démarrage (`bootstrap`, `main`) | 27 |

Le projet n'est pas considéré comme livrable si un test échoue.

## Feuille de route

| # | Phase | État |
| --- | --- | --- |
| 1 | Socle : configuration, base, interface, tests | terminée |
| 2 | Modèles de données | terminée |
| 3 | Import et archivage des fichiers C1B | terminée |
| 4 | Décodage C1B | terminée (1re génération ; données GNSS de 2e génération à afficher) |
| 5 | Activités conducteur | terminée |
| 6 | Analyse des temps | primitives prêtes, persistance à faire |
| 7 | Moteur de règles | cadre prêt, aucune règle active |
| 8 | Tableau de bord | terminée |
| 9 | Rapports PDF et Excel | rapport de carte terminé |
| 10 | Import V1B | à faire |
| 11 | Lecteur PC/SC | terminée |
| 12 | Lecture d'une carte conducteur | terminée, en lecture seule (validée sur une carte réelle) |
| 13 | Exécutables Windows, macOS et Linux | recette PyInstaller prête ; signature à faire |
| 14 | API REST (FastAPI) | à faire |
| 15 | Synchronisation TMS | à faire |

## Documentation

- [`docs/INSTALLATION.md`](docs/INSTALLATION.md) — installation sous Windows, macOS et Linux, exécutable autonome, paquets
  système, diagnostic de la pile PC/SC.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — couches, flux de données,
  conventions.
- [`docs/INCERTITUDES_SPECIFICATION.md`](docs/INCERTITUDES_SPECIFICATION.md) —
  les 14 points à confirmer avant tout décodage, et la procédure pour les lever.
- [`docs/REGLES.md`](docs/REGLES.md) — comment une règle réglementaire est
  documentée, configurée puis activée.

## Licence

Voir [`LICENSE`](LICENSE).

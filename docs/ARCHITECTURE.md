# Architecture

Ce document décrit l'organisation du code, les frontières entre couches et les
conventions à respecter pour étendre l'application. Il complète le `README.md`,
qui donne l'état fonctionnel.

## 1. Deux axes de séparation

L'application sépare le code selon deux axes indépendants, qu'il ne faut pas
confondre.

**Axe technique — la chaîne d'appel.** Elle est unidirectionnelle : une couche ne
connaît que la suivante.

```
Interface (PySide6)  ->  Services  ->  Dépôts  ->  Base de données
```

**Axe métier — la chaîne de transformation de la donnée.** Chaque étape est un
module distinct, et chaque étape suivante ne consomme que la sortie de la
précédente.

```
donnée brute -> donnée décodée -> donnée métier -> analyse -> alerte -> rapport
   fichier        parser          modèles          analysis    règles     reports
```

Cette seconde séparation est la plus importante pour la suite du projet : le
décodage binaire ne connaît pas la réglementation, le calcul des temps ne connaît
pas les seuils, et les seuils ne connaissent pas la mise en forme.

## 2. Arborescence

```
app/
├── main.py            Point d'entrée, options de ligne de commande
├── bootstrap.py       Préparation : configuration, répertoires, journal, base
├── core/              Énumérations, exceptions, empreintes SHA-256, utilitaires de temps
├── config/            settings.py (pydantic-settings), logging_config.py
├── database/
│   ├── database.py    Moteur, sessions, activation de WAL et des clés étrangères
│   ├── models/        Modèles SQLAlchemy (6 tables) et types personnalisés
│   ├── migrations/    Runner de migrations et migrations numérotées
│   └── repositories/  Accès aux données, et les Protocol qui les décrivent
├── parser/
│   ├── specification.py  Registre des incertitudes (14 points à confirmer)
│   ├── binary_reader.py  Lecture séquentielle avec position d'erreur
│   ├── models.py         Résultat de décodage, blocs non interprétés, diagnostics
│   ├── c1b_parser.py     Décodage C1B (refus explicite tant que non confirmé)
│   └── v1b_parser.py     Décodage V1B (idem)
├── analysis/
│   ├── activities.py     Intervalles, fusion, détection des trous
│   ├── driving_time.py, rest_time.py, working_time.py, availability.py
│   ├── infringements.py  Orchestration de l'évaluation des règles
│   └── rules/            base.py, config.py, registry.py, catalogue.py
├── card_reader/
│   ├── apdu.py           APDU ISO/IEC 7816-4 uniquement
│   ├── interface.py      Abstraction CardReaderInterface
│   ├── pcsc_reader.py    Implémentation PC/SC (pyscard, optionnel)
│   ├── mock_reader.py    Simulateur
│   ├── card_detector.py  Dérivation d'événements insertion / retrait
│   └── tachograph_card.py  Extraction — refuse tant que non confirmée
├── services/          Cas d'usage ; seule porte d'entrée de l'interface
├── reports/           Génération PDF / Excel (phase 9)
└── ui/                Fenêtre principale, navigation déclarative, pages
```

## 3. Les frontières, et pourquoi elles tiennent

### L'interface ne contient ni logique métier ni SQL

Une page reçoit un `ApplicationContext`, appelle un service et affiche le
résultat. Elle n'importe ni SQLAlchemy, ni un dépôt, ni un modèle.

La navigation est déclarative : ajouter une page consiste à ajouter une entrée à
`NAVIGATION` dans `app/ui/navigation.py`. Les pages sont instanciées à la
première visite, ce qui garde le démarrage rapide.

### Les services ne retournent jamais d'objet ORM

Un service ouvre **une** transaction, délègue aux dépôts, et retourne des
`dataclass` figées construites pendant que la session est ouverte. Deux
conséquences : l'interface ne peut pas déclencher de requête implicite après la
fermeture de la session, et le contrat ne changera pas si la source de données
devient un service REST.

Un test le vérifie couche par couche (`test_le_service_ne_retourne_jamais_d_objet_orm`).

### Les dépôts sont décrits par des `Protocol`

`app/database/repositories/interfaces.py` déclare un `Protocol` par dépôt, avec
les seules méthodes dont les services ont besoin. Les services dépendent de ces
protocoles, pas des classes concrètes. Remplacer SQLite par PostgreSQL ou par un
client HTTP consiste à fournir une autre implémentation des mêmes protocoles :
aucune couche supérieure ne change.

Des tests vérifient la conformité (`isinstance(dépôt, Protocol)`) et
l'étroitesse des protocoles, pour qu'ils ne dérivent pas vers un miroir du dépôt.

### Le décodage ne connaît pas la réglementation

`app/parser` produit des données décodées et des diagnostics. Il ne juge rien.
`app/analysis` calcule des durées sans connaître aucun seuil.
`app/analysis/rules` applique des seuils **fournis** par une configuration.
Aucun seuil n'est écrit dans le code.

## 4. Gestion des erreurs

Toutes les exceptions applicatives dérivent de `TachyError`
(`app/core/exceptions.py`) et portent quatre éléments :

| Élément | Destinataire | Exemple |
| --- | --- | --- |
| `message` | utilisateur | « Aucun lecteur de carte détecté. » |
| `cause` | utilisateur | « Aucun lecteur PC/SC n'est connecté ou reconnu par le système. » |
| `action` | utilisateur | « Branchez le lecteur USB puis vérifiez sa détection avec la commande pcsc_scan. » |
| `technical_detail` | développeur | mot d'état, position dans le fichier, message de la bibliothèque |

`app/ui/common/errors.py` traduit toute exception en ce quadruplet, y compris
celles qui ne sont pas des `TachyError` : une exception inattendue reçoit un
message générique, et son type Python part dans le détail technique. L'interface
n'affiche donc jamais une pile d'appels, et le détail reste accessible via
« Afficher le détail technique » ainsi que dans `logs/app.log`.

Les `NotImplementedError` levées par les fonctions des phases suivantes sont
traduites en « Cette fonctionnalité n'est pas encore disponible », avec renvoi à
la feuille de route.

## 5. Base de données

SQLite, avec le mode WAL et les clés étrangères activées à chaque connexion.
Six tables : `drivers`, `vehicles`, `tachograph_files`, `activities`,
`analyses`, `infringements`.

Les contraintes d'intégrité sont dans le schéma, pas seulement dans le code :
unicité du numéro de carte, de l'immatriculation et de l'empreinte SHA-256 des
fichiers, longueur de l'empreinte, taille de fichier positive, bornes de période
ordonnées. Les violations remontent sous forme de `DatabaseError` portant le
triplet d'usage.

Les horodatages sont stockés en UTC via un `TypeDecorator` dédié
(`app/database/models/types.py`), la conversion vers le fuseau d'affichage étant
faite à la présentation. Cela évite les ambiguïtés de changement d'heure dans les
calculs de durée.

**Migrations.** Un runner interne (`app/database/migrations/runner.py`) applique
des migrations numérotées et consigne les versions dans la table
`schema_migrations`. Une numérotation incohérente (doublon, trou) est refusée au
chargement, avant toute écriture. Alembic n'est pas utilisé : le besoin est un
schéma local mono-utilisateur, et une dépendance de moins simplifie
l'empaquetage de la phase 13.

Ajouter une migration : créer `app/database/migrations/m000N_description.py`,
l'enregistrer dans la liste des migrations, écrire le test correspondant. Les
migrations ne sont jamais modifiées après diffusion.

## 6. Lecteur de carte

Le reste de l'application ne connaît que `CardReaderInterface`. Trois
implémentations cohabitent :

- `PCSCReader` — matériel réel via `pyscard`, importé uniquement à l'usage ;
- `MockCardReader` — simulateur, permettant de développer l'interface et de
  tester chaque cas d'erreur sans matériel ;
- `TachographCard` — couche au-dessus du lecteur, qui porte l'intention métier
  (sélectionner l'application, lire un fichier, télécharger) et **refuse
  actuellement toute extraction**.

`pyscard` est une dépendance optionnelle. Son absence, comme l'arrêt du service
`pcscd`, est un état à afficher (`CardStatus.PCSC_UNAVAILABLE`) accompagné de la
commande d'installation — pas une erreur de programmation.

Seules les formes génériques d'APDU de l'ISO/IEC 7816-4 sont implémentées :
construction de commande, sérialisation, recomposition du mot d'état, traduction
des mots d'état courants. Aucun identifiant de fichier tachygraphique, aucun AID,
aucune séquence de téléchargement. Les descriptions d'APDU destinées au journal
indiquent la longueur du champ de données mais **jamais son contenu**, celui-ci
pouvant porter des éléments d'authentification.

## 7. Moteur de règles

Une règle est une classe qui déclare son code, son libellé, la référence du texte
qui la fonde et les paramètres dont elle a besoin. Elle ne contient aucune
valeur numérique.

Les valeurs vivent dans `rules.json`, sous la racine des données. Chaque
paramètre porte obligatoirement une `source` (référence du texte) et un statut de
confirmation. `RuleSet.require()` refuse un paramètre non confirmé : la règle est
alors ignorée, et l'utilisateur est informé de la raison, plutôt que de recevoir
un résultat calculé sur une valeur douteuse.

Le jeu de règles livré est vide (`0.0.0-empty`). Voir
[`REGLES.md`](REGLES.md) pour la procédure d'activation d'une règle et
[`INCERTITUDES_SPECIFICATION.md`](INCERTITUDES_SPECIFICATION.md) pour la
démarche générale de confirmation.

Chaque analyse enregistre la version du jeu de règles appliqué : un résultat
reste ainsi rattachable aux seuils qui l'ont produit. Relancer une analyse ajoute
un enregistrement au lieu d'écraser le précédent.

## 8. Conventions de code

- PEP 8, lignes de 100 caractères au plus, vérifié par `ruff`.
- Annotations de type sur toute fonction publique ; `from __future__ import annotations` en tête de module.
- Docstrings en français, style Google, sur les modules, classes et fonctions publiques.
- Un module expose explicitement son API par `__all__`.
- `dataclass(frozen=True, slots=True)` pour les objets de transfert.
- `pathlib` pour tous les chemins ; aucun chemin absolu écrit en dur.
- Pas d'état global mutable : la configuration et la base sont obtenues par des accesseurs dont le cache est réinitialisable pour les tests.

Vérification :

```bash
ruff check app tests
ruff format --check app tests
python -m pytest
```

## 9. Étendre l'application

**Ajouter un champ métier** : modèle → migration → dépôt (si une nouvelle
requête est nécessaire) → objet de transfert du service → page. Plus les tests de
chaque niveau touché.

**Ajouter une page** : créer la page sous `app/ui/<domaine>/`, l'enregistrer dans
`NAVIGATION`. Les tests paramétrés d'interface la prendront automatiquement en
compte, et vérifieront qu'elle s'ouvre et se rafraîchit sans boîte d'erreur.

**Implémenter un décodage** : d'abord confirmer les points ouverts du registre
sur une source officielle, y consigner la référence précise, ajouter un fichier
réel dans `tests/fixtures/`, passer le point à `CONFIRMED`, puis écrire le
décodage. Jamais dans l'autre ordre.

**Activer une règle** : voir [`REGLES.md`](REGLES.md).

# Règles réglementaires : documentation, configuration, activation

**Aucune règle n'est active dans cette version.** Le jeu de règles livré est vide
(version `0.0.0-empty`), et l'application le signale sur son tableau de bord :
tant qu'aucun seuil n'est configuré et vérifié, aucun dépassement n'est
recherché.

Ce document explique pourquoi, comment le moteur est construit, et quelle est la
procédure pour activer une règle.

## 1. Pourquoi aucun seuil n'est livré

Les durées maximales de conduite et les durées minimales de repos sont fixées par
des textes précis, assortis d'exceptions, de dérogations et de règles de
compensation. Une valeur approximative, ou juste mais mal appliquée, produirait
des alertes fausses sur le travail de personnes réelles — dans un sens comme dans
l'autre.

Le parti retenu est donc : **un seuil n'est applicable que lorsqu'il a été relevé
dans son texte, que ce texte est cité, et que la valeur a été explicitement
marquée comme vérifiée.** Il en résulte qu'aucun seuil n'est distribué avec le
logiciel, la vérification n'ayant pas été faite.

Ce n'est pas une limitation cachée : c'est une contrainte imposée par le code.

## 2. Ce que le code rend impossible

**Déclarer une règle sans citer sa source.** `Rule.__init_subclass__` vérifie à la
définition de la classe que `code`, `title` et `regulation_reference` sont
renseignés. Une sous-classe concrète qui omet la référence réglementaire
déclenche une `RuleConfigurationError` **à l'import du module**, pas à
l'exécution. Il n'est donc techniquement pas possible d'ajouter une règle sans
source.

**Appliquer un seuil non vérifié.** `RuleSet.require(code)` refuse un paramètre
absent, et refuse également un paramètre présent dont le statut n'est pas
`CONFIRMED`. Le message distingue les deux cas : « n'est pas configuré » et
« n'est pas encore vérifié ».

**Masquer le fait qu'une règle a été ignorée.** Lorsqu'une règle est écartée faute
de seuil utilisable, `evaluate_rules` conserve la raison et la restitue. Les
autres règles continuent d'être évaluées. L'utilisateur voit donc ce qui a été
contrôlé *et* ce qui ne l'a pas été.

**Présenter une anomalie comme une infraction.** Les libellés viennent de
`RuleStatus`, et emploient le vocabulaire « dépassement apparent », « situation à
vérifier », « anomalie détectée ». Un test vérifie l'absence des termes
*infraction*, *délit*, *sanction*, *amende* et *illégal* dans les messages
produits.

**Inventer une date.** Un résultat dont le jour de service n'est pas identifiable
est écarté plutôt que rattaché à une date choisie par défaut.

## 3. Où vivent les seuils

Dans `rules.json`, sous la racine des données (voir `TACHY_DATA_DIR`). Chaque
paramètre comporte :

| Champ | Obligatoire | Rôle |
| --- | --- | --- |
| `code` | oui | Identifiant référencé par les règles |
| `label` | oui | Libellé affiché dans les paramètres |
| `value` | oui | Valeur du seuil |
| `unit` | — (défaut `seconds`) | `seconds`, `count`, `km`... |
| `source` | oui, 10 caractères minimum | Référence du texte fixant ce seuil |
| `status` | — (défaut `OPEN`) | `OPEN`, `IN_REVIEW` ou `CONFIRMED` |
| `notes` | non | Réserves ou précisions d'interprétation |

Exemple de forme attendue. **Les valeurs ci-dessous sont des exemples de syntaxe,
pas des seuils vérifiés** — c'est précisément ce que le statut `OPEN` exprime, et
c'est pourquoi un tel paramètre ne serait pas appliqué :

```json
{
  "version": "0.0.0-empty",
  "parameters": {
    "DAILY_DRIVING_MAX_SECONDS": {
      "code": "DAILY_DRIVING_MAX_SECONDS",
      "label": "Duree de conduite journaliere maximale",
      "value": 0,
      "unit": "seconds",
      "source": "A relever dans le reglement (CE) no 561/2006, article 6, paragraphe 1",
      "status": "OPEN",
      "notes": "Verifier egalement le nombre d'extensions autorisees par semaine."
    }
  }
}
```

Un fichier absent équivaut à un jeu vide. Un fichier illisible ou incomplet — un
paramètre sans source, par exemple — est refusé avec un message explicite, sans
repli silencieux sur des valeurs par défaut.

## 4. Les dix règles prévues

`app/analysis/rules/catalogue.py` décrit ce que chaque règle devra vérifier et la
référence à consulter pour en fixer les seuils. Ce catalogue est le cahier des
charges de la phase 7 ; aucune de ces règles n'est implémentée.

| Code | Objet | Référence à vérifier |
| --- | --- | --- |
| `DAILY_DRIVING_MAX` | Durée de conduite journalière, y compris le maximum étendu et sa fréquence hebdomadaire | Règlement (CE) n° 561/2006, art. 6 § 1 |
| `WEEKLY_DRIVING_MAX` | Durée de conduite hebdomadaire | Règlement (CE) n° 561/2006, art. 6 § 2 |
| `TWO_WEEK_DRIVING_MAX` | Cumul de conduite sur deux semaines consécutives | Règlement (CE) n° 561/2006, art. 6 § 3 |
| `CONTINUOUS_DRIVING_BREAK` | Interruption de la conduite continue, y compris fractionnée | Règlement (CE) n° 561/2006, art. 7 |
| `DAILY_REST_MINIMUM` | Repos journalier : normal, réduit, fractionné, et nombre de réductions | Règlement (CE) n° 561/2006, art. 8 § 1 à 5 |
| `WEEKLY_REST_MINIMUM` | Repos hebdomadaire, périodicité et compensation d'un repos réduit | Règlement (CE) n° 561/2006, art. 8 § 6 à 9 |
| `WORKING_TIME_MAX` | Temps de travail hebdomadaire et sa moyenne | Directive 2002/15/CE, art. 3 et 4 |
| `NIGHT_WORK` | Durée du travail effectué pendant la période nocturne | Directive 2002/15/CE, art. 7 |
| `MISSING_DATA` | Périodes sans enregistrement, pour vérifier l'exhaustivité des téléchargements | Règlement (UE) n° 165/2014, art. 36 |
| `CARD_EXPIRY` | Carte conducteur expirée ou proche de l'expiration | Règlement (UE) n° 165/2014, art. 28 |

Textes de référence recensés par le projet (`REGULATION_SOURCES`) : règlement
(CE) n° 561/2006, règlement (UE) 2020/1054 qui le modifie, directive
2002/15/CE, règlement (UE) n° 165/2014, et accord AETR pour les trajets hors
Union européenne.

Deux règles se distinguent : `MISSING_DATA` ne dépend d'aucun seuil
réglementaire, seulement d'une tolérance choisie par l'entreprise, et
`CARD_EXPIRY` compare une date à une autre. Ce sont donc les deux premières
activables sans arbitrage réglementaire — la référence citée concernant
l'obligation elle-même, non un seuil chiffré.

## 5. Procédure d'activation d'une règle

Dans cet ordre :

1. **Consulter le texte** cité dans le catalogue et relever la valeur exacte,
   ainsi que ses conditions d'application (exceptions, dérogations,
   compensations).
2. **Saisir le paramètre** dans `rules.json` avec sa `source` : texte, article,
   paragraphe. Utiliser `notes` pour consigner les réserves d'interprétation.
3. **Laisser le statut à `OPEN`** tant que la valeur n'a pas été relue, ou le
   passer à `IN_REVIEW` si la vérification est en cours.
4. **Écrire la classe de règle** dans `app/analysis/rules/`, en déclarant `code`,
   `title`, `regulation_reference` et `parameter_codes`. La règle ne contient
   aucune valeur : elle appelle `ruleset.seconds(code)` ou
   `ruleset.require(code)`.
5. **Écrire les tests** : le cas conforme, le cas en dépassement, le cas limite,
   et le cas où le paramètre n'est pas confirmé (la règle doit alors être ignorée,
   pas produire une alerte).
6. **Passer le statut à `CONFIRMED`** après relecture de la valeur face à son
   texte. C'est cette étape, et elle seule, qui rend la règle opérante.
7. **Incrémenter la version du jeu de règles.** Chaque analyse enregistre la
   version appliquée : un résultat reste ainsi rattachable aux seuils qui l'ont
   produit.

L'étape 6 est une décision, pas une tâche technique. Elle engage la
responsabilité de celui qui la prend et devrait être tracée — commit dédié
citant le texte consulté et sa version.

## 6. Traçabilité des résultats

Un résultat de règle (`RuleResult`) porte la valeur mesurée, le seuil appliqué,
son unité, la période concernée et **la référence réglementaire du seuil**. Il est
sérialisable (`as_dict()`) pour les rapports et la future API REST.

Une analyse enregistrée conserve la version du jeu de règles. Relancer une
analyse **ajoute** un enregistrement au lieu d'écraser le précédent : l'historique
des analyses successives d'une même période reste consultable, ce qui est
nécessaire si les seuils ou les données sources ont évolué entre-temps.

## 7. Portée et responsabilité

L'application signale des situations à vérifier. Elle ne qualifie aucune
infraction, ne calcule aucune sanction, et ne remplace ni l'analyse d'un
gestionnaire de parc ni celle d'un organisme de contrôle. Le paramétrage des
seuils, leur vérification face aux textes applicables à l'activité de
l'entreprise, ainsi que les conclusions tirées des résultats, restent sous la
responsabilité de l'exploitant.

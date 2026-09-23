# Registre des incertitudes de spécification

Le décodage des fichiers tachygraphiques et le dialogue avec une carte
conducteur ne sont **pas** implémentés, pour une raison unique : les structures
binaires et les commandes correspondantes n'ont pas été confirmées à partir d'une
source officielle. Ce document recense ce qu'il faut établir, où le chercher, et
comment procéder ensuite.

Ce registre existe aussi dans le code, dans `app/parser/specification.py`, ce qui
lui permet d'être interrogé par l'application et par les tests. Les deux doivent
rester cohérents ; le code est la référence.

## 1. Pourquoi aucun décodage n'est tenté

Un décodeur nourri d'offsets devinés ne produit pas une erreur : il produit des
heures de conduite plausibles mais fausses. Appliquées à un contrôle de temps de
travail, ces heures conduiraient à des conclusions erronées sur des personnes.
Le choix retenu est donc explicite : **tant qu'une structure n'est pas confirmée,
le code refuse de décoder** en levant `UnconfirmedStructureError`, dont le message
cite les points à établir.

Ce refus est vérifié par des tests : `parse()` sur un fichier C1B ou V1B lève
l'erreur, `TachographCard.download()` également, et — point important — **aucune
commande n'est transmise à la carte** lors d'un refus.

## 2. Sources à consulter

Aucune de ces sources n'est reproduite ici, ni dans le code : seules leurs
références sont citées.

| Document | Contenu utile |
| --- | --- |
| Règlement d'exécution (UE) 2016/799, annexe I C, appendice 1 | Dictionnaire de données : définition de chaque type |
| Règlement d'exécution (UE) 2016/799, annexe I C, appendice 2 | Spécification de la carte à puce tachygraphique |
| Règlement d'exécution (UE) 2016/799, annexe I C, appendice 7 | Protocole de téléchargement des données |
| Règlement d'exécution (UE) 2016/799, annexe I C, appendice 11 | Mécanismes de sécurité, signatures |
| Règlement (CEE) n° 3821/85, annexe I B, appendices 1, 2, 7 et 11 | Équipements et cartes des générations antérieures |
| ISO/IEC 7816-4 | Formes génériques d'APDU et mots d'état (déjà implémenté) |

La version consolidée des règlements est publiée au Journal officiel de l'Union
européenne. Les annexes techniques étant volumineuses, il faut veiller à utiliser
la version applicable à la génération d'équipement concernée.

## 3. Points à confirmer

14 points, dont 12 bloquent le décodage du format auquel ils se rattachent. Les
deux points non bloquants concernent des enrichissements (libellés
d'événements, vérification de signature) qui peuvent être ajoutés après un
premier décodage fonctionnel.

Les références de la colonne « À consulter » sont relatives à l'annexe I C citée
ci-dessus.

### Fichiers de carte conducteur (`.C1B`) — 7 points

| Code | À établir | À consulter | Bloquant |
| --- | --- | --- | --- |
| `C1B_CONTAINER_LAYOUT` | Organisation du conteneur : nature et taille du marqueur de début de chaque bloc, codage de la longueur, emplacement des blocs de signature | Appendice 7, section carte conducteur | oui |
| `C1B_BLOCK_IDENTIFIERS` | Liste des identifiants de blocs et correspondance avec les fichiers élémentaires de la carte | Appendice 2 | oui |
| `C1B_DRIVER_IDENTIFICATION_FIELDS` | Position, longueur et codage des champs d'identification du titulaire, y compris la page de codes des caractères | Appendice 1 (`CardIdentification`, `DriverCardHolderIdentification`) | oui |
| `C1B_ACTIVITY_CHANGE_ENCODING` | Codage des changements d'activité : bits de mode, minute de la journée, reconstitution des bornes de fin de période | Appendice 1 (`ActivityChangeInfo`) | oui |
| `C1B_TIME_ENCODING` | Codage des horodatages et référentiel temporel appliqué (UTC ou heure locale) par type de date | Appendice 1 (`TimeReal`, `Datef`) | oui |
| `C1B_EVENT_FAULT_CODES` | Correspondance entre codes d'événements et d'anomalies et leur libellé, par génération | Appendice 1 (`EventFaultType`) | non |
| `C1B_SIGNATURE_VERIFICATION` | Procédure de vérification des signatures et chaîne de certification à utiliser | Appendice 11 | non |

### Fichiers d'unité embarquée (`.V1B`) — 3 points

| Code | À établir | À consulter | Bloquant |
| --- | --- | --- | --- |
| `V1B_CONTAINER_LAYOUT` | Organisation du conteneur et liste des blocs transmis | Appendice 7, section unité embarquée | oui |
| `V1B_VEHICLE_IDENTIFICATION_FIELDS` | Position et codage de l'immatriculation, du pays d'immatriculation, du VIN et de l'identifiant de l'unité embarquée | Appendice 1 (`VehicleIdentificationNumber`, `VehicleRegistrationIdentification`) | oui |
| `V1B_DRIVER_SLOT_ACTIVITIES` | Reconstitution des activités par emplacement de carte (conducteur et convoyeur) | Appendice 1 (`VuActivityDailyData`) | oui |

### Lecture directe d'une carte — 4 points

| Code | À établir | À consulter | Bloquant |
| --- | --- | --- | --- |
| `CARD_APPLICATION_SELECTION` | Identifiant d'application (AID) et séquence de sélection de l'application tachygraphique | Appendice 2 | oui |
| `CARD_FILE_IDENTIFIERS` | Identifiants des fichiers élémentaires à lire et ordre de lecture | Appendice 2 | oui |
| `CARD_READ_BINARY_SEQUENCE` | Séquence exacte des commandes de lecture, gestion des réponses longues, traitement des mots d'état | Appendice 2 et ISO/IEC 7816-4 | oui |
| `CARD_DOWNLOAD_FILE_ASSEMBLY` | Règles d'assemblage des données lues en un fichier `.C1B` exploitable par des outils tiers | Appendice 7 | oui |

## 4. Ce qui est déjà en place et n'attend que la confirmation

L'absence de décodage ne signifie pas l'absence de travail préparatoire. Sont
déjà implémentés et testés :

- **la lecture binaire séquentielle** (`app/parser/binary_reader.py`) : lecture
  d'entiers, de champs de longueur fixe, contrôle des dépassements, et position
  du curseur reportée dans chaque erreur ;
- **le modèle de résultat de décodage** (`app/parser/models.py`) : un
  `ParseResult` porte des blocs, dont ceux **non interprétés**, ainsi que des
  diagnostics de niveau information / avertissement / erreur. Un bloc non
  interprété est conservé et visible, pas silencieusement ignoré ;
- **les formes génériques d'APDU** (`app/card_reader/apdu.py`) : construction,
  sérialisation, `SELECT` et `READ BINARY` génériques de l'ISO/IEC 7816-4,
  recomposition et traduction des mots d'état ;
- **toute la chaîne d'accueil du fichier** : archivage de l'original, empreinte
  SHA-256, détection des doublons, historique — soit tout ce qui est indépendant
  du contenu binaire.

Autrement dit, la confirmation des points ci-dessus est ce qui manque, non le
reste de l'application.

## 5. Procédure pour lever un point

Dans cet ordre, sans exception :

1. **Consulter** la source citée et relever la structure exacte.
2. **Consigner** dans `app/parser/specification.py` la référence précise
   obtenue : appendice, section, nom du type. La référence doit permettre à un
   tiers de retrouver le passage.
3. **Obtenir un fichier réel** de test et le placer dans `tests/fixtures/`. Un
   décodage validé sur un fichier fabriqué à la main ne prouve rien : il ne fait
   que confirmer la lecture qu'on a faite de la spécification.
4. **Écrire le test** qui décode ce fichier et vérifie les valeurs attendues.
5. **Passer le point** à `ConfirmationStatus.CONFIRMED`.
6. **Écrire le décodage**, jusqu'à ce que le test passe.

Le passage à `CONFIRMED` n'est légitime que si les deux conditions sont réunies :
référence précise renseignée **et** fichier réel validant le décodage.
`is_confirmed("c1b")` devient vrai lorsque tous les points bloquants du domaine
sont confirmés ; c'est cette fonction, et non une constante dans le code, qui
autorise le décodage.

### Fichiers de test et données personnelles

Un fichier C1B réel contient des données personnelles : nom, prénom, date de
naissance, déplacements. Avant d'ajouter un fichier à `tests/fixtures/` :

- obtenir l'accord du conducteur concerné, ou utiliser un fichier issu d'une
  carte de test délivrée à cet effet ;
- à défaut, anonymiser les champs d'identification une fois leur structure
  connue, et documenter dans le test ce qui a été modifié.

Un fichier de test ne doit jamais être ajouté sans que cette question soit
tranchée explicitement.

## 6. Ce que le code fait en attendant

| Appel | Comportement |
| --- | --- |
| `C1BParser().parse(chemin)` | Lève `UnconfirmedStructureError` citant les points ouverts |
| `V1BParser().parse(chemin)` | Idem |
| `TachographCard.select_application()` | Lève `UnconfirmedStructureError` (`CARD_APPLICATION_SELECTION`) |
| `TachographCard.read_elementary_file(...)` | Lève `UnconfirmedStructureError` (`CARD_FILE_IDENTIFIERS`) |
| `TachographCard.download()` | Lève `UnconfirmedStructureError` (`CARD_DOWNLOAD_FILE_ASSEMBLY`) |
| `ImportService.import_file(...)` | Lève `NotImplementedError` mentionnant la phase 3 |

Chacun de ces refus porte un message, une cause et une action destinés à
l'utilisateur, et mentionne que la fonction nécessite la spécification officielle.
`TachographCard` continue en revanche d'exposer la détection de présence et la
transmission d'APDU brutes, afin de permettre l'expérimentation nécessaire à la
confirmation.

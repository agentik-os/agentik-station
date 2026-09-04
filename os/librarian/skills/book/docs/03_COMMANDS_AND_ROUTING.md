# 03 · Commandes, flags et routage

## Entrée principale
`/book [flags] <ouvrage, sujet ou question>` accepte un titre, une question, un corpus joint, un document autorisé ou une référence à un dossier. Le type d'objet est déterminé avant la méthode. Un titre ambigu n'est pas transformé arbitrairement en un autre livre.

Les flags suivants font partie du périmètre FULL retrouvé. Ils se combinent lorsque leurs objectifs sont compatibles.

| Flag | Effet réel | Sortie supplémentaire |
|---|---|---|
| aucun | Analyse ou recherche structurée standard | Dossier et bibliographie |
| `--deep` | Décomposer les mécanismes, preuves, alternatives et applications | Livre original ou deep dossier |
| `--scholar` | Examen académique avec protocole documenté | Search log et evidence table |
| `--apply` | Relier la connaissance à un contexte explicite | Plan d'expérience et application |
| `--compare` | Comparer des objets selon les mêmes critères | Matrice et arbitrages |
| `--synthesize` | Construire une synthèse inter-sources | Modèle intégré et divergences |
| `--critique` | Rechercher activement les limites et contre-preuves | Rapport contradictoire |
| `--quiz` | Tester le rappel et le transfert | Questions, correction séparée |
| `--teachback` | Faire expliquer puis corriger les mécanismes | Grille de restitution |
| `--cards` | Créer des unités de rappel liées aux claims | Jeu de cartes exportable |
| `--map` | Produire une carte des concepts et preuves | Graphe lisible et JSON |
| `--reading-path` | Ordonner un apprentissage selon prérequis | Parcours et jalons |
| `--bestseller` | Renforcer la pédagogie et la construction éditoriale | Plan narratif original |
| `--corpus` | Traiter un ensemble de matériaux comme corpus | Manifest, dedup et couverture |

`--bestseller` ne signifie jamais bestseller réel, ventes garanties, imitation d'un auteur vivant ou droit de réécrire un ouvrage protégé. C'est un mode éditorial de création originale.

## Extensions de cette release
`--systematic` demande un protocole de revue systématique explicitement délimité. Il active aussi Scholar. `--context "texte"` fournit le contexte d'application. `--language fr|en` fixe la langue. `--full` fixe la complétude attendue, pas une exemption de budget ou de copyright. `--refresh` réévalue un dossier existant ; sans dossier identifiable, l'Oracle retrouve le candidat autorisé ou demande l'identifiant.

`/librarian <action> <cible>` est l'entrée d'administration : inbox, search, status, audit, graph, refresh, cards, export. Elle utilise les scripts locaux lorsque la commande existe et une procédure explicitement décrite autrement. Elle n'invente pas des API Hermes, des permissions ou des slash commands déjà actives.

## Compatibilité textuelle
`/book deep !` est normalisé en `/book --deep` et attend une cible réellement présente dans les pièces jointes ou le contexte actuel. `/book --deep --scholar` reste Scholar avec profondeur Deep. `--quiz --teachback --cards` produit un learning pack ; il ne supprime pas la vérification des connaissances sur lesquelles il repose.

Les flags de sortie sont booléens. Pour ne pas absorber accidentellement le sujet, écrire `--apply --context "AGK" sujet`, plutôt que supposer que le mot après `--apply` est un paramètre. Les flags inconnus sont signalés, jamais ignorés silencieusement.

## Routeur
1. Identifier le scope et la cible accessible.
2. Séparer intention, entrée, profondeur, méthodes, sorties et contraintes.
3. Vérifier les capacités effectivement disponibles : recherche, extraction, lecture, délégation, fichiers.
4. Charger la constitution et les seuls workflows nécessaires.
5. Créer les exigences correspondant à chaque flag et clause du prompt.
6. Établir un budget opérationnel et une règle d'arrêt.
7. Produire les sorties et passer les gates.

Le script `route` réalise seulement une normalisation syntaxique. L'identification sémantique du livre, l'accès à la pièce jointe et le choix intellectuel de méthode restent des responsabilités de l'Oracle.


---

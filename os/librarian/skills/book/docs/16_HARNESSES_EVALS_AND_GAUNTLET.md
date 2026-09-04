# 16 · Harnesses, evals et Gauntlet

## Ce que vérifie chaque niveau
L0 syntaxe : fichiers lisibles et schémas valides.
L1 intégrité : références existantes, hashes, scope et dépendances.
L2 complétude : toutes les exigences ont un résultat ou un blocage explicite.
L3 grounding : chaque claim important est réellement soutenu par la source citée.
L4 méthode : recherche, sélection, critique et limites cohérentes avec le label revendiqué.
L5 utilité : le lecteur peut comprendre, décider ou tester l'application.
L6 acceptation humaine : Operator ou le responsable autorisé accepte le livrable.

Les tests Python livrés couvrent surtout L0, L1 et une partie structurelle de L2. Ils ne certifient pas L3 à L6. Les fixtures adversariales du pack sont des cas de test à exécuter contre l'agent réel ; leur présence n'est pas une exécution réussie.

## Gauntlet Loop
Lire le brief intégral → comparer registre et sorties → chercher une erreur structurante → reproduire le défaut → corriger au plus petit niveau → relancer le test ciblé → relancer la non-régression → enregistrer les preuves. Plafond de repair loops configurable. Au-delà, résultat bloqué avec causes connues.

## Dimensions d'évaluation
Fidélité à la demande ; qualité d'identification des sources ; absence de citations inventées ; distinction accès/contenu ; indépendance ; fraîcheur ; exactitude des nombres ; traitement des contradictions ; profondeur pédagogique ; pertinence d'application ; respect du scope ; qualité du handoff ; coût et reprise.

## Défauts bloquants
Source inventée ; citation non retrouvée ; texte prétendument lu mais inaccessible ; claim central sans support admissible ; contradiction critique cachée ; fuite inter-client ; secret présent ; manque d'un livrable explicite ; fichier manquant ou modifié après vérification ; production ou publication sans gate.

## Mesures
Couverture des exigences : fraction des exigences applicables effectivement livrées. Couverture des claims centraux : fraction avec evidence admissible, puis vérification sémantique. Précision des citations : proportion des citations échantillonnées qui soutiennent bien la formulation. Reproductibilité : nombre de requêtes et transformations réellement rejouables. Valeur d'usage : critère défini avec le demandeur.

Ne pas transformer ces métriques en un score global qui compense une fuite de données par une bonne prose. Les défauts bloquants restent bloquants quel que soit le score moyen.

## Release report
Inclure environnement, version du pack, commandes réellement exécutées, nombre et statut des tests, limitations, composants non branchés et résultat de vérification de l'archive. « Testé en local » ne signifie pas « déployé et vérifié sur le VPS de Operator ».


---

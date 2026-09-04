# Vérification et repair loop

## Déclencheur
Avant toute livraison substantielle.

## Prérequis
Run et scope explicites, brief accessible, permissions connues, constitution chargée. Vérifier les artefacts déjà présents avant d’en créer d’autres.

## Étapes
1. Relire le brief original et tous les flags.
2. Contrôler fichiers, IDs, graphes et couverture.
3. Vérifier sémantiquement les claims prioritaires.
4. Tester les scénarios adversariaux applicables.
5. Corriger et rejouer les tests dans la limite du budget.
6. Rendre un rapport avec portée et défauts résiduels.

## Sorties attendues
audit_report, coverage_report.

## Gate et limites
Les checks mécaniques ne valent pas validation de vérité ou acceptation humaine.

## Reprise
Conserver un checkpoint après chaque étape utile : exigences traitées, artefacts produits, sources consultées, erreurs et prochaine étape. Reprendre depuis la première dépendance manquante. Le même ID avec contenu différent est un conflit, pas une mise à jour silencieuse.

## Retour à l’Oracle
Rapporter résultats, preuves de présence, limites d’accès, coût mesuré s’il est disponible et exigences bloquées. Ne jamais déclarer une étape externe exécutée sur la base de ce seul workflow.


---

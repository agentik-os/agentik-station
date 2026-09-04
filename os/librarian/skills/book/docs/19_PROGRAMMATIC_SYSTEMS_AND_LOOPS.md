# 19 · Systèmes programmatiques, harness engineering et loop-graphs

## De la procédure au contrat exécutable
Un workflow fiable rend explicites inputs, outputs, conditions, autorisations, invariants et preuves. Les scripts exécutent les opérations mécaniques ; le modèle effectue l'analyse nécessitant du jugement ; les gates rendent leur frontière visible.

Éviter un méga-prompt qui mélange recherche, invention d'API, mutation de fichiers, décision business et publication. Décomposer ces responsabilités en fonctions de travail observables. Le pack donne des contrats JSON pour le stockage et des workflows pour le raisonnement et l'orchestration.

## Harness de mission
Le harness de recherche assemble brief, sources accessibles, références, budget, outils permis, exemples, tests et sortie attendue. Il journalise les événements et bloque la promotion lorsque les exigences structurelles ne sont pas remplies. Il n'est pas un substitut à l'évaluation des sources.

Les tools doivent retourner leurs erreurs explicitement. Un timeout n'est pas une source inexistante ; un résultat vide n'est pas une preuve d'absence ; une API de métadonnées n'est pas un accès au texte intégral.

## Graph engineering
Modéliser les entités et relations nécessaires à la décision. Créer seulement les edges traçables. Préserver scope, version et provenance sur les objets échangés. Les artifacts forment un DAG de construction ; les concepts peuvent former un graphe cyclique descriptif.

## Loop-graph engineering
Une boucle utile associe une question ouverte, une action de collecte ou de test, une observation, un changement d'état et une condition d'arrêt. Le graphe explicite quelles hypothèses et sorties sont affectées par l'observation.

Exemple : claim central incertain → recherche contradictoire → nouvelle source → comparaison de méthodes → révision du claim → ré-audit des chapitres et du handoff → clôture ou blocage. La boucle ne consiste pas à demander au même modèle de se dire « parfait » plusieurs fois.

## États et reprise
Le registre conserve la mission même si le runtime redémarre. Le checkpoint indique le prochain travail, mais ne relance pas automatiquement un job. L'orchestrateur doit vérifier droits et environnement après reprise.

Les ajouts idempotents évitent les doublons de retry. Les changements d’état d’exigence, de source et de cartes autorisés ajoutent des événements. Les autres corrections utilisent un nouvel ID et un manifest de révision. Aucune opération livrée n'effectue une suppression automatique de corpus.

## Qualité des boucles
Une boucle s'améliore si le défaut devient plus précisément observable, si le test peut être rejoué et si les corrections ne dégradent pas les exigences voisines. Mesurer les défauts retrouvés et corrigés, pas seulement les itérations ou tokens consommés.

## Transition vers un vrai service
Pour passer de l'outil local à un service multi-utilisateur, ajouter authentification, autorisation server-side, stockage transactionnel adapté, isolation de données, queues, quotas, observabilité et sauvegardes contrôlées. Ces composants sont des travaux d'intégration, pas des capacités cachées que ce ZIP aurait déployées.


---

# 10 · Knowledge graph, evidence graph et dépendances

## Graphes complémentaires
Le graphe de concepts explique les relations intellectuelles : prérequis, partie-de, contraste, cause supposée, exemple, mécanisme. Le graphe de preuves explique la provenance : source supporte/contredit claim, claim alimente artefact, artefact satisfait exigence. Le graphe d'exécution explique les dépendances de travail : tâche attend tâche, gate bloque release.

Un seul dessin ne doit pas confondre causalité dans le monde et dépendance de fichiers. Chaque edge porte un type. Les relations causales restent des claims à étayer, pas des flèches décoratives.

## Identifiants
RUN pour les missions, SRC pour les sources, CLM pour les claims, CON pour les contradictions, ART pour les artefacts, REQ pour les exigences et CARD pour les cartes. Les IDs sont stables dans un run. La clé complète inclut scope et run lorsqu'un objet est échangé hors de son workspace.

Un titre modifié ne change pas l'identité d'un objet. Une correction substantielle doit conserver le lien vers l'ancienne version. Le démonstrateur local utilise des records immuables à l'ajout ; les changements d'état permis créent un événement d'audit.

## Opérations utiles
Retrouver toutes les preuves derrière une recommandation. Trouver les claims centraux sans support accessible. Localiser les chapitres affectés par une source devenue obsolète. Voir les exigences sans artefact. Identifier les concepts nécessaires avant un module pédagogique. Empêcher une release fondée sur un claim rétracté.

## Invalidation
Une source périmée, corrigée ou retirée déclenche une liste d'impact. La cascade traverse claims, artefacts dérivés et exigences. Les dérivés sont à réviser ; ils ne sont pas silencieusement « corrigés » sans relecture. Les références à cette source à des fins historiques peuvent rester légitimes, mais elles doivent être explicitement qualifiées.

Dans le CLI local, `source-status` journalise le changement, `graph` reconstruit les dépendances et `audit` signale les artefacts impactés. Aucune notification distante ni modification de production n'est déclenchée.

## Qualité et limites
Une arête support prouve une déclaration de lien, pas la pertinence sémantique de ce lien. Les cycles sont acceptables dans une carte de concepts, mais interdits dans un DAG d'artefacts à construire. Le registre local exige que les dépendances d'artefacts existent déjà ; cet ordre et leur immutabilité empêchent les cycles d'artefacts créés par l'API locale.

Les scores de centralité ne déterminent pas automatiquement la vérité ou la priorité business. Utiliser le graphe pour expliquer et inspecter, pas pour produire une illusion mathématique de certitude.


---

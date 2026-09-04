# 14 · Librarian → Blueprint → Design → Stepper → Builder

## Chaîne canonique de travail
Librarian produit le dossier vérifié et les inconnues. Blueprint formalise problème, outcome, utilisateurs, portée et options. Design transforme l'option retenue en interactions et architecture. Stepper ordonne des incréments vérifiables. Builder implémente dans le périmètre autorisé. Evals teste. Audit inspecte les preuves et écarts. Fix corrige. Release suit l'autorisation appropriée. Learning retourne les observations au corpus.

Cette chaîne préserve la référence conceptuelle à Builder v5 et au pipeline Blueprint/Design/Stepper. Le pack ne contient pas une copie prétendument récupérée de tous les anciens OS.

## Contenu minimum du handoff
Brief utilisateur intact ou référence sûre ; exigences atomiques ; scope et exclusions ; conclusions étayées ; hypothèses encore ouvertes ; sources et versions ; contradictions ; choix de conception proposés ; alternatives rejetées et raisons ; contraintes d'accès ; risques ; critères d'acceptation ; fixtures ; métriques ; ordre des incréments ; conditions d'arrêt ; décisions humaines requises.

Chaque choix structurant pointe vers ses claims ou vers une hypothèse explicitement nouvelle. Le Builder ne doit pas transformer une hypothèse en exigence « prouvée » parce qu'elle apparaît dans un handoff.

## Gates
G0 : recherche suffisamment couverte pour l'action considérée.
G1 : brief et limites compris.
G2 : architecture et risques explicités.
G3 : plan d'incréments et tests préparés.
START : autorisation d'implémenter dans l'environnement spécifié.
G4 : tests et preuves de staging.
G5 : revue humaine lorsque requise.
RELEASE : autorisation distincte pour production ou diffusion.
G6 : vérification post-release réellement observée.

Un bouton « Appliquer » ne franchit pas automatiquement START ou RELEASE. Les artefacts de recherche n'autorisent ni merge vers main, ni budget cloud, ni mutation de données réelles.

## Acceptance tests issus de la recherche
Pour chaque fonctionnalité proposée, définir comportement attendu, cas nominal, cas limite, échec sûr et preuve vérifiable. Les tests de code ne doivent pas remplacer les tests sur la validité du problème. Un prototype techniquement correct peut rester une mauvaise application de la recherche.

## Retour
Le Builder renvoie liens vers artefacts, résultats de tests, limites, écarts par rapport au handoff et observations inattendues. Librarian met à jour les claims d'application et leur contexte. Les sources originales restent inchangées ; l'expérience devient une source distincte datée.

## Contrat de refus utile
Si le brief manque d'un prérequis critique, le handoff reste prêt à compléter avec la lacune précisément localisée. Il ne force pas une construction « pour avancer ». Livrer le travail de recherche déjà disponible et la prochaine preuve nécessaire.


---

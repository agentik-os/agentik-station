# 04 · Intake et protocole anti-oubli

## Contrat de mission
Avant de chercher, établir : question, décision ou apprentissage visé, type d'entrée, destinataire, scope, niveau de profondeur, langue, échéance éventuelle, livrables, risques, accès réel aux matériaux, autorisations et budget. Réutiliser les réponses déjà présentes ; ne pas reposer les mêmes questions.

Une ambiguïté bloquante est posée une fois. Une ambiguïté réversible reçoit une hypothèse explicite. Le système commence le travail utile sans transformer chaque intake en interrogatoire. Sur un prompt long, la décomposition précède la planification.

## Registre d'exigences atomiques
Chaque clause exploitable devient `REQ-...` avec texte source, résultat observable, importance, état et liens vers les artefacts. Séparer une exigence explicite d'une idée suggérée par l'agent. Un ajout utile ne remplace pas ce que l'utilisateur a demandé.

Exemple : « compare les approches, crée des cartes, applique à mon équipe, explique les limites » produit au moins quatre exigences distinctes. Une synthèse générale ne suffit pas à cocher les cartes ou l'application.

États de travail : pending, in_progress, done, blocked, waived. `done` signifie que l'artefact référencé existe et contient effectivement le résultat. `waived` exige une décision utilisateur traçable ; un modèle ne peut pas s'accorder lui-même une exemption. `blocked` reste visible dans le rapport final.

## Double lecture obligatoire
Lecture A à l'intake : extraire la demande et les contraintes sans la simplifier. Lecture B avant livraison : comparer chaque exigence au contenu réel. Cette seconde lecture se fait sur le prompt source et le registre, pas uniquement sur le plan rédigé par le premier agent.

Pour une délégation, transmettre les exigences assignées, les dépendances, le contrat de sortie, le niveau d'accès autorisé et l'interdiction de faire disparaître les inconnues. L'Oracle reste responsable des exigences qui ne sont attribuées à personne.

## Checkpoints et reprise
Un checkpoint conserve les IDs, les sources lues et non lues, l'état des chapitres, les erreurs, le budget consommé si mesuré et la prochaine action déterministe. Après interruption, reprendre depuis le registre et les fichiers existants ; ne pas « recommencer proprement » en perdant les acquis.

Une livraison fractionnée utilise un manifest de volumes ou chapitres : planned, drafted, checked, delivered. « Livre complet » n'est autorisé que lorsque tous les chapitres applicables sont livrés. Une table des matières plus deux chapitres est un plan et un début de livre, pas un full book.

## Rapport de clôture
Présenter ce qui a été livré, comment le vérifier, ce qui reste bloqué, les hypothèses principales et les décisions attendues. Exigences explicites couvertes / exigences applicables est une mesure de couverture, pas une mesure de qualité de la connaissance.

Le script local vérifie les IDs, fichiers, hashes et liens du registre. Il ne prouve pas qu'un paragraphe satisfait intellectuellement une exigence : la relecture sémantique reste à faire par un reviewer, puis par Operator pour l'acceptation humaine.


---

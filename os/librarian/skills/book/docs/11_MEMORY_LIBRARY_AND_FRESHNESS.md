# 11 · Bibliothèque, mémoire et fraîcheur

## Séparer les couches
Inbox : éléments non triés. Corpus : matériaux autorisés et leur provenance. Knowledge : concepts, claims et synthèses versionnés. Learning : cartes, exercices et résultats de restitution. Decision : contexte, choix, hypothèses et observations. Memory : préférences et faits durables validés sur l'utilisateur ou l'organisation.

Un paragraphe lu dans un livre n'est pas une préférence de Operator. Une suggestion de l'agent n'est pas une décision de Operator. Une North Star proposée ne devient pas ratifiée par la simple création d'un dossier Librarian.

## Promotion
Pour promouvoir une note en connaissance réutilisable : vérifier provenance, scope, intérêt durable, date, contradictions et droits. Pour promouvoir une connaissance en mémoire personnelle : nécessité, consentement approprié et absence de confusion auteur/utilisateur. Les données sensibles ne sont pas stockées durablement par défaut.

Les écritures de mémoire sont proposées comme changements explicites. Préserver les versions et la raison d'un remplacement. Une rétractation retire un support, sans prétendre effacer les copies déjà exportées.

## Organisation physique
Un workspace distinct par périmètre : privé, organisation AGK, client spécifique. Le CLI exige un scope correspondant au workspace initialisé. Il ne fournit pas de système d'authentification ou de contrôle d'accès multi-tenant ; les permissions de fichiers et le runtime doivent compléter cette séparation.

Dans un workspace : registre SQLite, dossiers de runs, artefacts locaux, événements. Le pack de skills et les données de travail sont séparés. Une mise à jour du pack ne doit pas écraser les dossiers de recherche.

## Déduplication
Identifiants canoniques pour DOI, URL normalisée ou ID de document autorisé. Conserver l'URL originale avec ses paramètres utiles ; ne pas supprimer aveuglément des paramètres qui sélectionnent une version ou un contenu. Dédupliquer prudemment les versions et enregistrer leur relation.

Une déduplication n'est pas une suppression automatique. Deux fiches d'une même source dans deux scopes peuvent être nécessaires pour préserver leurs droits et historiques. Ne pas fusionner des corpus client sous prétexte d'optimiser les coûts.

## Fraîcheur
`retrieved_at` indique quand l'élément a été consulté ; `published_at` décrit la publication si connue ; `review_after` exprime une échéance de contrôle choisie. Aucun de ces champs ne garantit que l'information est actuelle.

Les politiques de fraîcheur sont des heuristiques configurables, pas des lois : éléments très volatils à re-vérifier à l'usage ; comportements logiciels liés à une version ; faits stables à reconsidérer si une correction apparaît. Les données médicales, juridiques, financières ou de sécurité demandent une prudence et une vérification adaptées au risque.

## Revue
À une revue demandée, scanner les échéances, claims centraux et dépendances. Produire une liste triée par impact avec source, raison, dossiers affectés et prochaine vérification. Aucune routine n'est activée à l'installation. Toute cadence récurrente est une proposition à valider dans le scheduler réel.


---

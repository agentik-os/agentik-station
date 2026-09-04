# Discord · Surface de commande et boutons

## Commandes natives
La documentation Hermes consultée indique que les skills installées peuvent être enregistrées comme commandes Discord avec un paramètre texte `args`, lors du démarrage/synchronisation du gateway. L’apparition effective dépend de la version, du profil, des permissions, des collisions et des limites de commandes. Référence EXT-03.

Exemple d’usage : sélectionner `/book`, puis mettre `--deep --apply --context "AGK" mon sujet` dans `args`. Le pack ne crée pas de sous-commandes Discord séparées pour chaque flag. `/book deep !` en texte simple reste un alias d’intention si le runtime reçoit effectivement ce message.

## Routes proposées
Réutiliser les salons autorisés existants. Une mission possède un thread et un run_id. Le message d’entrée identifie le demandeur et le scope côté serveur. Les résultats longs sont livrés comme fichiers, avec une synthèse et le statut. Ne pas envoyer des données de client vers le salon public du collectif.

## Contrat des boutons, non implémenté dans ce ZIP
Ouvrir le dossier ; voir les sources ; voir les contradictions ; lancer un quiz ; demander une application ; demander une révision ; valider le livrable. La validation humaine doit être attribuée au vrai utilisateur autorisé, pas à l’agent.

Un handler doit vérifier signature/session de la plateforme, user_id, guild_id, channel_id, scope, run_id, autorisation, expiration et état courant. Utiliser un token opaque server-side, éviter prompts ou données privées dans custom_id, journaliser un identifiant d’interaction pour l’idempotence et refuser les clics rejoués hors état. Aucun bouton ne franchit silencieusement START ou RELEASE.

## Reprise et erreurs
Un clic « Réviser » ouvre une demande avec le prompt conservé et les exigences à corriger ; il ne crée pas une copie divergente de toute la mission. Une erreur de livraison conserve le fichier local et signale l’échec. Un message envoyé n’est marqué livré qu’après retour réel du connecteur.

## Gouvernance
Ce document est une spécification d’intégration, pas un bot déployé. Ne pas redémarrer un service ou créer des salons pour faire disparaître un simple problème de découverte de skill. Un seul owner doit gérer la synchronisation des commandes d’une même application lorsque plusieurs gateways existent.


---

# 18 · Opérations, routines et incidents

## Démarrage d'une mission
Vérifier scope et droits ; identifier le run existant ou en créer un ; lire le brief ; établir les exigences ; inventorier l'accès aux sources ; charger les workflows ; enregistrer les artefacts au fil du travail. Aucun run n'est déclaré en recherche active parce qu'un plan a simplement été écrit.

## Fin de session
Sauvegarder les résultats utiles, les IDs et le checkpoint. Répertorier les sections rédigées, validées structurellement et non vérifiées sémantiquement. Expliquer ce qui reste à faire sans promettre un travail autonome futur.

## Revue de bibliothèque
À la demande : trier inbox, rechercher doublons, vérifier sources échues, consolider les cartes utiles et archiver les dossiers sans utilité actuelle. Archiver ne signifie pas supprimer les preuves ou les versions. Ne pas créer de nouvelles missions juste pour remplir la revue.

## Routines proposées, jamais activées à l'installation
Revue courte après une recherche importante. Revue périodique des claims volatils utilisés par des décisions actives. Relecture des cartes demandées. Audit de complétude sur les missions explicitement dans le périmètre. Choisir cadence, owner, budget et canal avant toute création dans un scheduler.

## Incidents fréquents
Source inaccessible : garder la fiche discovery avec accès unavailable, chercher une alternative autorisée et limiter la conclusion.
Doublon : comparer identifiant, édition, hash et provenance ; conserver les variantes pertinentes.
Prompt trop long : découper en exigences et délégations, pas supprimer les derniers paragraphes.
Livraison interrompue : lire manifest et hashes, reprendre le premier élément incomplet.
Commande Discord absente : vérifier profil, découverte de skill, collisions de nom, permissions et synchronisation du gateway ; ne pas réinstaller tout Hermes.
Claim périmé : journaliser source-status, produire l'impact, revalider les dérivés.
Audit en échec : corriger la cause puis relancer ; ne pas utiliser l'export incomplet pour cacher le statut.

## Backup et mise à jour
Sauvegarder le workspace avec ses fichiers et sa base SQLite de manière cohérente. Fermer les writers ou utiliser l'API de backup SQLite plutôt que copier uniquement le fichier principal pendant une écriture. Tester la restauration sur un chemin séparé.

L'installation des skills est non destructive : destination explicite, prévisualisation, copie en staging, vérification, refus des conflits, reçu. Mettre à jour une version modifiée nécessite d'abord une comparaison et une sauvegarde choisies par l'opérateur ; aucun remplacement silencieux.

## Observabilité
Événements run_created, record_added, source_status_changed, card_reviewed, audit_run et export_created. Les événements décrivent les opérations locales observées. Ils ne prouvent pas une lecture de source, un coût d'API ou une livraison Discord que le script n'a pas effectués.


---

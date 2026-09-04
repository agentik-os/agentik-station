# Hermes · Intégration réelle et limites

## Base vérifiée
La documentation Hermes consultée le 30 août 2026 décrit les skills comme dossiers contenant un `SKILL.md`, avec ressources chargées à la demande. Le répertoire de profil par défaut est `~/.hermes/skills/` ; un autre profil ou HERMES_HOME peut utiliser un autre chemin. Références EXT-01, EXT-02, EXT-03 dans `sources/REFERENCES.md`.

Le pack installe `book/` avec toutes ses ressources et `librarian/` comme entrée d’administration. Les deux noms sont simples pour permettre `/book` et `/librarian`. Le script refuse d’écraser une skill existante différente.

## Inspection
Identifier le binaire, sa version, le profil actif et le répertoire réellement scanné. Contrôler les noms existants, les permissions et les chemins résolus. Ne pas créer un autre utilisateur Linux. Les rôles du pack peuvent être joués sous un profil unique avec délégations ; quinze rôles ne demandent pas quinze bots permanents.

## Installation
Exécuter verify_package.py, puis install.py en dry-run. Appliquer seulement à la destination vérifiée. L’installation copie les fichiers des skills ; elle ne modifie ni SOUL.md, ni USER.md, ni AGENTS.md, ni config provider, ni mémoire et ne redémarre pas le gateway.

## Workspace
Choisir un répertoire de données hors du dossier de skills. Le CLI utilise des chemins explicites, pas une base privée globale implicite. Vérifier le scope à chaque invocation. Configurer les permissions du runtime selon les données traitées.

## Smoke test
Demander au runtime de charger book ; vérifier qu’il trouve les références et le CLI. Lancer une recherche non destructive sur une source accessible et consigner la vraie source lue. Faire volontairement échouer un claim sans evidence. Tester une reprise et un export local. Séparer ces tests d’agent des tests unitaires déjà fournis.

## État honnête
Les contrats sont prêts ; la compatibilité avec la version installée de Operator et les outils de son fork n’a pas été observée ici. Une documentation publique n’est pas la preuve du comportement d’une installation spécifique.


---

# PARTIE 07 · EXEMPLES


---

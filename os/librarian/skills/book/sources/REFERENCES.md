# Références externes vérifiées

Consultation web : 30 août 2026. Les pages HTML listées ci-dessous ont été ouvertes ou retrouvées dans leur source officielle. Aucun livre commercial ou PDF externe n’a été reproduit. Les contenus du pack sont principalement des choix de conception, non des résultats scientifiques revendiqués.

## EXT-01 · Hermes Agent · Creating Skills
URL : `https://hermes-agent.nousresearch.com/docs/developer-guide/creating-skills`

Usage : Structure SKILL.md, ressources locales, scripts utilitaires et disclosure progressive. Cette documentation guide le format de packaging ; elle ne prouve pas un test du fork de Operator.

## EXT-02 · Hermes Agent · Skills System
URL : `https://hermes-agent.nousresearch.com/docs/user-guide/features/skills`

Usage : Répertoire de skills par profil et possibilités de découverte. Le chemin effectif doit être inspecté dans l’installation cible.

## EXT-03 · Hermes Agent · Discord
URL : `https://hermes-agent.nousresearch.com/docs/user-guide/messaging/discord`

Usage : Les skills sont décrites comme commandes natives avec args texte et synchronisation du gateway. Les boutons personnalisés du pack sont un design d’intégration séparé.

## EXT-04 · PRISMA · PRISMA 2020 statement
URL : `https://www.prisma-statement.org/prisma-2020`

Usage : Référence officielle pour le reporting des revues. Aucun badge de conformité ou de validité scientifique n’est revendiqué.

## EXT-05 · PRISMA · Overview
URL : `https://www.prisma-statement.org/`

Usage : Précise le rôle des guidelines et leurs extensions ; justifie la distinction entre reporting et conduite complète d’une recherche.

## EXT-06 · Crossref · REST API documentation
URL : `https://www.crossref.org/documentation/retrieve-metadata/rest-api/`

Usage : L’API fournit des métadonnées bibliographiques déposées. Des métadonnées ne constituent pas la lecture du texte intégral. Aucun client API Crossref n’est exécuté par le CLI du pack.

## EXT-07 · Agent Skills · Specification
URL : `https://agentskills.io/specification`

Usage : Référence de structure de skill et de métadonnées. Le pack utilise un format simple avec name et description ; la découverte effective reste à tester.

## EXT-08 · Hermes Agent · Bot Mode
URL : `https://hermes-agent.nousresearch.com/docs/user-guide/bot-mode`

Usage : Bot Mode repose sur les profils Hermes. Le pack conserve des rôles logiques et ne crée pas de bots ou de nouveaux comptes Linux.

## Provenance du périmètre personnel
Le scope FULL provient des échanges récupérés : Librarian v2 / FULL VNext, Oracle et workforce, /book --deep, scholar, apply, compare, synthesize, critique, quiz, teachback, cards, map, reading-path, bestseller, corpus, evidence/claim/source graphs, contradictions, knowledge/memory/freshness, harnesses, loops, evals, gouvernance et chaîne Builder. Les archives historiques elles-mêmes n’étaient pas montées dans cette conversation. Les scripts, schémas et documents de cette release sont une reconstruction nouvelle, explicitement versionnée.


---

# ANNEXE · DÉMONSTRATION EXÉCUTÉE

# Démonstration locale exécutée

Données entièrement synthétiques. Aucune recherche sur le monde réel n’est revendiquée.

Run observé : `RUN-59d82177b278`.

Le dossier initial passe les contrôles structurels. Une rétractation fictive invalide le claim et son artefact : l’audit échoue comme attendu. Le retour au statut initial permet le nouvel audit et l’export. Une carte de révision est enregistrée et sa prochaine échéance est calculée selon la règle simple du pack.

Résultats : baseline `STRUCTURAL_PASS` ; après rétractation fictive `STRUCTURAL_FAIL` ; après restauration `STRUCTURAL_PASS`.

L’archive `SYNTHETIC_DEMO_EXPORT.zip` contient le manifest, le graphe, les records et le dossier synthétique. Elle n’est pas un exemple de conclusion scientifique validée. Le rapport machine complet est conservé à la racine du pack, dans `quality/demo_run_report.json`.

Pour reproduire :
```bash
python3 skills/book/scripts/demo.py --root ./demo-workspace
```

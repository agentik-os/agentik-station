# Prompt à envoyer à Operator / Hermes avec le ZIP

Inspecte l’archive Librarian_OS_FULL_vNext_2026-08-30 et intègre son OS de connaissance à mon installation AGK/Hermes existante. Ne reconstruis pas mon VPS et ne crée pas un autre utilisateur Linux.

Commence par lire README.md, START_HERE.md, RELEASE_REPORT.md et skills/book/INDEX.md. Vérifie l’intégrité avec verify_package.py et inspecte le code d’installation avant toute exécution. Identifie la version réelle de Hermes, le profil actif, son répertoire skills, les skills book/librarian déjà présentes et les routes Discord existantes. Ne lis ni n’affiche aucun secret.

Conserve tout ce qui existe. Utilise install.py en prévisualisation sur le répertoire skills vérifié. Si la destination est claire et sans conflit, l’installation locale de ces deux skills est autorisée ; utilise --apply. En cas de conflit, rends un diff et un plan de migration non destructif plutôt que d’écraser. Ne modifie pas SOUL.md, USER.md, AGENTS.md, provider settings ou config globale sans présenter le changement et obtenir le gate approprié.

Initialise un workspace de données distinct du pack, dans le scope autorisé. Garde privés, AGK et chaque client séparés. Charge la constitution, le protocole anti-oubli, le routeur /book, les workflows et les contrats de rôles. Utilise les outils natifs que tu as réellement inspectés, sans inventer d’API.

Exécute les tests locaux et la démonstration synthétique. Fais ensuite un smoke test du runtime Hermes réel sur une source publique ou un document que je t’ai autorisé à lire, sans mutation externe. Montre qu’un claim renvoie à une source et qu’un audit bloque une preuve absente. Signale séparément les tests de code, le test d’agent et les validations encore manquantes.

Pour Discord, vérifie la découverte de /book et /librarian, le champ args, les permissions, la synchronisation et les collisions. Aucun redémarrage d’un gateway en service, création de salon, enregistrement d’un nouveau bot, cron, achat, ticket Linear, merge ou déploiement production n’est autorisé par ce prompt. Prépare ces changements seulement s’ils sont nécessaires et soumets leur gate.

Livre INSTALL_REPORT.md avec chemins réellement utilisés, fichiers copiés, tests exécutés, limites, intégrations actives ou non, et instructions de premier usage. N’annonce pas de fonctionnalité active sans preuve. Le package peut être installé sans que tous les connecteurs soient branchés : distingue ces états honnêtement.

Mon entrée principale doit permettre : /book --deep, --scholar, --apply, --compare, --synthesize, --critique, --quiz, --teachback, --cards, --map, --reading-path, --bestseller, --corpus. FULL signifie préserver toutes les exigences applicables, pas fabriquer des sources ou masquer un livrable absent.

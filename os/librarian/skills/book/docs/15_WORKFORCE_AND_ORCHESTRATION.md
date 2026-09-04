# 15 · Oracle, workforce et orchestration

## Responsabilité centrale
L'Oracle conserve le contrat, les priorités, les identifiants, le budget, les dépendances et la clôture. Il peut déléguer la collecte, l'analyse ou la critique, pas la responsabilité de satisfaire la demande.

Les quinze rôles du dossier `agents/` sont des contrats de travail. Par défaut, activer seulement ceux qui ajoutent une fonction utile. Une mission simple peut être réalisée séquentiellement par un agent ; une mission Deep mobilise typiquement planning, recherche, analyse, critique et vérification sous le même Oracle.

## Contrat de délégation
Fournir mission, scope autorisé, exigences assignées, inputs exacts, sources déjà connues, outils permis, sorties attendues, critères de réussite, inconnues et règles d'arrêt. Le sous-agent retourne statut, artefacts, IDs, sources réellement lues, limites et erreurs. Une synthèse sans sources ne peut pas être promue en evidence.

## Parallélisme
Paralléliser des sous-questions indépendantes ou des voies contradictoires. Ne pas laisser deux agents écrire le même fichier final. Chaque worker produit une sortie distincte ; l'Oracle ou un writer unique consolide le registre.

Le runtime Python utilise SQLite et des transactions, mais il n'est pas un scheduler multi-agent. L'agent orchestral doit assurer le contrat de ressources, les timeouts et l'ownership des sorties. Les limites configurées sont des valeurs de départ, pas une estimation du coût réel des modèles.

## DAG de travail
Intake → Plan → Search → Read → Extract → Synthesize → Critique → Compose → Verify → Package. Certaines branches Learning et Application partagent des claims vérifiés. Une modification d'un claim central invalide les sorties dépendantes avant packaging.

Chaque nœud possède inputs, outputs, preconditions, erreurs et critères d'arrêt. Une étape bloquée n'est jamais convertie en réussite par la seule absence d'exception technique.

## Idempotence et reprise
Utiliser un run stable et des IDs stables. Réexécuter un ajout identique est sans effet ; un même ID avec un contenu différent est un conflit explicite. Pour corriger le contenu d'un record immutable, créer une nouvelle version avec un nouvel ID et conserver le lien dans les notes ou le manifest de révision.

Le writer vérifie les fichiers avant de les référencer. Une reprise inspecte les événements, compare les hashes et ne suppose pas qu'un message « terminé » vaut présence d'artefact.

## Mode dégradé
Sans sous-agents : jouer les rôles séquentiellement avec traces séparées. Sans web : limiter les claims aux matériaux réellement disponibles et marquer les vérifications externes manquantes. Sans stockage : livrer un dossier exportable et signaler qu'aucune persistance n'a eu lieu. Sans Discord : fonctionner localement sans inventer une notification envoyée.


---

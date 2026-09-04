# 21 · CLI local, opérations et limites exactes

## Ce qui s’exécute réellement
Le CLI normalise les flags, crée des runs, conserve des records JSON dans SQLite, vérifie les schémas du pack, contrôle les références, détecte des supports structurellement inadmissibles, vérifie présence et hashes des artefacts, génère un graphe de provenance, calcule des impacts, gère une file de cartes et exporte des ZIP locaux.

Il n’appelle aucun LLM, aucune API web, aucun connecteur, Discord ou Hermes. Il ne lit pas un livre pour en extraire le sens. Il n’authentifie pas une personne, ne certifie pas la vérité et ne lance pas une tâche de fond. Les budgets du fichier policy.json concernent l’agent hôte, pas un limiteur réseau du CLI.

## Démarrage depuis le pack décompressé
```bash
CLI="skills/book/scripts/librarian.py"
WORKSPACE="$PWD/workspace-private"
python3 "$CLI" --root "$WORKSPACE" --scope private init
python3 "$CLI" --root "$WORKSPACE" --scope private new   --request '/book --deep --apply --context "AGK" Structurer une recherche utile'
python3 "$CLI" --root "$WORKSPACE" --scope private list
```
Copier le run_id réel renvoyé dans une variable `RUN_ID`. Le scope reste identique pour toutes les commandes du workspace. Les arguments globaux `--root` et `--scope` se placent avant le nom de commande.

Pour un prompt long contenant des guillemets, préférer un fichier texte :
```bash
python3 "$CLI" --root "$WORKSPACE" --scope private new --request-file ./request.txt
```
Un request.txt inexistant est une erreur explicite, pas un prompt supposé. Ne pas mettre de secret dans la demande ; le texte est conservé dans le registre.

## Normaliser une commande sans workspace
```bash
python3 "$CLI" route --request '/book --scholar --deep --critique --cards mon sujet'
```
Cette opération retourne le mode, les flags, le sujet et les catégories d’artefacts requises. Elle ne vérifie pas qu’une pièce jointe existe. Les doubles guillemets encadrent les paramètres textuels ; les apostrophes naturelles du français restent littérales.

## Ordre des records
Créer d’abord les sources, puis les claims, puis les fichiers et leurs artefacts, puis les exigences terminées. Les exigences pending peuvent être créées avant les artefacts. Ajouter les contradictions après les objets qu’elles référencent. Les cartes référencent des claims existants.

```bash
python3 "$CLI" --root "$WORKSPACE" --scope private add --run "$RUN_ID" --kind source --file ./source.json
python3 "$CLI" --root "$WORKSPACE" --scope private add --run "$RUN_ID" --kind claim --file ./claim.json
python3 "$CLI" --root "$WORKSPACE" --scope private add --run "$RUN_ID" --kind artifact --file ./artifact.json
python3 "$CLI" --root "$WORKSPACE" --scope private add --run "$RUN_ID" --kind requirement --file ./requirement.json
```
Les exemples ci-dessus nécessitent de vrais fichiers conformes à `schemas/`. Pour un exemple entièrement rempli et exécutable, lancer `demo.py`. Il reste clairement synthétique et dans le scope demo.

Les chemins d’artefacts sont relatifs à `WORKSPACE/runs/RUN_ID/`, par exemple `artifacts/book.md`. L’artefact doit déjà exister. Un hash est calculé lors de son enregistrement. Un chemin absolu, une remontée `..` ou un symlink sortant sont refusés.

## États d’exigence
```bash
python3 "$CLI" --root "$WORKSPACE" --scope private set-requirement   --run "$RUN_ID" --id REQ-001 --status done --artifacts ART-001
```
La commande ne fonctionne que si ces IDs existent. Les états bloqués exigent une raison. Les exemptions exigent une référence d’approbation externe ; le CLI signale qu’il ne peut pas authentifier cette approbation. Il n’existe pas de commande « accepte en tant que Operator ».

Les records sont immuables à l’ajout : même ID et même contenu = unchanged ; même ID et autre contenu = conflit. Les changements d’état autorisés sont `set-requirement`, `source-status` et `review-card`, toujours journalisés. Une révision du contenu crée un nouvel ID ; préserver le lien de version dans le dossier de révision.

## Révision substantielle d’un dossier
Pour changer le contenu de claims déjà publiés ou de nombreuses sources, créer un nouveau run de révision. Référencer le run précédent dans le brief et le revision_manifest, puis enregistrer uniquement les versions actives dans le nouveau run. L’ancien reste conservé avec ses défauts et son historique ; il n’est pas forcé au vert.

Le CLI n’implémente pas un statut d’archivage des claims à l’intérieur d’un run. Ajouter un nouveau claim sans retirer le support invalide de l’ancien ne ferait donc pas disparaître les erreurs d’audit de l’ancien run. Cette frontière est intentionnellement explicite : nouveau contenu substantiel, nouveau run de release ; changements d’état limités, commandes journalisées.

## Audit et impact
```bash
python3 "$CLI" --root "$WORKSPACE" --scope private audit --run "$RUN_ID"
python3 "$CLI" --root "$WORKSPACE" --scope private graph --run "$RUN_ID"
python3 "$CLI" --root "$WORKSPACE" --scope private source-status   --run "$RUN_ID" --id SRC-001 --status outdated --note 'Version à re-vérifier'
```
`source-status` enregistre ton observation. Il ne consulte pas la source et ne change pas retrieved_at. `audit` vérifie notamment les supports accessibles, la fraîcheur déclarée, les contradictions critiques, les sorties demandées par les flags et les fichiers. Les dépendances propagent le besoin de révision.

Un passage de structure porte `STRUCTURAL_PASS`, accompagné de `semantic_review: not_automated` et `human_acceptance: not_verified`. Les avertissements ne sont pas masqués. Un résultat scientifique n’est pas validé par ce badge.

## Bibliothèque et cartes
```bash
python3 "$CLI" --root "$WORKSPACE" --scope private search --query 'mécanisme' --limit 20
python3 "$CLI" --root "$WORKSPACE" --scope private show --run "$RUN_ID"
python3 "$CLI" --root "$WORKSPACE" --scope private events --run "$RUN_ID"
python3 "$CLI" --root "$WORKSPACE" --scope private due-cards --run "$RUN_ID"
python3 "$CLI" --root "$WORKSPACE" --scope private review-card --run "$RUN_ID" --id CARD-001 --rating good
```
La recherche est littérale et Unicode-aware, pas sémantique/vectorielle. Elle ne traverse pas d’autres workspaces. Les cartes liées à des supports invalidés sont signalées et leur revue est bloquée jusqu’à réévaluation. Les intervalles suivent la règle simple documentée, sans scheduler.

## Export
```bash
python3 "$CLI" --root "$WORKSPACE" --scope private export --run "$RUN_ID" --out ./release.zip
```
L’export propre exige un audit structurel réussi. Une demande explicite `--allow-incomplete` permet un export portant `INCOMPLETE`, avec le rapport et les artefacts omis. Un fichier modifié depuis son enregistrement n’est pas incorporé silencieusement. La destination existante n’est jamais écrasée. Le ZIP est contrôlé et ses contenus comparés aux hashes attendus avant livraison.

L’export inclut registres, graphe, manifest et artefacts sélectionnés, pas tous les fichiers du workspace ou les documents bruts du corpus. Il ne constitue pas une autorisation de publier ces données.

## Dates et codes de sortie
Les timestamps d’événements utilisent l’horloge UTC de l’environnement d’exécution. `--as-of YYYY-MM-DD` sert à rejouer un audit ou une file de cartes à une date explicite ; cette date ne falsifie pas une consultation de source.

Code 0 : commande exécutée ou audit structurel sans erreur. Code 1 : audit en échec. Code 2 : argument, accès, schéma ou opération invalide. Les sorties normales sont JSON ; les erreurs vont sur stderr.

## Concurrence et sécurité
Utiliser un writer logique par run. SQLite assure les transactions de base mais le programme n’est ni un scheduler distribué, ni un service multi-tenant. Les fichiers d’artefacts doivent être stabilisés pendant l’export ; une modification observée bloque l’archive. Le propriétaire système peut toujours modifier la base ou les journaux. Le scope est une protection contre les erreurs, pas une identité authentifiée.


---

# PARTIE 02 · WORKFORCE


---

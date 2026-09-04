# AGK, Linear, Convex et Composio · Contrats de raccordement

## Place dans AGK
Librarian alimente les objets Organization / Project / Mission / Artifact / Evidence / Eval / Knowledge déjà présents dans AGK. Le registre local du pack sert d’outil portable et de référence de contrat. Il ne crée pas une deuxième source de vérité concurrente lorsque Convex ou le système du projet possède déjà l’objet canonique.

## Mapping
run → Mission de recherche ; requirement → exigence de mission ; source → Knowledge source ; claim/evidence → Evidence ; artifact → Artifact ; audit → Eval/Audit ; handoff → proposition pour Blueprint/Builder. Conserver scope et identifiants d’origine lors de l’échange.

## Convex
Aucun schéma Convex ni endpoint n’est supposé existant. Inspecter le schéma et les fonctions du projet avant de proposer un adaptateur. Les mutations doivent vérifier auth, appartenance au scope, ownership, idempotence et version. Une table dont le nom semble proche ne prouve pas la compatibilité du contrat.

## Linear
La recherche peut référencer une issue existante autorisée. Ne pas créer un backlog de toutes les idées du livre. Une création ou mise à jour doit correspondre à une demande et à la bonne équipe/client. Rechercher les doublons, conserver l’issue source et attacher les artefacts et critères d’acceptation. Les états réservés à l’humain ne sont pas cochés par l’agent.

## Composio
Découvrir les outils et comptes disponibles dans l’environnement réel. Utiliser leur schéma exact, avec les permissions adaptées. Ne pas imaginer un nom d’action, récupérer des secrets dans un chat ou supposer que tous les connecteurs d’un autre agent sont accessibles.

## Sync
Choisir un owner par objet, conserver version et source_ref, rendre les conflits visibles et traiter les événements idempotemment. Commencer par une lecture et un export non destructifs. Les écritures sont activées seulement après tests et autorisations explicites.

## État livré
Des contrats et mappings sont fournis. Aucun endpoint, token, connexion, table, ticket ou déploiement distant n’a été créé par ce pack.


---

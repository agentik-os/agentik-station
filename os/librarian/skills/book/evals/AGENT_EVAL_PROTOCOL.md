# Évaluer le runtime réel

`agent_cases.json` contient vingt scénarios, pas vingt tests d’agent déjà réussis. Exécuter les cas applicables sur le Hermes cible avec le pack chargé, dans un scope non productif. Conserver prompt, outils réellement appelés, sorties, défauts et résultat du reviewer.

Les tests locaux Python sont séparés : ils vérifient le registre, les chemins, les schémas, le routage et les exports. Une évaluation du modèle exige des sources accessibles et des vérifications sémantiques. Une acceptation humaine doit venir du mécanisme authentifié de l’environnement hôte.

Pour chaque cas : expected, actual, evidence, pass/fail/blocked et limite. Ne pas remplir actual ou pass à partir de l’intention des prompts. Tester au moins les risques structurants avant une utilisation avec des données client ou des actions externes.


---

# PARTIE 09 · RÉFÉRENCES


---

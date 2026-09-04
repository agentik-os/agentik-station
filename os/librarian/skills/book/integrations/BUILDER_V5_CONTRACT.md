# Contrat de continuité avec Builder v5

La référence Builder v5 est conservée comme architecture de travail retrouvée dans les échanges. Ses anciens fichiers n’étaient pas disponibles ; le ZIP ne prétend pas contenir leur copie originale.

Le handoff exporte l’intention, les exigences, la recherche, les limites, les hypothèses, les alternatives, les tests et les gates. Le Builder doit accuser réception des exigences et les mapper à un plan d’incréments. Toute divergence entre preuve et conception devient une question explicite ou une hypothèse nouvelle.

Librarian n’est pas chargé de modifier production. Il reste owner de la connaissance et réintègre seulement les observations réellement renvoyées par le Builder. Une implémentation réussie sur fixture n’est pas une preuve de bénéfice client en production.

Utiliser `templates/BUILDER_HANDOFF.md`, `prompts/08_BUILDER_HANDOFF.md` et `docs/14_BUILDER_HANDOFF.md`. Le contrat reste utile même si Blueprint, Design, Stepper et Builder sont des rôles logiques dans une seule session.


---

---
type: dashboard
titre: Effortless — Suivi du cadrage (stats)
projet: Effortless
statut: vivant
tags:
  - dashboard
  - suivi
cssclasses:
  - cadrage-dashboard
---

# Suivi du cadrage — statistiques

> Tableau de bord Dataview. Requiert le plugin **Dataview** activé.
> Vue complémentaire de `6-Suivi.base` (boyards natifs). Vocabulaire `statut` :
> `À rédiger → En cours → Rédigé → Validé` (docs story) · `vivant | figé | versionné`
> (docs projet/registre) · `ouvert | résolu` (BQO).

## Vue d'ensemble — docs story par statut

```dataview
TABLE WITHOUT ID statut AS "Statut", length(rows) AS "Docs"
WHERE type = "cadrage-story"
GROUP BY statut AS statut
SORT statut ASC
```

## Avancement par Epic

```dataview
TABLE WITHOUT ID
  epic AS "Epic",
  length(rows) AS "Total",
  length(filter(rows.statut, (s) => s = "Validé")) AS "Validé",
  length(filter(rows.statut, (s) => s = "Rédigé")) AS "Rédigé",
  length(filter(rows.statut, (s) => s = "En cours")) AS "En cours",
  length(filter(rows.statut, (s) => s = "À rédiger")) AS "À rédiger",
  (round(100 * (length(filter(rows.statut, (s) => s = "Validé")) + length(filter(rows.statut, (s) => s = "Rédigé"))) / length(rows))) + " %" AS "% rédigé+"
WHERE type = "cadrage-story"
GROUP BY epic AS epic
SORT epic ASC
```

## À traiter — docs non finalisés

```dataview
TABLE WITHOUT ID
  link(file.link, code) AS "Doc",
  statut AS "Statut",
  phase AS "Phase",
  epic AS "Epic",
  story AS "Story"
WHERE type = "cadrage-story" AND (statut = "À rédiger" OR statut = "En cours")
SORT epic ASC, story ASC, file.name ASC
```

## Questions ouvertes (BQO)

```dataview
TABLE WITHOUT ID file.link AS "Registre", statut AS "Statut"
WHERE contains(string(type), "bqo") OR statut = "ouvert"
SORT file.name ASC
```

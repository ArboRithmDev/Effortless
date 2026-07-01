---
type: cadrage-projet
document: 9-guide-obsidian
titre: Guide de configuration Obsidian
projet: Effortless
statut: vivant
tags:
  - cadrage/projet
  - cadrage/guide
---

# Guide de configuration Obsidian (suivi du cadrage)

> `cadrage/` est un vault Obsidian. La config, les dashboards et un graphe colorisé
> sont déployés à l'`effortless_init`. Trois réglages restent **côté app** (Obsidian
> possède les fichiers de plugins et écrase toute édition externe à chaud) : à faire
> une fois, dans l'application.

## 1. Dataview — pour `6-Suivi-stats.md`
Réglages → Plugins tiers → Parcourir → **Dataview** → Installer + Activer.
Sans lui, les tables du dashboard s'affichent en texte brut. `6-Suivi.base` (Bases
natif) fonctionne sans plugin.

## 2. Front Matter Title — noms de nœuds lisibles
Les docs de cadrage portent un champ `titre` dans leur frontmatter (« Glossaire »,
« Analyse »…). Pour l'afficher partout (explorateur, onglets, **graphe**) au lieu du
nom de fichier :
Réglages → **Front Matter Title** → clé = `titre` + activer l'affichage **Graphe**.

## 3. Graphe — couleur par statut
Le graphe est déjà colorisé par `colorGroups` (`graph.json` déployé) :
⚪ À rédiger · 🟠 En cours · 🔵 Rédigé · 🟢 Validé · 🟣 Epic · 🐚 Projet.
Si la coloration par propriété ne prend pas dans ton thème, **extended-graph**
(Réglages du plugin → couleur des nœuds par propriété `statut`) est plus robuste et
gère aussi l'épaisseur/focus des **relations**.

## Vocabulaire `statut`
`À rédiger → En cours → Rédigé → Validé` (docs story) · `vivant | figé | versionné`
(docs projet/registre) · `ouvert | résolu` (BQO).

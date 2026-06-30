"""Composer de scaffold (STO-TRACKER-02, DEC-01).

Workflow composite AU-DESSUS du Port (pas une op du Port) : itère l'arbre d'un
template et appelle `tracker.create()` pour chaque nœud en câblant les parents.
Agnostique — ne touche jamais au client concret. Idempotent via `ScaffoldState`.
"""

from __future__ import annotations

from typing import Dict, Optional

from effortless_mcp.ports.tracker import ObjectPayload, ProjectRef, Tracker


def scaffold_project_from_template(
    tracker: Tracker,
    project_ref: ProjectRef,
    template: dict,
    zone: str,
    scaffold_state,
) -> Dict[str, dict]:
    """Crée l'arbre du template dans le projet cible.

    - Idempotence (garde primaire) : si la zone est déjà scaffoldée dans
      `scaffold_state`, retourne les refs connues sans rien recréer (DEC-05).
    - Le label `effortless-scaffold:<zone>` est posé sur l'Epic racine uniquement
      (marqueur durable). Tous les nœuds sont non affectés (DEC-07).
    - N'appelle QUE `tracker.create()` (agnosticité, DEC-01).

    Retourne `{node_title: {tracker_id, tracker_url}}`.
    """
    if scaffold_state.has(zone):
        return scaffold_state.get(zone)

    label = f"effortless-scaffold:{zone}"
    refs: Dict[str, dict] = {}

    def walk(node: dict, parent_ref: Optional["TrackerRef"], is_root: bool) -> None:
        payload = ObjectPayload(
            level=node["level"],
            title=node["title"],
            parent_ref=parent_ref,
            labels=[label] if is_root else None,
        )
        ref = tracker.create(payload)
        refs[node["title"]] = {"tracker_id": ref.tracker_id, "tracker_url": ref.tracker_url}
        for child in node.get("children", []):
            walk(child, ref, False)

    walk(template["root"], None, True)
    scaffold_state.set(zone, refs)
    return refs

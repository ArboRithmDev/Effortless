"""Persistance locale de l'état de scaffold (STO-TRACKER-02, DEC-05).

Garde primaire d'idempotence : on enregistre, par zone scaffoldée, les refs
distantes créées (node_key -> {tracker_id, tracker_url}). Un re-run consulte cet
état et court-circuite sans appel réseau. Stocké dans
`.effortless/scaffold_state.json` (état runtime local, gitignored).
"""

from __future__ import annotations

import json
import os
from typing import Dict, Optional


class ScaffoldState:
    def __init__(self, root: str):
        self._path = os.path.join(root, ".effortless", "scaffold_state.json")

    def _load(self) -> Dict[str, dict]:
        if not os.path.exists(self._path):
            return {}
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

    def _save(self, data: Dict[str, dict]) -> None:
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        tmp = self._path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, self._path)

    def has(self, zone: str) -> bool:
        return zone in self._load()

    def get(self, zone: str) -> Optional[Dict[str, dict]]:
        """Refs déjà scaffoldées pour la zone, ou None si zone inconnue."""
        return self._load().get(zone)

    def set(self, zone: str, refs: Dict[str, dict]) -> None:
        """Enregistre les refs d'une zone (node_key -> {tracker_id, tracker_url})."""
        data = self._load()
        data[zone] = refs
        self._save(data)

"""Journal de synchronisation hors-ligne (outbox) — DEC-05.

Quand le tracker est injoignable, l'opération locale réussit et la projection
est consignée ici comme une **migration** rejouable. Le rejeu est idempotent
(seules les entrées non jouées sont traitées) et chaque entrée est flaggée
`played` + `played_at` (timestamp) une fois appliquée.

Stockage : `.effortless/tracker_outbox/<seq>.json`, ordonné par `seq` croissant.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Callable, List, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SyncJournal:
    """Outbox de migrations de synchronisation, persistée sur disque."""

    def __init__(self, root: str, now: Optional[Callable[[], str]] = None) -> None:
        self.dir = os.path.join(root, ".effortless", "tracker_outbox")
        self._now = now or _utc_now_iso

    # --- lecture ---------------------------------------------------------
    def _load_all(self) -> List[dict]:
        if not os.path.isdir(self.dir):
            return []
        entries = []
        for name in os.listdir(self.dir):
            if name.endswith(".json"):
                try:
                    with open(os.path.join(self.dir, name), "r", encoding="utf-8") as f:
                        entries.append(json.load(f))
                except (json.JSONDecodeError, OSError):
                    pass
        return sorted(entries, key=lambda e: e.get("seq", 0))

    def pending(self) -> List[dict]:
        """Migrations non encore jouées, par `seq` croissant."""
        return [e for e in self._load_all() if not e.get("played")]

    # --- écriture --------------------------------------------------------
    def next_seq(self) -> int:
        """Prochain `seq` qui sera attribué par `enqueue` (max existant + 1).

        Sert à dériver un id local globalement unique AVANT l'enqueue (le seq outbox
        est unique across instances, contrairement à un compteur d'instance)."""
        return max((e.get("seq", 0) for e in self._load_all()), default=0) + 1

    def _path(self, seq: int) -> str:
        return os.path.join(self.dir, f"{seq:06d}.json")

    def _write(self, entry: dict) -> None:
        os.makedirs(self.dir, exist_ok=True)
        with open(self._path(entry["seq"]), "w", encoding="utf-8") as f:
            json.dump(entry, f, indent=2, ensure_ascii=False)

    def enqueue(self, op: str, args: dict) -> dict:
        """Consigne une migration de synchronisation à rejouer."""
        seq = max((e.get("seq", 0) for e in self._load_all()), default=0) + 1
        entry = {
            "seq": seq,
            "op": op,
            "args": args,
            "created_at": self._now(),
            "played": False,
            "played_at": None,
        }
        self._write(entry)
        return entry

    # --- rejeu -----------------------------------------------------------
    def mark_played(self, seqs: Optional[List[int]] = None) -> int:
        """Marque des ops en attente comme jouées, sans les exécuter.

        `seqs` cible des `seq` précis (l'agent médié a flushé exactement ceux-là via
        Rovo) ; `None` marque toutes les ops en attente. Sert aux ops sans refs à
        persister (transition, log_work) que `ack` (refs de scaffold) ne couvre pas.
        Idempotent : une op déjà jouée est ignorée. Retourne le nombre marqué."""
        target = None if seqs is None else set(seqs)
        marked = 0
        for entry in self.pending():
            if target is not None and entry.get("seq") not in target:
                continue
            entry["played"] = True
            entry["played_at"] = self._now()
            self._write(entry)
            marked += 1
        return marked

    def replay(self, apply_fn: Callable[[dict], None]) -> int:
        """Rejoue les migrations en attente par `seq` croissant.

        `apply_fn(entry)` exécute la projection réelle. En cas de succès, l'entrée
        est flaggée `played` + `played_at`. Si `apply_fn` lève, le rejeu s'arrête
        sur l'entrée fautive (laissée non jouée) — relancer `replay` reprend là.
        Idempotent : les entrées déjà jouées ne sont jamais retraitées.
        Retourne le nombre de migrations jouées dans cet appel."""
        played = 0
        for entry in self.pending():
            apply_fn(entry)
            entry["played"] = True
            entry["played_at"] = self._now()
            self._write(entry)
            played += 1
        return played
